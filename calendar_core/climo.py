"""CMH (Columbus) climate data from RCC-ACIS: daily normals (1991-2020) and period-of-record
daily records, keyed by MM-DD so they work for any year; plus 1991-2020 threshold statistics
used for milestone proposals."""
import csv, datetime as dt, json, os, statistics, urllib.request
from functools import lru_cache
from . import paths

STATION = "CMH"
ACIS = "https://data.rcc-acis.org/StnData"
NORMALS_YEARS = (1991, 2020)

def _post(body, timeout=90):
    r = urllib.request.Request(ACIS, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=timeout))

def _file(name):
    return paths.first_existing(os.path.join(paths.CACHE, name), os.path.join(paths.REFERENCE, name))

# ---- normals and records, by MM-DD
def fetch_normals_records():
    """Normals for leap year 2024 (so Feb 29 exists) plus por daily records. Writes cache CSV."""
    normals = _post({"sid": STATION, "sdate": "2024-01-01", "edate": "2024-12-31",
                     "elems": [{"name": "maxt", "normal": "1"}, {"name": "mint", "normal": "1"}]})["data"]
    def por(elem, reduce):
        q = {"sid": STATION, "sdate": "por", "edate": "por", "elems": [{
            "name": elem, "interval": "dly", "duration": "dly",
            "smry": {"reduce": reduce, "add": "date"}, "smry_only": 1, "groupby": "year"}]}
        return {d[5:]: (v, d[:4]) for v, d in _post(q)["smry"][0]}
    hi, lo = por("maxt", "max"), por("mint", "min")
    os.makedirs(paths.CACHE, exist_ok=True)
    tmp = os.path.join(paths.CACHE, "climo_md.csv.tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["md", "normal_high", "normal_low", "record_high", "record_high_year", "record_low", "record_low_year"])
        for date, h, l in normals:
            md = date[5:]; rh, rl = hi.get(md, ("", "")), lo.get(md, ("", ""))
            w.writerow([md, round(float(h)), round(float(l)), rh[0], rh[1], rl[0], rl[1]])
    os.replace(tmp, os.path.join(paths.CACHE, "climo_md.csv"))
    return len(normals)

@lru_cache(maxsize=2)
def _load(mtime):
    p = _file("climo_md.csv")
    return {r["md"]: r for r in csv.DictReader(open(p))} if p else {}
def table():
    p = _file("climo_md.csv"); return _load(os.path.getmtime(p) if p else 0)

def day(d):
    """dict with normal_high, normal_low, record_high, record_low (strings) or None."""
    return table().get(d.strftime("%m-%d"))

def line(d, records=True, normals=True):
    r = day(d)
    if not r: return ""
    parts = []
    if normals: parts.append(f"Nrm {r['normal_high']}/{r['normal_low']}")
    if records and r.get("record_high") not in (None, ""): parts.append(f"Rec {r['record_high']}/{r['record_low']}")
    return "   ".join(parts)

# ---- 1991-2020 threshold statistics (for milestones)
def fetch_stats():
    """Pull daily maxt/mint/snow for 1991-2020 and store, per threshold, the first/last date each year.
    Keys: first_/last_ + freeze|hot90|hot80|snow_meas|snow_1in. Series are {year: iso date}; snow
    series are keyed by season start year (seasons run Jul 1-Jun 30)."""
    y0, y1 = NORMALS_YEARS
    rows = _post({"sid": STATION, "sdate": f"{y0}-01-01", "edate": f"{y1}-12-31", "elems": ["maxt", "mint", "snow"]}, 180)["data"]
    def num(v):
        if v in ("M", "", None): return None
        if v == "T": return 0.0
        try: return float(v)
        except ValueError: return None
    D = [(dt.date.fromisoformat(r[0]), num(r[1]), num(r[2]), num(r[3])) for r in rows]
    out = {}
    def series(name, idx, test, season, part=None):
        by = {}
        for d, *v in D:
            x = v[idx]
            if x is None or not test(x): continue
            if part == "spring" and d.month >= 7: continue
            if part == "fall" and d.month < 7: continue
            y = (d.year if d.month >= 7 else d.year - 1) if season == "snow" else d.year
            by.setdefault(y, []).append(d)
        if season == "snow": by = {y: v for y, v in by.items() if y0 <= y <= y1 - 1}   # full seasons only
        return by
    def put(key, by, fn): out[key] = {str(y): fn(v).isoformat() for y, v in by.items() if v}
    put("last_freeze", series("f", 1, lambda x: x <= 32, "cal", "spring"), max)
    put("first_freeze", series("f", 1, lambda x: x <= 32, "cal", "fall"), min)
    for n, idx, test in (("hot90", 0, lambda x: x >= 90), ("hot80", 0, lambda x: x >= 80)):
        by = series(n, idx, test, "cal"); put("first_" + n, by, min); put("last_" + n, by, max)
    for n, thr in (("snow_meas", 0.1), ("snow_1in", 1.0)):
        by = series(n, 2, lambda x, t=thr: x >= t, "snow"); put("first_" + n, by, min); put("last_" + n, by, max)
    out["_meta"] = {"station": STATION, "period": [y0, y1], "fetched": dt.date.today().isoformat(),
                    "thresholds": {"freeze": "min temp <= 32F", "hot90": "max temp >= 90F", "hot80": "max temp >= 80F",
                                   "snow_meas": "snowfall >= 0.1 in", "snow_1in": "snowfall >= 1.0 in"},
                    "note": "Averages are the mean date over 1991-2020. Snow seasons run Jul 1-Jun 30 (29 full seasons); trace counts as 0; missing days ignored."}
    os.makedirs(paths.CACHE, exist_ok=True)
    json.dump(out, open(os.path.join(paths.CACHE, "climo_stats.json"), "w"), indent=1)
    return out

def stats():
    p = _file("climo_stats.json"); return json.load(open(p)) if p else {}

def _ref(key, y, d):
    """Reference date for offsets: Jul 1 of the season year for snow, Jan 1 of the year otherwise."""
    return dt.date(y, 7, 1) if "snow" in key else dt.date(d.year, 1, 1)

def summary(key, target_year, st=None):
    """(mean_date, earliest, latest) for a series, mapped into `target_year`. Each of earliest/latest is
    (date_in_target_year, actual_year_it_happened). None if no data."""
    st = st or stats(); series = st.get(key)
    if not series: return None
    snow = "snow" in key
    offs = []
    for y, iso in series.items():
        d = dt.date.fromisoformat(iso); offs.append(((d - _ref(key, int(y), d)).days, d))
    def place(o):
        base = dt.date(target_year - (1 if (snow and key.startswith("last_")) else 0), 7 if snow else 1, 1)
        return base + dt.timedelta(days=o)
    mean = place(round(statistics.mean(o for o, _ in offs)))
    lo, hi = min(offs, key=lambda t: t[0]), max(offs, key=lambda t: t[0])
    return mean, (place(lo[0]), lo[1].year), (place(hi[0]), hi[1].year)
