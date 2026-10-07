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

def test_dst_transition_days_and_usno_vs_ephem():
    assert astro.sun_times(D(2026, 10, 31))[:2] == ("8:00", "6:31") and astro.sun_times(D(2026, 11, 1))[:2] == ("7:01", "5:30")
    worst = 0
    for k, v in astro.usno_data(2026).items():
        d = D.fromisoformat(k); sr, ss = astro.sun_ephem(d)
        h = lambda s: int(s[:2]) * 60 + int(s[3:])
        worst = max(worst, abs(h(v["rise"]) - (sr.hour * 60 + sr.minute + sr.second / 60)), abs(h(v["set"]) - (ss.hour * 60 + ss.minute + ss.second / 60)))
    assert len(astro.usno_data(2026)) == 365 and worst < 1.0

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
    assert store.load_text("astro_usno_2026.json")            # bundled reference file is the fallback
    # database mode: same API, backed by the cache_files table (libsql local file stands in for Turso)
    c = db.connect(str(tmp_path / "remote.db"), libsql=True)
    monkeypatch.setattr(store, "_remote", lambda: True); monkeypatch.setattr(db, "connect", lambda *a, **k: c)
    store._mem.clear(); store.write("y.json", '{"b": 2}'); assert store.load_json("y.json") == {"b": 2} and store.has_cached("y.json")
    store.write("y.json", '{"b": 3}'); store._mem.clear(); assert store.load_json("y.json") == {"b": 3}
