"""Selectable holiday sets. Each item is a repeat rule, so dates are calculated for any year (nothing to retype at rollover).
Religious dates: Christian from the Easter computus; Jewish from the Hebrew calendar (a holiday begins at sundown the evening
BEFORE the first date shown, as on Hebcal-style calendars); Muslim dates are predicted from the Umm al-Qura calendar and the
observed day depends on moon sighting, so they can differ by a day (those events carry a note in the Events tab)."""

def _fixed(m, d): return {"kind": "yearly_fixed", "month": m, "day": d}
def _nth(m, wd, n): return {"kind": "yearly_nth_weekday", "month": m, "weekday": wd, "n": n}
def _easter(off, orthodox=False, days=1): return {"kind": "easter_relative", "offset": off, "orthodox": orthodox, "days": days}
def _heb(m, d, days=1, late_adar=False): return {"kind": "hebrew", "month": m, "day": d, "days": days, "late_adar": late_adar}
def _isl(m, d): return {"kind": "islamic", "month": m, "day": d, "days": 1}

FEDERAL = [
    ("New Year's Day", _fixed(1, 1)),
    ("Martin Luther King Jr. Day", _nth(1, 0, 3)),
    ("Presidents Day", _nth(2, 0, 3)),
    ("Memorial Day", _nth(5, 0, -1)),
    ("Juneteenth", _fixed(6, 19)),
    ("Fourth of July", _fixed(7, 4)),
    ("Labor Day", _nth(9, 0, 1)),
    ("Columbus / Indigenous Peoples' Day", _nth(10, 0, 2)),
    ("Veterans Day", _fixed(11, 11)),
    ("Thanksgiving", _nth(11, 3, 4)),
    ("Christmas", _fixed(12, 25)),
]
CHRISTIAN = [
    ("Epiphany", _fixed(1, 6)),
    ("Orthodox Christmas", _fixed(1, 7)),
    ("Mardi Gras", _easter(-47)),
    ("Ash Wednesday", _easter(-46)),
    ("Palm Sunday", _easter(-7)),
    ("Good Friday", _easter(-2)),
    ("Easter", _easter(0)),
    ("Orthodox Easter", _easter(0, True)),
    ("Ascension Day", _easter(39)),
    ("Pentecost", _easter(49)),
    ("All Saints' Day", _fixed(11, 1)),
    ("First Sunday of Advent", {"kind": "weekday_nearest", "month": 11, "day": 30, "weekday": 6}),
    ("Christmas Eve", _fixed(12, 24)),
    ("Christmas", _fixed(12, 25)),            # same title as the federal entry, so it is added only once
]
JEWISH = [
    ("Purim", _heb(12, 14, 1, True)),
    ("Passover", _heb(1, 15, 8)),
    ("Shavuot", _heb(3, 6, 2)),
    ("Tisha B'Av", _heb(5, 9)),
    ("Rosh Hashanah", _heb(7, 1, 2)),
    ("Yom Kippur", _heb(7, 10)),
    ("Sukkot", _heb(7, 15, 7)),
    ("Shemini Atzeret", _heb(7, 22)),
    ("Simchat Torah", _heb(7, 23)),
    ("Hanukkah", _heb(9, 25, 8)),
]
MUSLIM = [
    ("Islamic New Year", _isl(1, 1)),
    ("Ashura", _isl(1, 10)),
    ("Mawlid al-Nabi", _isl(3, 12)),
    ("Ramadan begins", _isl(9, 1)),
    ("Laylat al-Qadr", _isl(9, 27)),
    ("Eid al-Fitr", _isl(10, 1)),
    ("Day of Arafah", _isl(12, 9)),
    ("Eid al-Adha", _isl(12, 10)),
]
POPULAR = [
    ("Groundhog Day", _fixed(2, 2)),
    ("Valentine's Day", _fixed(2, 14)),
    ("St. Patrick's Day", _fixed(3, 17)),
    ("Earth Day", _fixed(4, 22)),
    ("Mother's Day", _nth(5, 6, 2)),
    ("Father's Day", _nth(6, 6, 3)),
    ("Halloween", _fixed(10, 31)),
]

# key -> (label, description, items, flag for the Events tab or None)
HOLIDAY_SETS = {
    "federal": ("U.S. federal holidays", "Actual dates (not the Friday/Monday 'observed' dates).", FEDERAL, None),
    "christian": ("Christian", "Western and Orthodox Easter and the days around it, Advent, Christmas Eve, and other major feasts.", CHRISTIAN, None),
    "jewish": ("Jewish", "Major holidays. Each begins at sundown the evening before the first date shown.", JEWISH, None),
    "muslim": ("Muslim", "Major observances, predicted from the Umm al-Qura calendar (valid 1924-2077). The observed day depends on moon sighting "
                          "and can differ by a day; confirm and edit as needed.", MUSLIM, "predicted date: confirm"),
    "popular": ("Other popular observances", "Mother's Day, Father's Day, Halloween, Valentine's Day, St. Patrick's Day, Groundhog Day, Earth Day.", POPULAR, None),
}
DEFAULT_SETS = ["federal"]
