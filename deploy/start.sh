#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check_stripe_sandbox
python manage.py check_live_stripe_account --verify-provider || echo "Live account read-only check unavailable; existing customer service continues."
python manage.py verify_stripe_test_connection || echo "Stripe identity verification unavailable; account service continues."
# Provider-only QA is OFF by default, guarded by one-shot flag and deadline.
# It only creates/expires a TEST Checkout session; no app/customer database writes.
python manage.py stripe_checkout_provider_smoke || echo "Stripe provider smoke unavailable; account service continues."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 30 --access-logfile -
