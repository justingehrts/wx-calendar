"""Fetched data files (USNO years, ACIS tables). Stored in the database when a hosted database is
configured (so they survive restarts on ephemeral-disk hosts), otherwise in data/cache/. Falls back to
the bundled files in reference/."""
import json, os, time
from . import db, paths

_mem = {}              # name -> (stamp, checked_at, text)
_TTL = 60              # seconds between freshness checks in database mode

def _remote(): return db.turso_config() is not None

def _read_raw(name):
    if _remote():
        r = db._tuples(db.connect(), "SELECT value, updated_at FROM cache_files WHERE name=?", (name,))
        if r: return r[0][0], r[0][1]
    else:
        p = os.path.join(paths.CACHE, name)
        if os.path.exists(p): return open(p).read(), str(os.path.getmtime(p))
    p = os.path.join(paths.REFERENCE, name)
    if os.path.exists(p): return open(p).read(), "ref"
    return None, None

def load_text(name):
    """Text of `name`, or None. Re-checks the source at most every 60 s in database mode."""
    hit = _mem.get(name); now = time.time()
    if hit and (not _remote() and _stamp_file(name) == hit[0] or _remote() and now - hit[1] < _TTL): return hit[2]
    text, stamp = _read_raw(name); _mem[name] = (_stamp_file(name) if not _remote() else stamp, now, text); return text

def _stamp_file(name):
    p = os.path.join(paths.CACHE, name)
    return str(os.path.getmtime(p)) if os.path.exists(p) else "ref"

def load_json(name):
    t = load_text(name); return json.loads(t) if t else None

def write(name, text):
    if _remote():
        con = db.connect()
        con.execute("INSERT OR REPLACE INTO cache_files(name,value,updated_at) VALUES(?,?,?)", (name, text, db.now())); con.commit()
    else:
        os.makedirs(paths.CACHE, exist_ok=True); tmp = os.path.join(paths.CACHE, name + ".tmp")
        open(tmp, "w").write(text); os.replace(tmp, os.path.join(paths.CACHE, name))
    _mem.pop(name, None)

def has_cached(name):
    """True if a fetched (not just bundled) copy exists."""
    return _read_raw(name)[1] not in (None, "ref")
