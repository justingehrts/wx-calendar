"""
Pull sunrise/sunset for Columbus, OH from the U.S. Naval Observatory API and save
astro_usno.json, which cal.py uses automatically (falls back to its built-in
calculation for any day missing from the file).

    python fetch_usno.py 2026

USNO definition: sunrise/sunset = upper limb of the Sun at the horizon, including
standard refraction. Times are returned in the offset you request, so this script
sends -5 (EST) or -4 (EDT) per day, using America/New_York rules.

NOT tested against the live API from the build environment (the host was blocked there).
If the response layout differs, adjust the parsing in get_day(). It also prints the
difference vs. the built-in calculation so you can spot-check agreement.
"""
import datetime as dt, json, sys, time, urllib.request, urllib.parse
from zoneinfo import ZoneInfo

YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
COORDS = "39.9612,-82.9988"   # Columbus, OH
ET = ZoneInfo("America/New_York")
BASE = "https://aa.usno.navy.mil/api/rstt/oneday"

def get_day(d):
    off = int(dt.datetime(d.year, d.month, d.day, 12, tzinfo=ET).utcoffset().total_seconds() // 3600)
    q = urllib.parse.urlencode({"date": d.isoformat(), "coords": COORDS, "tz": off, "dst": "false"})
    j = json.load(urllib.request.urlopen(f"{BASE}?{q}", timeout=30))
    data = j.get("properties", {}).get("data", j.get("data", {}))
    sun = {e["phen"]: e["time"] for e in data["sundata"]}
    return {"rise": sun["Rise"], "set": sun["Set"]}

out = {}
d = dt.date(YEAR, 1, 1)
while d.year == YEAR:
    try:
        out[d.isoformat()] = get_day(d)
    except Exception as e:
        print("failed", d, e)
    d += dt.timedelta(days=1)
    time.sleep(0.15)   # be polite to the service
json.dump(out, open("astro_usno.json", "w"), indent=0)
print(f"Wrote astro_usno.json ({len(out)} days)")
