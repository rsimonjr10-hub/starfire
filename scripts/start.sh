#!/bin/sh
# Railway startup script — waits for DB, runs migrations, then starts server

set -e

echo "STARFIRE starting up..."

# Wait for PostgreSQL to be ready (Railway can boot DB after app service)
MAX_TRIES=30
TRIES=0
until python -c "
import asyncio, asyncpg, os, sys
async def check():
    url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
    try:
        conn = await asyncpg.connect(url, timeout=3)
        await conn.close()
        print('DB ready')
    except Exception as e:
        print(f'DB not ready: {e}', file=sys.stderr)
        sys.exit(1)
asyncio.run(check())
" 2>/dev/null; do
  TRIES=$((TRIES+1))
  if [ "$TRIES" -ge "$MAX_TRIES" ]; then
    echo "Database never became ready. Exiting."
    exit 1
  fi
  echo "Waiting for database... ($TRIES/$MAX_TRIES)"
  sleep 2
done

echo "Running database migrations..."
alembic upgrade head

echo "Starting STARFIRE server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
