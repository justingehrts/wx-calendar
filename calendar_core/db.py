"""SQLite storage (WAL mode). All data access goes through this module so the backend can be
swapped later if hosting requires it."""
import datetime as dt, json, os, re, sqlite3, tempfile
from . import recurrence

DB_PATH = os.environ.get("CALENDAR_DB", os.path.join(os.path.dirname(__file__), "..", "data", "calendar.db"))

# bw_style: solid_dark, medium_gray, light_gray, hatch, dots, outline
DEFAULT_CATEGORIES = [
    ("Sports", "#1F5FA8", "solid_dark", "Clippers,Crew,OSU,Aviators,Tournament,Tourney,Open"),
    ("Sky / Astronomy", "#6B3FA0", "hatch", "moon,peak,equilux,begins,Last sun,sunset,sunrise,eclipse,solstice,equinox,meteor"),
    ("Climo records", "#B8501E", "dots", "Avg,Earliest,Latest,snow,freeze"),
    ("Community events", "#2E7D4F", "medium_gray", ""),
    ("Holidays", "#555555", "outline", "Halloween,Veterans,Thanksgiving,Christmas,Hanukkah,DST,Labor Day,Mother,Father,Memorial Day,Juneteenth,Fourth,New Year,Presidents"),
]
FALLBACK_CATEGORY = "Community events"

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, color_hex TEXT NOT NULL,
  bw_style TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rules(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, params_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT,
  category_id INTEGER REFERENCES categories(id), rule_id INTEGER REFERENCES rules(id),
  time TEXT, location TEXT, notes TEXT, url TEXT,
  detail_only INTEGER NOT NULL DEFAULT 0, flag TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS ix_events_start ON events(start_date);
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY, event_id INTEGER, at TEXT NOT NULL, action TEXT NOT NULL,
  before_json TEXT, after_json TEXT, undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS milestone_decisions(
  key TEXT PRIMARY KEY, status TEXT NOT NULL, decided_at TEXT NOT NULL, event_id INTEGER);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS regional_candidates(
  id INTEGER PRIMARY KEY, source TEXT NOT NULL, uid TEXT NOT NULL, title TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  city TEXT, county TEXT, url TEXT, fetched_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', event_id INTEGER, UNIQUE(source, uid));
CREATE TABLE IF NOT EXISTS cache_files(name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
"""
EDITABLE = ["title", "start_date", "end_date", "category_id", "time", "location", "notes", "url", "detail_only", "flag"]

# ----------------------------------------------------------------- backends
# Default: a local SQLite file (WAL mode). If TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set, the data
# lives in a hosted Turso database (SQLite-compatible) through an embedded replica, so it survives hosts
# with ephemeral disks such as Streamlit Community Cloud.
class Row(dict):
    """Dict row that also supports row[0], like sqlite3.Row."""
    def __getitem__(self, k): return list(self.values())[k] if isinstance(k, int) else dict.__getitem__(self, k)

class _Cursor:
    def __init__(self, cur):
        self._c = cur
        self.lastrowid = getattr(cur, "lastrowid", None); self.rowcount = getattr(cur, "rowcount", -1)
        self._names = [d[0] for d in cur.description] if cur.description else []
    def _row(self, t): return None if t is None else Row(zip(self._names, t))
    def fetchone(self): return self._row(self._c.fetchone())
    def fetchall(self): return [self._row(t) for t in self._c.fetchall()]
    def fetchall_tuples(self): return [tuple(t) for t in self._c.fetchall()]
    def __iter__(self): return iter(self.fetchall())

class LibsqlConn:
    """Gives a libsql connection the small slice of the sqlite3 API this app uses."""
    is_libsql = True
    def __init__(self, raw): self._raw = raw
    def execute(self, sql, params=()): return _Cursor(self._raw.execute(sql, tuple(params)))
    def executescript(self, sql): self._raw.executescript(sql)
    def commit(self): self._raw.commit()
    def rollback(self): self._raw.rollback()
    def close(self): self._raw.close()
    def sync(self): self._raw.sync()

def turso_config():
    url, tok = os.environ.get("TURSO_DATABASE_URL"), os.environ.get("TURSO_AUTH_TOKEN")
    return (url, tok) if url and tok else None

_initialised = set()

def _init_schema(con, key):
    """Create tables / migrate / seed once per process (not on every Streamlit rerun)."""
    if key in _initialised: return
    con.executescript(SCHEMA)
    cols = {t[1] for t in _tuples(con, "PRAGMA table_info(events)")}   # migrate older files
    for c, ddl in (("detail_only", "INTEGER NOT NULL DEFAULT 0"), ("flag", "TEXT")):
        if c not in cols: con.execute(f"ALTER TABLE events ADD COLUMN {c} {ddl}")
    if not _tuples(con, "SELECT 1 FROM categories LIMIT 1"):
        for i, (n, c, s, k) in enumerate(DEFAULT_CATEGORIES):
            con.execute("INSERT INTO categories(name,color_hex,bw_style,keywords,sort_order) VALUES(?,?,?,?,?)", (n, c, s, k, i))
    con.commit(); _initialised.add(key)

def connect(path=None, libsql=False):
    """Open the database. `libsql=True` forces the libsql driver on a local file (used by the tests);
    Turso settings in the environment select the hosted database."""
    turso = turso_config()
    path = path or (os.path.join(tempfile.gettempdir(), "wxcal_replica.db") if turso else DB_PATH)
    if turso or libsql:
        import libsql as _l
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        raw = _l.connect(path, sync_url=turso[0], auth_token=turso[1]) if turso else _l.connect(path)
        con = LibsqlConn(raw)
        if turso: con.sync()                 # pick up other people's changes
        _init_schema(con, ("libsql", turso[0] if turso else os.path.abspath(path)))
        return con
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys=ON")
    _init_schema(con, ("sqlite", os.path.abspath(path)))
    return con

def now(): return dt.datetime.now().isoformat(timespec="seconds")

# ---------------------------------------------------------------- categories
CAT_COLS = ["id", "name", "color_hex", "bw_style", "keywords", "sort_order"]
def categories(con):
    return _named(con, "SELECT " + ",".join(CAT_COLS) + " FROM categories ORDER BY sort_order,id", (), CAT_COLS)

def category_id_by_name(con, name):
    r = _tuples(con, "SELECT id FROM categories WHERE name=?", (name,))
    return r[0][0] if r else None

def categorize(con, title):
    """First category whose keywords match the title (case-insensitive); else the fallback."""
    for c in categories(con):
        for kw in filter(None, (k.strip() for k in c["keywords"].split(","))):
            if kw.lower() in title.lower(): return c["id"]
    return category_id_by_name(con, FALLBACK_CATEGORY) or categories(con)[0]["id"]

def add_category(con, name, color_hex="#444444", bw_style="light_gray", keywords=""):
    order = _tuples(con, "SELECT COALESCE(MAX(sort_order),-1)+1 FROM categories")[0][0]
    rid = _insert(con, "INSERT INTO categories(name,color_hex,bw_style,keywords,sort_order) VALUES(?,?,?,?,?)",
                  (name, color_hex, bw_style, keywords, order), "SELECT id FROM categories WHERE name=?", (name,))
    con.commit(); return rid

def update_category(con, cid, **f):
    f = {k: v for k, v in f.items() if k in ("name", "color_hex", "bw_style", "keywords", "sort_order")}
    if f: con.execute(f"UPDATE categories SET {','.join(k+'=?' for k in f)} WHERE id=?", (*f.values(), cid)); con.commit()

def delete_category(con, cid, move_to):
    """Delete a category, moving its events (including trashed ones) to `move_to`."""
    if cid == move_to: raise ValueError("move_to must differ from the deleted category")
    con.execute("UPDATE events SET category_id=? WHERE category_id=?", (move_to, cid))
    con.execute("DELETE FROM categories WHERE id=?", (cid,)); con.commit()

def category_counts(con, year, month):
    """{category_id: number of events with a date in that month}."""
    out = {}
    for e in events(con):
        if any(d.month == month for d in recurrence.occurrence_dates(e, year)):
            out[e["category_id"]] = out.get(e["category_id"], 0) + 1
    return out

# -------------------------------------------------------------------- events
EVENT_COLS = ["id", "title", "start_date", "end_date", "category_id", "rule_id", "time", "location", "notes", "url",
              "detail_only", "flag", "created_at", "updated_at", "deleted_at"]
_NAMES = EVENT_COLS + ["category", "kind", "params_json"]

def _tuples(con, sql, params=()):
    """Rows as plain tuples (no column names involved)."""
    cur = con.execute(sql, params)
    return cur.fetchall_tuples() if hasattr(cur, "fetchall_tuples") else [tuple(r) for r in cur.fetchall()]

def _insert(con, sql, params, lookup_sql, lookup_params):
    """INSERT and return the new row id. The id is looked up by content, because hosted libsql connections
    do not reliably report lastrowid; falls back to lastrowid if the lookup finds nothing."""
    cur = con.execute(sql, params)
    found = _tuples(con, lookup_sql, lookup_params)
    return found[0][0] if found else cur.lastrowid

def _named(con, sql, params, cols):
    """Run a query and name the columns by position, independent of what the driver reports for column
    names (hosted libsql connections have returned unexpected names for wildcard selects)."""
    cur = con.execute(sql, params)
    raw = cur.fetchall_tuples() if hasattr(cur, "fetchall_tuples") else [tuple(r) for r in cur.fetchall()]
    return [dict(zip(cols, tuple(t) + (None,) * (len(cols) - len(t)))) for t in raw]

def _row(d):
    d = dict(d); pj, kind = d.pop("params_json"), d.pop("kind")
    d["rule"] = {**json.loads(pj), "kind": kind} if pj else None
    return d

_SEL = ("SELECT " + ",".join("e." + c for c in EVENT_COLS) + ", c.name, r.kind, r.params_json FROM events e "
        "LEFT JOIN categories c ON c.id=e.category_id LEFT JOIN rules r ON r.id=e.rule_id")

def get_event(con, event_id):
    rows = _named(con, _SEL + " WHERE e.id=?", (event_id,), _NAMES)
    return _row(rows[0]) if rows else None

def events(con, include_deleted=False, only_deleted=False):
    q = _SEL
    if only_deleted: q += " WHERE e.deleted_at IS NOT NULL"
    elif not include_deleted: q += " WHERE e.deleted_at IS NULL"
    return [_row(r) for r in _named(con, q + " ORDER BY e.start_date, e.title", (), _NAMES)]

def _log(con, event_id, action, before, after):
    con.execute("INSERT INTO history(event_id,at,action,before_json,after_json) VALUES(?,?,?,?,?)",
                (event_id, now(), action, json.dumps(before) if before else None, json.dumps(after) if after else None))

def _snap(e):
    if not e: return None
    s = {k: e.get(k) for k in EDITABLE + ["deleted_at"]}
    s["rule"] = e.get("rule"); return s

def _set_rule(con, rule):
    if not rule or rule.get("kind") == "one_off": return None
    p = {k: v for k, v in rule.items() if k != "kind"}
    pj = json.dumps(p)
    return _insert(con, "INSERT INTO rules(kind,params_json) VALUES(?,?)", (rule["kind"], pj),
                   "SELECT id FROM rules WHERE kind=? AND params_json=? ORDER BY id DESC LIMIT 1", (rule["kind"], pj))

def add_event(con, title, start, end=None, category_id=None, rule=None, log=True, **kw):
    t = now(); start = str(start)
    eid = _insert(con,
        "INSERT INTO events(title,start_date,end_date,category_id,rule_id,time,location,notes,url,detail_only,flag,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, start, str(end) if end and str(end) != start else None,
         category_id or categorize(con, title), _set_rule(con, rule), kw.get("time"), kw.get("location"),
         kw.get("notes"), kw.get("url"), int(bool(kw.get("detail_only"))), kw.get("flag"), t, t),
        "SELECT id FROM events WHERE created_at=? AND title=? AND start_date=? ORDER BY id DESC LIMIT 1", (t, title, start))
    if log: _log(con, eid, "create", None, _snap(get_event(con, eid)))
    con.commit(); return eid

def update_event(con, event_id, expect_updated_at=None, **fields):
    """Update fields (and `rule=` dict/None). If expect_updated_at is given and the row has changed
    since, nothing is written and False is returned (edit conflict)."""
    before = get_event(con, event_id)
    if not before: return False
    if expect_updated_at and before["updated_at"] != expect_updated_at: return False
    f = {k: v for k, v in fields.items() if k in EDITABLE}
    sets, vals = [f"{k}=?" for k in f], list(f.values())
    if "rule" in fields:
        sets.append("rule_id=?"); vals.append(_set_rule(con, fields["rule"]))
    if not sets: return True
    con.execute(f"UPDATE events SET {','.join(sets)}, updated_at=? WHERE id=?", (*vals, now(), event_id))
    _log(con, event_id, "update", _snap(before), _snap(get_event(con, event_id))); con.commit(); return True

def delete_event(con, event_id):  # soft delete -> trash
    before = get_event(con, event_id)
    if not before or before["deleted_at"]: return
    con.execute("UPDATE events SET deleted_at=?, updated_at=? WHERE id=?", (now(), now(), event_id))
    _log(con, event_id, "delete", _snap(before), _snap(get_event(con, event_id))); con.commit()

def restore_event(con, event_id):
    before = get_event(con, event_id)
    if not before or not before["deleted_at"]: return
    con.execute("UPDATE events SET deleted_at=NULL, updated_at=? WHERE id=?", (now(), event_id))
    _log(con, event_id, "restore", _snap(before), _snap(get_event(con, event_id))); con.commit()

def purge_event(con, event_id):
    con.execute("DELETE FROM events WHERE id=? AND deleted_at IS NOT NULL", (event_id,)); con.commit()

def events_on_day(con, day):
    """Events covering `day` (a date), expanding multi-day spans and repeat rules."""
    return [e for e in events(con) if day in recurrence.occurrence_dates(e, day.year)]

# ------------------------------------------------------------- history / undo
HISTORY_COLS = ["id", "event_id", "at", "action", "before_json", "after_json", "undone"]

def history(con, limit=100):
    q = ("SELECT " + ",".join("h." + c for c in HISTORY_COLS) + ", e.title FROM history h "
         "LEFT JOIN events e ON e.id=h.event_id ORDER BY h.id DESC LIMIT ?")
    return _named(con, q, (limit,), HISTORY_COLS + ["title"])

def undo_last(con):
    """Revert the most recent change that has not been undone. Returns a description or None."""
    rows = _named(con, "SELECT " + ",".join(HISTORY_COLS) + " FROM history WHERE undone=0 ORDER BY id DESC LIMIT 1", (), HISTORY_COLS)
    if not rows: return None
    h = rows[0]
    before = json.loads(h["before_json"]) if h["before_json"] else None
    eid = h["event_id"]
    if before is None:      # undoing a create -> move to trash
        con.execute("UPDATE events SET deleted_at=?, updated_at=? WHERE id=?", (now(), now(), eid))
    else:
        sets = [f"{k}=?" for k in EDITABLE + ["deleted_at"]]
        vals = [before.get(k) for k in EDITABLE + ["deleted_at"]]
        sets.append("rule_id=?"); vals.append(_set_rule(con, before.get("rule")))
        con.execute(f"UPDATE events SET {','.join(sets)}, updated_at=? WHERE id=?", (*vals, now(), eid))
    con.execute("UPDATE history SET undone=1 WHERE id=?", (h["id"],)); con.commit()
    title = (before or json.loads(h["after_json"]) or {}).get("title", "event")
    return f"Undid {h['action']} of “{title}”"

# ----------------------------------------------------------------- milestones
def milestone_status(con):
    return {k: v for k, v in _tuples(con, "SELECT key,status FROM milestone_decisions")}

def decide_milestone(con, key, status, event_id=None):
    con.execute("INSERT OR REPLACE INTO milestone_decisions(key,status,decided_at,event_id) VALUES(?,?,?,?)",
                (key, status, now(), event_id)); con.commit()

_OLD_EXTREME = "(key LIKE 'climo:%:earliest:%' OR key LIKE 'climo:%:latest:%')"   # computed from 1991-2020 only (superseded)

def outdated_climo_milestones(con):
    """Accepted milestone events whose calculation has since changed: [(key, event)]. Cases: climo earliest/latest entries made before extremes used
    the whole record; 'Avg' entries whose date is no longer what the current method gives (30-year xmACIS-style means); and meteor shower peaks whose
    dates or span changed (e.g. a typical date replaced by the American Meteor Society's peak night)."""
    from . import milestones
    out = []
    for key, eid in _tuples(con, f"SELECT key, event_id FROM milestone_decisions WHERE status='accepted' AND {_OLD_EXTREME}"):
        e = get_event(con, eid) if eid else None
        if e and not e["deleted_at"]: out.append((key, e))
    cache = {}
    for like, make in (("climo:%:avg:%", milestones.climo_milestones), ("meteor:%", milestones.meteor_milestones)):
        for key, eid in _tuples(con, f"SELECT key, event_id FROM milestone_decisions WHERE status='accepted' AND key LIKE '{like}'"):
            e = get_event(con, eid) if eid else None
            if not e or e["deleted_at"]: continue
            year = int(key.rsplit(":", 1)[1]); cache.setdefault((make, year), {r[0]: r for r in make(year)})   # rows: (key, title, date, category, note[, end])
            now_ = cache[(make, year)].get(key)
            if not now_: continue
            end = now_[5] if len(now_) > 5 else None
            if (str(now_[2]), str(end) if end else None, now_[1]) != (e["start_date"], e["end_date"], e["title"]): out.append((key, e))
    return out

def retire_outdated_climo_milestones(con):
    """Move those events to the trash (restorable) and forget their decisions so corrected proposals appear."""
    items = outdated_climo_milestones(con)
    for key, e in items:
        delete_event(con, e["id"]); con.execute("DELETE FROM milestone_decisions WHERE key=?", (key,))
    con.execute(f"DELETE FROM milestone_decisions WHERE {_OLD_EXTREME}"); con.commit()
    return len(items)

# ------------------------------------------------------------------- settings
def get_setting(con, key, default=None):
    r = _tuples(con, "SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r[0][0]) if r else default

def set_setting(con, key, value):
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value))); con.commit()

# ----------------------------------------------------------- holidays/rollover
def load_holidays(con, set_keys=("federal",)):
    """Add the chosen holiday sets as repeat rules (see holidays.py). Skips titles already present, so it is safe to repeat and
    shared titles (Christmas) are added once. Returns {set_key: number added}."""
    from . import holidays
    have = {e["title"] for e in events(con, include_deleted=True) if e["rule"]}
    cid = category_id_by_name(con, "Holidays") or categorize(con, "Holiday")
    added = {}
    for key in set_keys:
        _, _, items, flag = holidays.HOLIDAY_SETS[key]; n = 0
        for title, rule in items:
            if title in have: continue
            add_event(con, title, f"{dt.date.today().year}-01-01", None, cid, rule=rule, flag=flag); have.add(title); n += 1
        added[key] = n
    return added

def holiday_proposals(con, set_keys=None):
    """Holidays from the chosen sets (default: the 'holiday_sets' setting) that are waiting in Review: not already on the calendar as a
    repeating event (trash included) and not accepted or rejected before. Each holiday is asked about once, not every year.
    Returns [{key, title, rule, flag, set}] in set order, each title once."""
    from . import holidays
    set_keys = get_setting(con, "holiday_sets", []) if set_keys is None else set_keys
    have = {e["title"] for e in events(con, include_deleted=True) if e["rule"]}
    seen = milestone_status(con); out, titles = [], set()
    for k in set_keys:
        if k not in holidays.HOLIDAY_SETS: continue
        label, _, items, flag = holidays.HOLIDAY_SETS[k]
        for title, rule in items:
            key = f"holiday:{title}"
            if title in have or title in titles or key in seen: continue
            titles.add(title); out.append({"key": key, "title": title, "rule": rule, "flag": flag, "set": label})
    return out

def accept_holiday(con, item):
    """Add a proposed holiday as a repeating event (category Holidays) and remember the decision. Returns the event id."""
    cid = category_id_by_name(con, "Holidays") or categorize(con, "Holiday")
    eid = add_event(con, item["title"], f"{dt.date.today().year}-01-01", None, cid, rule=item["rule"], flag=item["flag"])
    decide_milestone(con, item["key"], "accepted", eid); return eid

def reject_holiday(con, item): decide_milestone(con, item["key"], "rejected")

def retired_holidays(con):
    """Events that earlier versions of the holiday sets created and that are no longer offered (title and rule both match)."""
    from . import holidays
    return [e for e in events(con) if e["rule"] and holidays.RETIRED.get(e["title"]) == e["rule"]]

def retire_holidays(con):
    """Move those events to the trash (restorable). Returns how many."""
    items = retired_holidays(con)
    for e in items: delete_event(con, e["id"])
    return len(items)

def load_federal_holidays(con):
    """Kept for compatibility: the federal set only. Returns the number added."""
    return load_holidays(con, ["federal"])["federal"]

def one_offs(con, year):
    """One-off (no repeat rule) events whose first day falls in `year` - these need review at rollover."""
    return [e for e in events(con) if not e["rule"] and e["start_date"].startswith(str(year))]

def lookup_rules_missing(con, year):
    return [e for e in events(con) if e["rule"] and e["rule"]["kind"] == "lookup_by_year"
            and str(year) not in e["rule"].get("table", {})]

def shift_year(iso, years):
    d = dt.date.fromisoformat(iso)
    try: return d.replace(year=d.year + years).isoformat()
    except ValueError: return d.replace(year=d.year + years, day=28).isoformat()   # Feb 29

def carry_forward(con, items):
    """items: [(event_id, new_start_iso, new_end_iso_or_None)] -> copies; originals are kept."""
    n = 0
    for eid, s, e in items:
        src = get_event(con, eid)
        add_event(con, src["title"], s, e, src["category_id"], time=src["time"], location=src["location"],
                  notes=src["notes"], url=src["url"], detail_only=src["detail_only"]); n += 1
    return n

def backup_bytes(con):
    """A consistent copy of the whole database as a SQLite file (bytes)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "backup.db"); dst = sqlite3.connect(p)
        if isinstance(con, sqlite3.Connection): con.backup(dst)
        else:      # libsql: copy schema and rows table by table
            for name, sql in _tuples(con, "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'libsql_%'"):
                dst.execute(sql); cols = [t[1] for t in _tuples(con, f'PRAGMA table_info("{name}")')]
                rows = _tuples(con, f'SELECT {",".join(cols)} FROM "{name}"')
                if rows: dst.executemany(f'INSERT INTO "{name}"({",".join(cols)}) VALUES({",".join("?" * len(cols))})', rows)
            dst.commit()
        dst.close(); return open(p, "rb").read()


def diagnose(con):
    """Plain-text report about what the driver returns for the history query (for troubleshooting hosted setups)."""
    import importlib.metadata as md
    out = []
    try: out.append(f"libsql {md.version('libsql')}")
    except Exception: out.append("libsql not installed")
    out.append("backend: " + ("hosted (Turso)" if turso_config() else "local file") + f"; connection type: {type(con).__name__}")
    cols = ", ".join(HISTORY_COLS)
    for label, sql, params in (("history rows (3 newest), positional", f"SELECT {cols} FROM history ORDER BY id DESC LIMIT 3", ()),
                               ("same with bound LIMIT", f"SELECT {cols} FROM history ORDER BY id DESC LIMIT ?", (3,)),
                               ("table_info(history)", "PRAGMA table_info(history)", ()),
                               ("counts", "SELECT (SELECT COUNT(*) FROM history), (SELECT COUNT(*) FROM events), (SELECT COUNT(*) FROM categories)", ())):
        try:
            rows = _tuples(con, sql, params)
            out.append(f"{label}: {len(rows)} row(s), lengths {[len(r) for r in rows]}")
            for r in rows[:3]: out.append("   " + repr(r)[:300])
        except Exception as ex: out.append(f"{label}: ERROR {type(ex).__name__}: {ex}")
    return "\n".join(out)


# ------------------------------------------------------------ regional event candidates
CAND_COLS = ["id", "source", "uid", "title", "start_date", "end_date", "city", "county", "url", "fetched_at", "status", "event_id"]

def upsert_candidate(con, source, uid, title, start, end, city, county, url):
    """Insert a candidate, or refresh the details of one still awaiting review. Accepted/rejected ones are left alone (a rejected one never
    returns). Returns 1 if it was new, else 0."""
    row = _tuples(con, "SELECT id, status FROM regional_candidates WHERE source=? AND uid=?", (source, uid))
    if row:
        if row[0][1] == "new":
            con.execute("UPDATE regional_candidates SET title=?, start_date=?, end_date=?, city=?, county=?, url=?, fetched_at=? WHERE id=?",
                        (title, str(start), str(end), city, county, url, now(), row[0][0])); con.commit()
        return 0
    con.execute("INSERT INTO regional_candidates(source,uid,title,start_date,end_date,city,county,url,fetched_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (source, uid, title, str(start), str(end), city, county, url, now())); con.commit(); return 1

def candidates(con, status="new"):
    return _named(con, "SELECT " + ",".join(CAND_COLS) + " FROM regional_candidates WHERE status=? ORDER BY start_date, title", (status,), CAND_COLS)

def get_candidate(con, cand_id):
    rows = _named(con, "SELECT " + ",".join(CAND_COLS) + " FROM regional_candidates WHERE id=?", (cand_id,), CAND_COLS)
    return rows[0] if rows else None

def decide_candidate(con, cand_id, status, event_id=None):
    con.execute("UPDATE regional_candidates SET status=?, event_id=? WHERE id=?", (status, event_id, cand_id)); con.commit()

def likely_duplicates(con, cand):
    """Existing calendar events with the same title (ignoring case/punctuation) overlapping the candidate's dates."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())
    return [e for e in events(con) if norm(e["title"]) == norm(cand["title"]) and e["start_date"] <= cand["end_date"] and (e["end_date"] or e["start_date"]) >= cand["start_date"]]
