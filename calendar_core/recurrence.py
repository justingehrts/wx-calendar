"""Repeat rules -> concrete dates. A rule is {"kind": ..., **params}."""
import calendar, datetime as dt

KINDS = ["one_off", "yearly_fixed", "yearly_nth_weekday", "weekly_in_range", "lookup_by_year", "yearly_relative"]
# Calculated automatically for any year (religious calendars); shown read-only in the rule editor
CALCULATED_KINDS = ["easter_relative", "weekday_nearest", "hebrew", "islamic"]
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

def easter(year, orthodox=False):
    """Easter Sunday (Gregorian calendar date). Western: Meeus/Jones/Butcher; Orthodox: Julian computus + calendar offset."""
    if not orthodox:
        a, b, c = year % 19, year // 100, year % 100
        d, e = b // 4, b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30; i, k = c // 4, c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
        return dt.date(year, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30; e = (2 * a + 4 * b - d + 34) % 7
    julian = dt.date(year, (d + e + 114) // 31, (d + e + 114) % 31 + 1)
    return julian + dt.timedelta(days=year // 100 - year // 400 - 2)       # Julian -> Gregorian (13 days in 1900-2099)

def _span(start, days, year):
    return [d for d in (start + dt.timedelta(days=i) for i in range(days)) if d.year == year]

def hebrew_dates(rule, year):
    """Gregorian dates in `year` for a Hebrew-calendar holiday: {month, day, days, late_adar, offset}. Nisan=1 ... Elul=6, Tishrei=7 ...
    Adar=12 (Adar II = 13 in leap years when late_adar is set). Holidays begin at sundown the evening before the first full day, so
    offset=-1 puts the date on that evening."""
    from pyluach import dates, hebrewcal
    out = set()
    for hy in (year + 3760, year + 3761):
        month = 13 if rule.get("late_adar") and rule["month"] == 12 and hebrewcal.Year(hy).leap else rule["month"]
        first_day = dates.HebrewDate(hy, month, rule["day"]).to_pydate()
        out.update(_span(first_day + dt.timedelta(days=rule.get("offset", 0)), rule.get("days", 1), year))
    return sorted(out)

def islamic_dates(rule, year):
    """Gregorian dates in `year` for a Hijri-calendar date {month, day, days} using the Umm al-Qura calendar (valid 1924-2077).
    The observed day depends on moon sighting and can differ by a day."""
    from hijridate import Hijri
    out = set()
    for hy in range(year - 580, year - 576):               # a Gregorian year overlaps two or three Hijri years
        try: g = Hijri(hy, rule["month"], rule["day"]).to_gregorian()
        except (ValueError, OverflowError): continue          # outside the supported range
        out.update(_span(dt.date(g.year, g.month, g.day), rule.get("days", 1), year))
    return sorted(out)

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
    if k == "easter_relative":
        return _span(easter(year, rule.get("orthodox", False)) + dt.timedelta(days=rule["offset"]), rule.get("days", 1), year)
    if k == "weekday_nearest":       # e.g. the Sunday nearest Nov 30 (first Sunday of Advent)
        target = dt.date(year, rule["month"], rule["day"])
        return [d for d in (target + dt.timedelta(days=i) for i in range(-3, 4)) if d.weekday() == rule["weekday"]][:1]
    if k == "hebrew": return hebrew_dates(rule, year)
    if k == "islamic": return islamic_dates(rule, year)
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
    if k == "easter_relative":
        off = rule["offset"]; base = "Orthodox Easter" if rule.get("orthodox") else "Easter"
        return f"{base}" + (f" {off:+d} days" if off else "") + (f", {rule['days']} days" if rule.get("days", 1) > 1 else "")
    if k == "weekday_nearest": return f"{calendar.day_name[rule['weekday']]} nearest {calendar.month_name[rule['month']]} {rule['day']}"
    if k == "hebrew":
        names = {1: "Nisan", 2: "Iyar", 3: "Sivan", 4: "Tammuz", 5: "Av", 6: "Elul", 7: "Tishrei", 8: "Cheshvan", 9: "Kislev", 10: "Tevet", 11: "Shevat", 12: "Adar"}
        what = f"{rule['day']} {names.get(rule['month'], rule['month'])}"
        if rule.get("offset") == -1: return f"Hebrew calendar: the evening it begins (sundown before {what})"
        return f"Hebrew calendar: {what}" + (f", {rule['days']} days" if rule.get("days", 1) > 1 else "")
    if k == "islamic":
        names = {1: "Muharram", 2: "Safar", 3: "Rabi' al-awwal", 4: "Rabi' al-thani", 5: "Jumada al-awwal", 6: "Jumada al-thani", 7: "Rajab",
                 8: "Sha'ban", 9: "Ramadan", 10: "Shawwal", 11: "Dhu al-Qi'dah", 12: "Dhu al-Hijjah"}
        return f"Islamic calendar: {rule['day']} {names.get(rule['month'], rule['month'])} (predicted, Umm al-Qura)"
    return "One time"

# kept for older imports/tests; the sets live in holidays.py
from .holidays import FEDERAL as FEDERAL_HOLIDAYS


def format_dates(dates):
    """Compact text for a sorted list of dates: 'Sep 12-13', 'Dec 26 - Jan 2', 'Apr 5'."""
    runs = []
    for d in sorted(dates):
        if runs and (d - runs[-1][1]).days == 1: runs[-1][1] = d
        else: runs.append([d, d])
    def one(a, b):
        if a == b: return f"{a:%b} {a.day}"
        return f"{a:%b} {a.day}-{b.day}" if a.month == b.month else f"{a:%b} {a.day} - {b:%b} {b.day}"
    return ", ".join(one(a, b) for a, b in runs)
