#!/bin/bash
set -e

# Prod startup. Migrations + collectstatic only for the WEB service (gunicorn) —
# the worker/beat (celery) share this image but must NOT re-run migrations
# (concurrent migrate_schemas race) or collectstatic (they don't serve static).
# Then exec the service command (gunicorn for web, celery for worker/beat).
if [ "$1" = "gunicorn" ]; then
    python manage.py migrate_schemas --shared
    python manage.py migrate_schemas --tenant
    python manage.py collectstatic --noinput
fi

exec "$@"
