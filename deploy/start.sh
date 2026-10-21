#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput
# Only report whether values exist; never print credentials.
python manage.py check_stripe_sandbox
# Read-only Stripe API identity/mode check; do not block existing customers if
# Stripe is temporarily unavailable. No billing feature switch is changed.
python manage.py verify_stripe_test_connection || echo "Stripe identity check could not complete; customer services continue."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 30 --access-logfile -
