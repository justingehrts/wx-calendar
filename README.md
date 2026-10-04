# Weathercast Planning Calendar

Streamlit app for the weather team's shared event list and a printable monthly calendar.
See `BUILD_PLAN.md` for the full spec and build order.

## Run locally
    pip install -r requirements.txt
    CALENDAR_PASSCODE=yourcode streamlit run app.py
    pytest

Passcode comes from `st.secrets["passcode"]` or `CALENDAR_PASSCODE`. Data lives in
`data/calendar.db` (override with `CALENDAR_DB`).

## Hosting and backups (recommendation)
Streamlit Community Cloud has an **ephemeral disk**: a SQLite file there is lost on restart or
redeploy, so do not host the database there. Run the same app in a small container on a host
with a **persistent volume** (Fly.io, Render, or a small VM), mount it at `data/`, and set
`CALENDAR_DB` and `CALENDAR_PASSCODE`. For backups, run [Litestream](https://litestream.io)
alongside the app to replicate the database continuously to an S3-compatible bucket
(AWS S3, Backblaze B2 or Cloudflare R2, a few cents per month). The app's CSV export is a
second, manual way to get your data out.

## Data (scripts/)
- `fetch_usno.py 2026` -> `astro_usno.json` (sunrise/sunset, USNO; verified against PyEphem)
- `fetch_climo.py 2026` -> `climo.csv` (1991-2020 normals and daily records, RCC-ACIS CMH)
