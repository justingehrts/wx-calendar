"""What the app's event tables show, and what an edit to them means. Kept out of app.py so it can be tested without Streamlit."""
import datetime as dt
from . import recurrence

def is_rule(e): return bool(e.get("rule")) and e["rule"].get("kind") != "one_off"

def fmt_span(s, e=None):
    """'Dec 13–14, 2026', 'Dec 30, 2026 – Jan 2, 2027' or 'Nov 21, 2026'."""
    s = s if isinstance(s, dt.date) else dt.date.fromisoformat(str(s))
    e = s if not e else (e if isinstance(e, dt.date) else dt.date.fromisoformat(str(e)))
    if e == s: return f"{s:%b} {s.day}, {s.year}"
    if (e.year, e.month) == (s.year, s.month): return f"{s:%b} {s.day}–{e.day}, {s.year}"
    if e.year == s.year: return f"{s:%b} {s.day} – {e:%b} {e.day}, {s.year}"
    return f"{s:%b} {s.day}, {s.year} – {e:%b} {e.day}, {e.year}"

def event_rows(evs, show, year, month, today, cat="All categories", kind="One-time and repeating", text=""):
    """Rows for an event table: [{'ev', 'date', 'through'}], in calendar order. `show` is 'This month', 'This year' or 'All'.
    A repeating event's stored start date is only a placeholder (the day it was added), so it shows its real date in the period:
    'Christmas  2026-12-25', and in 'All' its next date on or after `today`."""
    rows = []
    for e in evs:
        if cat != "All categories" and e["category"] != cat: continue
        if kind == "One-time only" and is_rule(e) or kind == "Repeating only" and not is_rule(e): continue
        if text and text.lower() not in e["title"].lower(): continue
        if show == "This month": ds = [d for d in recurrence.occurrence_dates(e, year) if d.month == month]
        elif show == "This year": ds = recurrence.occurrence_dates(e, year)
        elif is_rule(e): ds = recurrence.next_occurrences(e["rule"], today, 1)[:1]
        else: ds = [dt.date.fromisoformat(e["start_date"])] + ([dt.date.fromisoformat(e["end_date"])] if e["end_date"] else [])
        if not ds and show != "All": continue
        rows.append({"ev": e, "date": min(ds) if ds else None, "through": max(ds) if ds and max(ds) > min(ds) else None})
    return sorted(rows, key=lambda r: (r["date"] or dt.date.max, r["ev"]["title"]))

def table_changes(rows, state, category_ids):
    """Turn a data-editor state ({'edited_rows', 'deleted_rows', 'added_rows'}) on `rows` into changes:
    {'updates': [(event, fields)], 'deletes': [id], 'adds': [(title, start, end, category_id)], 'skipped': n}.
    Dates typed over a repeating event are skipped (its dates come from its rule), as is the 'details' tick box."""
    out = {"updates": [], "deletes": [], "adds": [], "skipped": 0}
    for idx, ch in state.get("edited_rows", {}).items():
        ev = rows[int(idx)]["ev"]; fields = {}
        for k, v in ch.items():
            if k == "title" and v: fields["title"] = v
            elif k == "category" and v in category_ids: fields["category_id"] = category_ids[v]
            elif k in ("date", "through"):
                if is_rule(ev): out["skipped"] += 1; continue
                if k == "date" and v: fields["start_date"] = str(v)
                if k == "through": fields["end_date"] = str(v) if v else None
        if fields: out["updates"].append((ev, fields))
    out["deletes"] = [rows[int(i)]["ev"]["id"] for i in state.get("deleted_rows", [])]
    for r in state.get("added_rows", []):
        if r.get("title") and r.get("date"):
            out["adds"].append((r["title"], str(r["date"]), str(r["through"]) if r.get("through") else None, category_ids.get(r.get("category"))))
    return out
