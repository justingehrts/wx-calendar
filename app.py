import datetime as dt, json, os, hmac
import pandas as pd
import streamlit as st
from calendar_core import astro, climo, db, ical, importers, milestones, patterns, preview, recurrence, render_pdf as R

st.set_page_config(page_title="Weathercast Planning Calendar", layout="wide")
APP_VERSION = "2026-10-10a"

# Hosted database settings may come from Streamlit secrets; the storage layer reads the environment.
for _k in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
    try:
        if _k in st.secrets: os.environ.setdefault(_k, str(st.secrets[_k]))
    except Exception: pass

# ------------------------------------------------------------------ passcode
def passcode():
    try: return st.secrets["passcode"]
    except Exception: return os.environ.get("CALENDAR_PASSCODE")

def gate():
    code = passcode()
    if not code:
        st.error("No passcode configured. Set `passcode` in Streamlit secrets or the CALENDAR_PASSCODE environment variable.")
        st.stop()
    if st.session_state.get("ok"): return
    with st.form("login"):
        p = st.text_input("Passcode", type="password")
        if st.form_submit_button("Enter"):
            if hmac.compare_digest(p.encode(), code.encode()): st.session_state["ok"] = True; st.rerun()
            st.error("Wrong passcode")
    st.stop()

gate()
con = db.connect()
if not db.turso_config() and os.path.abspath(__file__).startswith("/mount/src"):
    st.error("This app is running on Streamlit Community Cloud without a hosted database. Anything you enter will be LOST "
             "on the next restart. Add TURSO_DATABASE_URL and TURSO_AUTH_TOKEN to the app's secrets (see the README).")
cats = db.categories(con)
cat_names = [c["name"] for c in cats]
cat_by_name = {c["name"]: c for c in cats}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# ------------------------------------------------------------------- sidebar
today = dt.date.today()
with st.sidebar:
    st.header("Print options")
    month = st.selectbox("Month", range(1, 13), today.month - 1, format_func=lambda m: MONTHS[m - 1])
    year = st.number_input("Year", 2020, 2100, today.year)
    st.caption("Location: Columbus, OH (39.9612 N, 82.9988 W). Times are Eastern.")
    st.subheader("Show on each day")
    o_sun = st.checkbox("Sunrise / sunset", True); o_day = st.checkbox("Daylight length and change", True)
    o_moon = st.checkbox("Moon phases (new, quarters, full)", True); o_nrm = st.checkbox("Normal high/low", True)
    o_rec = st.checkbox("Record high/low", True); o_notes = st.checkbox("Notes boxes at bottom", True)
    o_det = st.checkbox("Details page (second page)", True)
    st.subheader("Page")
    bw = st.radio("Printer", ["Color", "Black & white"], horizontal=True) == "Black & white"
    gray_prev = st.checkbox("Grayscale preview", value=bw, disabled=bw, help="Shows what a B&W printer makes of the color page.")
    compact = st.checkbox("Smaller bars (fit more per day)", False)
    week_start = 6 if st.selectbox("Week starts on", ["Sunday", "Monday"]) == "Sunday" else 0
    paper = st.selectbox("Paper", ["letter", "a4"], format_func=lambda p: {"letter": "US Letter", "a4": "A4"}[p])
    opts = R.Options(sun=o_sun, moon=o_moon, normals=o_nrm, records=o_rec, daylight=o_day, notes=o_notes, bw=bw,
                     details_page=o_det, week_start=week_start, paper=paper, compact=compact)
    year = int(year)
    st.divider()
    b1, b2 = st.columns(2)
    if b1.button("Generate PDF", type="primary"):
        pdf, rep = R.render(db.events(con), cats, year, [month], opts)
        st.session_state["pdf"] = (f"Calendar_{year}_{month:02d}.pdf", pdf)
    if b2.button("All 12 months"):
        pdf, rep = R.render(db.events(con), cats, year, range(1, 13), opts)
        st.session_state["pdf"] = (f"Calendar_{year}.pdf", pdf)
    if "pdf" in st.session_state:
        st.download_button(f"Download {st.session_state['pdf'][0]}", st.session_state["pdf"][1], st.session_state["pdf"][0], "application/pdf")
    st.divider()
    st.caption(f"App version {APP_VERSION}  |  storage: {'hosted database' if db.turso_config() else 'local file'}")
    st.caption("Sunrise/sunset: NOAA solar-calculator algorithm, truncated to the minute like the NWS climate report; moon: PyEphem; normals (1991-2020) and records: RCC-ACIS, Columbus Area (threaded record, CMHthr).")

tab_events, tab_cats, tab_ms, tab_hist, tab_set = st.tabs(["Events", "Categories", "Milestones", "History & trash", "Settings"])

# -------------------------------------------------------------------- events
def snapshot():
    evs = db.events(con); st.session_state["snap"] = evs; st.session_state["snap_v"] = st.session_state.get("snap_v", 0) + 1

def repeat_text(e): return recurrence.describe(e["rule"]) if e["rule"] else ""

with tab_events:
    if "snap" not in st.session_state: snapshot()
    left, right = st.columns([3, 2])
    with left:
        snap = st.session_state["snap"]; ver = st.session_state["snap_v"]
        df = pd.DataFrame([{"date": dt.date.fromisoformat(e["start_date"]),
                            "through": dt.date.fromisoformat(e["end_date"]) if e["end_date"] else None,
                            "title": e["title"], "category": e["category"], "repeats": repeat_text(e), "note": e["flag"] or ""}
                           for e in snap], columns=["date", "through", "title", "category", "repeats", "note"])
        st.caption("Edit directly, add rows at the bottom, or select rows and press Delete (deleted events go to the trash). Repeating events show their rule under 'repeats'.")
        st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"ed{ver}",
                       disabled=["repeats", "note"],
                       column_config={"date": st.column_config.DateColumn(required=True, help="First date (repeating events: see the rule editor)"),
                                      "through": st.column_config.DateColumn(), "title": st.column_config.TextColumn(required=True),
                                      "category": st.column_config.SelectboxColumn(options=cat_names)})
        c1, c2, c3 = st.columns(3)
        if c1.button("Save changes", type="primary"):
            state = st.session_state.get(f"ed{ver}", {}); conflicts = 0
            def conv(k, v):
                if k == "category": return "category_id", (cat_by_name[v]["id"] if v in cat_by_name else None)
                if k == "date": return "start_date", v
                if k == "through": return "end_date", (v if v and v != "" else None)
                return k, v
            for idx, ch in state.get("edited_rows", {}).items():
                row = snap[int(idx)]
                fields = dict(conv(k, v) for k, v in ch.items() if k in ("date", "through", "title", "category"))
                if "category_id" in fields and fields["category_id"] is None: fields.pop("category_id")
                if "title" in fields and not fields["title"]: fields.pop("title")
                if not db.update_event(con, row["id"], expect_updated_at=row["updated_at"], **fields): conflicts += 1
            for idx in state.get("deleted_rows", []): db.delete_event(con, snap[int(idx)]["id"])
            for r in state.get("added_rows", []):
                if r.get("title") and r.get("date"):
                    cid = cat_by_name[r["category"]]["id"] if r.get("category") in cat_by_name else None
                    db.add_event(con, r["title"], r["date"], r.get("through"), cid)
            snapshot()
            if conflicts: st.session_state["msg"] = ("warning", f"{conflicts} edit(s) skipped: someone else changed that event first. Their version is shown now; redo your edit if needed.")
            else: st.session_state["msg"] = ("success", "Saved")
            st.rerun()
        if c2.button("Reload from database"): snapshot(); st.rerun()
        if c3.button("Undo last change"):
            m = db.undo_last(con); snapshot(); st.session_state["msg"] = ("info", m or "Nothing to undo"); st.rerun()
        if "msg" in st.session_state:
            kind, text = st.session_state.pop("msg"); getattr(st, kind)(text)

        with st.expander("Event details and repeat rules"):
            labels = {e["id"]: f"{e['start_date']}  {e['title']}" for e in snap}
            eid = st.selectbox("Event", list(labels), format_func=labels.get, index=None, placeholder="Choose an event to edit…")
            if eid:
                e = db.get_event(con, eid)
                with st.form(f"detail{eid}"):
                    t = st.text_input("Title", e["title"])
                    d1, d2 = st.columns(2)
                    s = d1.date_input("Date", dt.date.fromisoformat(e["start_date"]))
                    f = d2.date_input("Through (optional)", dt.date.fromisoformat(e["end_date"]) if e["end_date"] else None)
                    cat = st.selectbox("Category", cat_names, cat_names.index(e["category"]) if e["category"] in cat_names else 0)
                    tm, loc = st.columns(2)
                    time_ = tm.text_input("Time", e["time"] or ""); loc_ = loc.text_input("Location", e["location"] or "")
                    notes = st.text_area("Notes", e["notes"] or ""); url = st.text_input("Link", e["url"] or "")
                    donly = st.checkbox("Details page only (lower priority: keep off the calendar grid)", bool(e["detail_only"]))
                    st.markdown("**Repeat**")
                    rule = e["rule"] or {"kind": "one_off"}
                    kind = st.selectbox("Repeats", recurrence.KINDS, recurrence.KINDS.index(rule["kind"]),
                                        format_func=lambda k: {"one_off": "Does not repeat", "yearly_fixed": "Every year on a fixed date",
                                                               "yearly_nth_weekday": "Every year on the nth weekday of a month",
                                                               "weekly_in_range": "Certain weekdays between two dates (each year)",
                                                               "lookup_by_year": "Listed dates per year", "yearly_relative": "Days from another rule"}[k])
                    p = {"kind": kind}
                    r1, r2, r3 = st.columns(3)
                    if kind == "yearly_fixed":
                        p["month"] = r1.number_input("Month", 1, 12, rule.get("month", s.month)); p["day"] = r2.number_input("Day", 1, 31, rule.get("day", s.day))
                    elif kind == "yearly_nth_weekday":
                        p["month"] = r1.number_input("Month", 1, 12, rule.get("month", s.month))
                        p["weekday"] = r2.selectbox("Weekday", range(7), rule.get("weekday", s.weekday()), format_func=lambda i: recurrence.WEEKDAYS[i])
                        p["n"] = r3.selectbox("Which", [1, 2, 3, 4, -1], [1, 2, 3, 4, -1].index(rule.get("n", 1)), format_func=lambda n: "last" if n == -1 else str(n))
                    elif kind == "weekly_in_range":
                        p["weekdays"] = r1.multiselect("Weekdays", range(7), rule.get("weekdays", []), format_func=lambda i: recurrence.WEEKDAYS[i])
                        p["start"] = r2.date_input("From", dt.date.fromisoformat(rule["start"]) if "start" in rule else s).isoformat()
                        p["end"] = r3.date_input("To", dt.date.fromisoformat(rule["end"]) if "end" in rule else (f or s)).isoformat()
                    elif kind == "lookup_by_year":
                        txt = st.text_area("One line per year: YEAR: YYYY-MM-DD, YYYY-MM-DD", "\n".join(f"{y}: {', '.join(v)}" for y, v in rule.get("table", {}).items()))
                        p["table"] = {l.split(":")[0].strip(): [x.strip() for x in l.split(":", 1)[1].split(",") if x.strip()] for l in txt.splitlines() if ":" in l}
                    elif kind == "yearly_relative":
                        st.info("Edit the base rule's dates by choosing its kind above, then offset it.")
                        p["offset"] = r1.number_input("Offset (days)", -400, 400, rule.get("offset", 0)); p["base"] = rule.get("base", {"kind": "yearly_fixed", "month": s.month, "day": s.day})
                    if kind != "one_off":
                        try: st.caption("Next 3 occurrences: " + ", ".join(d.strftime("%a %b %d, %Y") for d in recurrence.next_occurrences(p, today)) or "none")
                        except Exception as ex: st.caption(f"Cannot preview this rule yet: {ex}")
                    if st.form_submit_button("Save event", type="primary"):
                        ok = db.update_event(con, eid, expect_updated_at=e["updated_at"], title=t, start_date=s.isoformat(),
                                             end_date=f.isoformat() if f and f != s else None, category_id=cat_by_name[cat]["id"],
                                             time=time_ or None, location=loc_ or None, notes=notes or None, url=url or None,
                                             detail_only=int(donly), rule=None if kind == "one_off" else p)
                        snapshot(); st.session_state["msg"] = ("success", "Saved") if ok else ("warning", "Someone else changed this event first; reloaded."); st.rerun()
        with st.expander("Import / export"):
            st.download_button("Export all events (CSV)", importers.export_csv(con), "events.csv", "text/csv")
            up = st.file_uploader("Import CSV", type="csv")
            if up and st.button("Import CSV file"):
                n = importers.import_csv(con, up.getvalue().decode("utf-8-sig")); snapshot(); st.session_state["msg"] = ("success", f"Added {n} events"); st.rerun()
            xl = st.file_uploader("Import the legacy Excel calendar (Content_Idea_Calendar.xlsx)", type="xlsx")
            if xl and st.button("Import Excel file"):
                n = importers.import_workbook(con, xl, year); snapshot()
                st.session_state["msg"] = ("success", f"Added {n} events for {year}. Please review the categories, and items marked 'could be auto-generated' (see Milestones)."); st.rerun()
    with right:
        st.subheader(f"{MONTHS[month - 1]} {year}")
        pdf, rep = R.render(db.events(con), cats, year, [month], opts)
        pages = preview.pdf_to_pngs(pdf, 1.5, grayscale=gray_prev and not bw or False)
        st.image(pages[0], width="stretch")
        for m in R.overflow_messages(rep): st.warning(f"{m}. Shorten a title, mark one 'details page only', or tick 'Smaller bars'.")
        if rep["truncated"]: st.info("Shortened on the page (full title on the details page): " + "; ".join(sorted({t for _, t in rep["truncated"]})))
        st.download_button("Download this month as PNG", preview.pdf_to_pngs(pdf, 3.0, grayscale=False)[0], f"Calendar_{year}_{month:02d}.png", "image/png")
        st.download_button(f"Download {year} as iCal (.ics)", ical.export_ics(db.events(con), cats, year), f"Calendar_{year}.ics", "text/calendar")

# ---------------------------------------------------------------- categories
with tab_cats:
    counts = db.category_counts(con, year, month)
    st.caption(f"Event counts are for {MONTHS[month - 1]} {year}. Each category has a color (for color printing) and a black-and-white style (for the laser printer).")
    for c in cats:
        with st.form(f"cat{c['id']}"):
            a, b, s_, k = st.columns([2, 1, 2, 3])
            name = a.text_input("Name", c["name"]); color = b.color_picker("Color", c["color_hex"])
            style = s_.selectbox("B&W style", list(patterns.STYLES), list(patterns.STYLES).index(c["bw_style"]), format_func=patterns.STYLES.get)
            kw = k.text_input("Auto-category keywords (comma separated)", c["keywords"])
            ratio = patterns.white_text_contrast(color)
            st.caption(f"{counts.get(c['id'], 0)} event(s) this month  |  white-text contrast on this color: {ratio:.1f}:1 "
                       + ("OK" if ratio >= 4.5 else "**too low (below 4.5:1): darken the color**"))
            x1, x2, x3 = st.columns([1, 2, 1])
            save = x1.form_submit_button("Save")
            others = [n for n in cat_names if n != c["name"]]
            move = x2.selectbox("If deleting, move its events to", others, key=f"mv{c['id']}")
            dele = x3.form_submit_button("Delete category")
            if save:
                db.update_category(con, c["id"], name=name, color_hex=color, bw_style=style, keywords=kw); st.rerun()
            if dele and others:
                db.delete_category(con, c["id"], cat_by_name[move]["id"]); snapshot(); st.rerun()
    with st.form("newcat"):
        st.markdown("**Add a category**"); a, b, s_ = st.columns([3, 1, 2])
        n_ = a.text_input("Name"); col_ = b.color_picker("Color", "#444444")
        st_ = s_.selectbox("B&W style", list(patterns.STYLES), 2, format_func=patterns.STYLES.get)
        if st.form_submit_button("Add") and n_.strip():
            try: db.add_category(con, n_.strip(), col_, st_); st.rerun()
            except Exception as ex: st.error(str(ex))
    for style, names in patterns.style_collisions(cats):
        st.warning(f"These categories share the B&W style “{patterns.STYLES[style]}” and will look the same on a B&W printer: {', '.join(names)}.")
    p1, p2 = st.columns(2)
    p1.markdown("**Color print**"); p1.image(preview.pdf_to_pngs(R.legend_preview(cats, False), 2)[0])
    p2.markdown("**Black & white print**"); p2.image(preview.pdf_to_pngs(R.legend_preview(cats, True), 2)[0])

# ---------------------------------------------------------------- milestones
with tab_ms:
    old = db.outdated_climo_milestones(con)
    if old:
        st.warning(f"{len(old)} accepted climo entr{'y was' if len(old) == 1 else 'ies were'} calculated from 1991-2020 only, so the "
                   "\"earliest/latest\" dates are wrong (e.g. the earliest 1\" snow is not Oct 30). Corrected versions use the full record: "
                   + "; ".join(f"{e['title']} ({e['start_date']})" for _, e in old))
        if st.button("Move these to the trash and propose corrected versions"):
            n = db.retire_outdated_climo_milestones(con); snapshot()
            st.session_state["msg"] = ("success", f"Moved {n} event(s) to the trash (restorable). Corrected proposals are below."); st.rerun()
    st.caption(f"Proposed entries for {year}: sun, sky, DST and climate milestones. Accept to add to the calendar; rejected ones do not come back. "
               "Climo averages are mean dates over 1991-2020 and earliest/latest are over the full record (about 1880 on) at Columbus Area (CMHthr): last/first 32° freeze (min temp), 80°/90° days (max temp), measurable (≥0.1\") and ≥1\" snowfall.")
    pend = milestones.pending(con, year)
    if not pend: st.success("Nothing pending for this year.")
    else:
        groups = {"Sun and sky": lambda r: r["key"].startswith(("sun:", "dst:")), "Meteor showers": lambda r: r["key"].startswith("meteor:"), "Climo": lambda r: r["key"].startswith("climo:")}
        pick = st.multiselect("Show", list(groups), list(groups))
        rows = [r for r in pend if any(groups[g](r) for g in pick)]
        mdf = pd.DataFrame([{"decision": "", "date": r["date"], "title": r["title"], "category": r["category"], "note": r["note"]} for r in rows])
        ed = st.data_editor(mdf, hide_index=True, width="stretch", disabled=["date", "title", "category", "note"], key=f"ms{year}{len(pend)}",
                            column_config={"decision": st.column_config.SelectboxColumn(options=["", "Accept", "Reject"])})
        if st.button("Apply decisions", type="primary"):
            n = 0
            for i, r in ed.iterrows():
                if r["decision"] == "Accept": milestones.accept(con, rows[i]); n += 1
                elif r["decision"] == "Reject": milestones.reject(con, rows[i]); n += 1
            snapshot(); st.session_state["msg"] = ("success", f"Applied {n} decision(s)"); st.rerun()
    flagged = [e for e in db.events(con) if e["flag"]]
    if flagged:
        with st.expander(f"{len(flagged)} imported event(s) that could be auto-generated"):
            st.dataframe(pd.DataFrame([{"date": e["start_date"], "title": e["title"]} for e in flagged]), hide_index=True)
            st.caption("These typed entries are things the app can now calculate. Compare with the proposals above, then delete the typed versions you don't need.")

# ---------------------------------------------------------- history & trash
with tab_hist:
    try:
        h1, h2 = st.columns(2)
        with h1:
            st.subheader("Recent changes")
            if st.button("Undo last change", key="undo2"):
                m = db.undo_last(con); snapshot(); st.session_state["msg"] = ("info", m or "Nothing to undo"); st.rerun()
            hist = db.history(con, 100)
            st.dataframe(pd.DataFrame([{"when": str(h.get("at") or "").replace("T", " "), "action": str(h.get("action") or "?") + (" (undone)" if h.get("undone") else ""), "event": h.get("title")} for h in hist],
                                      columns=["when", "action", "event"]), hide_index=True, width="stretch")
        with h2:
            st.subheader("Trash")
            trash = db.events(con, only_deleted=True)
            if not trash: st.caption("Trash is empty.")
            for e in trash:
                a_, b_ = st.columns([4, 1])
                a_.write(f"{e['start_date']}  {e['title']}  _(deleted {str(e['deleted_at'])[:16].replace('T', ' ')})_")
                if b_.button("Restore", key=f"rs{e['id']}"): db.restore_event(con, e["id"]); snapshot(); st.rerun()
    except Exception as ex:      # never let this tab take down the whole page
        if type(ex).__name__ in ("RerunException", "StopException"): raise
        st.error(f"The history view failed ({type(ex).__name__}: {ex}). The rest of the app still works. "
                 "Please send the details below to whoever maintains this app.")
        st.code(db.diagnose(con))

# ------------------------------------------------------------------ settings
with tab_set:
    st.subheader("Data for " + str(year))
    st.write("Sunrise/sunset are calculated with NOAA's solar-calculator algorithm (upper limb of the Sun, standard refraction) and printed "
             "**truncated to the whole minute**, matching the NWS climate report. There is nothing to download: it works for any year.")
    st.write(f"Climate normals/records: {'loaded' if climo.table() else 'missing'}; 1991-2020 statistics: {'loaded' if climo.stats() else 'missing'}")
    if st.button("Refresh normals, records and statistics from RCC-ACIS"):
        try: climo.fetch_normals_records(); climo.fetch_stats(); st.success("Climate data refreshed.")
        except Exception as ex: st.error(f"ACIS fetch failed: {ex}")
    st.divider(); st.subheader("Holidays")
    if st.button("Add the U.S. federal holidays (as repeating events)"):
        n = db.load_federal_holidays(con); snapshot(); st.success(f"Added {n} holiday(s)." if n else "They are all already there.")
    st.caption("They appear in the Holidays category; edit or delete any of them in the Events tab.")
    st.divider(); st.subheader(f"Prepare {year + 1}")
    st.write("Repeating events (holidays and other rules) carry forward automatically. One-time events from "
             f"{year} are listed here to keep, move, or drop. Nothing is deleted.")
    miss = db.lookup_rules_missing(con, year + 1)
    if miss: st.warning("These events list dates per year and have no dates for " + str(year + 1) + ": " + ", ".join(e["title"] for e in miss))
    oo = db.one_offs(con, year)
    if oo:
        rdf = pd.DataFrame([{"keep": False, "title": e["title"], "date": dt.date.fromisoformat(db.shift_year(e["start_date"], 1)),
                             "through": dt.date.fromisoformat(db.shift_year(e["end_date"], 1)) if e["end_date"] else None, "id": e["id"]} for e in oo])
        red = st.data_editor(rdf, hide_index=True, width="stretch", disabled=["title"], column_config={"id": None}, key=f"roll{year}")
        if st.button(f"Create {year + 1} copies of the checked events"):
            items = [(int(r["id"]), r["date"].isoformat(), r["through"].isoformat() if pd.notna(r["through"]) and r["through"] else None) for _, r in red.iterrows() if r["keep"]]
            n = db.carry_forward(con, items); snapshot(); st.success(f"Created {n} event(s) in {year + 1}.")
    else: st.caption("No one-time events in " + str(year) + ".")
    st.divider(); st.subheader("Backup")
    st.write("Data storage: **" + ("hosted Turso database" if db.turso_config() else "local file on this server") + "**")
    st.download_button("Download a copy of the database", db.backup_bytes(con), "calendar_backup.db", "application/octet-stream")
    st.caption("On the hosted app, nightly backups run automatically (see README); this is an extra manual copy.")
