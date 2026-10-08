"""Download a copy of the hosted (Turso) database as a SQLite file. Used by the nightly GitHub Action.
    TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... python scripts/backup.py backup.db"""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from calendar_core import db

def fail(msg):
    print(f"::error title=Database backup failed::{msg}")     # shows up as the annotation on the run page
    print(msg, file=sys.stderr); sys.exit(1)

out = sys.argv[1] if len(sys.argv) > 1 else "calendar_backup.db"
missing = [k for k in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN") if not os.environ.get(k)]
if missing:
    fail(f"Missing repository secret(s): {', '.join(missing)}. Add them under GitHub > Settings > Secrets and variables > Actions > Repository secrets.")
try:
    with tempfile.TemporaryDirectory() as tmp:
        con = db.connect(os.path.join(tmp, "replica.db"))
        data = db.backup_bytes(con)
        n = db._tuples(con, "SELECT COUNT(*) FROM events")[0][0]
except Exception as ex:
    fail(f"Could not read the hosted database ({type(ex).__name__}: {ex}). Check that the URL starts with libsql:// and the token is valid and has not expired.")
open(out, "wb").write(data)
print(f"Backed up {n} event row(s) to {out} ({len(data):,} bytes)")
