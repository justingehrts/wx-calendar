"""Regional festivals and fairs for the Columbus and Zanesville TV markets. Sources produce *candidates*; a person reviews them
(accept / reject) and accepted ones become normal calendar events in the 'Regional festivals & fairs' category. Nothing is added
automatically, and a rejected candidate never comes back.

Connectors:
  * Ohio Department of Agriculture (ODA): the official "Ohio Agricultural Fair Chronological Schedule" brochure (PDF, published each December):
    the Ohio State Fair, every county fair and the independent fairs, with dates. Read from the PDF with pypdfium2.
  * Experience Columbus: public event pages found through the site's sitemap (robots.txt allows it with a 2-second crawl delay, which
    we honor). The site has no calendar feed or open API, so this reads the same pages a visitor sees.
  * Visitors-bureau event APIs: sites running The Events Calendar (WordPress) publish their events as JSON at /wp-json/tribe/events/v1/events.
    Athens County is the one bureau in the 22 counties found with real published event data (see CVB_SOURCES).
  * ohio.org (TourismOhio): its Festivals & Events pages load every event from one public JSON search (the same request the page makes; robots.txt
    does not cover it). One request, then counties come from the ZIP in each event's address. Written from the page's own script, so the exact
    response shape is an assumption that has not been run against the live site (ohio.org refuses automated requests from some networks).
  * iCal (.ics) feeds: any visitors bureau / fairground that publishes one."""
import datetime as dt, html, json, re, time, urllib.parse, urllib.request
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

# ------------------------------------------------------------------ Ohio Department of Agriculture
ODA_BROCHURE = "https://agri.ohio.gov/"       # candidates link here; the brochure PDF address changes every year and is not fetched by the app
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ODA_LINE = re.compile(r"^(?P<name>[A-Z][A-Za-z.' -]*?(?:County Fair|Independent Fair|State Fair))\s*(?:\((?P<loc>[^)]*)\))?\s*\*?\s*"
                       r"(?P<sm>[A-Za-z]{3,9})\.?\s*(?P<sd>\d{1,2})\s*-\s*(?P<em>[A-Za-z]{3,9})\.?\s*(?P<ed>\d{1,2})\s*$")

def pdf_text(data):
    """Plain text of a PDF (bytes), one line per printed line."""
    import pypdfium2
    doc = pypdfium2.PdfDocument(data)
    try: return "\n".join(pg.get_textpage().get_text_range() for pg in doc).replace("\r\n", "\n")
    finally: doc.close()

def parse_oda_schedule(text, year=None):
    """The ODA chronological schedule -> [{uid, title, start, end, city, county}]. A line looks like 'Pickaway County Fair (Circleville)* June 20-June 27'
    (the * marks harness racing and is ignored). The year comes from the brochure's heading ('2026 Ohio Agricultural Fair ...') unless given.
    County fairs get their county from the name, independent fairs from '(Licking Co.)', and the Ohio State Fair is Franklin County."""
    if year is None:
        m = re.search(r"(20\d\d)\s+Ohio Agricultural Fair", text)
        if not m: raise ValueError("cannot find the schedule year; pass year=")
        year = int(m[1])
    out, seen = [], set()
    for ln in text.splitlines():
        m = _ODA_LINE.match(ln.strip().replace("\t", " "))
        if not m: continue
        sm, em = _MONTHS.get(m["sm"][:3].lower()), _MONTHS.get(m["em"][:3].lower())
        if not sm or not em: continue
        try: start, end = dt.date(year, sm, int(m["sd"])), dt.date(year, em, int(m["ed"]))
        except ValueError: continue
        if end < start: continue
        name, loc = " ".join(m["name"].split()), (m["loc"] or "").strip()
        if name == "Ohio State Fair": county, city = "Franklin", loc or "Columbus"
        elif name.endswith("County Fair"): county, city = name[:-len(" County Fair")], loc
        else: county, city = (re.sub(r"\s*Co\.?$", "", loc) or None), name.split()[0]           # 'Hartford Independent Fair (Licking Co.)'
        uid = f"{name}|{year}"
        if uid in seen: continue
        seen.add(uid); out.append({"uid": uid, "title": name, "start": start.isoformat(), "end": end.isoformat(), "city": city, "county": county})
    return out

def fetch_oda_fairs(pdf, counties=None, today=None, include_past=False, url=None):
    """Store the schedule's fairs in the chosen counties as candidates. `pdf` is the brochure's bytes. Fairs already over are left out unless
    include_past. Returns {'new', 'seen', 'outside', 'total', 'year'}."""
    counties = set(counties or MARKET_COUNTIES); today = today or dt.date.today(); con = db.connect()
    rows = parse_oda_schedule(pdf_text(pdf)); new = seen = outside = 0
    for r in rows:
        if r["county"] not in counties: outside += 1; continue
        if r["end"] < today.isoformat() and not include_past: continue
        seen += 1
        new += db.upsert_candidate(con, "oda_fairs", r["uid"], r["title"], r["start"], r["end"], r["city"], r["county"], url or ODA_BROCHURE)
    return {"new": new, "seen": seen, "outside": outside, "total": len(rows), "year": rows[0]["start"][:4] if rows else None}

# ----------------------------------------------------------- visitors bureaus with published event data
# Checked 2026-10-30 across the 22 counties: only Athens publishes a usable event feed. Others have blog-post RSS only (no event dates) or none.
# `delay` is the Crawl-delay in the site's robots.txt.
CVB_SOURCES = [{"id": "cvb:athens", "name": "Athens County Visitors Bureau", "county": "Athens", "kind": "tribe", "url": "https://athensohio.com", "delay": 10}]

def fetch_tribe_events(source_id, base_url, county, keywords=None, exclude=None, today=None, delay=10.0, per_page=50, max_pages=12, get=_http_get, sleep=time.sleep):
    """Read a WordPress 'The Events Calendar' site's public JSON (upcoming events, paged) and store the festival-like ones as candidates. Words are
    matched against the event's web address and title, as for Experience Columbus. Returns {'new', 'seen', 'total', 'skipped'}."""
    today = today or dt.date.today(); con = db.connect()
    kw = [k.lower() for k in (keywords or DEFAULT_KEYWORDS)]; ex = [x.lower() for x in (DEFAULT_EXCLUDE if exclude is None else exclude)]
    new = seen = skipped = total = 0; page = 1
    while page <= max_pages:
        if page > 1: sleep(delay)
        data = json.loads(get(f"{base_url.rstrip('/')}/wp-json/tribe/events/v1/events?per_page={per_page}&page={page}&start_date={today.isoformat()}"))
        for e in data.get("events", []):
            title = html.unescape(e.get("title") or "").strip(); url = e.get("url") or base_url
            hay = (url.rstrip("/").rsplit("/", 1)[-1] + " " + title.lower().replace(" ", "-"))
            if not title or not e.get("start_date") or not any(k in hay for k in kw) or any(x in hay for x in ex): skipped += 1; continue
            start, end = e["start_date"][:10], (e.get("end_date") or e["start_date"])[:10]
            if end < today.isoformat(): skipped += 1; continue
            v = e.get("venue") or {}; v = v if isinstance(v, dict) else {}
            seen += 1; new += db.upsert_candidate(con, source_id, str(e.get("id") or url), title, start, max(end, start), v.get("city") or "", county, url)
        total = data.get("total", total)
        if page >= int(data.get("total_pages") or 1): break
        page += 1
    return {"new": new, "seen": seen, "total": total, "skipped": skipped}

# ------------------------------------------------------------------------------------------- ohio.org
OHIO_ORG = "https://ohio.org"
OHIO_ORG_LIMIT = 10000          # the site's search will not page past its 10,000th result
OHIO_ORG_SEARCH = OHIO_ORG + "/wps/odx-common/content/search/tourism.en?from=0&size=5000&q=authoringTemplate%3Aevent"

def _ohio_date(v):
    """Event date from ohio.org's startDate/endDate: epoch milliseconds or an ISO string. Its times of day are unreliable placeholders (02:00-03:00),
    so only the date is used: the UTC date of an epoch, or the date part of a string."""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        return dt.datetime.fromtimestamp(float(v) / 1000, dt.timezone.utc).date().isoformat()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v or ""))
    return m[1] if m else None

def parse_ohio_org(data, keywords=None, exclude=None):
    """ohio.org search JSON (or its text) -> [{uid, title, start, end, city, zip, url, topics}] for festival-like events. An event is kept when its web
    address or title contains a festival word, or its topics include 'fairs' or 'festivals'; exclusion words always win. Events with no readable dates or
    no ZIP in the address are dropped."""
    if isinstance(data, str):
        try: data = json.loads(data)
        except ValueError: raise ValueError("ohio.org did not return event data (it may be refusing automated requests)")
    kw = [k.lower() for k in (keywords or DEFAULT_KEYWORDS)]; ex = [x.lower() for x in (DEFAULT_EXCLUDE if exclude is None else exclude)]
    out = []
    for h in ((data.get("hits") or {}).get("hits") or []):
        src = h.get("_source") or {}; el = src.get("elements") or {}
        title = html.unescape(src.get("title") or "").strip(); path = src.get("contentPath") or ""
        start, end = _ohio_date(el.get("startDate")), _ohio_date(el.get("endDate"))
        z = re.search(r"\b(\d{5})(?:-\d{4})?\s*$", (el.get("address") or "").strip())
        if not (title and start and z): continue
        topics = " ".join(t.rsplit("/", 1)[-1] for t in (el.get("topics") or "").split("|")).lower()
        slug = path.rstrip("/").rsplit("/", 1)[-1].lower(); hay = slug + " " + title.lower().replace(" ", "-")
        if any(x in hay for x in ex) or not (any(k in hay for k in kw) or "fair" in topics or "festival" in topics): continue
        tail = path.split("/tourism/", 1)[1] if "/tourism/" in path else ""
        city = (el.get("cities") or "").split("|")[0].rsplit("/", 1)[-1]
        out.append({"uid": h.get("_id") or path or title, "title": title, "start": start, "end": max(end or start, start), "city": city, "zip": z[1],
                    "url": f"{OHIO_ORG}/{tail}" if tail else OHIO_ORG, "topics": topics})
    return out

def fetch_ohio_org(counties=None, keywords=None, exclude=None, today=None, get=_http_get, sleep=time.sleep, size=1000):
    """Read ohio.org's event search a page at a time (`size` events, a second apart) and propose the festival-like upcoming ones in the chosen counties.
    The site refuses date filters (a range query returns a 500), lists events oldest to newest, and will not return anything past the 10,000th, so when
    the list reaches that limit the newest events may be unreachable: 'capped' is then True and the app says so.
    Returns {'new','seen','total','outside','capped'}."""
    counties = set(counties or MARKET_COUNTIES); today = today or dt.date.today(); con = db.connect(); hits = []
    for start in range(0, OHIO_ORG_LIMIT, size):
        if start: sleep(1.0)
        got = (json.loads(get(OHIO_ORG_SEARCH.replace("from=0&size=5000", f"from={start}&size={size}"))).get("hits") or {}).get("hits") or []
        hits += got
        if len(got) < size: break
    new = seen = outside = 0
    for e in parse_ohio_org({"hits": {"hits": hits}}, keywords, exclude):
        if e["end"] < today.isoformat(): continue
        county = county_for_zip(e["zip"])
        if county not in counties: outside += 1; continue
        seen += 1; new += db.upsert_candidate(con, "ohio_org", e["uid"], e["title"], e["start"], e["end"], e["city"], county, e["url"])
    return {"new": new, "seen": seen, "total": len(hits), "outside": outside, "capped": len(hits) >= OHIO_ORG_LIMIT}

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

SOURCE_NAMES = {"experience_columbus": "Experience Columbus (event pages)", "oda_fairs": "Ohio Department of Agriculture fair schedule", "ohio_org": "ohio.org (TourismOhio)"}
SOURCE_NAMES.update({c["id"]: c["name"] + " (event calendar)" for c in CVB_SOURCES})
