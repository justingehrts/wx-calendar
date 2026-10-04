"""iCalendar (.ics) export of one year of events (repeat rules expanded)."""
import datetime as dt
from . import recurrence

def _esc(s): return str(s).replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")

def _runs(dates):
    dates = sorted(dates); runs = []
    for d in dates:
        if runs and (d - runs[-1][1]).days == 1: runs[-1][1] = d
        else: runs.append([d, d])
    return runs

def export_ics(evs, cats, year):
    cat = {c["id"]: c["name"] for c in cats}
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Weathercast Planning Calendar//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Weathercast Planning Calendar"]
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for e in evs:
        for i, (s, f) in enumerate(_runs(recurrence.occurrence_dates(e, year))):
            desc = "\n".join(x for x in (e.get("time") and f"Time: {e['time']}", e.get("notes"), e.get("url")) if x)
            lines += ["BEGIN:VEVENT", f"UID:wxcal-{e['id']}-{year}-{i}@weathercast", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{s.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(f + dt.timedelta(days=1)).strftime('%Y%m%d')}",
                      f"SUMMARY:{_esc(e['title'])}"]
            if e.get("location"): lines.append(f"LOCATION:{_esc(e['location'])}")
            if desc: lines.append(f"DESCRIPTION:{_esc(desc)}")
            if cat.get(e["category_id"]): lines.append(f"CATEGORIES:{_esc(cat[e['category_id']])}")
            lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
