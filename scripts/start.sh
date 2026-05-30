#!/bin/sh
# Railway startup script — waits for DB port, runs migrations, starts server

set -e

echo "STARFIRE starting up..."

# Extract host and port from DATABASE_URL for TCP check
DB_HOST=$(python3 -c "
import os, urllib.parse
url = os.environ.get('DATABASE_URL', '')
p = urllib.parse.urlparse(url.replace('+asyncpg',''))
print(p.hostname or 'localhost')
")
DB_PORT=$(python3 -c "
import os, urllib.parse
url = os.environ.get('DATABASE_URL', '')
p = urllib.parse.urlparse(url.replace('+asyncpg',''))
print(p.port or 5432)
")

echo "Waiting for database at $DB_HOST:$DB_PORT..."

MAX_TRIES=40
TRIES=0
until python3 -c "
import socket, sys
try:
    s = socket.create_connection(('$DB_HOST', $DB_PORT), timeout=3)
    s.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
  TRIES=$((TRIES+1))
  if [ "$TRIES" -ge "$MAX_TRIES" ]; then
    echo "Database never became ready. Exiting."
    exit 1
  fi
  echo "Waiting for database... ($TRIES/$MAX_TRIES)"
  sleep 3
done

echo "Database port open."

echo "Running database migrations..."
alembic upgrade head

echo "Starting STARFIRE server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
