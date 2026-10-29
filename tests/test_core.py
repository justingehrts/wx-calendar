import datetime as dt, io, threading
import pypdfium2 as pdfium
from calendar_core import astro, db, ical, importers, milestones, patterns, preview, recurrence as rc, render_pdf as R

D = dt.date

# ---------------------------------------------------------------- recurrence
def test_thanksgiving_memorial_and_dst():
    th = dict(rc.FEDERAL_HOLIDAYS)["Thanksgiving"]; mem = dict(rc.FEDERAL_HOLIDAYS)["Memorial Day"]
    assert rc.dates_for_rule(th, 2026) == [D(2026, 11, 26)] and rc.dates_for_rule(th, 2027) == [D(2027, 11, 25)]
    assert rc.dates_for_rule(mem, 2026) == [D(2026, 5, 25)] and rc.dates_for_rule(mem, 2030) == [D(2030, 5, 27)]
    assert astro.dst_dates(2026) == (D(2026, 3, 8), D(2026, 11, 1))
    assert astro.dst_dates(2027) == (D(2027, 3, 14), D(2027, 11, 7))
    assert astro.dst_dates(2025) == (D(2025, 3, 9), D(2025, 11, 2))

def test_rules_weekly_lookup_relative_and_leap():
    wk = {"kind": "weekly_in_range", "weekdays": [4, 5], "start": "2026-07-10", "end": "2026-07-19"}
    assert rc.dates_for_rule(wk, 2026) == [D(2026, 7, 10), D(2026, 7, 11), D(2026, 7, 17), D(2026, 7, 18)]
    assert rc.dates_for_rule({"kind": "lookup_by_year", "table": {"2026": ["2026-12-04"]}}, 2027) == []
    assert rc.dates_for_rule({"kind": "yearly_relative", "offset": 1, "base": {"kind": "yearly_fixed", "month": 12, "day": 24}}, 2026) == [D(2026, 12, 25)]
    assert rc.dates_for_rule({"kind": "yearly_fixed", "month": 2, "day": 29}, 2027) == []
    assert len(rc.next_occurrences({"kind": "yearly_fixed", "month": 7, "day": 4}, D(2026, 8, 1), 3)) == 3

# --------------------------------------------------------------- astronomy
def test_principal_moon_phases_eastern():
    full = sorted(d for d, l in astro.principal_phases(2026).items() if l == "Full" and d.month in (10, 11, 12))
    assert full == [D(2026, 10, 26), D(2026, 11, 24), D(2026, 12, 23)]

def _fixture(name):
    import json, os
    return json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", name)))

def test_dst_transition_days_and_agreement_with_usno_and_pyephem():
    assert astro.sun_times(D(2026, 10, 31)) == ("7:59", "6:30") and astro.sun_times(D(2026, 11, 1)) == ("7:01", "5:29")
    usno, worst_usno, worst_pe = _fixture("usno_2026.json"), 0, 0
    mins = lambda t: t.hour * 60 + t.minute + t.second / 60
    h = lambda s: int(s[:2]) * 60 + int(s[3:])
    for k, v in usno.items():
        d = D.fromisoformat(k); sr, ss = astro.sun_precise(d); pr, ps = astro.sun_pyephem(d)
        worst_usno = max(worst_usno, abs(h(v["rise"]) - mins(sr)), abs(h(v["set"]) - mins(ss)))     # USNO rounds: ~0.5 min plus the location offset
        worst_pe = max(worst_pe, abs(mins(pr) - mins(sr)), abs(mins(ps) - mins(ss)))
    assert len(usno) == 365 and worst_usno < 0.75 and worst_pe < 0.25                              # independent engines agree within ~15 s

def test_daylight_shape():
    ln, ch = astro.daylight(D(2026, 6, 20)); assert ln.startswith("15:") and ch[0] in "+-"
    assert astro.daylight(D(2026, 3, 19))[1].startswith("+")

# ------------------------------------------------------------ layout / bars
def test_week_boundary_split():
    it = R.Item(1, "Homestand", 1, {D(2026, 10, d) for d in range(8, 15)})
    w1 = [D(2026, 10, 4) + dt.timedelta(days=i) for i in range(7)]; w2 = [d + dt.timedelta(days=7) for d in w1]
    assert [(a, b) for a, b, _ in R.layout_week(w1, [it])[0]] == [(4, 6)]
    assert [(a, b) for a, b, _ in R.layout_week(w2, [it])[0]] == [(0, 3)]

def test_gap_breaks_bar():
    it = R.Item(1, "Fri-Sat series", 1, {D(2026, 7, 10), D(2026, 7, 11), D(2026, 7, 17)})
    wk = [D(2026, 7, 5) + dt.timedelta(days=i) for i in range(7)]
    assert [(a, b) for a, b, _ in R.layout_week(wk, [it])[0]] == [(5, 6)]

# ------------------------------------------------------------- B&W / colors
def test_contrast_ratio():
    assert round(patterns.contrast_ratio("#FFFFFF", "#000000")) == 21
    assert patterns.white_text_contrast("#777777") > 4.4 and patterns.white_text_contrast("#BBBBBB") < 3

def test_default_categories_unique_bw_styles(con):
    assert patterns.style_collisions(db.categories(con)) == []
    assert len({patterns.signature(s) for s in patterns.STYLES}) == len(patterns.STYLES)

def test_bw_styles_render_distinct_in_grayscale():
    cats = [{"name": s, "color_hex": "#444444", "bw_style": s} for s in patterns.STYLES]
    sc = 3; img = pdfium.PdfDocument(R.legend_preview(cats, True))[0].render(scale=sc).to_pil().convert("L"); sigs = []
    for i in range(len(cats)):          # a text-free strip at the right end of each bar (PDF y runs upward, image rows downward)
        row = 16 + 14 * i                 # distance from the top of the page to the bar's baseline
        box = img.crop((300 * sc, int((row - 5.5) * sc), 334 * sc, int((row + 1.5) * sc)))
        px = list(box.getdata()); sigs.append((round(sum(px) / len(px)), len(set(px))))
    means = [m for m, _ in sigs]
    assert means[0] < 60 and 120 < means[1] < 170 and 190 < means[2] < 230       # dark, medium, light fills
    assert len(set(sigs)) == len(cats), sigs

# -------------------------------------------------------------- rendering
def _pages(pdf): return len(pdfium.PdfDocument(pdf))

def test_render_months_and_week_counts(con):
    db.load_federal_holidays(con); db.add_event(con, "Clippers", "2026-08-01", "2026-08-09")
    evs, cats = db.events(con), db.categories(con)
    for bw in (False, True):
        for m, weeks in ((2, 4), (8, 6), (10, 5)):
            pdf, rep = R.render(evs, cats, 2026, [m], R.Options(bw=bw, details_page=False)); assert _pages(pdf) == 1
    assert len(__import__("calendar").Calendar(6).monthdatescalendar(2026, 8)) == 6
    assert len(__import__("calendar").Calendar(6).monthdatescalendar(2026, 2)) == 4
    pdf, _ = R.render(evs, cats, 2026, range(1, 13), R.Options(details_page=False)); assert _pages(pdf) == 12
    pdf, _ = R.render(evs, cats, 2026, [10], R.Options(week_start=0, paper="a4")); assert _pages(pdf) >= 1

def test_overflow_never_silent_and_details_page(con):
    for i in range(9): db.add_event(con, f"Event {i}", "2026-10-31")
    pdf, rep = R.render(db.events(con), db.categories(con), 2026, [10])
    msgs = R.overflow_messages(rep); assert msgs and msgs[0].startswith("Oct 31: 9 events")
    hidden = {t for _, t in rep["hidden"]}; assert len(hidden) == rep["overflow"][0]["hidden"] >= 4
    assert _pages(pdf) == 2          # calendar + details page listing the hidden events

def test_compact_mode_fits_more(con):
    for i in range(6): db.add_event(con, f"Event {i}", "2026-10-31")
    _, rep = R.render(db.events(con), db.categories(con), 2026, [10]); assert rep["overflow"]
    pdf, rep2 = R.render(db.events(con), db.categories(con), 2026, [10], R.Options(compact=True)); assert not rep2["overflow"]

def test_details_page_and_detail_only(con):
    db.add_event(con, "Live shot", "2026-10-14", time="10 AM", location="Expo Center", notes="Midway")
    db.add_event(con, "Minor thing", "2026-10-15", detail_only=True)
    pdf, rep = R.render(db.events(con), db.categories(con), 2026, [10]); assert _pages(pdf) == 2
    img = preview.pdf_to_pngs(pdf, 1); assert len(img) == 2 and img[0][:4] == b"\x89PNG"
    assert preview.pdf_to_pngs(pdf, 1, grayscale=True)

def test_may_not_show_events_outside_month_but_spill_shown(con):
    db.add_event(con, "Spill", "2026-09-30")     # appears in the leading spill row of October
    pdf, rep = R.render(db.events(con), db.categories(con), 2026, [10], R.Options(details_page=False)); assert _pages(pdf) == 1

# -------------------------------------------------------------- milestones
def test_milestones_accept_reject_persist(con):
    c = {m["key"]: m for m in milestones.propose(2026)}
    assert c["sun:summer_solstice:2026"]["date"] == D(2026, 6, 21) and c["dst:ends:2026"]["date"] == D(2026, 11, 1)
    assert c["sun:fall_equinox:2026"]["date"] == D(2026, 9, 22)
    assert c["sun:earliest_sunrise:2026"]["date"] in (D(2026, 6, 13), D(2026, 6, 14), D(2026, 6, 15))
    assert "TYPICAL" in c["meteor:perseids:2026"]["note"]
    first = milestones.pending(con, 2026)
    milestones.accept(con, c["dst:ends:2026"]); milestones.reject(con, c["sun:summer_solstice:2026"])
    keys = {m["key"] for m in milestones.pending(con, 2026)}
    assert "dst:ends:2026" not in keys and "sun:summer_solstice:2026" not in keys and len(keys) == len(first) - 2
    assert any(e["title"] == "DST ends" and e["category"] == "Holidays" for e in db.events(con))

def test_climo_milestones_reasonable():
    c = {m["key"]: m for m in milestones.propose(2026)}
    d = c["climo:last_freeze:avg:2026"]["date"]; assert D(2026, 4, 5) <= d <= D(2026, 5, 5)
    d = c["climo:first_freeze:avg:2026"]["date"]; assert D(2026, 10, 10) <= d <= D(2026, 11, 10)

# --------------------------------------------------------- team safety
def test_undo_trash_restore(con):
    i = db.add_event(con, "A", "2026-01-01")
    db.update_event(con, i, title="B"); assert db.get_event(con, i)["title"] == "B"
    db.undo_last(con); assert db.get_event(con, i)["title"] == "A"
    db.delete_event(con, i); assert db.events(con) == [] and len(db.events(con, only_deleted=True)) == 1
    db.undo_last(con); assert len(db.events(con)) == 1
    db.undo_last(con); assert db.events(con) == []          # undo the create -> trash
    db.restore_event(con, i); assert len(db.events(con)) == 1
    assert db.undo_last(con).startswith("Undid")

def test_undo_restores_rule(con):
    i = db.add_event(con, "Xmas", "2026-12-25", rule={"kind": "yearly_fixed", "month": 12, "day": 25})
    db.update_event(con, i, rule=None); assert db.get_event(con, i)["rule"] is None
    db.undo_last(con); assert db.get_event(con, i)["rule"]["kind"] == "yearly_fixed"

def test_edit_conflict_detected(con):
    i = db.add_event(con, "A", "2026-01-01"); e = db.get_event(con, i)
    assert db.update_event(con, i, expect_updated_at=e["updated_at"], title="Mine")
    # a second session that loaded the old row now loses instead of clobbering
    import time; time.sleep(1.1)
    assert db.update_event(con, i, title="Theirs")
    assert not db.update_event(con, i, expect_updated_at=e["updated_at"], title="Stale")
    assert db.get_event(con, i)["title"] == "Theirs"

def test_concurrent_writers_lose_nothing(tmp_path):
    p = str(tmp_path / "c.db"); db.connect(p)
    def work(k):
        c = db.connect(p)
        for j in range(25): db.add_event(c, f"s{k}-{j}", "2026-03-01")
    ts = [threading.Thread(target=work, args=(k,)) for k in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(db.events(db.connect(p))) == 100

# ------------------------------------------------ categories / io / rollover
def test_delete_category_moves_events(con):
    cats = {c["name"]: c["id"] for c in db.categories(con)}
    i = db.add_event(con, "Game", "2026-10-10", category_id=cats["Sports"])
    db.delete_category(con, cats["Sports"], cats["Community events"])
    assert db.get_event(con, i)["category"] == "Community events"

def test_csv_roundtrip_with_rule_and_ics(con, tmp_path):
    db.load_federal_holidays(con); db.add_event(con, "Pumpkin Show", "2026-10-21", "2026-10-25", notes="Circleville; fun")
    txt = importers.export_csv(con); c2 = db.connect(str(tmp_path / "u.db")); n = importers.import_csv(c2, txt)
    assert n == len(db.events(con)) and any(e["rule"] for e in db.events(c2))
    ics = ical.export_ics(db.events(c2), db.categories(c2), 2026)
    assert "SUMMARY:Thanksgiving" in ics and "DTSTART;VALUE=DATE:20261126" in ics and "DTEND;VALUE=DATE:20261026" in ics

def test_holidays_idempotent_and_rollover(con):
    assert db.load_federal_holidays(con) == 11 and db.load_federal_holidays(con) == 0
    i = db.add_event(con, "One-off 2026", "2026-02-29" if False else "2026-10-10", "2026-10-12")
    assert [e["id"] for e in db.one_offs(con, 2026)] == [i]
    assert db.carry_forward(con, [(i, db.shift_year("2026-10-10", 1), db.shift_year("2026-10-12", 1))]) == 1
    assert db.shift_year("2024-02-29", 1) == "2025-02-28"
    day = [e["title"] for e in db.events_on_day(con, D(2027, 11, 25))]; assert day == ["Thanksgiving"]

def test_backup_bytes(con):
    db.add_event(con, "x", "2026-01-01"); assert db.backup_bytes(con)[:15] == b"SQLite format 3"


def test_store_roundtrip_file_and_database_modes(tmp_path, monkeypatch):
    from calendar_core import store, paths
    monkeypatch.setattr(paths, "CACHE", str(tmp_path / "cache"))
    store._mem.clear(); store.write("x.json", '{"a": 1}'); assert store.load_json("x.json") == {"a": 1} and store.has_cached("x.json")
    assert store.load_text("meteor_showers.json")             # bundled reference file is the fallback
    # database mode: same API, backed by the cache_files table (libsql local file stands in for Turso)
    c = db.connect(str(tmp_path / "remote.db"), libsql=True)
    monkeypatch.setattr(store, "_remote", lambda: True); monkeypatch.setattr(db, "connect", lambda *a, **k: c)
    store._mem.clear(); store.write("y.json", '{"b": 2}'); assert store.load_json("y.json") == {"b": 2} and store.has_cached("y.json")
    store.write("y.json", '{"b": 3}'); store._mem.clear(); assert store.load_json("y.json") == {"b": 3}


class _HostileCursor:
    """Mimics a hosted connection that reports no column names and no lastrowid."""
    def __init__(self, c): self._c = c; self.description = None; self.lastrowid = None; self.rowcount = -1
    def fetchall(self): return self._c.fetchall()
    def fetchone(self): return self._c.fetchone()

class _HostileRaw:
    def __init__(self, raw): self._r = raw
    def execute(self, sql, params=()): return _HostileCursor(self._r.execute(sql, params))
    def __getattr__(self, n): return getattr(self._r, n)

def test_nothing_depends_on_driver_column_names_or_lastrowid(tmp_path):
    con = db.connect(str(tmp_path / "h.db"), libsql=True); con._raw = _HostileRaw(con._raw)
    cid = db.add_category(con, "Test cat"); assert cid
    i = db.add_event(con, "Clippers", "2026-10-10", "2026-10-12")
    j = db.add_event(con, "Xmas", "2026-12-25", rule={"kind": "yearly_fixed", "month": 12, "day": 25})
    assert i and j and i != j
    assert db.get_event(con, j)["rule"] == {"kind": "yearly_fixed", "month": 12, "day": 25}
    assert [h["action"] for h in db.history(con)] == ["create", "create"] and db.history(con)[0]["at"]
    db.update_event(con, i, title="Clippers!"); assert db.undo_last(con).startswith("Undid update")
    assert db.get_event(con, i)["title"] == "Clippers" and db.category_id_by_name(con, "Test cat") == cid
    assert [e["title"] for e in db.events(con)] == ["Clippers", "Xmas"] and len(db.categories(con)) == 6
    db.set_setting(con, "k", {"a": 1}); assert db.get_setting(con, "k") == {"a": 1}
    db.decide_milestone(con, "m1", "rejected"); assert db.milestone_status(con) == {"m1": "rejected"}
    assert db.backup_bytes(con)[:15] == b"SQLite format 3"


def test_short_rows_are_padded_not_crashing():
    class Cur:
        def fetchall_tuples(self): return [(1, 2, 3)]
    class FakeCon:
        def execute(self, sql, params=()): return Cur()
    assert db._named(FakeCon(), "", (), ["a", "b", "c", "d"]) == [{"a": 1, "b": 2, "c": 3, "d": None}]

def test_diagnose_reports(con):
    db.add_event(con, "A", "2026-01-01"); txt = db.diagnose(con)
    assert "history rows" in txt and "lengths [7]" in txt


def test_moon_icons_only_on_principal_phases(con):
    """Each month page draws one moon icon per principal phase it shows, not one per day."""
    import calendar as cal
    drawn = []
    orig = R.moon_icon
    R.moon_icon = lambda *a, **k: drawn.append(1)
    try:
        R.render([], db.categories(con), 2026, [10], R.Options(details_page=False))
    finally: R.moon_icon = orig
    expected = sum(1 for wk in cal.Calendar(6).monthdatescalendar(2026, 10) for d in wk if astro.principal(d))
    assert len(drawn) == expected and 4 <= expected <= 6


def test_climate_data_uses_threaded_columbus_record():
    from calendar_core import climo
    assert climo.STATION == "CMHthr" and "CMHthr" in climo.MD_FILE and "CMHthr" in climo.STATS_FILE
    assert climo.stats()["_meta"]["station"] == "CMHthr"
    r = climo.day(D(2026, 7, 14)); assert (r["record_high"], r["record_high_year"]) == ("106", "1936")   # airport-only record is 104 (1954)
    r = climo.day(D(2026, 10, 31)); assert (r["record_low"], r["record_low_year"]) == ("20", "1887")      # airport-only record is 25 (1988)
    assert len(climo.table()) == 366 and climo.day(D(2024, 2, 29))["record_high"]


def test_climo_extremes_use_full_record_but_averages_use_1991_2020():
    from calendar_core import climo
    st = climo.stats(); assert "record" in st and st["_meta"]["record_start"] < "1890"
    m, early, late = climo.summary("first_snow_1in", 2026, st)
    assert (early[0], early[1]) == (D(2026, 10, 22), 1925)                    # earliest 1" snow on record
    rec = {k: v for k, v in st["record"]["first_snow_1in"].items()}; assert rec["1962"] == "1962-10-25"   # Oct 25, 1962 is in the record
    assert D(2026, 11, 25) < m < D(2026, 12, 25) and early[2] < 1900           # average still the 1991-2020 mean (~Dec 10)
    assert len(st["first_snow_1in"]) == 30 and len(st["record"]["first_snow_1in"]) > 100
    assert climo.summary("first_snow_meas", 2026, st)[1][0] == D(2026, 10, 10)      # Oct 10, 1906 (0.1 in)

def test_missing_data_years_are_excluded_from_record_extremes():
    from calendar_core import climo
    # season 1900: snow >=1in on Dec 20, but October-December snow data is mostly missing -> cannot say "first"
    D1 = [(D(1900, 10, 1) + dt.timedelta(days=i), 50, 40, None) for i in range(92)]
    D1 = [(d, mx, mn, 1.5 if d == D(1900, 12, 20) else None) for d, mx, mn, _ in D1]
    assert "first_snow_1in" not in climo.compute_series(D1, 1900, 1900, True, extras=False)
    full = [(d, mx, mn, 1.5 if d == D(1900, 12, 20) else 0.0) for d, mx, mn, _ in D1]
    assert climo.compute_series(full, 1900, 1900, True, extras=False)["first_snow_1in"] == {"1900": "1900-12-20"}

def test_old_climo_extremes_can_be_retired_and_reproposed(con):
    cands = {m["key"]: m for m in milestones.propose(2026)}
    assert "climo:first_snow_1in:rec_earliest:2026" in cands and "climo:first_snow_1in:earliest:2026" not in cands
    assert "on record (1925)" in cands["climo:first_snow_1in:rec_earliest:2026"]["title"]
    i = db.add_event(con, "Earliest first 1\" snow (1993)", "2026-10-30")
    db.decide_milestone(con, "climo:first_snow_1in:earliest:2026", "accepted", i)       # an entry from the old definition
    db.decide_milestone(con, "climo:first_snow_1in:avg:2026", "accepted", db.add_event(con, "Avg first 1\" snow", str(cands["climo:first_snow_1in:avg:2026"]["date"])))
    assert [e["id"] for _, e in db.outdated_climo_milestones(con)] == [i]
    assert db.retire_outdated_climo_milestones(con) == 1
    assert [e["title"] for e in db.events(con)] == ["Avg first 1\" snow"] and len(db.events(con, only_deleted=True)) == 1


def test_leap_year_dates_are_not_shifted():
    from calendar_core import climo
    st = climo.stats()
    assert st["record"]["last_snow_1in"]["1907"] == "1908-04-30" and st["record"]["last_freeze"]["2016"] == "2016-05-16"
    assert climo.summary("last_snow_1in", 2026, st)[2][0] == D(2026, 4, 30)        # Apr 30, 1908 (leap year) stays Apr 30
    assert climo.summary("last_freeze", 2026, st)[2][0] == D(2026, 5, 16)           # May 16, 2016 (leap year) stays May 16
    assert climo.summary("last_freeze", 2028, st)[2][0] == D(2028, 5, 16)
    assert climo.summary("last_freeze", 2026, st)[2][1] == 2016                      # May 16 also happened in 1959: tie shows the most recent year
    assert climo.place("last_freeze", 2026, 0) == D(2026, 1, 1) and climo.place("first_snow_1in", 2024, (D(2001, 2, 28) - D(2001, 7, 1)).days + 365) == D(2024, 2, 28)


# timeanddate.com's October 2026 table for Columbus (sunrise AM, sunset PM, length h:mm:ss), used as a reference
TD_RISE = "7:28 7:29 7:30 7:31 7:32 7:33 7:34 7:35 7:36 7:37 7:38 7:39 7:40 7:41 7:42 7:43 7:44 7:45 7:46 7:47 7:48 7:50 7:51 7:52 7:53 7:54 7:55 7:56 7:57 7:58 7:59".split()
TD_SET = "7:14 7:12 7:10 7:09 7:07 7:06 7:04 7:02 7:01 6:59 6:58 6:56 6:55 6:53 6:52 6:50 6:49 6:47 6:46 6:45 6:43 6:42 6:40 6:39 6:38 6:36 6:35 6:34 6:33 6:31 6:30".split()
TD_LEN = "11:45:46 11:43:10 11:40:34 11:37:58 11:35:23 11:32:48 11:30:13 11:27:38 11:25:04 11:22:29 11:19:56 11:17:22 11:14:49 11:12:17 11:09:44 11:07:13 11:04:42 11:02:11 10:59:41 10:57:12 10:54:43 10:52:15 10:49:48 10:47:21 10:44:56 10:42:31 10:40:07 10:37:44 10:35:22 10:33:01 10:30:41".split()

def test_sunrise_sunset_are_truncated_to_the_minute_like_nws_and_timeanddate():
    # NWS climate report: Oct 10 sunset is 6:59 PM (true time 6:59:52); USNO/NOAA GML round it to 7:00
    assert astro.sun_times(D(2026, 10, 10))[1] == "6:59"
    for i in range(31):          # every day of October 2026 matches timeanddate's table
        d = D(2026, 10, i + 1)
        assert astro.sun_times(d)[:2] == (TD_RISE[i], TD_SET[i]), d
        h, m, s = (int(x) for x in TD_LEN[i].split(":"))
        assert astro.daylight(d)[0] == f"{h}:{m:02d}", d
        sr, ss = astro.sun_pyephem(d); assert abs((ss - sr).total_seconds() - (h * 3600 + m * 60 + s)) <= 1.5

def test_matches_nws_climate_reports_for_columbus():
    """Every sunrise/sunset the NWS printed in its 2026 Columbus climate reports (342 values)."""
    nws = _fixture("nws_sun_2026.json")["data"]; miss = []
    for k, (r, s) in nws.items():
        d = D.fromisoformat(k); sr, ss = astro.sun_precise(d)
        for name, tm, want in (("rise", sr, r), ("set", ss, s)):
            if tm.hour * 60 + tm.minute != want: miss.append((k, name, tm.strftime("%H:%M:%S"), want))
    assert len(nws) > 150 and len(miss) <= 6, miss                       # 339 of 342 match today
    for k, name, tm, want in miss:                                       # a miss is only allowed within 2 s of a minute boundary
        sec = int(tm[-2:]); assert sec <= 2 or sec >= 58, (k, name, tm, want)


def test_normals_and_records_match_nws_climate_reports():
    """Normals round half-up like the NWS (ACIS rounds half to even: Mar 5 high 46.5 -> 47, not 46); records match the NWS."""
    from calendar_core import climo
    fx = _fixture("nws_climo_2026.json"); bad = []; n = 0
    for block in ("today", "day"):
        for k, r in fx[block].items():
            c = climo.day(D.fromisoformat(k)); n += 1
            got = (int(c["normal_high"]), int(c["normal_low"]), int(c["record_high"]), int(c["record_low"]))
            want = (r["norm_hi"], r["norm_lo"], r["rec_hi"], r["rec_lo"])
            if got[:2] != want[:2]: bad.append(("normal", k, got, want))
            if got[2:] != want[2:] and k != "2026-03-22": bad.append(("record", k, got, want))     # Mar 22: a record set after the report
    assert n > 450 and not bad, bad[:5]
    assert (climo.day(D(2026, 3, 5))["normal_high"], climo.day(D(2026, 2, 7))["normal_low"]) == ("47", "23")
    assert climo.half_up(46.5) == 47 and climo.half_up(47.5) == 48 and climo.half_up(28.8) == 29

def test_record_ties_keep_all_years():
    from calendar_core import climo
    c = climo.day(D(2026, 4, 19)); assert (c["record_high"], c["record_high_years"]) == ("85", "1958;2002")   # the NWS lists both years


# ------------------------------------------------------------------ holiday sets
def _on(title, year):
    from calendar_core import holidays
    for key, (_, _, items, _) in holidays.HOLIDAY_SETS.items():
        for t, rule in items:
            if t == title: return rc.dates_for_rule(rule, year)
    raise KeyError(title)

def test_easter_and_christian_holidays():
    assert [rc.easter(y) for y in (2024, 2025, 2026, 2027)] == [D(2024, 3, 31), D(2025, 4, 20), D(2026, 4, 5), D(2027, 3, 28)]
    assert [rc.easter(y, True) for y in (2024, 2025, 2026, 2027)] == [D(2024, 5, 5), D(2025, 4, 20), D(2026, 4, 12), D(2027, 5, 2)]
    assert _on("Mardi Gras", 2026) == [D(2026, 2, 17)] and _on("Easter", 2027) == [D(2027, 3, 28)] and _on("Orthodox Easter", 2027) == [D(2027, 5, 2)]
    assert _on("Christmas Eve", 2026) == [D(2026, 12, 24)] and _on("Christmas", 2026) == [D(2026, 12, 25)]
    from calendar_core import holidays
    assert [t for t, _ in holidays.CHRISTIAN] == ["Mardi Gras", "Easter", "Orthodox Easter", "Christmas Eve", "Christmas"]
    assert rc.dates_for_rule({"kind": "weekday_nearest", "month": 11, "day": 30, "weekday": 6}, 2026) == [D(2026, 11, 29)]   # rule kind still supported

def test_jewish_holidays_are_single_begins_markers_on_the_evening():
    from calendar_core import holidays
    assert [t for t, _ in holidays.JEWISH] == ["Purim begins", "Passover begins", "Rosh Hashanah begins", "Yom Kippur begins", "Hanukkah begins"]
    # the evening each holiday starts (the day before its first full day); exactly one date each
    assert _on("Rosh Hashanah begins", 2025) == [D(2025, 9, 22)] and _on("Yom Kippur begins", 2025) == [D(2025, 10, 1)]
    assert _on("Rosh Hashanah begins", 2026) == [D(2026, 9, 11)] and _on("Yom Kippur begins", 2026) == [D(2026, 9, 20)]
    assert _on("Rosh Hashanah begins", 2027) == [D(2027, 10, 1)] and _on("Yom Kippur begins", 2027) == [D(2027, 10, 10)]
    assert _on("Passover begins", 2025) == [D(2025, 4, 12)] and _on("Passover begins", 2026) == [D(2026, 4, 1)] and _on("Passover begins", 2027) == [D(2027, 4, 21)]
    assert _on("Hanukkah begins", 2025) == [D(2025, 12, 14)] and _on("Hanukkah begins", 2026) == [D(2026, 12, 4)] and _on("Hanukkah begins", 2027) == [D(2027, 12, 24)]
    assert _on("Purim begins", 2026) == [D(2026, 3, 2)] and _on("Purim begins", 2027) == [D(2027, 3, 22)] and _on("Purim begins", 2024) == [D(2024, 3, 23)]   # Adar II in leap years

def test_hanukkah_eve_appears_exactly_once_per_gregorian_year():
    rule = {"kind": "hebrew", "month": 9, "day": 25, "days": 1, "offset": -1}
    assert rc.dates_for_rule(rule, 2024) == [D(2024, 12, 25)] and rc.dates_for_rule(rule, 2025) == [D(2025, 12, 14)]
    for y in range(2020, 2060): assert len(rc.dates_for_rule(rule, y)) == 1          # exactly one Hanukkah eve per Gregorian year, none lost or doubled

def test_islamic_holidays_predicted_and_safe_outside_range():
    assert _on("Ramadan begins", 2025) == [D(2025, 3, 1)] and _on("Eid al-Fitr", 2025) == [D(2025, 3, 30)] and _on("Eid al-Adha", 2025) == [D(2025, 6, 6)]
    assert _on("Ramadan begins", 2026) == [D(2026, 2, 18)] and _on("Eid al-Fitr", 2026) == [D(2026, 3, 20)]
    assert _on("Eid al-Adha", 2026) == [D(2026, 5, 27)] and _on("Ramadan begins", 2027) == [D(2027, 2, 8)] and _on("Eid al-Fitr", 2027) == [D(2027, 3, 9)]
    new_year = {"kind": "islamic", "month": 1, "day": 1}
    assert rc.dates_for_rule(new_year, 2026) == [D(2026, 6, 16)] and len(rc.dates_for_rule(new_year, 2041)) == 2   # the lunar year is ~11 days short: a date can occur twice in a year
    assert _on("Eid al-Fitr", 2100) == [] and _on("Eid al-Fitr", 1900) == []     # outside the calendar's supported range: no crash

def test_load_holiday_sets_dedupes_flags_and_round_trips(con, tmp_path):
    first = db.load_holidays(con, ["federal", "christian"]); assert first == {"federal": 11, "christian": 4}      # Christmas only once
    assert db.load_holidays(con, ["federal", "christian"]) == {"federal": 0, "christian": 0}
    assert db.load_holidays(con, ["jewish", "muslim", "popular"]) == {"jewish": 5, "muslim": 3, "popular": 7}
    evs = {e["title"]: e for e in db.events(con)}
    assert len(evs) == 30 and sum(1 for e in db.events(con) if e["title"] == "Christmas") == 1
    assert evs["Eid al-Fitr"]["flag"] == "predicted date: confirm" and evs["Easter"]["flag"] is None and evs["Hanukkah begins"]["flag"] is None
    assert {e["title"] for e in db.events_on_day(con, D(2027, 3, 28))} == {"Easter"}
    assert {e["title"] for e in db.events_on_day(con, D(2026, 12, 4))} == {"Hanukkah begins"}
    assert not {e["title"] for e in db.events_on_day(con, D(2026, 12, 9))}                 # a marker, not a week-long bar
    for e in evs.values(): assert recurrence_describe(e["rule"])                    # every rule can be described for the editor
    c2 = db.connect(str(tmp_path / "copy.db")); assert importers.import_csv(c2, importers.export_csv(con)) == 30          # rules survive CSV export/import
    assert {e["title"] for e in db.events_on_day(c2, D(2026, 9, 20))} == {"Yom Kippur begins"}
    i = evs["Easter"]["id"]; db.update_event(con, i, rule=None); db.undo_last(con)                                    # undo restores a calculated rule
    assert db.get_event(con, i)["rule"]["kind"] == "easter_relative"

def test_retired_holiday_entries_can_be_moved_to_the_trash(con):
    from calendar_core import holidays
    for t, r in holidays.RETIRED.items(): db.add_event(con, t, "2026-01-01", None, rule=r)               # everything an earlier version created
    db.add_event(con, "Pentecost", "2026-05-24", None, rule={"kind": "yearly_fixed", "month": 5, "day": 24})   # a person's own rule with the same title: kept
    db.add_event(con, "Pentecost Sunday picnic", "2026-05-24")                       # a person's own event with a similar name: kept
    db.add_event(con, "Hanukkah", "2026-12-05", "2026-12-12")                        # a one-off the user typed (no rule): kept
    db.load_holidays(con, ["christian", "jewish", "muslim"])
    assert len(db.retired_holidays(con)) == len(holidays.RETIRED) == 24
    assert db.retire_holidays(con) == 24
    titles = [e["title"] for e in db.events(con)]
    assert titles.count("Pentecost") == 1 and "Pentecost Sunday picnic" in titles and titles.count("Hanukkah") == 1       # only the user's own ones remain
    assert "Hanukkah begins" in titles and "Easter" in titles and "Epiphany" not in titles and "Rosh Hashanah" not in titles
    assert len(db.events(con, only_deleted=True)) == 24 and db.retired_holidays(con) == []

def recurrence_describe(rule): return rc.describe(rule)

def test_holiday_months_render_without_dropping_events(con):
    from calendar_core import holidays
    db.load_holidays(con, list(holidays.HOLIDAY_SETS))
    for m in (3, 4, 9, 12):
        pdf, rep = R.render(db.events(con), db.categories(con), 2026, [m], R.Options(bw=(m % 2 == 0)))
        assert _pages(pdf) >= 1 and all(o["hidden"] < 6 for o in rep["overflow"])

def test_format_dates_compact():
    span = {"kind": "hebrew", "month": 9, "day": 25, "days": 8}; two = {"kind": "hebrew", "month": 7, "day": 1, "days": 2}
    assert rc.format_dates(rc.dates_for_rule(span, 2026)) == "Dec 5-12" and rc.format_dates(rc.dates_for_rule(two, 2026)) == "Sep 12-13"
    assert rc.format_dates([D(2026, 12, 30), D(2026, 12, 31), D(2027, 1, 1)]) == "Dec 30 - Jan 1" and rc.format_dates([D(2026, 4, 5)]) == "Apr 5"


def test_measurable_snow_series_and_means_match_xmacis_table():
    """The xmACIS First/Last Summary for Columbus Area (measurable snow, 1991-2020): all 60 dates plus min/mean/max."""
    from calendar_core import climo
    fx = _fixture("xmacis_snow_meas_1991_2020.json"); st = climo.stats()
    first, last = st["first_snow_meas"], st["last_snow_meas"]       # first keyed by the season's start year; last keyed by season (spring is the next year)
    assert len(first) == len(last) == 30
    for y, row in fx["rows"].items():
        assert first[y][5:] == row["first"], ("first", y, first[y], row["first"])
        assert last[str(int(y) - 1)][5:] == row["last"], ("last", y, last[str(int(y) - 1)], row["last"])
    mean_first, early, late = climo.summary("first_snow_meas", 2026, st)
    assert (f"{mean_first:%m-%d}", f"{climo.summary('last_snow_meas', 2026, st)[0]:%m-%d}") == (fx["summary"]["first"]["mean"], fx["summary"]["last"]["mean"])   # 11-23 and 03-27
    # min/max over the 1991-2020 series only (the app's earliest/latest use the full record)
    offs = lambda k: sorted(climo._offsets(k, st[k]), key=lambda t: t[0])
    assert (f"{offs('first_snow_meas')[0][1]:%m-%d}", f"{offs('first_snow_meas')[-1][1]:%m-%d}") == ("10-30", "01-10")
    assert (f"{offs('last_snow_meas')[0][1]:%m-%d}", f"{offs('last_snow_meas')[-1][1]:%m-%d}") == ("02-16", "04-24")

def test_mean_date_drops_the_fraction_of_a_day():
    from calendar_core import climo
    st = {"first_freeze": {"2000": "2000-10-01", "2001": "2001-10-02", "2002": "2002-10-02"}}      # offsets 273, 274, 274 -> mean 273.67
    mean = climo.summary("first_freeze", 2026, st)[0]; assert mean == D(2026, 10, 1)             # Oct 1.67 -> Oct 1, not Oct 2


def test_stale_accepted_average_is_flagged_only_when_its_date_changed(con):
    from calendar_core import milestones
    cands = {m["key"]: m for m in milestones.propose(2026)}
    good, stale = cands["climo:last_snow_meas:avg:2026"], cands["climo:first_snow_meas:avg:2026"]
    assert str(stale["date"]) == "2026-11-23"
    milestones.accept(con, good)                                                       # accepted with the current date
    i = db.add_event(con, stale["title"], "2026-11-24"); db.decide_milestone(con, stale["key"], "accepted", i)     # accepted under the old rounding (Nov 24)
    assert [(k, e["start_date"]) for k, e in db.outdated_climo_milestones(con)] == [("climo:first_snow_meas:avg:2026", "2026-11-24")]
    assert db.retire_outdated_climo_milestones(con) == 1
    pending = {m["key"] for m in milestones.pending(con, 2026)}
    assert "climo:first_snow_meas:avg:2026" in pending and "climo:last_snow_meas:avg:2026" not in pending      # re-proposed; the good one stays accepted
    assert [e["title"] for e in db.events(con)] == [good["title"]]


# --------------------------------------------------------- American Meteor Society calendar
def _ams_cards():
    import os
    return open(os.path.join(os.path.dirname(__file__), "fixtures", "ams_calendar_cards.html")).read()

def test_ams_calendar_parse():
    from calendar_core import meteors
    s = {x["slug"]: x for x in meteors.parse_calendar(_ams_cards())}
    assert len(s) == 12 and list(s)[:2] == ["orionids", "southern_taurids"]
    o = s["orionids"]; assert (o["start"], o["end"], o["moon_pct"], o["moon_phase"]) == ("2026-10-21", "2026-10-22", 74, "Waxing gibbous")
    assert (s["geminids"]["start"], s["geminids"]["end"]) == ("2026-12-13", "2026-12-14") and s["geminids"]["moon_pct"] == 15
    q = s["quadrantids"]; assert (q["start"], q["end"]) == ("2027-01-03", "2027-01-04")           # year comes from the peak night itself, not the Dec 2026 activity start
    assert s["lyrids"]["moon_phase"] == "Full moon" and s["lyrids"]["moon_pct"] == 100 and s["perseids"]["start"] == "2027-08-12"
    assert "eta_aquariids" in s and "southern_delta_aquariids" in s and s["eta_aquariids"]["name"] == "Eta Aquariids"
    assert meteors.slug("η Aquariids") == "eta_aquariids" and meteors.slug("Southern δ-Aquariids") == "southern_delta_aquariids"

def test_ams_peak_across_a_month_and_year_boundary():
    from calendar_core import meteors
    card = lambda peak: ('<article id="x" class="shower-card"><div class="shower-card__date"><div class="shower-card__date_title">PEAK NIGHT</div>Dec 31–Jan 1</div>'
                         f'<h2 class="shower-card__name">Test Shower</h2><p>The Moon will be 50 % illuminated · First quarter on peak night ( {peak} ).</p></article>')
    for peak in ("Dec 31 – Jan 1, 2027", "Dec 31, 2026 – Jan 1, 2027"):          # the year belongs to the end date, or both years are spelled out
        [s] = meteors.parse_calendar(card(peak)); assert (s["start"], s["end"]) == ("2026-12-31", "2027-01-01"), peak
    [s] = meteors.parse_calendar(card("Jan 3–4, 2027")); assert (s["start"], s["end"]) == ("2027-01-03", "2027-01-04")
    shows, skipped = meteors.parse_calendar_with_skips(card("Oct 3-4, 2027") + card("sometime in October").replace("Test Shower", "Odd Shower"))
    assert [x["name"] for x in shows] == ["Test Shower"] and skipped == ["Odd Shower"]         # an unreadable card is reported, not silently dropped
    assert meteors.parse_calendar("<html>no cards here</html>") == []

def test_ams_fetch_refuses_a_changed_layout_and_keeps_the_old_cache(tmp_path, monkeypatch):
    from calendar_core import meteors, paths, store
    monkeypatch.setattr(paths, "CACHE", str(tmp_path / "cache")); store._mem.clear()
    class Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body.encode()
    monkeypatch.setattr(meteors.urllib.request, "urlopen", lambda req, timeout=0: Resp(_ams_cards()))
    assert meteors.fetch() == 12 and meteors.cached()["showers"][0]["slug"] == "orionids"
    monkeypatch.setattr(meteors.urllib.request, "urlopen", lambda req, timeout=0: Resp("<html><body>redesigned</body></html>"))
    try: meteors.fetch(); raise AssertionError("should have refused")
    except ValueError as e: assert "layout" in str(e)
    assert len(meteors.cached()["showers"]) == 12                                       # the good copy is still there

def test_meteor_milestones_prefer_ams_then_fall_back_to_typical():
    from calendar_core import milestones
    m26 = {r["key"]: r for r in milestones.propose(2026) if r["key"].startswith("meteor:")}
    o = m26["meteor:orionids:2026"]; assert (o["date"], o["end"]) == (D(2026, 10, 21), D(2026, 10, 22)) and "American Meteor Society" in o["note"] and "TYPICAL" not in o["note"]
    assert "74% illuminated" in o["note"] and o["title"] == "Orionids meteor shower peak"
    assert (m26["meteor:geminids:2026"]["date"], m26["meteor:geminids:2026"]["end"]) == (D(2026, 12, 13), D(2026, 12, 14))
    assert "meteor:southern_taurids:2026" in m26 and "meteor:northern_taurids:2026" in m26                      # AMS showers beyond the typical list
    p = m26["meteor:perseids:2026"]; assert p["date"] == D(2026, 8, 12) and p["end"] is None and "TYPICAL" in p["note"]      # past, outside AMS's window
    m27 = {r["key"]: r for r in milestones.propose(2027) if r["key"].startswith("meteor:")}
    assert m27["meteor:quadrantids:2027"]["date"] == D(2027, 1, 3) and m27["meteor:perseids:2027"]["end"] == D(2027, 8, 13) and "American" in m27["meteor:perseids:2027"]["note"]
    assert "TYPICAL" in m27["meteor:leonids:2027"]["note"] and "TYPICAL" in m27["meteor:geminids:2027"]["note"]      # Nov/Dec 2027 not yet on AMS's page
    assert len([k for k in m27 if k.startswith("meteor:orionids")]) == 1                                         # a shower is never proposed twice

def test_accepting_a_meteor_peak_makes_a_two_night_bar_and_old_entries_are_flagged(con):
    from calendar_core import milestones
    cands = {m["key"]: m for m in milestones.propose(2026)}
    eid = milestones.accept(con, cands["meteor:geminids:2026"]); e = db.get_event(con, eid)
    assert (e["start_date"], e["end_date"], e["category"]) == ("2026-12-13", "2026-12-14", "Sky / Astronomy")
    assert {x["title"] for x in db.events_on_day(con, D(2026, 12, 14))} == {"Geminids meteor shower peak"} and not db.outdated_climo_milestones(con)
    # an entry accepted earlier from the typical date (a single day, Dec 14) is now stale
    old = db.add_event(con, "Orionids meteor shower peak", "2026-10-21"); db.decide_milestone(con, "meteor:orionids:2026", "accepted", old)
    assert [(k, x["start_date"]) for k, x in db.outdated_climo_milestones(con)] == [("meteor:orionids:2026", "2026-10-21")]
    assert db.retire_outdated_climo_milestones(con) == 1
    assert "meteor:orionids:2026" in {m["key"] for m in milestones.pending(con, 2026)} and "meteor:geminids:2026" not in {m["key"] for m in milestones.pending(con, 2026)}
    pdf, rep = R.render(db.events(con), db.categories(con), 2026, [12], R.Options(details_page=False)); assert _pages(pdf) == 1
