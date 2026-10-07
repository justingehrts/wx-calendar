# Weathercast Planning Calendar

A Streamlit app where the weather team keeps one shared list of events and prints a clean monthly
planning calendar (US Letter or A4 landscape, color or black-and-white laser). It replaces
`Content_Idea_Calendar.xlsx`. The full spec is in `BUILD_PLAN.md`.

Location for all sun, moon and climate data: Columbus, OH (39.9612 N, 82.9988 W; climate station CMH). All times Eastern.

## What it does
- **Events**: editable table, live month preview, overflow warnings, details panel (time, location, notes, link),
  repeat rules with a "next 3 occurrences" check, CSV import/export, legacy Excel import, iCal and PNG export.
- **Categories**: color + black-and-white style per category, contrast check, legend preview in color and B&W.
- **Milestones**: proposed sun, sky, DST, meteor-shower and climo entries to accept or reject.
- **History & trash**: every change is logged; undo; deleted events go to the trash.
- **Settings**: fetch USNO sunrise/sunset for a year, refresh ACIS climate data, add federal holidays, year rollover, database download.
- **Print options** (sidebar): what shows on each day, color/B&W, grayscale preview, Sunday/Monday start, paper size, smaller bars.
- The PDF never silently drops an event: anything that does not fit is listed on the app screen and on the details page.

## Run locally
    pip install -r requirements-dev.txt
    CALENDAR_PASSCODE=yourcode streamlit run app.py
    pytest

The passcode comes from `st.secrets["passcode"]` or `CALENDAR_PASSCODE`. It keeps casual visitors out; it is not real security.
Locally, data lives in `data/` (`CALENDAR_DATA_DIR`, database path `CALENDAR_DB`).

## Hosting (free): Streamlit Community Cloud + Turso
Streamlit Community Cloud wipes its disk on every restart, so the data lives in a free hosted
[Turso](https://turso.tech) database (SQLite-compatible) instead. The app switches to it automatically when two
secrets are present; without them it uses a local file, which is what you want on your own computer.

1. **Create the database** (Turso account, then the `turso` CLI or the dashboard):
   `turso db create wxcal`, `turso db show wxcal --url` (the `libsql://...` address), `turso db tokens create wxcal`.
2. **Deploy**: at share.streamlit.io choose *New app*, this repo, branch `main`, file `app.py`. Under *Advanced settings > Secrets* paste:

       passcode = "pick-a-shared-passcode"
       TURSO_DATABASE_URL = "libsql://wxcal-yourname.turso.io"
       TURSO_AUTH_TOKEN = "the-token-from-step-1"

   Set the app to *Private* (viewers must sign in) if your plan allows it, otherwise the passcode is the only gate.
3. **First run**: open Events > Import / export and import `Content_Idea_Calendar.xlsx`, then Settings > add the federal holidays.
   If the app shows a red "running without a hosted database" banner, the secrets are missing or misspelled.
4. **Backups**: the Settings tab downloads a copy of the database any time. For automatic nightly copies, add the same two
   Turso values as *repository* secrets (GitHub > Settings > Secrets and variables > Actions); `.github/workflows/backup.yml`
   then saves a copy as a workflow artifact every night (kept 30 days; GitHub pauses scheduled runs on repos idle for 60 days).
   A backup file is a normal SQLite file; open it with any SQLite tool or restore by importing its events.

Free tiers and limits change; check Streamlit's and Turso's current terms. The app sleeps when idle and wakes on the next visit.
The Turso connection has been tested here only in local-file mode (all tests run against both drivers); the live connection
and the GitHub Action are untested until you deploy.

### Alternative: your own container
`Dockerfile`, `run.sh`, `litestream.yml` and `fly.toml` run the app with a plain SQLite file on a persistent disk and
continuous Litestream backup to an S3-compatible bucket (Fly.io, Render and similar, a few dollars a month). Run one instance only.
Variables: `CALENDAR_PASSCODE`, `LITESTREAM_REPLICA_URL`, `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY`.
This path is also untested (no Docker daemon in the authoring environment).

## Data sources
- **Sunrise/sunset**: U.S. Naval Observatory API (upper limb, standard refraction), cached per year (in `data/cache/`, or in the database when hosted).
  2026 is bundled in `reference/`. For other years use Settings > fetch (about 2 minutes). Until then, a PyEphem calculation
  with the same definition is used (it agreed with USNO to within 0.52 minute on every day of 2026) and the app says so.
- **Moon phases and seasons**: PyEphem, converted to Eastern before taking the date.
- **Normals (1991-2020) and daily records**: RCC-ACIS, station CMH. Stored by month-day in `reference/climo_md.csv`.
- **Climo milestones**: computed from CMH daily data for 1991-2020 (`reference/climo_stats.json`): mean date of last/first
  32° freeze (min temp), first/last 80° and 90° day (max temp), first/last measurable (≥0.1") and ≥1" snowfall (seasons Jul 1-Jun 30).
- **Meteor showers**: `reference/meteor_showers.json` has *typical* peak dates. Add verified dates for a year under `"years"`
  (from the IMO or AMS calendar); until then the proposals say "typical date, not verified".

## Layout
    app.py                  Streamlit UI + passcode gate
    calendar_core/          db, recurrence, astro, climo, milestones, render_pdf, patterns, importers, ical, preview
    reference/              bundled 2026 sun data, climo tables, meteor table
    tests/                  pytest suite
    scripts/legacy/         the original prototype scripts (superseded by calendar_core)
