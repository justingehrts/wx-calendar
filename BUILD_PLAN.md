# Weathercast Planning Calendar: Build Plan

A Streamlit app that lets the weather team keep one list of events and print a clean monthly planning calendar on a **black-and-white laser printer**. It replaces `Content_Idea_Calendar.xlsx`.

Read this whole file first. Section 12 lists decisions that still need the owner's input; ask before building anything those decisions affect.

---

## 1. Context

- Owner: Justin, broadcast meteorologist, Columbus, Ohio TV market. Comfortable with Python and Streamlit.
- Users: Justin plus other meteorologists who add and edit events. Nobody needs individual accounts.
- Output: one **US Letter, landscape** page per month, printed on a grayscale printer.
- Location for all astronomy and climate data: **Columbus, OH** (39.9612° N, 82.9988° W; climate station **CMH**). All times are **Eastern Time**, with DST handled correctly (the Nov 1, 2026 change must show correct sunrise and sunset).

## 2. What already exists (starting material)

Files delivered in the chat session. Treat them as a working prototype, not final code.

| File | What it does | Status |
|---|---|---|
| `cal.py` | Reads the old spreadsheet, renders 3 sample pages (Oct–Dec 2026) with reportlab | **Works.** Layout, spanning bars and moon icons are done. Uses PyEphem for sun and moon. |
| `fetch_usno.py` | Pulls sunrise/sunset from the U.S. Naval Observatory API into `astro_usno.json` | **Never run against the live API.** The build sandbox could not reach it. Verify first. |
| `fetch_climo.py` | Pulls daily normal highs and lows for CMH from RCC-ACIS into `climo.csv` | **Never run against the live API.** Records (record highs and lows) are not implemented. |
| UI mockup | Static mockup of the app: Events tab, Categories tab | https://claude.ai/artifact/77MEY8ChC6uQZ8JSxrg9D7 (owner can share). Follow its layout. |
| `Content_Idea_Calendar.xlsx` | The old template, with the 2026 events | Source for the first import (see section 6). |

Page layout in `cal.py` (keep it unless the owner says otherwise): 22 pt margins; header with month and year, subtitle, and category legend; mini calendars for the previous and next month at top right; Sun–Sat grid with only the weeks the month needs; each day cell shows the day number, a moon icon, event bars, a climo line and a sun line; two short note boxes at the bottom ("Content ideas & segments" and "Notes / To do").

## 3. Decisions already made

1. **Access:** simple shared **passcode**, no accounts. Recommend deploying on the newsroom network or a station computer, not the public internet. A passcode keeps casual visitors out; it is not real security.
2. **Categories:** one global list (name and color), the same all year. Managed on a Categories tab.
3. **Black-and-white printing is a primary requirement**, not an afterthought.
4. **No "priority/on-air" flag.**
5. **Sunrise/sunset definition:** upper limb of the Sun at the horizon with standard refraction (the USNO definition). Use the **Navy's API** as the authoritative source, with PyEphem as the offline fallback. The fallback must use the same definition (`horizon='-0:34'`, `use_center=False`, `pressure=0`).
6. **Moon phase icons and principal phase dates** are computed locally (PyEphem), converted to Eastern time. Verified: Full moons fall on Oct 26, Nov 24 and Dec 23 (Eastern) in 2026.
7. **Recurring series draw as one spanning bar** across consecutive days, broken at week boundaries. Already implemented in `cal.py`.

## 4. Architecture

Suggested layout (adjust if there's a better one):

```
planning-calendar/
  app.py                  # Streamlit entry point + passcode gate
  pages/ or tabs         # Events, Categories, (Details), Settings
  calendar_core/
    db.py                 # SQLite access (WAL mode), migrations
    models.py             # dataclasses for Event, Category, Rule
    recurrence.py         # repeat rules -> concrete dates
    astro.py              # sun/moon: USNO fetch + PyEphem fallback, cached
    climo.py              # ACIS normals/records, cached
    milestones.py         # auto-generated milestone proposals
    render_pdf.py         # reportlab page renderer (from cal.py)
    patterns.py           # B&W fill styles
  data/                   # calendar.db, caches (gitignored)
  tests/
  README.md
```

- **Storage:** SQLite, one file. Turn on WAL mode because several people may save at once. Provide CSV export and import so the owner can always get his data out.
- **Caching:** Cache USNO and ACIS results to disk by (year, location). Never block the UI on a network call; fall back to PyEphem if USNO is unavailable and show a small "using built-in calculation" notice.
- **Secrets:** passcode comes from `st.secrets` or an environment variable, never hard-coded.
- **Python libs already used:** `reportlab`, `ephem`, `openpyxl`, `streamlit`. Add others only when needed.

## 5. Data model

**Category**: `id`, `name`, `color_hex`, `bw_style`, `keywords` (comma separated), `sort_order`.

**Event**: `id`, `title`, `start_date`, `end_date` (nullable; multi-day), `category_id`, `rule_id` (nullable), `time`, `location`, `notes`, `url`, `added_by` (initials), `created_at`, `updated_at`, `deleted_at` (nullable; soft delete).

**Rule** (repeat definition): `kind` plus parameters. Kinds to support:
- `yearly_fixed`: month and day (e.g. Christmas)
- `yearly_nth_weekday`: nth weekday of a month (e.g. Thanksgiving, 4th Thursday of November), including "last" weekday (Memorial Day)
- `yearly_relative`: offset from another rule (optional; only if needed)
- `weekly_in_range`: certain weekdays between two dates (series like a homestand)
- `lookup_by_year`: dates that cannot be computed simply (Hanukkah, any lunar-based holiday). Use a table or a well-maintained library; ask the owner which holidays he wants.
- `one_off`: no rule

**History**: append-only change log (`event_id`, `who`, `when`, `action`, `before_json`, `after_json`). This enables undo (section 7, item 9).

Overlap behavior: an event can appear on many days; the renderer places consecutive-day runs as a single bar per week.

## 6. First import of existing events

Parse `Content_Idea_Calendar.xlsx` (2026). The structure, so you don't have to rediscover it:

- One sheet per month. Day grid starts in column D (Sun) through J (Sat).
- Date rows are 4, 6, 8, 10, 12, 14; event text is in the row directly **below** each date row.
- The first date row begins on the Sunday on or before the 1st of the month, so cells can belong to neighboring months. The same event may appear on two sheets; de-duplicate.
- A cell can hold several events separated by newlines or by runs of two or more spaces.
- Ignore the cell "NOTES:" and typed "Full moon" entries (moon phases are now computed).
- Auto-assign categories using the keyword rules in `cal.py` `cat()`, then let the owner review. Initial keyword lists: Sports (Clippers, Crew, OSU, Aviators, Tournament, Open), Sky (moon, peak, equilux, begins, sunset, eclipse), Climo (Avg, Earliest, Latest, snow, freeze), Holidays (Halloween, Veterans, Thanksgiving, Christmas, Hanukkah, DST, Labor Day, Mother, Father, Memorial Day, Juneteenth, Fourth), Community (everything else).
- Collapse consecutive-day repeats (e.g. "Clippers") into one multi-day event where it's unambiguous; otherwise import as single days and let the owner merge.
- Known oddity: a few typed items are things the app will now calculate (sun milestones, climo averages). Flag these as "could be auto-generated" rather than silently dropping them.

## 7. Features

### Core (build first)
1. **Events tab**: editable table (date, through, title, category), add/delete rows, import/export CSV, import the Excel file. Mirrors the mockup.
2. **Categories tab**: name, color picker, B&W style, keywords, count of events this month, delete with a "move events to…" prompt. Includes a **white-text contrast check** (WCAG ratio, flag below 4.5:1). Live print preview of legend and sample bars.
3. **Calendar PDF**: one month or all 12; Letter landscape; sidebar options for what appears (sun, moon, normals, records, daylight, notes boxes) and a **color / black-and-white** toggle.
4. **Per-day data**: sunrise/sunset, moon icon with labeled principal phases, normal high/low, record high/low (see section 8).
5. **Daylight length**: show hours:minutes and the change from the previous day in minutes:seconds, e.g. `11:43  −2:41`, on the sun line. Derive from the same sunrise/sunset values, so both come from one source.
6. **Passcode gate** (section 4).

### Repeats and year-to-year
7. **Repeat rules** as in section 5, with a rule editor in the Events tab. Show "next 3 occurrences" so people can sanity-check a rule.
8. **Year rollover**: one action to prepare next year. Fixed and rule-based events carry forward and recompute; one-off events are listed for review (keep, move, or drop). Never auto-delete.

### Team safety
9. **Added-by initials** (dropdown, remembered per browser session), **change history**, **undo**, and a **trash** that soft-deletes. Several people will edit one list; accidental deletes will happen. (Proposed; confirm with the owner that he wants the initials dropdown.)

### Layout protection
10. **Overflow warnings**: when a day or week has more event bars than fit, show it in the app ("Oct 31: 6 events, 2 won't fit") with options: shorten the title, mark one lower priority (it moves to the details page), or reduce bar font for that month. The PDF must never silently drop events. The existing "+N more" marker is a stopgap; replace it with a warning plus the details page.

### Event details
11. **Optional time, location, notes, link** per event, editable in a side panel.
12. **Details page**: optional second PDF page per month listing events that have details, grouped by date.

### Auto-generated milestones
13. A **Milestones** view proposes entries the owner can accept or reject (rejected ones don't come back). Candidates:
    - Sun: earliest/latest sunrise and sunset of the year, the last/first sunset after a round hour (e.g. 7 p.m., 8 p.m.), the last/first sunrise before a round hour, solstices, equinoxes, equilux, DST start/end.
    - Meteor shower peaks: use a small maintained table (Quadrantids, Lyrids, Eta Aquariids, Perseids, Orionids, Leonids, Geminids, etc.); verify dates for the target year against an authoritative source, don't hard-code from memory.
    - Climo: average first/last freeze, first/last 90° and 80°, average first/last measurable snow, earliest/latest 1" snow, from CMH data. **Definitions matter** (normals period, threshold, whether "average" means mean date); see section 12.

### Output extras (after the above works)
14. **PNG export** of a month for the graphics system; **iCal export** for phones.
15. **Page options**: week start day, paper size (Letter default).

## 8. Data sources and calculations

- **Sunrise/sunset: USNO API** `https://aa.usno.navy.mil/api/rstt/oneday?date=YYYY-MM-DD&coords=LAT,LON&tz=OFFSET&dst=false`. Send `tz=-5` or `-4` per date using America/New_York rules. Parse `properties.data.sundata` (entries with `phen` of Rise/Set). Public, no key. Run `fetch_usno.py` first, fix the parser if the layout differs, and **compare against the PyEphem fallback** for all 365 days; they should agree within about a minute. Report any larger differences to the owner.
- **Moon phases:** PyEphem (`next_new_moon`, `next_first_quarter_moon`, etc.), converted to Eastern *before* taking the calendar date. The USNO also offers a moon-phase service; optional cross-check.
- **Climo normals and records:** RCC-ACIS (`https://data.rcc-acis.org/StnData`, station `CMH`). `fetch_climo.py` pulls daily normals using `"normal":"1"`. **Records (daily record high/low) are not implemented**: work out the right ACIS query or a cached period-of-record calculation, and verify with a few known dates against NWS Wilmington/Columbus climate pages. Confirm the data's period of record and its threaded-station coverage for Columbus.
- **Network note:** the original build sandbox blocked both the USNO and ACIS hosts. In your environment, confirm both are reachable. If either goes down, the app must still print using cached or computed values and show a notice.

## 9. Black-and-white rendering

The printer is grayscale, so color alone cannot separate categories.

- Each category has a **B&W style** in addition to its color: *solid dark*, *medium gray*, *light gray*, *diagonal hatch*, *dots*, *outline only*. Provide sensible defaults so no two categories collide (the five default categories should be visually distinct in grayscale).
- Text color flips to match (white on dark fills, black on light fills and hatches). Hatch and dot patterns need a readable label area; test at 6.5 pt bold.
- The **legend and the event bars use the same style** so people can match them by eye.
- Weekend shading, spillover days and the moon icons must still read well in grayscale. Check for any fill that would print as a muddy gray.
- Add a **grayscale preview** in the app so users can see what the printer will produce.
- Validation: convert the PDF to grayscale (e.g. `pdftoppm -gray`) and inspect it; add a test that checks no two categories render the same fill style.

## 10. UI notes (from the mockup)

- Sidebar: month, year, location, "show on each day" checkboxes, **Generate PDF**, **Generate all 12 months**, source footer ("Sun and moon: U.S. Naval Observatory; normals and records: RCC-ACIS; last refreshed ...").
- Main area: title, tab bar (Events, Categories, and add Details/Milestones/Settings as needed), then Events table on the left and live month preview on the right.
- Keep the plain Streamlit look. Prioritize readable contrast over decoration.

## 11. Testing and acceptance

- **Unit tests:** recurrence rules (Thanksgiving, Memorial Day, DST dates for several years); week-boundary splitting of multi-day bars; contrast calculation; milestone logic.
- **Astronomy checks:** compare sunrise/sunset to the USNO for every day of 2026; verify the DST transition days; verify principal moon phase dates (2026: Full moon Oct 26, Nov 24, Dec 23 in Eastern time).
- **Rendering checks:** generate Oct–Dec 2026 from the imported spreadsheet data and compare against the prototype pages. Check a 6-week month (e.g. a month starting on Saturday) and a 4-week month (February 2026).
- **B&W test:** grayscale render has no two categories with the same look.
- **Concurrency:** two browser sessions saving at once do not lose data; undo works.
- **Acceptance:** the owner can add an event in the app, generate a page, print it on the newsroom printer, and read every event.

## 12. Questions to ask the owner before building

1. **Normals period and definitions:** use the 1991–2020 normals? Does "average first/last freeze" mean mean date across a stated period of record? Which thresholds (32°F) count?
2. **Hosting:** will this run on a newsroom computer, a station server, or a cloud host? That decides how the passcode is set and how data is backed up.
3. **Initials dropdown:** include it (section 7, item 9)?
4. **Schedule feeds:** should the app subscribe to team schedule calendar feeds (Clippers, Crew, OSU) instead of manual entry? If so, which, and are official feeds available?
5. **Holiday list:** which holidays should be automatic, including any religious and lunar-based ones?
6. **Weather-sensitive flag** (outdoor events like the State Fair or Pumpkin Show) was suggested but not yet decided. Ask.
7. **Backups:** where should the SQLite file be copied nightly?

## 13. Suggested order of work

0. **Verify the foundations**: run `fetch_usno.py` and `fetch_climo.py` with network access; reconcile with PyEphem; implement daily records. Do not build on unverified data.
1. Scaffold the app, the SQLite schema, the passcode gate and the CSV/Excel import.
2. Events and Categories tabs plus the PDF renderer, wired to live data (items 1–6).
3. B&W mode and the grayscale preview (section 9).
4. Repeat rules and year rollover (items 7–8).
5. Overflow warnings, event details and the details page (items 10–12).
6. Change history, undo and trash (item 9).
7. Milestones (item 13), then output extras (items 14–15).

Show the owner the printed page at each step; he is the judge of layout.
