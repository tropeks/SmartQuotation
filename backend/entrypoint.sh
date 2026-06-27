#!/bin/bash
set -e

# Prod startup: apply schema + tenant migrations and collect static files
# (WhiteNoise serves from STATIC_ROOT), then exec the service command passed by
# the image CMD / compose `command` (gunicorn for web, celery for worker/beat).
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant
python manage.py collectstatic --noinput

exec "$@"
