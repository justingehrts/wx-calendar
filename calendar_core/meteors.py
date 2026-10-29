"""Meteor shower peak nights from the American Meteor Society's calendar page (https://www.amsmeteors.org/calendar/).
The page is a rolling window of the next twelve months; each shower card gives the peak night (e.g. 'Oct 21-22'), the
activity period and the Moon on the peak night. We parse the cards and cache the result (see store.py)."""
import datetime as dt, html, json, re, urllib.request
from . import store

URL = "https://www.amsmeteors.org/calendar/"
FILE = "meteor_ams.json"
UA = "wx-calendar/1.0 (planning calendar; reads the public AMS calendar page)"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

def slug(name):
    """'Eta Aquariids' / 'η Aquariids' -> 'eta_aquariids' (same keys as the typical-date table)."""
    n = name.lower().replace("η", "eta").replace("δ", "delta").replace("α", "alpha")
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")

def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", fragment, flags=re.S)))).strip()

# "peak night (Oct 21–22, 2026)", "(Dec 31 – Jan 1, 2027)" (the year belongs to the END date), or "(Dec 31, 2026 – Jan 1, 2027)"
_PEAK = re.compile(r"peak night\s*\(\s*([A-Z][a-z]{2}) (\d{1,2})(?:,\s*(\d{4}))?\s*[–-]\s*(?:([A-Z][a-z]{2}) )?(\d{1,2}),\s*(\d{4})\s*\)")
_MOON = re.compile(r"The Moon will be (\d+)\s*% illuminated\s*·\s*([^.(]+?)\s+on peak night")

def _peak_dates(match):
    m1, d1, y1, m2, d2, y2 = match.groups(); m2 = m2 or m1
    end = dt.date(int(y2), MONTHS[m2], int(d2))
    start = dt.date(int(y1) if y1 else int(y2) - (1 if (MONTHS[m1], int(d1)) > (MONTHS[m2], int(d2)) else 0), MONTHS[m1], int(d1))
    return start, end

def parse_calendar_with_skips(page):
    """-> (showers, skipped_names). A card whose peak night cannot be read is reported in skipped_names, never silently dropped."""
    out, skipped = [], []
    for card in re.findall(r"(?is)<article\b[^>]*class=\"[^\"]*shower-card[^\"]*\"[^>]*>.*?</article>", page):
        name = re.search(r"(?is)<h2[^>]*shower-card__name[^>]*>(.*?)</h2>", card)
        txt = _text(card); peak = _PEAK.search(txt)
        if not (name and peak): skipped.append(_text(name[1]) if name else "(unnamed card)"); continue
        start, end = _peak_dates(peak)
        active = re.search(r"(?is)Active through.*?<span class=\"hide-mobile\">(.*?)</span>", card)
        moon = _MOON.search(txt)
        out.append({"slug": slug(_text(name[1])), "name": _text(name[1]), "start": start.isoformat(), "end": end.isoformat(),
                    "active": _text(active[1]) if active else "", "moon_pct": int(moon[1]) if moon else None,
                    "moon_phase": moon[2].strip() if moon else ""})
    return out, skipped

def parse_calendar(page): return parse_calendar_with_skips(page)[0]

def fetch():
    """Download and parse the AMS calendar; cache it (cards that could not be read are listed under "skipped"). Returns the number of showers. Raises (and keeps the old cache) if the page layout changed."""
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    showers, skipped = parse_calendar_with_skips(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace"))
    if len(showers) < 3: raise ValueError(f"The AMS page layout seems to have changed (found {len(showers)} showers); nothing was saved.")
    store.write(FILE, json.dumps({"source": URL, "fetched": dt.date.today().isoformat(), "showers": showers, "skipped": skipped}, indent=1))
    return len(showers)

def cached():
    """{'source', 'fetched', 'showers': [...]} or None."""
    return store.load_json(FILE)
