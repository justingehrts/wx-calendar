"""Sun and moon for Columbus, OH. Sunrise/sunset: USNO API (cached per year) with a PyEphem
fallback using the same definition (upper limb, standard refraction). Moon phases: PyEphem.
All times Eastern, DST handled via America/New_York rules."""
import datetime as dt, json, os, math, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from zoneinfo import ZoneInfo
import ephem
from . import store

LAT, LON, ELEV = "39.9612", "-82.9988", 235
ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
USNO_URL = "https://aa.usno.navy.mil/api/rstt/oneday"

def _obs():
    o = ephem.Observer(); o.lat, o.lon, o.elevation = LAT, LON, ELEV
    o.pressure = 0; o.horizon = "-0:34"   # upper limb + standard refraction (USNO definition)
    return o

def to_et(e): return e.datetime().replace(tzinfo=UTC).astimezone(ET)
def _utc_midnight_et(d): return ephem.Date(dt.datetime.combine(d, dt.time(0), tzinfo=ET).astimezone(UTC).replace(tzinfo=None))

# ---- USNO cache (see store.py)
def usno_name(year): return f"astro_usno_{year}.json"
def usno_data(year): return store.load_json(usno_name(year)) or {}

def _fetch_day(d):
    off = int(dt.datetime(d.year, d.month, d.day, 12, tzinfo=ET).utcoffset().total_seconds() // 3600)
    q = urllib.parse.urlencode({"date": d.isoformat(), "coords": f"{LAT},{LON}", "tz": off, "dst": "false"})
    j = json.load(urllib.request.urlopen(f"{USNO_URL}?{q}", timeout=30))
    data = j.get("properties", {}).get("data", j.get("data", {}))
    sun = {e["phen"]: e["time"] for e in data["sundata"]}
    return d.isoformat(), {"rise": sun["Rise"], "set": sun["Set"]}

def fetch_usno_year(year, progress=None, workers=4):
    """Fetch a whole year (~1.5 min with 4 workers) and write the cache atomically.
    Returns number of days fetched. Days that fail are left out (fallback fills them)."""
    days, d = [], dt.date(year, 1, 1)
    while d.year == year: days.append(d); d += dt.timedelta(days=1)
    out, done = {}, [0]
    def work(day):
        for attempt in range(3):
            try: k, v = _fetch_day(day); out[k] = v; break
            except Exception: time.sleep(1 + attempt)
        done[0] += 1
        if progress: progress(done[0], len(days))
    with ThreadPoolExecutor(workers) as ex: list(ex.map(work, days))
    if out: store.write(usno_name(year), json.dumps(dict(sorted(out.items()))))
    return len(out)

# ---- sun times
def _fmt12(m): return f"{(m // 60) % 12 or 12}:{m % 60:02d}"
@lru_cache(maxsize=4000)
def sun_ephem(d):
    """(rise, set) as aware Eastern datetimes (with seconds)."""
    o = _obs(); o.date = _utc_midnight_et(d)
    return to_et(o.next_rising(ephem.Sun())), to_et(o.next_setting(ephem.Sun()))

def sun_minutes(d):
    """(rise, set, source) as minutes after midnight (24h clock), rounded to the minute like USNO."""
    u = usno_data(d.year).get(d.isoformat())
    if u:
        h = lambda s: int(s[:2]) * 60 + int(s[3:5])
        return h(u["rise"]), h(u["set"]), "usno"
    sr, ss = sun_ephem(d)
    m = lambda t: (t + dt.timedelta(seconds=30)).hour * 60 + (t + dt.timedelta(seconds=30)).minute
    return m(sr), m(ss), "ephem"

def sun_times(d):
    """(rise, set, source) display strings in 12-hour form, e.g. ('7:01', '5:30', 'usno')."""
    r, s, src = sun_minutes(d)
    return _fmt12(r), _fmt12(s), src

def daylight(d):
    """(length 'H:MM' from displayed rise/set, change vs previous day 'm:ss' string with sign).
    Change uses PyEphem seconds so it is not quantized to whole minutes."""
    rm, sm, _ = sun_minutes(d); n = sm - rm
    def secs(x): a, b = sun_ephem(x); return (b - a).total_seconds()
    delta = round(secs(d) - secs(d - dt.timedelta(days=1)))
    sign = "+" if delta >= 0 else "-"; delta = abs(delta)
    return f"{n // 60}:{n % 60:02d}", f"{sign}{delta // 60}:{delta % 60:02d}"

def data_source(year):
    """'usno' if every day of the year is in the USNO cache, 'partial', or 'ephem'."""
    n = len(usno_data(year)); full = 366 if (year % 4 == 0 and (year % 100 or year % 400 == 0)) else 365
    return "usno" if n >= full else ("partial" if n else "ephem")

# ---- moon
@lru_cache(maxsize=8)
def principal_phases(year):
    labels = ((ephem.next_new_moon, "New"), (ephem.next_first_quarter_moon, "1st Qtr"),
              (ephem.next_full_moon, "Full"), (ephem.next_last_quarter_moon, "Last Qtr"))
    out, end = {}, ephem.Date(f"{year + 1}/01/05")
    for fn, lab in labels:
        e = ephem.Date(f"{year - 1}/12/20")
        while True:
            e = fn(e)
            if e > end: break
            out[to_et(e).date()] = lab     # converted to Eastern before taking the date
    return out
def principal(d): return principal_phases(d.year).get(d) or (principal_phases(d.year + 1).get(d) if d.month == 12 else principal_phases(d.year - 1).get(d))

def moon_phase28(d):
    """0-28 scale (fraction of synodic month * 28) at Eastern noon."""
    e = ephem.Date(dt.datetime.combine(d, dt.time(12), tzinfo=ET).astimezone(UTC).replace(tzinfo=None))
    prev, nxt = ephem.previous_new_moon(e), ephem.next_new_moon(e)
    return (e - prev) / (nxt - prev) * 28

# ---- seasons / DST (for milestones)
def seasons(year):
    out = {"Spring equinox": to_et(ephem.next_vernal_equinox(f"{year}/01/01")),
           "Summer solstice": to_et(ephem.next_summer_solstice(f"{year}/01/01")),
           "Fall equinox": to_et(ephem.next_autumnal_equinox(f"{year}/01/01")),
           "Winter solstice": to_et(ephem.next_winter_solstice(f"{year}/01/01"))}
    return out

def dst_dates(year):
    d = dt.date(year, 3, 1); sundays = 0
    while True:
        if d.weekday() == 6:
            sundays += 1
            if sundays == 2: start = d; break
        d += dt.timedelta(days=1)
    d = dt.date(year, 11, 1)
    while d.weekday() != 6: d += dt.timedelta(days=1)
    return start, d
