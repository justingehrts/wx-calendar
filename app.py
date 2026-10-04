import datetime as dt, hmac, os
import pandas as pd
import streamlit as st
from calendar_core import db, importers

st.set_page_config(page_title="Weathercast Planning Calendar", layout="wide")

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
        if st.form_submit_button("Enter") and hmac.compare_digest(p, code):
            st.session_state["ok"] = True; st.rerun()
        elif p: st.error("Wrong passcode")
    st.stop()

gate()
con = db.connect()
cats = db.categories(con)
cat_names = [c["name"] for c in cats]
st.title("Weathercast Planning Calendar")
tab_events, tab_cats = st.tabs(["Events", "Categories"])

with tab_events:
    year = st.number_input("Year", 2020, 2100, dt.date.today().year, key="yr")
    evs = db.events(con)
    df = pd.DataFrame([{"id": e["id"], "date": dt.date.fromisoformat(e["start_date"]),
                        "through": dt.date.fromisoformat(e["end_date"]) if e["end_date"] else None,
                        "title": e["title"], "category": e["category"]} for e in evs],
                      columns=["id", "date", "through", "title", "category"])
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key="ed",
        column_config={"id": None, "date": st.column_config.DateColumn(required=True),
                       "through": st.column_config.DateColumn(),
                       "category": st.column_config.SelectboxColumn(options=cat_names)})
    if st.button("Save changes", type="primary"):
        keep = set()
        for _, r in edited.iterrows():
            if pd.isna(r["title"]) or pd.isna(r["date"]): continue
            cid = db.category_id_by_name(con, r["category"]) if pd.notna(r["category"]) else None
            end = r["through"].isoformat() if pd.notna(r["through"]) else None
            if pd.notna(r["id"]):
                keep.add(int(r["id"]))
                db.update_event(con, int(r["id"]), title=r["title"], start_date=r["date"].isoformat(),
                                end_date=end, category_id=cid or db.categorize(con, r["title"]))
            else:
                keep.add(db.add_event(con, r["title"], r["date"], end, cid))
        for e in evs:
            if e["id"] not in keep: db.delete_event(con, e["id"])
        st.success("Saved"); st.rerun()
    c1, c2, c3 = st.columns(3)
    c1.download_button("Export CSV", importers.export_csv(con), "events.csv", "text/csv")
    up = c2.file_uploader("Import CSV", type="csv")
    if up and c2.button("Import CSV file"):
        st.success(f"Added {importers.import_csv(con, up.getvalue().decode())} events"); st.rerun()
    xl = c3.file_uploader("Import legacy Excel calendar", type="xlsx")
    if xl and c3.button("Import Excel file"):
        st.success(f"Added {importers.import_workbook(con, xl, int(year))} events. Review categories."); st.rerun()

with tab_cats:
    st.dataframe(pd.DataFrame(cats)[["name", "color_hex", "bw_style", "keywords"]], hide_index=True, width="stretch")
    st.caption("Editing categories, contrast checks and B&W previews arrive in the next step.")
