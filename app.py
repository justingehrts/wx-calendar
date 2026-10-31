import datetime as dt, json, os, hmac
import pandas as pd
import streamlit as st
from calendar_core import astro, climo, db, holidays, ical, importers, meteors, milestones, patterns, preview, recurrence, regional, views, render_pdf as R

st.set_page_config(page_title="Weathercast Planning Calendar", layout="wide")
APP_VERSION = "2026-10-31a"

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

# ------------------------------------------------------------------ month being viewed and printed
today = dt.date.today()
if "vm" not in st.session_state: st.session_state["vm"], st.session_state["vy"] = today.month, today.year

def shift_month(d):
    m, y = st.session_state["vm"] + d, st.session_state["vy"]
    if m < 1: m, y = 12, y - 1
    if m > 12: m, y = 1, y + 1
    st.session_state["vm"], st.session_state["vy"] = m, y

h1, h2, h3, h4, h5 = st.columns([6, 0.6, 2, 1.2, 0.6], vertical_alignment="center")
h1.markdown("### Weather Calendar")
h2.button("‹", on_click=shift_month, args=(-1,), help="Previous month", width="stretch")
h3.selectbox("Month", range(1, 13), key="vm", format_func=lambda m: MONTHS[m - 1], label_visibility="collapsed")
h4.number_input("Year", 2020, 2100, key="vy", label_visibility="collapsed")
h5.button("›", on_click=shift_month, args=(1,), help="Next month", width="stretch")
month, year = int(st.session_state["vm"]), int(st.session_state["vy"])

if "msg" in st.session_state:
    kind, text = st.session_state.pop("msg")
    st.toast(text) if kind == "success" else getattr(st, kind)(text)

def snapshot():
    st.session_state["snap"] = db.events(con); st.session_state["snap_v"] = st.session_state.get("snap_v", 0) + 1
if "snap" not in st.session_state: snapshot()

def repeat_text(e): return recurrence.describe(e["rule"]) if e["rule"] else ""
is_rule, fmt_span = views.is_rule, views.fmt_span
def view_rows(evs, show, cat="All categories", kind="One-time and repeating", text=""): return views.event_rows(evs, show, year, month, today, cat, kind, text)

def event_table(rows, key):
    """The spreadsheet of events: type to edit, add rows at the bottom, select rows and press Delete. Returns the event ticked for details."""
    df = pd.DataFrame([{"details": False, "date": r["date"], "through": r["through"], "title": r["ev"]["title"], "category": r["ev"]["category"],
                        "repeats": repeat_text(r["ev"]), "note": r["ev"]["flag"] or ""} for r in rows],
                      columns=["details", "date", "through", "title", "category", "repeats", "note"])
    st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=key, disabled=["repeats", "note"], placeholder="",
                   column_config={"date": st.column_config.DateColumn(help="Repeating events show their date in the period shown; change it with their repeat rule"),
                                  "through": st.column_config.DateColumn(), "title": st.column_config.TextColumn(required=True),
                                  "category": st.column_config.SelectboxColumn(options=cat_names),
                                  "details": st.column_config.CheckboxColumn(help="Tick to open time, location, notes and repeat rule")})
    ticked = [int(i) for i, ch in st.session_state.get(key, {}).get("edited_rows", {}).items() if ch.get("details") and int(i) < len(rows)]
    return rows[ticked[-1]]["ev"]["id"] if ticked else None

def save_table(rows, key):
    ch = views.table_changes(rows, st.session_state.get(key, {}), {n: c["id"] for n, c in cat_by_name.items()})
    conflicts = sum(1 for ev, fields in ch["updates"] if not db.update_event(con, ev["id"], expect_updated_at=ev["updated_at"], **fields))
    for i in ch["deletes"]: db.delete_event(con, i)
    for t, s_, e_, cid in ch["adds"]: db.add_event(con, t, s_, e_, cid)
    snapshot()
    notes = []
    if conflicts: notes.append(f"{conflicts} edit(s) skipped: someone else changed that event first. Their version is shown now.")
    if ch["skipped"]: notes.append("Dates of repeating events come from their repeat rule: tick 'details' to change the rule.")
    st.session_state["msg"] = ("warning", " ".join(notes)) if notes else ("success", "Saved")

def table_buttons(rows, key):
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("Save changes", type="primary", key=f"save{key}"): save_table(rows, key); st.rerun()
    if b2.button("Undo", key=f"undo{key}"):
        m = db.undo_last(con); snapshot(); st.session_state["msg"] = ("info", m or "Nothing to undo"); st.rerun()

def detail_form(eid):
    e = db.get_event(con, eid)
    if not e: return
    st.markdown(f"**{e['title']}**")
    with st.form(f"detail{eid}"):
        t = st.text_input("Title", e["title"])
        d1, d2 = st.columns(2)
        s = d1.date_input("Date", dt.date.fromisoformat(e["start_date"]))
        f = d2.date_input("Through (optional)", dt.date.fromisoformat(e["end_date"]) if e["end_date"] else None)
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Category", cat_names, cat_names.index(e["category"]) if e["category"] in cat_names else 0)
        time_ = c2.text_input("Time", e["time"] or "")
        loc_ = st.text_input("Location", e["location"] or "")
        notes = st.text_area("Notes", e["notes"] or "", height=68); url = st.text_input("Link", e["url"] or "")
        donly = st.checkbox("Details page only (keep off the calendar grid)", bool(e["detail_only"]))
        rule = e["rule"] or {"kind": "one_off"}
        kinds = recurrence.KINDS + ([rule["kind"]] if rule["kind"] in recurrence.CALCULATED_KINDS else [])
        kind = st.selectbox("Repeats", kinds, kinds.index(rule["kind"]),
                            format_func=lambda k: {"one_off": "Does not repeat", "yearly_fixed": "Every year on a fixed date",
                                                   "yearly_nth_weekday": "Every year on the nth weekday of a month",
                                                   "weekly_in_range": "Certain weekdays between two dates (each year)",
                                                   "lookup_by_year": "Listed dates per year", "yearly_relative": "Days from another rule",
                                                   "easter_relative": "Calculated from Easter", "weekday_nearest": "Weekday nearest a date",
                                                   "hebrew": "Calculated from the Hebrew calendar", "islamic": "Calculated from the Islamic calendar"}[k])
        p = dict(rule) if kind in recurrence.CALCULATED_KINDS else {"kind": kind}
        r1, r2, r3 = st.columns(3)
        if kind in recurrence.CALCULATED_KINDS:
            st.info(f"Calculated automatically for every year: {recurrence.describe(rule)}. To override it with dates you confirm yourself, choose 'Listed dates per year'.")
        elif kind == "yearly_fixed":
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
            try: st.caption("Next: " + (" · ".join(d.strftime("%a %b %d, %Y") for d in recurrence.next_occurrences(p, today)) or "none"))
            except Exception as ex: st.caption(f"Cannot preview this rule yet: {ex}")
        x1, x2, _ = st.columns([1, 1, 2])
        if x1.form_submit_button("Save event", type="primary"):
            ok = db.update_event(con, eid, expect_updated_at=e["updated_at"], title=t, start_date=s.isoformat(),
                                 end_date=f.isoformat() if f and f != s else None, category_id=cat_by_name[cat]["id"],
                                 time=time_ or None, location=loc_ or None, notes=notes or None, url=url or None,
                                 detail_only=int(donly), rule=None if kind == "one_off" else p)
            snapshot(); st.session_state["msg"] = ("success", "Saved") if ok else ("warning", "Someone else changed this event first; reloaded."); st.rerun()
        if x2.form_submit_button("Move to trash"):
            db.delete_event(con, eid); snapshot(); st.session_state["msg"] = ("success", f"Moved '{e['title']}' to the trash"); st.rerun()

@st.dialog("Add event")
def add_event_dialog():
    with st.form("add_event"):
        t = st.text_input("Title")
        d1, d2 = st.columns(2)
        d = d1.date_input("Date", dt.date(year, month, 1) if (year, month) != (today.year, today.month) else today)
        thr = d2.date_input("Through (optional)", None)
        cat = st.selectbox("Category", cat_names)
        st.caption("Time, notes and repeat rules: tick 'details' on the event's row after adding it.")
        if st.form_submit_button("Add", type="primary") and t.strip():
            db.add_event(con, t.strip(), d.isoformat(), thr.isoformat() if thr and thr > d else None, cat_by_name[cat]["id"] if cat in cat_by_name else None)
            snapshot(); st.session_state["msg"] = ("success", f"Added '{t.strip()}'"); st.rerun()

# ------------------------------------------------------------------ what is waiting in Review
counties = db.get_setting(con, "market_counties", regional.MARKET_COUNTIES)
SOURCE_LABEL = {"oda_fairs": "Fair schedule", "experience_columbus": "Experience Columbus"}
def cand_source(c): return SOURCE_LABEL.get(c["source"], "Calendar feeds" if c["source"].startswith("ics:") else c["source"])
pend = milestones.pending(con, year)
cands = [c for c in db.candidates(con, "new") if c["county"] in counties or not c["county"]]
waiting = len(pend) + len(cands)

tab_cal, tab_ev, tab_rev, tab_src, tab_set = st.tabs(["Calendar", "Events", f"Review ({waiting})" if waiting else "Review", "Sources", "Setup"])

# ------------------------------------------------------------------ Calendar: this month's events, the print preview, downloads
with tab_cal:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown(f"#### Events in {MONTHS[month - 1]} {year}")
        st.caption("Type in the table, add rows at the bottom, or select rows and press Delete (deleted events go to the trash). "
                   "Repeating events show their date this month; tick 'details' for time, notes or the repeat rule.")
        mrows = view_rows(st.session_state["snap"], "This month")
        mkey = f"cal{st.session_state['snap_v']}-{year}-{month}"
        open_id = event_table(mrows, mkey)
        table_buttons(mrows, mkey)
        if open_id:
            with st.container(border=True): detail_form(open_id)
    with right:
        box_preview, box_downloads = st.container(), st.container()
        with st.expander("Print settings"):
            p1, p2 = st.columns(2)
            o_sun = p1.checkbox("Sunrise / sunset", True); o_day = p2.checkbox("Daylight length and change", True)
            o_moon = p1.checkbox("Moon phases", True); o_nrm = p2.checkbox("Normal high/low", True)
            o_rec = p1.checkbox("Record high/low", True); o_notes = p2.checkbox("Notes boxes at bottom", True)
            o_det = p1.checkbox("Details page (second page)", True); compact = p2.checkbox("Smaller bars (fit more per day)", False)
            bw = p1.radio("Printer", ["Color", "Black & white"], horizontal=True) == "Black & white"
            gray_prev = p2.checkbox("Grayscale preview", value=bw, disabled=bw, help="Shows what a B&W printer makes of the color page.")
            week_start = 6 if p1.selectbox("Week starts on", ["Sunday", "Monday"]) == "Sunday" else 0
            paper = p2.selectbox("Paper", ["letter", "a4"], format_func=lambda p: {"letter": "US Letter", "a4": "A4"}[p])
            st.caption("Location: Columbus, OH (39.9612 N, 82.9988 W). Times are Eastern.")
        opts = R.Options(sun=o_sun, moon=o_moon, normals=o_nrm, records=o_rec, daylight=o_day, notes=o_notes, bw=bw,
                         details_page=o_det, week_start=week_start, paper=paper, compact=compact)
        pdf, rep = R.render(db.events(con), cats, year, [month], opts)
        with box_preview:
            st.image(preview.pdf_to_pngs(pdf, 1.5, grayscale=gray_prev and not bw or False)[0], width="stretch")
            for m in R.overflow_messages(rep): st.warning(f"{m}. Shorten a title, mark one 'details page only', or tick 'Smaller bars' in Print settings.")
            if rep["truncated"]: st.info("Shortened on the page (full title on the details page): " + "; ".join(sorted({t for _, t in rep["truncated"]})))
        with box_downloads:
            d1, d2, d3, d4 = st.columns([1.5, 1.5, 1, 1])
            d1.download_button("PDF", pdf, f"Calendar_{year}_{month:02d}.pdf", "application/pdf", type="primary", width="stretch")
            if d2.button("All 12 months", width="stretch"):
                st.session_state["pdf_year"] = (f"Calendar_{year}.pdf", R.render(db.events(con), cats, year, range(1, 13), opts)[0])
            d3.download_button("PNG", preview.pdf_to_pngs(pdf, 3.0, grayscale=False)[0], f"Calendar_{year}_{month:02d}.png", "image/png", width="stretch")
            d4.download_button("iCal", ical.export_ics(db.events(con), cats, year), f"Calendar_{year}.ics", "text/calendar", width="stretch")
            if "pdf_year" in st.session_state:
                st.download_button(f"Download {st.session_state['pdf_year'][0]}", st.session_state["pdf_year"][1], st.session_state["pdf_year"][0], "application/pdf")

# ------------------------------------------------------------------ Events: the full list
with tab_ev:
    f1, f2, f3, f4, f5 = st.columns([2.2, 1.6, 1.8, 1.8, 2.6], vertical_alignment="bottom")
    show = f1.segmented_control("Show", ["This month", "This year", "All"], default="This year", key="ev_show") or "This year"
    fcat = f2.selectbox("Category", ["All categories"] + cat_names, key="ev_cat")
    fkind = f3.selectbox("Type", ["One-time and repeating", "One-time only", "Repeating only"], key="ev_kind")
    ftext = f4.text_input("Search", key="ev_text", placeholder="Search titles")
    with f5:
        a1, a2, a3 = st.columns(3)
        if a1.button("Add event", type="primary", width="stretch"): add_event_dialog()
        with a2.popover("Import", width="stretch"):
            up = st.file_uploader("CSV file", type="csv")
            if up and st.button("Import CSV file"):
                n = importers.import_csv(con, up.getvalue().decode("utf-8-sig")); snapshot(); st.session_state["msg"] = ("success", f"Added {n} events"); st.rerun()
            xl = st.file_uploader("The legacy Excel calendar (Content_Idea_Calendar.xlsx)", type="xlsx")
            if xl and st.button("Import Excel file"):
                n = importers.import_workbook(con, xl, year); snapshot()
                st.session_state["msg"] = ("success", f"Added {n} events for {year}. Please review their categories."); st.rerun()
        a3.download_button("Export", importers.export_csv(con), "events.csv", "text/csv", width="stretch")
    left, right = st.columns([3, 2], gap="large")
    erows = view_rows(st.session_state["snap"], show, fcat, fkind, ftext)
    ekey = f"ev{st.session_state['snap_v']}-{show}-{fcat}-{fkind}-{ftext}-{year}-{month}"
    with left:
        st.caption({"This month": f"{MONTHS[month - 1]} {year}", "This year": str(year), "All": "Every event; repeating ones show their next date"}[show]
                   + f" · {len(erows)} event(s). Repeating events show their real date, not the date they were added.")
        open_id = event_table(erows, ekey)
        table_buttons(erows, ekey)
    with right:
        if open_id:
            with st.container(border=True): detail_form(open_id)
        else: st.info("Tick 'details' on a row to see its time, location, notes and repeat rule here.")

# ------------------------------------------------------------------ Review: everything proposed, from every source
with tab_rev:
    st.caption("Everything the app proposes lands here, from every source. Nothing reaches the calendar until you accept it, and a rejected item never comes back.")
    old = db.outdated_climo_milestones(con)
    if old:
        st.warning(f"{len(old)} accepted milestone entr{'y was' if len(old) == 1 else 'ies were'} calculated with an older method and now differ from the current numbers: "
                   + "; ".join(f"{e['title']} ({e['start_date']})" for _, e in old))
        if st.button("Move these to the trash and propose corrected versions"):
            n = db.retire_outdated_climo_milestones(con); snapshot()
            st.session_state["msg"] = ("success", f"Moved {n} event(s) to the trash (restorable). Corrected proposals are below."); st.rerun()
    items = [{"kind": "m", "obj": r, "dates": fmt_span(r["date"], r["end"]), "title": r["title"], "source": "Sun, sky & climate", "category": r["category"],
              "county": "", "dup": "", "link": None} for r in pend]
    items += [{"kind": "c", "obj": c, "dates": fmt_span(c["start_date"], c["end_date"]), "title": c["title"], "source": cand_source(c), "category": regional.CATEGORY,
               "county": c["county"] or "", "dup": "yes" if db.likely_duplicates(con, c) else "", "link": c["url"]} for c in cands]
    srcs = ["All", "Sun, sky & climate", "Fair schedule", "Experience Columbus", "Calendar feeds"]
    count = {s: len(items) if s == "All" else sum(1 for i in items if i["source"] == s) for s in srcs}
    src = st.pills("Source", srcs, default="All", key="rv_src", format_func=lambda s: f"{s} {count[s]}", label_visibility="collapsed") or "All"
    shown = [i for i in items if src == "All" or i["source"] == src]
    if not shown: st.success("Nothing waiting for review. Run a source in the Sources tab to get more proposals.")
    else:
        fill = st.session_state.get("rv_fill", "")
        rdf = pd.DataFrame([{"decision": fill, "dates": i["dates"], "title": i["title"], "source": i["source"], "category": i["category"],
                             "county": i["county"], "already on calendar": i["dup"], "link": i["link"]} for i in shown])
        red = st.data_editor(rdf, hide_index=True, width="stretch", key=f"rv{year}-{src}-{len(shown)}-{fill}", placeholder="",
                             disabled=["dates", "title", "source", "category", "county", "already on calendar", "link"],
                             column_config={"decision": st.column_config.SelectboxColumn(options=["", "Accept", "Reject"]),
                                            "link": st.column_config.LinkColumn(display_text="open")})
        def prefill(v): st.session_state["rv_fill"] = v
        b1, b2, b3, _ = st.columns([1.2, 1.2, 1.2, 3])
        if b1.button("Apply decisions", type="primary"):
            n = 0
            for k, r in red.iterrows():
                it = shown[k]
                if r["decision"] == "Accept": (milestones.accept(con, it["obj"]) if it["kind"] == "m" else regional.accept(con, it["obj"]["id"])); n += 1
                elif r["decision"] == "Reject": (milestones.reject(con, it["obj"]) if it["kind"] == "m" else db.decide_candidate(con, it["obj"]["id"], "rejected")); n += 1
            st.session_state["rv_fill"] = ""; snapshot(); st.session_state["msg"] = ("success", f"Applied {n} decision(s)"); st.rerun()
        b2.button("Accept all shown", on_click=prefill, args=("Accept",), help="Fills in 'Accept' for every row; press Apply decisions to confirm.")
        b3.button("Reject all shown", on_click=prefill, args=("Reject",), help="Fills in 'Reject' for every row; press Apply decisions to confirm.")
    flagged = [e for e in st.session_state["snap"] if e["flag"] == "could be auto-generated"]
    if flagged:
        with st.expander(f"{len(flagged)} imported event(s) that the app can now calculate"):
            st.dataframe(pd.DataFrame([{"date": e["start_date"], "title": e["title"]} for e in flagged]), hide_index=True)
            st.caption("Compare with the proposals above, then delete the typed versions you don't need in the Events tab.")

# ------------------------------------------------------------------ Sources: where calendar entries come from
with tab_src:
    st.caption("Holidays go straight onto the calendar as repeating events. Every other source sends proposals to the Review tab first.")
    col1, col2 = st.columns(2, gap="medium")
    with col1:
        with st.container(border=True):
            st.markdown("**Holidays** · adds directly")
            st.caption("Pick the sets you want. They repeat every year on their own, so this is a one-time setup.")
            have = {e["title"] for e in st.session_state["snap"] if is_rule(e)}
            loaded = [k for k, v in holidays.HOLIDAY_SETS.items() if all(t in have for t, _ in v[2])]
            hc = st.columns(2)
            chosen = [k for i, k in enumerate(holidays.HOLIDAY_SETS) if hc[i % 2].checkbox(holidays.HOLIDAY_SETS[k][0], k in holidays.DEFAULT_SETS or k in loaded, key=f"hs{k}",
                                                                                          help=holidays.HOLIDAY_SETS[k][1])]
            if chosen:
                with st.expander(f"Preview the dates for {year}"):
                    st.dataframe(pd.DataFrame([{"set": holidays.HOLIDAY_SETS[k][0], "holiday": t, "dates": recurrence.format_dates(recurrence.dates_for_rule(rule, year)) or "(none this year)"}
                                               for k in chosen for t, rule in holidays.HOLIDAY_SETS[k][2]]), hide_index=True, width="stretch")
            if st.button("Add selected sets", type="primary", disabled=not chosen):
                added = db.load_holidays(con, chosen); snapshot(); total = sum(added.values())
                st.session_state["msg"] = ("success", f"Added {total} holiday(s)" if total else "They are all already on the calendar"); st.rerun()
            st.caption(("On the calendar: " + ", ".join(holidays.HOLIDAY_SETS[k][0] for k in loaded) + ". " if loaded else "") + "Nothing is added twice.")
            retired = db.retired_holidays(con)
            if retired:
                st.warning(f"{len(retired)} holiday entr{'y' if len(retired) == 1 else 'ies'} you added earlier {'is' if len(retired) == 1 else 'are'} no longer in the holiday lists: "
                           + ", ".join(sorted(e["title"] for e in retired)))
                if st.button("Move those to the trash"):
                    n = db.retire_holidays(con); snapshot(); st.session_state["msg"] = ("success", f"Moved {n} to the trash (restorable)."); st.rerun()
        with st.container(border=True):
            st.markdown("**Ohio fair schedule** · to Review")
            st.caption("The Ohio Department of Agriculture brochure: the Ohio State Fair, county fairs and independent fairs. A new one comes out each December.")
            up = st.file_uploader("Brochure PDF (the 2026 one is built in)", type="pdf", key="oda_pdf")
            past = st.checkbox("Include fairs that are already over", False)
            if st.button("Read the schedule", type="primary"):
                try:
                    data = up.getvalue() if up else open(os.path.join(os.path.dirname(__file__), "reference", "ohio_fair_schedule_2026.pdf"), "rb").read()
                    r = regional.fetch_oda_fairs(data, counties, include_past=past)
                    st.success(f"{r['year']} schedule: {r['total']} fairs listed; {r['new']} new proposal(s), {r['seen']} in your counties" + ("" if past else " still to come") + ".")
                except Exception as ex: st.error(f"Could not read the fair schedule: {ex}")
        with st.container(border=True):
            st.markdown("**Calendar feeds (.ics)** · to Review")
            st.caption("Any visitors bureau or fairground that publishes a calendar address.")
            feeds = db.get_setting(con, "ics_feeds", [])
            if not feeds: st.caption("No feeds yet.")
            for i, fd in enumerate(feeds):
                x1, x2 = st.columns([5, 1], vertical_alignment="center"); x1.write(f"{fd['name']} · {fd.get('county') or 'any county'} · {fd['url']}")
                if x2.button("Remove", key=f"rmfeed{i}"): feeds.pop(i); db.set_setting(con, "ics_feeds", feeds); st.rerun()
            with st.form("addfeed", border=False):
                n1, n2, n3 = st.columns([2, 1.3, 3]); fn = n1.text_input("Name"); fc = n2.selectbox("County", [""] + regional.MARKET_COUNTIES)
                fu = n3.text_input("Feed address", placeholder="https://… .ics")
                if st.form_submit_button("Add feed") and fn.strip() and fu.strip().startswith("http"):
                    feeds.append({"name": fn.strip(), "county": fc or None, "url": fu.strip()}); db.set_setting(con, "ics_feeds", feeds); st.rerun()
            if feeds and st.button("Fetch all feeds", type="primary"):
                for fd in feeds:
                    try: r = regional.fetch_ics(f"ics:{fd['url']}", fd["url"], fd.get("county")); st.write(f"{fd['name']}: {r['new']} new of {r['seen']} upcoming")
                    except Exception as ex: st.error(f"{fd['name']}: {ex}")
    with col2:
        with st.container(border=True):
            st.markdown("**Sun, sky & climate** · to Review")
            st.caption(f"DST changes, solstices, meteor shower peaks and climo dates for {year}. They appear in Review automatically for the year you're viewing.")
            st.caption(f"Climate normals and records (RCC-ACIS): {'loaded' if climo.table() else 'missing'}; 1991-2020 statistics: {'loaded' if climo.stats() else 'missing'}")
            ams = meteors.cached()
            st.caption(f"Meteor shower peak nights (American Meteor Society): {len(ams['showers'])} showers, fetched {ams['fetched']}" if ams else "Meteor shower peak nights: not loaded (typical dates are used)")
            s1, s2 = st.columns(2)
            if s1.button("Refresh climate data", width="stretch"):
                try: climo.fetch_normals_records(); climo.fetch_stats(); st.success("Climate data refreshed.")
                except Exception as ex: st.error(f"ACIS fetch failed: {ex}")
            if s2.button("Refresh meteor showers", width="stretch"):
                try:
                    n = meteors.fetch(); st.success(f"Loaded {n} showers (the next twelve months).")
                    if (meteors.cached() or {}).get("skipped"): st.warning("These cards could not be read and were left out: " + ", ".join(meteors.cached()["skipped"]))
                except Exception as ex: st.error(f"Could not read the AMS calendar: {ex}")
        with st.container(border=True):
            st.markdown("**Experience Columbus** · to Review")
            st.caption("Festival-like event pages from the Columbus visitors bureau, read 2 seconds apart (as its robots.txt asks) and remembered between runs.")
            with st.expander("Words that decide what counts as a festival"):
                kws = st.text_input("Keep addresses containing", ", ".join(db.get_setting(con, "ec_keywords", regional.DEFAULT_KEYWORDS)))
                exs = st.text_input("Skip addresses containing", ", ".join(db.get_setting(con, "ec_exclude", regional.DEFAULT_EXCLUDE)))
            split = lambda s: [x.strip().lower() for x in s.split(",") if x.strip()]
            if st.button("Fetch upcoming events", type="primary"):
                db.set_setting(con, "ec_keywords", split(kws)); db.set_setting(con, "ec_exclude", split(exs)); bar = st.progress(0.0, "Reading event pages…")
                try:
                    r = regional.fetch_experience_columbus(counties, split(kws), split(exs), progress=lambda i, n: bar.progress(i / max(n, 1), f"Read {i} of {n} pages"), max_pages=60)
                    st.success(f"{r['new']} new proposal(s); {r['seen']} upcoming event(s) in your counties" + (f"; {r['outside']} in other counties skipped" if r["outside"] else "") + "."
                               + (f" {r['remaining']} more pages are left: press the button again to continue." if r["remaining"] else ""))
                except Exception as ex: st.error(f"Could not read Experience Columbus: {ex}")
            st.caption("Reads up to 60 pages a run; press again to continue.")
        with st.container(border=True):
            st.markdown("**Counties** · applies to fairs, festivals and feeds")
            pick = st.multiselect("Counties", regional.MARKET_COUNTIES, [c for c in counties if c in regional.MARKET_COUNTIES], label_visibility="collapsed")
            st.caption("Remove a county to stop proposals from it.")
            if pick != counties: db.set_setting(con, "market_counties", pick); st.rerun()

# ------------------------------------------------------------------ Setup: categories, next year, history and trash, backup
with tab_set:
    with st.container(border=True):
        st.markdown("**Categories**")
        st.caption(f"Type in the table, or add a row at the bottom. Colors are hex codes like #c0392b. 'This month' counts {MONTHS[month - 1]} {year}.")
        counts = db.category_counts(con, year, month)
        styles = list(patterns.STYLES); label_of = patterns.STYLES; key_of = {v: k for k, v in patterns.STYLES.items()}
        cdf = pd.DataFrame([{"color": c["color_hex"], "name": c["name"], "B&W pattern": label_of[c["bw_style"]], "this month": counts.get(c["id"], 0),
                             "auto-category words": c["keywords"] or ""} for c in cats])
        ck = f"cats{len(cats)}-{st.session_state.get('cats_v', 0)}"
        g1, g2 = st.columns([3, 1.3], gap="large")
        with g1:
            st.data_editor(cdf, hide_index=True, width="stretch", num_rows="add", key=ck, disabled=["this month"], placeholder="",
                           column_config={"color": st.column_config.TextColumn(validate=r"^#[0-9a-fA-F]{6}$", required=True),
                                          "name": st.column_config.TextColumn(required=True),
                                          "B&W pattern": st.column_config.SelectboxColumn(options=[label_of[s] for s in styles], required=True)})
            if st.button("Save categories", type="primary"):
                state = st.session_state.get(ck, {})
                for idx, ch in state.get("edited_rows", {}).items():
                    c = cats[int(idx)]; f = {}
                    if ch.get("name"): f["name"] = ch["name"]
                    if ch.get("color"): f["color_hex"] = ch["color"]
                    if ch.get("B&W pattern"): f["bw_style"] = key_of[ch["B&W pattern"]]
                    if "auto-category words" in ch: f["keywords"] = ch["auto-category words"] or ""
                    if f: db.update_category(con, c["id"], **f)
                errs = []
                for r in state.get("added_rows", []):
                    if r.get("name"):
                        try: db.add_category(con, r["name"].strip(), r.get("color") or "#444444", key_of.get(r.get("B&W pattern"), "light_gray"))
                        except Exception as ex: errs.append(str(ex))
                st.session_state["cats_v"] = st.session_state.get("cats_v", 0) + 1; snapshot()
                st.session_state["msg"] = ("warning", "; ".join(errs)) if errs else ("success", "Categories saved"); st.rerun()
            for c in cats:
                ratio = patterns.white_text_contrast(c["color_hex"])
                if ratio < 4.5: st.warning(f"{c['name']}: white text on {c['color_hex']} is {ratio:.1f}:1, below 4.5:1. Darken the color.")
            for style, names in patterns.style_collisions(cats):
                st.warning(f"These categories share the B&W pattern “{patterns.STYLES[style]}” and will look the same on a B&W printer: {', '.join(names)}.")
            with st.expander("Delete a category"):
                x1, x2, x3 = st.columns([2, 2, 1], vertical_alignment="bottom")
                gone = x1.selectbox("Category", cat_names, key="del_cat")
                others = [n for n in cat_names if n != gone]
                move = x2.selectbox("Move its events to", others, key="del_move")
                if x3.button("Delete", disabled=not others):
                    db.delete_category(con, cat_by_name[gone]["id"], cat_by_name[move]["id"]); snapshot(); st.session_state["msg"] = ("success", f"Deleted '{gone}'"); st.rerun()
        with g2:
            st.caption("Legend as printed: color, then black & white")
            st.image(preview.pdf_to_pngs(R.legend_preview(cats, False), 2)[0])
            st.image(preview.pdf_to_pngs(R.legend_preview(cats, True), 2)[0])
    s1, s2 = st.columns(2, gap="medium")
    with s1:
        with st.container(border=True):
            st.markdown(f"**Prepare {year + 1}**")
            st.caption(f"Repeating events carry over by themselves. Tick the one-time {year} events to copy into {year + 1}, and fix their dates if they move.")
            miss = db.lookup_rules_missing(con, year + 1)
            if miss: st.warning(f"These events list dates per year and have no dates for {year + 1}: " + ", ".join(e["title"] for e in miss))
            oo = db.one_offs(con, year)
            if oo:
                rdf = pd.DataFrame([{"copy": False, "title": e["title"], "date": dt.date.fromisoformat(db.shift_year(e["start_date"], 1)),
                                     "through": dt.date.fromisoformat(db.shift_year(e["end_date"], 1)) if e["end_date"] else None, "id": e["id"]} for e in oo])
                red = st.data_editor(rdf, hide_index=True, width="stretch", disabled=["title"], column_config={"id": None}, key=f"roll{year}", placeholder="")
                if st.button(f"Copy ticked events to {year + 1}", type="primary"):
                    items = [(int(r["id"]), r["date"].isoformat(), r["through"].isoformat() if pd.notna(r["through"]) and r["through"] else None) for _, r in red.iterrows() if r["copy"]]
                    n = db.carry_forward(con, items); snapshot(); st.session_state["msg"] = ("success", f"Created {n} event(s) in {year + 1}"); st.rerun()
            else: st.caption(f"No one-time events in {year}.")
        with st.container(border=True):
            st.markdown("**Backup**")
            st.caption("Stored in the " + ("hosted database, backed up every night (see README)" if db.turso_config() else "local file on this computer") + ". Download an extra copy any time.")
            st.download_button("Download a copy of the database", db.backup_bytes(con), "calendar_backup.db", "application/octet-stream")
    with s2:
        with st.container(border=True):
            try:
                t1, t2 = st.columns([3, 1.4], vertical_alignment="center")
                t1.markdown("**History & trash**")
                if t2.button("Undo last change", width="stretch"):
                    m = db.undo_last(con); snapshot(); st.session_state["msg"] = ("info", m or "Nothing to undo"); st.rerun()
                hist = db.history(con, 100)
                st.dataframe(pd.DataFrame([{"when": str(h.get("at") or "").replace("T", " ")[:16], "action": str(h.get("action") or "?") + (" (undone)" if h.get("undone") else ""), "event": h.get("title")} for h in hist],
                                          columns=["when", "action", "event"]), hide_index=True, width="stretch", height=220)
                trash = db.events(con, only_deleted=True)
                st.caption(f"Trash: {len(trash)} event(s)" if trash else "Trash is empty.")
                for e in trash:
                    a_, b_ = st.columns([4, 1], vertical_alignment="center")
                    a_.write(f"{e['title']}  _({e['start_date']}, deleted {str(e['deleted_at'])[:16].replace('T', ' ')})_")
                    if b_.button("Restore", key=f"rs{e['id']}"): db.restore_event(con, e["id"]); snapshot(); st.rerun()
            except Exception as ex:      # never let this section take down the whole page
                if type(ex).__name__ in ("RerunException", "StopException"): raise
                st.error(f"The history view failed ({type(ex).__name__}: {ex}). The rest of the app still works.")
                st.code(db.diagnose(con))
    st.caption(f"App version {APP_VERSION}  |  storage: {'hosted database' if db.turso_config() else 'local file'}  |  "
               "Sunrise/sunset: NOAA solar-calculator algorithm, truncated to the minute like the NWS climate report; moon: PyEphem; "
               "normals (1991-2020) and records: RCC-ACIS, Columbus Area (threaded record, CMHthr).")
