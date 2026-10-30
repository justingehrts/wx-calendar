# Weathercast Planning Calendar

A Streamlit app where the weather team keeps one shared list of events and prints a clean monthly
planning calendar (US Letter or A4 landscape, color or black-and-white laser). It replaces
`Content_Idea_Calendar.xlsx`. The full spec is in `BUILD_PLAN.md`.

Location for all sun, moon and climate data: Columbus, OH (39.9612 N, 82.9988 W; climate record: Columbus Area, ACIS threaded station CMHthr). All times Eastern.

## What it does
- **Events**: editable table, live month preview, overflow warnings, details panel (time, location, notes, link),
  repeat rules with a "next 3 occurrences" check, CSV import/export, legacy Excel import, iCal and PNG export.
- **Categories**: color + black-and-white style per category, contrast check, legend preview in color and B&W.
- **Milestones**: proposed sun, sky, DST, meteor-shower and climo entries to accept or reject.
- **History & trash**: every change is logged; undo; deleted events go to the trash.
- **Settings**: refresh ACIS climate data, add holiday sets (U.S. federal, Christian, Jewish, Muslim, other popular observances), year rollover, database download.
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
- **Sunrise/sunset**: NOAA's solar-calculator algorithm (the method behind the NOAA GML web calculator; upper limb of the Sun, standard
  refraction) evaluated at 39.99 N, 83.00 W, and printed **truncated to the whole minute**. That reproduces the NWS Wilmington climate
  reports for Columbus on 339 of 342 values in 2026 (the 3 misses are within a second of a minute boundary), and all of timeanddate.com's
  October table. The point was fitted to the NWS output; on dates held out of the fit it still matched 98%. The airport's coordinates fit
  much worse, so the NWS evidently does not use them. USNO and NOAA GML **round** to the nearest minute instead, so they differ from the NWS
  by 1 minute on about half the days. Nothing is downloaded: it works for any year. Day length and its daily change come from PyEphem
  (matches timeanddate.com to about a second).
- **Moon phases, seasons and DST**: PyEphem, converted to Eastern before taking the date.
- **Normals (1991-2020)**: the NCEI daily normals in tenths of a degree (republished by the Iowa Environmental Mesonet), rounded **half-up**
  like the NWS does (46.5 becomes 47). ACIS returns whole degrees rounded half-to-even (46.5 becomes 46), which disagreed with the NWS on about 6% of
  days. Verified: 100% of normals match 488 NWS climate-report values from 2026.
- **Daily records**: computed from the whole daily record of the **threaded** Columbus Area station `CMHthr` (RCC-ACIS; plain `CMH` is the airport
  alone, whose records differ), with every tied year kept. Record values match the NWS on all days checked; a few tied-year lists differ
  (ours sometimes has one extra early year). Stored by month-day in `reference/climo_CMHthr_md_v2.csv`; records set after that file was made
  appear after Settings > Refresh.
- **Climo milestones**: computed from CMHthr daily data (`reference/climo_CMHthr_stats_v2.json`). Averages are mean dates over the 30 years 1991-2020 (the same first/last pairing as xmACIS: first snow after Jul 1 of each year, last snow before Jul 1; the fraction of a day is dropped, so a mean of Nov 23.8 prints as Nov 23; checked against xmACIS's measurable-snow table, all 60 dates and the means); earliest/latest use the whole record (1878 on), counting only years with at least 95% data coverage of the relevant window. Thresholds: last/first
  32° freeze (min temp), first/last 80° and 90° day (max temp), first/last measurable (≥0.1") and ≥1" snowfall (seasons Jul 1-Jun 30).
- **Holidays** (Settings > Holidays; every item is a repeat rule, so dates are calculated for any year and nothing is retyped at rollover):
  U.S. federal (actual dates, not "observed" days); Christian (Mardi Gras, Easter, Orthodox Easter, Christmas Eve, Christmas; Easter from the
  standard computus); Jewish (Purim, Passover, Rosh Hashanah, Yom Kippur, Hanukkah, each a single "... begins" marker on the evening it starts,
  i.e. the sundown before its first full day; dates from the Hebrew calendar via `pyluach`, with Purim moving to Adar II in leap years); Muslim
  (Ramadan begins, Eid al-Fitr, Eid al-Adha, predicted from the Umm al-Qura calendar via `hijridate`, valid 1924-2077; the observed day depends
  on moon sighting and can differ by a day, so those events carry a "predicted date: confirm" note in the Events tab and can be overridden with
  'Listed dates per year'); and optional popular observances (Mother's Day, Father's Day, Halloween, and others). Entries added by earlier
  versions of the lists are detected in Settings and can be moved to the trash in one click.
- **Meteor showers**: peak nights come from the [American Meteor Society's calendar](https://www.amsmeteors.org/calendar/) (Settings > Refresh meteor
  shower peak nights). That page is a rolling window of the next twelve months, so a snapshot is bundled in `reference/meteor_ams.json` and refreshing
  replaces it. Each shower is proposed as a two-night bar (e.g. Oct 21-22) with the Moon on the peak night in the note. Showers or years the AMS page does not
  cover (past showers, or dates more than a year out) fall back to `reference/meteor_showers.json`: verified dates under `"years"` if you add any, otherwise
  *typical* dates, which are clearly labelled "TYPICAL ... NOT verified". If the AMS page layout changes, the refresh refuses to save and keeps the old data;
  a card that cannot be read is reported.
- **Holidays** (Settings > Holidays; every item is a repeat rule, so dates are calculated for any year and nothing is retyped at rollover):
  U.S. federal (actual dates, not "observed" days); Christian (Mardi Gras, Easter, Orthodox Easter, Christmas Eve, Christmas; Easter from the
  standard computus); Jewish (Purim, Passover, Rosh Hashanah, Yom Kippur, Hanukkah, each a single "... begins" marker on the evening it starts,
  i.e. the sundown before its first full day; dates from the Hebrew calendar via `pyluach`, with Purim moving to Adar II in leap years); Muslim
  (Ramadan begins, Eid al-Fitr, Eid al-Adha, predicted from the Umm al-Qura calendar via `hijridate`, valid 1924-2077; the observed day depends
  on moon sighting and can differ by a day, so those events carry a "predicted date: confirm" note in the Events tab and can be overridden with
  'Listed dates per year'); and optional popular observances (Mother's Day, Father's Day, Halloween, and others). Entries added by earlier
  versions of the lists are detected in Settings and can be moved to the trash in one click.
- **Meteor showers**: `reference/meteor_showers.json` has *typical* peak dates. Add verified dates for a year under `"years"`
  (from the IMO or AMS calendar); until then the proposals say "typical date, not verified".

## Regional festivals and fairs (Regional events tab)
For outdoor festivals and fairs across the 22 counties in the Columbus and Zanesville markets. Sources only **propose** events; you accept or reject
each one, a rejected one never returns, and accepted ones go in a "Regional festivals & fairs" category (its own black-and-white style) tagged with the
county and a "confirm dates" note. Counties come from the event's ZIP code (a ZIP that straddles counties gets its primary county).

- **Experience Columbus**: the site has no calendar feed or open API (its data service refuses direct requests, which we respect), so the app reads its
  public event pages: it finds them through the sitemap, keeps festival-like addresses (editable word lists), reads each page's title line
  (name, dates, city and ZIP), waits 2 seconds between pages as the site's robots.txt asks, caches what it reads, and fetches in batches of 60.
- **Calendar (.ics) feeds**: add any visitors bureau or fairground feed in Sources. All-day events are handled correctly (the end date in a feed is exclusive).
- **Ohio Department of Agriculture fair schedule**: reads the official "Ohio Agricultural Fair Chronological Schedule" brochure (PDF): the Ohio State Fair,
  every county fair and the independent fairs, with dates. `agri.ohio.gov` refuses automated downloads, so upload the year's brochure in Sources (ODA
  publishes it each December); a copy of the 2026 one is bundled in `reference/`. The 2026 brochure covers all 22 counties (25 fairs). Fairs already over are
  skipped unless you tick the box.
- **ohio.org Festivals & Events** (TourismOhio): the site's pages load every event from one public JSON search; the app makes that single request (the path
  is not covered by its robots.txt), keeps events whose address ZIP falls in your counties and whose title/address has a festival-like word or whose topic is
  fairs/festivals, and proposes them. **Untested against the live site**: ohio.org returns an error page to automated requests from some networks (it did from
  the build server), and the response shape was written from the page's own script and two sample pages. Only the date of each event is used (its times of day
  are placeholders; WinterFest Columbus is one day despite a weekly hours table on its page). If the button reports an error, the site is refusing the request.
- **Visitors-bureau event data** (checked 2026-10-30, all 22 counties): only **Athens County** publishes a usable event feed (The Events Calendar's public
  JSON, read 50 events at a time, 10 seconds apart as its robots.txt asks, festival-like words only). The others have no calendar feed: Franklin
  (Experience Columbus, above); Fairfield, Guernsey and Madison publish an "events" RSS whose dates are only in the text or title, and Coshocton, Ross and Perry's
  county site publish blog-post or government-meeting feeds. Delaware, Hocking, Knox, Licking, Marion, Morgan, Muskingum and Pike have visitor sites with no feed at the usual
  addresses. No official bureau site was found for Crawford, Fayette, Hardin, Morrow, Pickaway or Union. If a bureau gives you an `.ics` address, add it under Calendar feeds.

## Layout
    app.py                  Streamlit UI + passcode gate
    calendar_core/          db, recurrence, astro, climo, milestones, render_pdf, patterns, importers, ical, preview
    reference/              bundled 2026 sun data, climo tables, meteor table
    tests/                  pytest suite
    scripts/backup.py       database backup used by the nightly GitHub Action
