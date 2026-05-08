#!/bin/sh
set -euo pipefail

echo "[entrypoint] Preparing database (auto-migrate)" >&2

# If DATABASE_URL is absent, try to synthesize it from standard Postgres vars.
if [ -z "${DATABASE_URL:-}" ]; then
  if [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_DB:-}" ] && [ -n "${DB_PASSWORD:-}" ]; then
    : "${POSTGRES_HOST:=postgres}"
  # Use psycopg2 driver (we have psycopg2-binary installed). If you later add the psycopg (v3) package,
  # you can switch this to postgresql+psycopg://
  export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB}"
  echo "[entrypoint] Synthesized DATABASE_URL (psycopg2) for ${POSTGRES_USER}@${POSTGRES_HOST}/${POSTGRES_DB}" >&2
  else
    echo "[entrypoint] DATABASE_URL not set and insufficient POSTGRES_* vars to build it; migrations may fail" >&2
  fi
fi

if [ -n "${POSTGRES_USER:-}" ] && [ -n "${POSTGRES_DB:-}" ] && [ -n "${DB_PASSWORD:-}" ]; then
  echo "[entrypoint] Ensuring database ${POSTGRES_DB} exists" >&2
  python - <<'PY'
import os
import sys

import psycopg2
from psycopg2 import sql

host = os.getenv("POSTGRES_HOST", "postgres")
user = os.getenv("POSTGRES_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("POSTGRES_DB")

if not (user and password and database):
    sys.exit(0)

conn = psycopg2.connect(
    host=host,
    user=user,
    password=password,
    dbname="postgres",
)
conn.autocommit = True

try:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(sql.SQL("CREATE DATABASE {}") .format(sql.Identifier(database)))
finally:
    conn.close()
PY
fi

if [ "${SKIP_AUTO_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] SKIP_AUTO_MIGRATIONS=1 set; skipping migrations" >&2
else
  echo "[entrypoint] Running alembic upgrade head" >&2
  python -m alembic upgrade head || {
    echo "[entrypoint] Migration failed; exiting" >&2
    exit 1
  }
fi

echo "[entrypoint] Starting application: $*" >&2
exec "$@"
