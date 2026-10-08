"""Auto-generated milestone proposals (sun, sky, DST, climo). Nothing is added to the calendar
until a person accepts it; rejected ones are remembered and do not come back."""
import datetime as dt, json, os
from . import astro, climo, db, paths

SKY, CLIMO, HOL = "Sky / Astronomy", "Climo records", "Holidays"

def _days(year):
    d = dt.date(year, 1, 1)
    while d.year == year: yield d; d += dt.timedelta(days=1)

def _clock(m): return f"{(m // 60) % 12 or 12}:{m % 60:02d} {'AM' if m < 720 else 'PM'}"
def _hour(h): return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"

def sun_milestones(year):
    days = list(_days(year)); out = []
    sec = {d: astro.sun_ephem(d) for d in days}
    def tod(t): return t.hour * 3600 + t.minute * 60 + t.second
    for label, idx, fn in (("Earliest sunrise", 0, min), ("Latest sunrise", 0, max), ("Earliest sunset", 1, min), ("Latest sunset", 1, max)):
        d = fn(days, key=lambda x: tod(sec[x][idx]))
        r, s, _ = astro.sun_minutes(d)
        out.append((f"sun:{label.lower().replace(' ', '_')}:{year}", f"{label} of the year ({_clock(r if idx == 0 else s)})", d, SKY,
                    "Sunrise/sunset: upper limb, standard refraction, Eastern Time."))
    mins = {d: astro.sun_minutes(d)[:2] for d in days}
    def longest_run(ok):
        runs, cur = [], [ok[0]]
        for d in ok[1:]:
            if (d - cur[-1]).days == 1: cur.append(d)
            else: runs.append(cur); cur = [d]
        return max(runs + [cur], key=len)
    def crossing(tag, label, test):
        """First/last day of the longest contiguous run where `test` holds; skips year-edge artifacts."""
        ok = [d for d in days if test(d)]
        if not ok or len(ok) == len(days): return
        run = longest_run(ok)
        if run[0] != days[0]: out.append((f"sun:first_{tag}:{year}", f"First {label}", run[0], SKY, ""))
        if run[-1] != days[-1]: out.append((f"sun:last_{tag}:{year}", f"Last {label}", run[-1], SKY, ""))
    mins = {d: astro.sun_minutes(d)[:2] for d in days}
    for h in (6, 7, 8, 9):           # sunsets at/after a round PM hour
        crossing(f"set_{h}pm", f"sunset at/after {_hour(h + 12)}", lambda d, h=h: mins[d][1] >= (h + 12) * 60)
    for h in (6, 7, 8):              # sunrises before a round AM hour
        crossing(f"rise_{h}am", f"sunrise before {_hour(h)}", lambda d, h=h: mins[d][0] < h * 60)
    for name, t in astro.seasons(year).items():
        out.append((f"sun:{name.lower().replace(' ', '_')}:{year}", name, t.date(), SKY,
                    f"{t.strftime('%I:%M %p').lstrip('0')} Eastern"))
    L = {d: (sec[d][1] - sec[d][0]).total_seconds() for d in days}
    half = lambda ds: min(ds, key=lambda d: abs(L[d] - 43200))
    spring = [d for d in days if d < dt.date(year, 6, 21)]; fall = [d for d in days if d > dt.date(year, 6, 21)]
    out.append((f"sun:equilux_spring:{year}", "Spring equilux (day = night)", half(spring), SKY, "Day length closest to 12 hours (sunrise to sunset, with refraction)."))
    out.append((f"sun:equilux_fall:{year}", "Fall equilux (day = night)", half(fall), SKY, "Day length closest to 12 hours (sunrise to sunset, with refraction)."))
    a, b = astro.dst_dates(year)
    out.append((f"dst:begins:{year}", "DST begins", a, HOL, "Clocks spring forward at 2 AM."))
    out.append((f"dst:ends:{year}", "DST ends", b, HOL, "Clocks fall back at 2 AM."))
    return out

def meteor_milestones(year):
    p = os.path.join(paths.REFERENCE, "meteor_showers.json")
    data = json.load(open(p)) if os.path.exists(p) else {"typical": [], "years": {}}
    verified = data.get("years", {}).get(str(year), {}); out = []
    for s in data["typical"]:
        if s["name"] in verified:
            d, note = dt.date.fromisoformat(verified[s["name"]]), "Peak date verified for this year."
        else:
            d, note = dt.date(year, s["month"], s["day"]), "TYPICAL date (±1 day), NOT verified for this year. Check the IMO/AMS calendar before airing."
        out.append((f"meteor:{s['name'].lower().replace(' ', '_')}:{year}", f"{s['name']} meteor shower peak", d, SKY, note))
    return out

CLIMO_ITEMS = [   # (series key, label, include earliest/latest extremes)
    ("last_freeze", "Avg last 32° freeze", True), ("first_freeze", "Avg first 32° freeze", True),
    ("first_hot80", "Avg first 80° day", False), ("last_hot80", "Avg last 80° day", False),
    ("first_hot90", "Avg first 90° day", False), ("last_hot90", "Avg last 90° day", False),
    ("first_snow_meas", "Avg first measurable snow", True), ("last_snow_meas", "Avg last measurable snow", True),
    ("first_snow_1in", "Avg first 1\" snow", True), ("last_snow_1in", "Avg last 1\" snow", True),
]
def climo_milestones(year):
    st = climo.stats(); out = []
    if not st: return out
    per = st["_meta"]["period"]; why = f"Mean date over {per[0]}-{per[1]}, Columbus Area (threaded record, CMHthr)."
    for key, label, extremes in CLIMO_ITEMS:
        s = climo.summary(key, year, st)
        if not s: continue
        mean, early, late = s
        if mean.year == year: out.append((f"climo:{key}:avg:{year}", label, mean, CLIMO, why))
        if extremes:
            what = label.replace("Avg ", "")
            for tag, (d, y, r0, r1) in (("earliest", early), ("latest", late)):
                if d.year == year:
                    out.append((f"climo:{key}:rec_{tag}:{year}", f"{tag.capitalize()} {what} on record ({y})", d, CLIMO,
                                f"{tag.capitalize()} on record ({r0}-{r1}, years with near-complete data); it happened in {y}, shown on this calendar date."))
    return out

def propose(year):
    rows = sun_milestones(year) + meteor_milestones(year) + climo_milestones(year)
    return sorted(({"key": k, "title": t, "date": d, "category": c, "note": n} for k, t, d, c, n in rows),
                  key=lambda r: (r["date"], r["title"]))

def pending(con, year):
    seen = db.milestone_status(con)
    return [r for r in propose(year) if r["key"] not in seen]

def accept(con, cand):
    eid = db.add_event(con, cand["title"], cand["date"], None, db.category_id_by_name(con, cand["category"]) or None,
                       notes=cand["note"], detail_only=False)
    db.decide_milestone(con, cand["key"], "accepted", eid); return eid

def reject(con, cand): db.decide_milestone(con, cand["key"], "rejected")
