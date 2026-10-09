"""Columbus Area (threaded record CMHthr) climate data from RCC-ACIS: daily normals (1991-2020) and period-of-record
daily records, keyed by MM-DD so they work for any year; plus 1991-2020 threshold statistics
used for milestone proposals."""
import csv, datetime as dt, decimal, io, json, statistics, urllib.request
from functools import lru_cache
from . import store

STATION = "CMHthr"   # "Columbus Area" threaded record (what NWS climate pages use); plain "CMH" is the airport alone
MD_FILE = f"climo_{STATION}_md_v2.csv"   # v2: normals from NCEI tenths (rounded half-up like the NWS), records with all tied years
STATS_FILE = f"climo_{STATION}_stats_v2.json"   # v2: adds whole-record extremes; old cached copies are ignored
ACIS = "https://data.rcc-acis.org/StnData"
NORMALS_YEARS = (1991, 2020)

def _post(body, timeout=90):
    r = urllib.request.Request(ACIS, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=timeout))

# ---- normals and records, by MM-DD
IEM_DAILY = "https://mesonet.agron.iastate.edu/cgi-bin/request/daily.py?network=OH_ASOS&stations=CMH&sts=2024-01-01&ets=2024-12-31&format=json"

def half_up(x):
    """Round like the NWS does (46.5 -> 47). Python's round() and ACIS round halves to even (46.5 -> 46)."""
    return int(decimal.Decimal(str(x)).quantize(decimal.Decimal(1), rounding=decimal.ROUND_HALF_UP))

def _iem_normals():
    """{MM-DD: (normal_high_F, normal_low_F)} in tenths: the NCEI 1991-2020 daily normals for the airport, republished
    by the Iowa Environmental Mesonet. (ACIS only returns whole degrees; its normals match CMHthr's.)"""
    rows = json.load(urllib.request.urlopen(IEM_DAILY, timeout=90))
    out = {r["day"][5:10]: (r["climo_high_f"], r["climo_low_f"]) for r in rows if r.get("climo_high_f") is not None}
    if len(out) < 366: raise ValueError(f"IEM returned normals for only {len(out)} days")
    return out

def _daily_records(rows):
    """{MM-DD: {hi: (value, [years]), lo: (value, [years])}} from the whole daily record (all tied years kept)."""
    rec = {}
    for r in rows:
        md = r[0][5:]; y = int(r[0][:4]); mx, mn = _num(r[1]), _num(r[2])
        e = rec.setdefault(md, {"hi": [None, []], "lo": [None, []]})
        if mx is not None:
            if e["hi"][0] is None or mx > e["hi"][0]: e["hi"] = [mx, [y]]
            elif mx == e["hi"][0]: e["hi"][1].append(y)
        if mn is not None:
            if e["lo"][0] is None or mn < e["lo"][0]: e["lo"] = [mn, [y]]
            elif mn == e["lo"][0]: e["lo"][1].append(y)
    return rec

def fetch_normals_records():
    """Normals (NCEI tenths via IEM, rounded half-up) and daily records with all tied years (ACIS CMHthr daily
    record). Writes the cache file."""
    normals = _iem_normals()
    rows = _post({"sid": STATION, "sdate": "por", "edate": dt.date.today().isoformat(), "elems": ["maxt", "mint"]}, 300)["data"]
    rec = _daily_records(rows)
    buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n")
    w.writerow(["md", "normal_high", "normal_low", "normal_high_f", "normal_low_f", "record_high", "record_high_year", "record_high_years",
                "record_low", "record_low_year", "record_low_years"])
    for md in sorted(normals):
        h, l = normals[md]; e = rec[md]
        w.writerow([md, half_up(h), half_up(l), h, l, int(e["hi"][0]), min(e["hi"][1]), ";".join(map(str, sorted(e["hi"][1]))),
                    int(e["lo"][0]), min(e["lo"][1]), ";".join(map(str, sorted(e["lo"][1])))])
    store.write(MD_FILE, buf.getvalue())
    return len(normals)

_tbl = {}
def table():
    text = store.load_text(MD_FILE)
    if _tbl.get("src") is not text: _tbl.update(src=text, rows={r["md"]: r for r in csv.DictReader(io.StringIO(text))} if text else {})
    return _tbl["rows"]

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

# ---- threshold statistics (for milestones)
# Averages use the 1991-2020 normals period. Earliest/latest dates use the whole available record, but only
# in years with nearly complete data for the window that matters (missing days could hide an earlier event).
MIN_COVERAGE = 0.95

def _num(v):
    if v in ("M", "", None): return None
    if v == "T": return 0.0                        # trace counts as zero
    v = v[:-1] if v.endswith("A") else v           # accumulated flag
    try: return float(v)
    except ValueError: return None

def compute_series(D, lo, hi, require_coverage, extras=True):
    """First/last threshold dates per year. D = [(date, maxt, mint, snow)] (None = missing).
    Keys: first_/last_ + freeze|hot90|hot80|snow_meas|snow_1in -> {year: iso date}. Calendar-year series are
    keyed by year; snow series by season start year (seasons run Jul 1-Jun 30). With require_coverage a
    series year is kept only if the relevant window has >= MIN_COVERAGE non-missing days."""
    have = {e: set() for e in ("maxt", "mint", "snow")}
    for d, mx, mn, sn in D:
        if mx is not None: have["maxt"].add(d)
        if mn is not None: have["mint"].add(d)
        if sn is not None: have["snow"].add(d)
    def cov_ok(elem, start, end):
        if not require_coverage: return True
        n = (end - start).days + 1
        return sum(1 for k in range(n) if start + dt.timedelta(days=k) in have[elem]) / n >= MIN_COVERAGE
    out = {}
    def put(key, year, d): out.setdefault(key, {})[str(year)] = d.isoformat()
    by_year = {}
    for d, mx, mn, sn in D: by_year.setdefault(d.year, []).append((d, mx, mn, sn))
    for y in range(lo, hi + 1):
        rows = by_year.get(y, [])
        spr = [d for d, mx, mn, sn in rows if mn is not None and mn <= 32 and d.month < 7]
        fal = [d for d, mx, mn, sn in rows if mn is not None and mn <= 32 and d.month >= 7]
        if spr and cov_ok("mint", dt.date(y, 1, 1), dt.date(y, 6, 30)): put("last_freeze", y, max(spr))
        if fal and cov_ok("mint", dt.date(y, 7, 1), dt.date(y, 12, 31)): put("first_freeze", y, min(fal))
        if extras:
            for name, thr in (("hot90", 90), ("hot80", 80)):
                hot = [d for d, mx, mn, sn in rows if mx is not None and mx >= thr]
                if hot: put("first_" + name, y, min(hot)); put("last_" + name, y, max(hot))
    snow_all = [(d, sn) for d, mx, mn, sn in D if sn is not None]
    for y in range(lo, hi + 1):                    # season y = Jul 1 y .. Jun 30 y+1
        s0, s1 = dt.date(y, 7, 1), dt.date(y + 1, 6, 30)
        for name, thr in (("snow_meas", 0.1), ("snow_1in", 1.0)):
            days = [d for d, sn in snow_all if s0 <= d <= s1 and sn >= thr]
            if not days: continue
            if cov_ok("snow", dt.date(y, 10, 1), dt.date(y, 12, 31)): put("first_" + name, y, min(days))
            if cov_ok("snow", dt.date(y + 1, 1, 1), dt.date(y + 1, 4, 30)): put("last_" + name, y, max(days))
    return out

def fetch_stats():
    """Pull the daily record for CMHthr once; store 1991-2020 series (for averages) and whole-record series
    (for earliest/latest) in the stats file."""
    y0, y1 = NORMALS_YEARS
    rows = _post({"sid": STATION, "sdate": "por", "edate": dt.date.today().isoformat(), "elems": ["maxt", "mint", "snow"]}, 300)["data"]
    D = [(dt.date.fromisoformat(r[0]), _num(r[1]), _num(r[2]), _num(r[3])) for r in rows]
    norm = [t for t in D if y0 <= t[0].year <= y1]
    out = compute_series(norm, y0, y1, False)
    for k in list(out):                            # snow seasons must lie fully inside the normals period
        if "snow" in k: out[k] = {y: v for y, v in out[k].items() if y0 <= int(y) <= y1 - 1}
    rec = compute_series(D, D[0][0].year, dt.date.today().year, True, extras=False)
    out["record"] = rec
    out["_meta"] = {"station": STATION, "period": [y0, y1], "fetched": dt.date.today().isoformat(),
                    "record_start": D[0][0].isoformat(), "record_end": D[-1][0].isoformat(),
                    "thresholds": {"freeze": "min temp <= 32F", "hot90": "max temp >= 90F", "hot80": "max temp >= 80F",
                                   "snow_meas": "snowfall >= 0.1 in", "snow_1in": "snowfall >= 1.0 in"},
                    "note": "Averages are mean dates over 1991-2020 (snow: 29 full seasons Jul 1-Jun 30). Earliest/latest use the full record, "
                            "only in years with >=95% data coverage of the relevant window. Trace counts as 0; missing days ignored."}
    store.write(STATS_FILE, json.dumps(out, indent=1))
    return out

def stats(): return store.load_json(STATS_FILE) or {}

def _base(key):
    """Reference day for offsets, in a non-leap year so Feb 29 never skews dates: Jul 1 for snow seasons, Jan 1 otherwise."""
    return dt.date(2001, 7, 1) if "snow" in key else dt.date(2001, 1, 1)

def _offsets(key, series):
    """[(offset_days, actual_date)]; the offset is measured on a leap-free calendar (Feb 29 counts as Feb 28)."""
    out = []
    for y, iso in series.items():
        d = dt.date.fromisoformat(iso); day = 28 if (d.month, d.day) == (2, 29) else d.day
        ref_year = (2001 if d.month >= 7 else 2002) if "snow" in key else 2001
        out.append(((dt.date(ref_year, d.month, day) - _base(key)).days, d))
    return out

def place(key, target_year, offset):
    """The same month/day in `target_year` for an offset from the series' reference day."""
    d = _base(key) + dt.timedelta(days=offset)
    return dt.date(target_year, d.month, d.day)

def summary(key, target_year, st=None):
    """(mean_date, earliest, latest) mapped into `target_year`. mean: average over 1991-2020. earliest/latest:
    (date_in_target_year, year_it_happened, record_start_year, record_end_year) over the whole record.
    None if no data."""
    st = st or stats(); series = st.get(key)
    if not series: return None
    mean = place(key, target_year, round(statistics.mean(o for o, _ in _offsets(key, series))))
    rec = st.get("record", {}).get(key) or series
    offs = _offsets(key, rec); years = sorted(int(y) for y in rec)
    lo = min(offs, key=lambda t: (t[0], -t[1].year)); hi = max(offs, key=lambda t: (t[0], t[1].year))   # ties: most recent year
    return mean, (place(key, target_year, lo[0]), lo[1].year, years[0], years[-1]), (place(key, target_year, hi[0]), hi[1].year, years[0], years[-1])
