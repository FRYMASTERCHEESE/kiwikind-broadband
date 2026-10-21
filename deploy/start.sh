#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput
# Existing read-only preflight prints booleans only; never keys, account IDs or webhooks.
# Do not test provider transactions or enable any payment setting at startup.
python manage.py check_stripe_sandbox
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 30 --access-logfile -
