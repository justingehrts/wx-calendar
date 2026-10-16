"""Selectable holiday sets. Each item is a repeat rule, so dates are calculated for any year (nothing to retype at rollover).
Religious dates: Christian from the Easter computus; Jewish from the Hebrew calendar, shown as a "... begins" marker on the evening
the holiday starts (sundown the day before its first full day); Muslim dates are predicted from the Umm al-Qura calendar and the
observed day depends on moon sighting, so they can differ by a day (those events carry a note in the Events tab)."""

def _fixed(m, d): return {"kind": "yearly_fixed", "month": m, "day": d}
def _nth(m, wd, n): return {"kind": "yearly_nth_weekday", "month": m, "weekday": wd, "n": n}
def _easter(off, orthodox=False, days=1): return {"kind": "easter_relative", "offset": off, "orthodox": orthodox, "days": days}
def _heb_eve(m, d, late_adar=False): return {"kind": "hebrew", "month": m, "day": d, "days": 1, "late_adar": late_adar, "offset": -1}   # the evening it begins
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
    ("Mardi Gras", _easter(-47)),
    ("Easter", _easter(0)),
    ("Orthodox Easter", _easter(0, True)),
    ("Christmas Eve", _fixed(12, 24)),
    ("Christmas", _fixed(12, 25)),            # same title as the federal entry, so it is added only once
]
JEWISH = [     # each is a single "begins" marker on the evening the holiday starts
    ("Purim begins", _heb_eve(12, 14, True)),
    ("Passover begins", _heb_eve(1, 15)),
    ("Rosh Hashanah begins", _heb_eve(7, 1)),
    ("Yom Kippur begins", _heb_eve(7, 10)),
    ("Hanukkah begins", _heb_eve(9, 25)),
]
MUSLIM = [
    ("Ramadan begins", _isl(9, 1)),
    ("Eid al-Fitr", _isl(10, 1)),
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
    "christian": ("Christian", "Mardi Gras, Easter, Orthodox Easter, Christmas Eve and Christmas.", CHRISTIAN, None),
    "jewish": ("Jewish", "Purim, Passover, Rosh Hashanah, Yom Kippur and Hanukkah, each shown as \"begins\" on the evening it starts (sundown before its first full day).", JEWISH, None),
    "muslim": ("Muslim", "Ramadan begins, Eid al-Fitr and Eid al-Adha, predicted from the Umm al-Qura calendar (valid 1924-2077). The observed day depends on moon sighting "
                          "and can differ by a day; confirm and edit as needed.", MUSLIM, "predicted date: confirm"),
    "popular": ("Other popular observances", "Mother's Day, Father's Day, Halloween, Valentine's Day, St. Patrick's Day, Groundhog Day, Earth Day.", POPULAR, None),
}
DEFAULT_SETS = ["federal"]

# Entries that earlier versions of the sets created and that are no longer offered (the old Jewish ones were multi-day bars named without
# "begins"). Matched by title AND exact rule, so an event someone made themselves is never touched. Settings offers to trash these.
def _old_heb(m, d, days=1, late_adar=False): return {"kind": "hebrew", "month": m, "day": d, "days": days, "late_adar": late_adar}
RETIRED = {
    "Epiphany": _fixed(1, 6), "Orthodox Christmas": _fixed(1, 7), "Ash Wednesday": _easter(-46), "Palm Sunday": _easter(-7),
    "Good Friday": _easter(-2), "Ascension Day": _easter(39), "Pentecost": _easter(49), "All Saints' Day": _fixed(11, 1),
    "First Sunday of Advent": {"kind": "weekday_nearest", "month": 11, "day": 30, "weekday": 6},
    "Purim": _old_heb(12, 14, 1, True), "Passover": _old_heb(1, 15, 8), "Shavuot": _old_heb(3, 6, 2), "Tisha B'Av": _old_heb(5, 9),
    "Rosh Hashanah": _old_heb(7, 1, 2), "Yom Kippur": _old_heb(7, 10), "Sukkot": _old_heb(7, 15, 7), "Shemini Atzeret": _old_heb(7, 22),
    "Simchat Torah": _old_heb(7, 23), "Hanukkah": _old_heb(9, 25, 8),
    "Islamic New Year": _isl(1, 1), "Ashura": _isl(1, 10), "Mawlid al-Nabi": _isl(3, 12), "Laylat al-Qadr": _isl(9, 27), "Day of Arafah": _isl(12, 9),
}
