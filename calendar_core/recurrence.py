"""Repeat rules -> concrete dates. A rule is {"kind": ..., **params}."""
import calendar, datetime as dt

KINDS = ["one_off", "yearly_fixed", "yearly_nth_weekday", "weekly_in_range", "lookup_by_year", "yearly_relative"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def nth_weekday(year, month, weekday, n):
    """n=1..4 -> nth weekday (0=Mon); n=-1 -> last."""
    if n > 0:
        first = dt.date(year, month, 1)
        d = first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
        return d if d.month == month else None
    last = dt.date(year, month, calendar.monthrange(year, month)[1])
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)

def _safe(year, month, day):
    try: return dt.date(year, month, day)
    except ValueError: return None     # Feb 29 in a non-leap year

def dates_for_rule(rule, year):
    """Dates this rule produces in calendar `year` (sorted list)."""
    k = rule["kind"]
    if k == "yearly_fixed":
        d = _safe(year, rule["month"], rule["day"]); return [d] if d else []
    if k == "yearly_nth_weekday":
        d = nth_weekday(year, rule["month"], rule["weekday"], rule["n"]); return [d] if d else []
    if k == "weekly_in_range":
        s, e = dt.date.fromisoformat(rule["start"]), dt.date.fromisoformat(rule["end"])
        shift = year - s.year          # the series repeats each year at the same calendar dates
        s, e = _shift(s, shift), _shift(e, shift)
        if not s or not e: return []
        wk = set(rule["weekdays"]); out, d = [], s
        while d <= e:
            if d.weekday() in wk and d.year == year: out.append(d)
            d += dt.timedelta(days=1)
        return out
    if k == "lookup_by_year":
        return sorted(dt.date.fromisoformat(x) for x in rule.get("table", {}).get(str(year), []))
    if k == "yearly_relative":
        return [d + dt.timedelta(days=rule["offset"]) for d in dates_for_rule(rule["base"], year)]
    return []

def _shift(d, years):
    return _safe(d.year + years, d.month, d.day)

def occurrence_dates(event, year):
    """Dates an event covers in `year`: its rule's dates, or its start..end span (one-offs only
    appear in the year(s) they cover)."""
    rule = event.get("rule")
    if rule and rule.get("kind") != "one_off":
        return dates_for_rule(rule, year)
    s = dt.date.fromisoformat(event["start_date"]); e = dt.date.fromisoformat(event["end_date"] or event["start_date"])
    out, d = [], s
    while d <= e:
        if d.year == year: out.append(d)
        d += dt.timedelta(days=1)
    return out

def next_occurrences(rule, after=None, n=3, horizon=12):
    """Next n occurrences on/after `after`, for the 'sanity check' preview in the rule editor."""
    after = after or dt.date.today(); out = []
    for y in range(after.year, after.year + horizon):
        for d in dates_for_rule(rule, y):
            if d >= after: out.append(d)
        if len(out) >= n: break
    return out[:n]

def describe(rule):
    k = rule["kind"]
    if k == "yearly_fixed": return f"Every year on {calendar.month_name[rule['month']]} {rule['day']}"
    if k == "yearly_nth_weekday":
        n = "last" if rule["n"] == -1 else {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}[rule["n"]]
        return f"{n} {calendar.day_name[rule['weekday']]} of {calendar.month_name[rule['month']]}"
    if k == "weekly_in_range":
        return f"{', '.join(WEEKDAYS[i] for i in sorted(rule['weekdays']))} from {rule['start']} to {rule['end']} (each year)"
    if k == "lookup_by_year": return "Dates listed per year: " + ", ".join(sorted(rule.get("table", {})))
    if k == "yearly_relative": return f"{rule['offset']:+d} days from: {describe(rule['base'])}"
    return "One time"

# US federal holidays (actual dates, not observed dates)
FEDERAL_HOLIDAYS = [
    ("New Year's Day", {"kind": "yearly_fixed", "month": 1, "day": 1}),
    ("Martin Luther King Jr. Day", {"kind": "yearly_nth_weekday", "month": 1, "weekday": 0, "n": 3}),
    ("Presidents Day", {"kind": "yearly_nth_weekday", "month": 2, "weekday": 0, "n": 3}),
    ("Memorial Day", {"kind": "yearly_nth_weekday", "month": 5, "weekday": 0, "n": -1}),
    ("Juneteenth", {"kind": "yearly_fixed", "month": 6, "day": 19}),
    ("Fourth of July", {"kind": "yearly_fixed", "month": 7, "day": 4}),
    ("Labor Day", {"kind": "yearly_nth_weekday", "month": 9, "weekday": 0, "n": 1}),
    ("Columbus / Indigenous Peoples' Day", {"kind": "yearly_nth_weekday", "month": 10, "weekday": 0, "n": 2}),
    ("Veterans Day", {"kind": "yearly_fixed", "month": 11, "day": 11}),
    ("Thanksgiving", {"kind": "yearly_nth_weekday", "month": 11, "weekday": 3, "n": 4}),
    ("Christmas", {"kind": "yearly_fixed", "month": 12, "day": 25}),
]
