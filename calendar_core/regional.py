"""Regional festivals and fairs for the Columbus and Zanesville TV markets. Sources produce *candidates*; a person reviews them
(accept / reject) and accepted ones become normal calendar events in the 'Regional festivals & fairs' category. Nothing is added
automatically, and a rejected candidate never comes back.

Connectors:
  * Experience Columbus: public event pages found through the site's sitemap (robots.txt allows it with a 2-second crawl delay, which
    we honor). The site has no calendar feed or open API, so this reads the same pages a visitor sees.
  * iCal (.ics) feeds: any visitors bureau / fairground that publishes one."""
import datetime as dt, html, json, re, time, urllib.request
from . import db, store

UA = "wx-calendar/1.0 (TV weather planning calendar; polite, cached)"
CATEGORY = "Regional festivals & fairs"
# The 22 counties in the Columbus and Zanesville markets (as supplied by the station)
MARKET_COUNTIES = ["Athens", "Coshocton", "Crawford", "Delaware", "Fairfield", "Fayette", "Franklin", "Guernsey", "Hardin", "Hocking", "Knox", "Licking",
                   "Madison", "Marion", "Morgan", "Morrow", "Muskingum", "Perry", "Pickaway", "Pike", "Ross", "Union"]
# Words in an event page's URL slug that suggest an outdoor festival or fair (editable in the app), and words that suggest it is not
DEFAULT_KEYWORDS = ["festival", "fair", "fest", "parade", "fireworks", "harvest", "carnival", "pumpkin", "tomato", "apple", "popcorn", "ice-cream", "regatta",
                    "rodeo", "balloon", "jubilee", "homecoming", "heritage", "bluegrass", "airshow", "air-show", "scarecrow", "sweet-corn", "street-fest"]
DEFAULT_EXCLUDE = ["class", "classes", "exhibit", "happening-hour", "workshop", "lesson", "literary", "-trio", "soul-sunday", "open-mic", "trivia", "yoga"]

def county_for_zip(zip_code):
    """Primary county name (without ' County') for a US ZIP, or None. A ZIP can straddle counties; this is the dataset's primary one."""
    import zipcodes
    try: m = zipcodes.matching(str(zip_code))
    except ValueError: return None
    return m[0]["county"].replace(" County", "") if m and m[0].get("state") == "OH" else None

# ------------------------------------------------------------------------- Experience Columbus
EC_BASE = "https://www.experiencecolumbus.com"
_EC_TITLE = re.compile(r"^(?P<title>.+?) \| (?P<s>\d{1,2}/\d{1,2}/\d{2})(?: - (?P<e>\d{1,2}/\d{1,2}/\d{2}))? \| (?P<city>.+?), (?P<st>[A-Z]{2}) (?P<zip>\d{5})\s*$")

def _mdy(s):
    m, d, y = (int(x) for x in s.split("/")); return dt.date(2000 + y, m, d)

def parse_ec_title(title):
    """'Circleville Pumpkin Show | 10/21/26 - 10/24/26 | Circleville, OH 43113' -> dict, or None if the page title has another shape."""
    m = _EC_TITLE.match(html.unescape(title).strip())
    if not m: return None
    try: start = _mdy(m["s"]); end = _mdy(m["e"]) if m["e"] else start
    except ValueError: return None                                   # an impossible date (e.g. 13/45/26): treat the page as unreadable
    return {"title": m["title"].strip(), "start": start.isoformat(), "end": end.isoformat(), "city": m["city"], "state": m["st"], "zip": m["zip"]}

def ec_event_urls(sitemap_xml, keywords, exclude=()):
    """Event page URLs whose slug contains any keyword and none of the exclusion words."""
    urls = [u for u in re.findall(r"<loc>(.*?)</loc>", sitemap_xml) if "/event/" in u]
    kw, ex = [k.lower() for k in keywords], [x.lower() for x in exclude]
    slug = lambda u: u.split("/event/")[1].lower()
    return [u for u in urls if any(k in slug(u) for k in kw) and not any(x in slug(u) for x in ex)]

def _http_get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")

def fetch_experience_columbus(counties=None, keywords=None, exclude=None, progress=None, max_pages=120, delay=2.0, today=None, get=_http_get, sleep=time.sleep):
    """Fetch upcoming festival-like events and store them as candidates. Pages already read are cached (past events are never re-read, upcoming ones
    are re-read after a week). Returns {'new': n, 'seen': n, 'pages_read': n, 'outside': n, 'remaining': n}."""
    counties = set(counties or MARKET_COUNTIES); today = today or dt.date.today()
    urls = ec_event_urls(get(EC_BASE + "/sitemap.xml"), keywords or DEFAULT_KEYWORDS, DEFAULT_EXCLUDE if exclude is None else exclude)
    cache = store.load_json("regional_ec_pages.json") or {}
    stale = lambda c: dt.date.fromisoformat(c["end"]) >= today and (today - dt.date.fromisoformat(c["fetched"])).days >= 7
    todo = [u for u in urls if u not in cache or (cache[u].get("end") and stale(cache[u]))]
    read = 0
    for u in todo[:max_pages]:
        sleep(delay)                                      # the site's robots.txt asks for a 2-second crawl delay
        try:
            page = get(u); t = re.search(r"(?is)<title>(.*?)</title>", page)
            info = parse_ec_title(t[1]) if t else None
        except Exception: info = None
        cache[u] = {**(info or {}), "fetched": today.isoformat()}
        read += 1
        if progress: progress(read, min(len(todo), max_pages))
    store.write("regional_ec_pages.json", json.dumps(cache))
    con = db.connect(); new = seen = outside = 0
    for u in urls:
        c = cache.get(u)
        if not c or "start" not in c or c["end"] < today.isoformat(): continue
        county = county_for_zip(c["zip"])
        if county not in counties: outside += 1; continue
        seen += 1
        new += db.upsert_candidate(con, "experience_columbus", u, c["title"], c["start"], c["end"], c["city"], county, u)
    return {"new": new, "seen": seen, "pages_read": read, "outside": outside, "remaining": max(0, len(todo) - max_pages)}

# ------------------------------------------------------------------------------- iCal feeds
def parse_ics(text):
    """Minimal iCalendar reader: VEVENTs -> [{uid, title, start, end (inclusive), location, url}]. All-day DTEND is exclusive in iCal, so one day is
    subtracted; date-times use the date part."""
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines: lines[-1] += raw[1:]
        else: lines.append(raw)
    out, cur = [], None
    unesc = lambda v: v.replace("\\n", " ").replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\").strip()
    for ln in lines:
        if ln == "BEGIN:VEVENT": cur = {}
        elif ln == "END:VEVENT":
            if cur and cur.get("title") and cur.get("start"):
                cur.setdefault("end", cur["start"]); out.append(cur)
            cur = None
        elif cur is not None and ":" in ln:
            key, val = ln.split(":", 1); name = key.split(";")[0].upper()
            if name == "SUMMARY": cur["title"] = unesc(val)
            elif name == "UID": cur["uid"] = val.strip()
            elif name == "LOCATION": cur["location"] = unesc(val)
            elif name == "URL": cur["url"] = val.strip()
            elif name in ("DTSTART", "DTEND"):
                m = re.match(r"(\d{4})(\d{2})(\d{2})", val.strip())
                if m:
                    d = dt.date(int(m[1]), int(m[2]), int(m[3]))
                    if name == "DTEND" and "VALUE=DATE" in key.upper() and len(val.strip()) == 8: d -= dt.timedelta(days=1)    # exclusive all-day end
                    cur["start" if name == "DTSTART" else "end"] = d.isoformat()
    for e in out:
        if e["end"] < e["start"]: e["end"] = e["start"]
        e.setdefault("uid", f"{e['title']}|{e['start']}")
    return out

def fetch_ics(source_id, url, county=None, today=None, get=_http_get):
    """Read an iCal feed and store its upcoming events as candidates. Returns {'new', 'seen'}."""
    today = today or dt.date.today(); con = db.connect(); new = seen = 0
    for e in parse_ics(get(url)):
        if e["end"] < today.isoformat(): continue
        seen += 1
        city = (e.get("location") or "").split(",")[-2].strip() if (e.get("location") or "").count(",") >= 2 else (e.get("location") or "")
        new += db.upsert_candidate(con, source_id, e["uid"], e["title"], e["start"], e["end"], city, county, e.get("url") or url)
    return {"new": new, "seen": seen}

# ------------------------------------------------------------------------------------ accept
def accept(con, cand_id):
    """Turn a candidate into a calendar event (category 'Regional festivals & fairs', flagged 'confirm dates'). Returns the event id."""
    c = db.get_candidate(con, cand_id)
    cat = db.category_id_by_name(con, CATEGORY) or db.add_category(con, CATEGORY, "#7A5C00", "light_gray", "")
    where = ", ".join(x for x in (c["city"], "OH") if x)
    notes = f"{c['county']} County. " if c["county"] else ""
    notes += f"Source: {SOURCE_NAMES.get(c['source'], c['source'])}. Confirm dates before airing."
    eid = db.add_event(con, c["title"], c["start_date"], c["end_date"], cat, location=where, notes=notes, url=c["url"], flag="confirm dates")
    db.decide_candidate(con, cand_id, "accepted", eid); return eid

SOURCE_NAMES = {"experience_columbus": "Experience Columbus (event pages)"}
