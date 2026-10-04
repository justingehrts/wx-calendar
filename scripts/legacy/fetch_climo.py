"""
Pull daily normal highs/lows for Columbus (CMH) from RCC-ACIS and write climo.csv
for the calendar generator (cal.py). Run on a machine with normal internet access:

    python fetch_climo.py 2026

Output columns: date, normal_high, normal_low, record_high, record_low
Records come from a period-of-record ACIS summary (max of maxt / min of mint for each
calendar day, threaded CMH record). Tested against the live API.
"""
import csv, json, sys, urllib.request

year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
STATION = "CMH"  # Columbus Port Columbus Intl (threaded record)

req = {
    "sid": STATION,
    "sdate": f"{year}-01-01",
    "edate": f"{year}-12-31",
    "elems": [
        {"name": "maxt", "normal": "1"},
        {"name": "mint", "normal": "1"},
    ],
}
r = urllib.request.Request(
    "https://data.rcc-acis.org/StnData",
    data=json.dumps(req).encode(),
    headers={"Content-Type": "application/json"},
)
data = json.load(urllib.request.urlopen(r, timeout=30))["data"]

def por_summary(elem, reduce):
    q = {"sid": STATION, "sdate": "por", "edate": "por", "elems": [{
        "name": elem, "interval": "dly", "duration": "dly",
        "smry": {"reduce": reduce, "add": "date"}, "smry_only": 1, "groupby": "year"}]}
    r = urllib.request.Request("https://data.rcc-acis.org/StnData", data=json.dumps(q).encode(),
                               headers={"Content-Type": "application/json"})
    out = {}
    for val, d in json.load(urllib.request.urlopen(r, timeout=60))["smry"][0]:
        out[d[5:]] = (val, d[:4])      # "MM-DD" -> (value, year set); first/last date is the record
    return out

rec_hi = por_summary("maxt", "max")
rec_lo = por_summary("mint", "min")

with open("climo.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "normal_high", "normal_low", "record_high", "record_low"])
    for date, hi, lo in data:
        md = date[5:]
        w.writerow([date, round(float(hi)), round(float(lo)),
                    rec_hi.get(md, ("", ""))[0], rec_lo.get(md, ("", ""))[0]])
print(f"Wrote climo.csv ({len(data)} days)")
