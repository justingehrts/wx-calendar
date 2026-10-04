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
    pip install -r requirements.txt
    CALENDAR_PASSCODE=yourcode streamlit run app.py
    pytest

The passcode comes from `st.secrets["passcode"]` or `CALENDAR_PASSCODE`. It keeps casual visitors out; it is not real security.
Data lives in `data/` (`CALENDAR_DATA_DIR`, database path `CALENDAR_DB`).

## Hosting and backups
Streamlit Community Cloud has an **ephemeral disk**, so a SQLite file there is lost on restart. Use the included
`Dockerfile` on a host with a **persistent volume** (Fly.io, Render, a small VM) mounted at `/data`.
Run exactly **one** instance (SQLite is single-writer).

`run.sh` starts [Litestream](https://litestream.io) when `LITESTREAM_REPLICA_URL` is set: on a fresh disk it restores the
latest copy from the bucket, then replicates every change continuously (30 days of restore points). Environment variables:

| Variable | Purpose |
|---|---|
| `CALENDAR_PASSCODE` | shared passcode (required) |
| `LITESTREAM_REPLICA_URL` | e.g. `s3://my-bucket/wx-calendar` (B2/R2: add `?endpoint=https://...&region=auto`) |
| `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY` | bucket credentials |

`fly.toml` is an example for Fly.io. The container build has not been tested in the authoring environment (no Docker daemon).
Restore by hand: `litestream restore -config litestream.yml $CALENDAR_DB`.
The Settings tab also offers a manual database download, and Events has a CSV export.

## Data sources
- **Sunrise/sunset**: U.S. Naval Observatory API (upper limb, standard refraction), cached per year in `data/cache/`.
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
