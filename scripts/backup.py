"""Download a copy of the hosted (Turso) database as a SQLite file. Used by the nightly GitHub Action.
    TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... python scripts/backup.py backup.db"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from calendar_core import db

out = sys.argv[1] if len(sys.argv) > 1 else "calendar_backup.db"
if not db.turso_config(): sys.exit("TURSO_DATABASE_URL / TURSO_AUTH_TOKEN not set")
con = db.connect(os.path.join(os.path.dirname(os.path.abspath(out)) or ".", "replica_tmp.db"))
open(out, "wb").write(db.backup_bytes(con))
n = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
print(f"Backed up {n} event row(s) to {out}")
