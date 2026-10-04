#!/bin/sh
# Starts the app. With LITESTREAM_REPLICA_URL set, restores the database from the replica on a
# fresh disk and continuously replicates it while the app runs.
set -e
mkdir -p "$(dirname "$CALENDAR_DB")"
APP="streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0"
if [ -n "$LITESTREAM_REPLICA_URL" ]; then
  litestream restore -if-db-not-exists -if-replica-exists -config /app/litestream.yml "$CALENDAR_DB"
  exec litestream replicate -config /app/litestream.yml -exec "$APP"
fi
echo "WARNING: LITESTREAM_REPLICA_URL is not set; the database is NOT being backed up." >&2
exec $APP
