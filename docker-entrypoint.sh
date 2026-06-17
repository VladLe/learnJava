#!/usr/bin/env bash
set -e

# Wait for the database if a host is configured (compose sets DB_HOST).
if [ -n "$DB_HOST" ]; then
  echo "Waiting for database at $DB_HOST:${DB_PORT:-5432}…"
  until python -c "import socket,sys; s=socket.socket(); s.settimeout(2); s.connect(('$DB_HOST', int('${DB_PORT:-5432}'))); s.close()" 2>/dev/null; do
    sleep 1
  done
fi

# The scheduler process should not run migrations/collectstatic — only web does.
if [ "$RUN_MIGRATIONS" != "0" ]; then
  echo "Running migrations…"
  python manage.py migrate --no-input

  echo "Collecting static files…"
  python manage.py collectstatic --no-input
fi

exec "$@"
