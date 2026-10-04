"""SQLite storage (WAL mode). All data access goes through this module so the
backend can be swapped later if hosting requires it."""
import os, sqlite3, datetime as dt

DB_PATH = os.environ.get("CALENDAR_DB", os.path.join(os.path.dirname(__file__), "..", "data", "calendar.db"))

# bw_style: solid_dark, medium_gray, light_gray, hatch, dots, outline
DEFAULT_CATEGORIES = [
    ("Sports", "#1F5FA8", "solid_dark", "Clippers,Crew,OSU,Aviators,Tournament,Tourney,Open"),
    ("Sky / Astronomy", "#6B3FA0", "hatch", "moon,peak,equilux,begins,Last sun,sunset,eclipse"),
    ("Climo records", "#D9622B", "dots", "Avg,Earliest,Latest,snow,freeze"),
    ("Community events", "#2E8B57", "medium_gray", ""),
    ("Holidays", "#555555", "outline", "Halloween,Veterans,Thanksgiving,Christmas,Hanukkah,DST,Labor Day,Mother,Father,Memorial Day,Juneteenth,Fourth"),
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
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS ix_events_start ON events(start_date);
"""

def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
        for i, (n, c, s, k) in enumerate(DEFAULT_CATEGORIES):
            con.execute("INSERT INTO categories(name,color_hex,bw_style,keywords,sort_order) VALUES(?,?,?,?,?)", (n, c, s, k, i))
        con.commit()
    return con

def now(): return dt.datetime.now().isoformat(timespec="seconds")

def categories(con): return [dict(r) for r in con.execute("SELECT * FROM categories ORDER BY sort_order,id")]

def category_id_by_name(con, name):
    r = con.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
    return r["id"] if r else None

def categorize(con, title):
    """First category whose keywords match the title (case-insensitive); else fallback."""
    for c in categories(con):
        for kw in filter(None, (k.strip() for k in c["keywords"].split(","))):
            if kw.lower() in title.lower(): return c["id"]
    return category_id_by_name(con, FALLBACK_CATEGORY)

def add_event(con, title, start, end=None, category_id=None, **kw):
    t = now()
    cur = con.execute(
        "INSERT INTO events(title,start_date,end_date,category_id,time,location,notes,url,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (title, str(start), str(end) if end and str(end) != str(start) else None,
         category_id or categorize(con, title), kw.get("time"), kw.get("location"), kw.get("notes"), kw.get("url"), t, t))
    con.commit(); return cur.lastrowid

def update_event(con, event_id, **fields):
    allowed = {"title", "start_date", "end_date", "category_id", "time", "location", "notes", "url"}
    f = {k: v for k, v in fields.items() if k in allowed}
    if not f: return
    con.execute(f"UPDATE events SET {','.join(k+'=?' for k in f)}, updated_at=? WHERE id=?", (*f.values(), now(), event_id))
    con.commit()

def delete_event(con, event_id):  # soft delete
    con.execute("UPDATE events SET deleted_at=? WHERE id=?", (now(), event_id)); con.commit()

def events(con, include_deleted=False):
    q = "SELECT e.*, c.name AS category FROM events e LEFT JOIN categories c ON c.id=e.category_id"
    if not include_deleted: q += " WHERE e.deleted_at IS NULL"
    return [dict(r) for r in con.execute(q + " ORDER BY e.start_date, e.title")]

def events_on_day(con, day):
    """Events covering `day` (a date), expanding multi-day spans."""
    d = str(day)
    return [e for e in events(con) if e["start_date"] <= d <= (e["end_date"] or e["start_date"])]
