"""Sun and moon for Columbus, OH. Sunrise/sunset: NOAA's solar-calculator algorithm (solar.py) at the
reference point the NWS climate reports appear to use, printed TRUNCATED to the minute like those reports
(USNO and NOAA GML round instead). Moon phases, seasons and DST: PyEphem. All times Eastern, DST via
America/New_York rules."""
import datetime as dt, math
from functools import lru_cache
from zoneinfo import ZoneInfo
import ephem
from . import solar

LAT, LON, ELEV = "39.9612", "-82.9988", 235     # PyEphem observer (cross-checks only)
# Point used for sunrise/sunset. Fitted to the NWS climate reports for Columbus (99% exact over 342 values, 98% on held-out
# dates); the airport coordinates fit far worse. It is within ~3 km of downtown, i.e. a few seconds of sun time.
SUN_LAT, SUN_LON_EAST = 39.99, -83.00
ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")

def _obs():
    o = ephem.Observer(); o.lat, o.lon, o.elevation = LAT, LON, ELEV
    o.pressure = 0; o.horizon = "-0:34"   # upper limb + standard refraction (USNO definition)
    return o

def to_et(e): return e.datetime().replace(tzinfo=UTC).astimezone(ET)
def _utc_midnight_et(d): return ephem.Date(dt.datetime.combine(d, dt.time(0), tzinfo=ET).astimezone(UTC).replace(tzinfo=None))

# ---- sun times
def _fmt12(m): return f"{(m // 60) % 12 or 12}:{m % 60:02d}"

@lru_cache(maxsize=4000)
def sun_precise(d):
    """(rise, set) as aware Eastern datetimes, to the second (NOAA algorithm)."""
    out = []
    for rise in (True, False):
        utc_min = solar.event_utc_minutes(d, SUN_LAT, SUN_LON_EAST, rise)
        t = dt.datetime.combine(d, dt.time(0), tzinfo=UTC) + dt.timedelta(minutes=utc_min)
        out.append(t.astimezone(ET))
    return tuple(out)

@lru_cache(maxsize=4000)
def sun_pyephem(d):
    """(rise, set) from PyEphem at the downtown point: an independent cross-check of sun_precise."""
    o = _obs(); o.date = _utc_midnight_et(d)
    return to_et(o.next_rising(ephem.Sun())), to_et(o.next_setting(ephem.Sun()))

def sun_minutes(d):
    """(rise, set) as minutes after midnight (24h clock), TRUNCATED to the whole minute (seconds dropped),
    which is how the NWS climate reports and timeanddate.com print them."""
    sr, ss = sun_precise(d)
    return sr.hour * 60 + sr.minute, ss.hour * 60 + ss.minute

def sun_times(d):
    """(rise, set) display strings in 12-hour form, e.g. ('7:01', '5:29')."""
    r, s = sun_minutes(d)
    return _fmt12(r), _fmt12(s)

def daylight(d):
    """(length 'H:MM', change vs previous day '+m:ss' / '-m:ss'). Computed with PyEphem, which matches
    timeanddate.com's day lengths to about a second (the NWS does not publish day length). The length is
    truncated to the minute like the printed sunrise/sunset, so it can differ by a minute from subtracting
    the two printed times."""
    def secs(x): a, b = sun_pyephem(x); return (b - a).total_seconds()
    n = int(secs(d) // 60)
    delta = round(secs(d) - secs(d - dt.timedelta(days=1)))
    sign = "+" if delta >= 0 else "-"; delta = abs(delta)
    return f"{n // 60}:{n % 60:02d}", f"{sign}{delta // 60}:{delta % 60:02d}"

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
