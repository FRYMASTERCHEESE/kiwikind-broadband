# Stripe checkout staging — NOT live billing

**Superseded implementation details:** this branch extends the original PR #35 staging. Use [owner and billing readiness](OWNER_AND_BILLING_READINESS.md) for current MFA, synthetic ledger restrictions, required webhook secret, recurring billing, refunds and remaining production gates. Historical limitations below describe the original PR. Live billing remains disabled.

This branch introduces a **disabled-by-default test-only** hosted Stripe Checkout action for *existing, staff-created unpaid NZD ledger invoices*. It does not issue invoices, create subscriptions, update paid status, provision Vetta services, or collect live payments. The existing website and Android accounts remain unchanged. Android clients can eventually call the same authenticated backend endpoint after native UX and CSRF/session checks.

## Gates

All three environment variables are required on the secure Django server (never GitHub Pages, browser JS or Android):

- `STRIPE_TEST_CHECKOUT_ENABLED=1`
- `STRIPE_TEST_PRICE_REVIEWED=1` (operator has explicitly checked the synthetic invoice)
- `STRIPE_TEST_SECRET_KEY=sk_test_...` (Stripe test-mode secret)

Default is disabled. **Never** set these in production until a separate security review, verified Stripe webhooks, invoice lifecycle and refunds are implemented. Do not substitute a live secret. The checkout URL must be returned from Stripe and points to Stripe's hosted domain. Returning from Stripe does not mean an invoice is paid.

## Known limitations / launch blockers

- Existing invoice ledger is read-only; no invoice issuance or recurring subscription engine.
- No webhook verification, settlement reconciliation, chargeback/refund handling or double-charge protection across providers.
- No GoCardless integration yet.
- No Android payment action yet.
- No confirmed deployed backend and no live payment activation.
- Vetta orders remain manual and disabled by default.

Run `python manage.py test --settings=config.test_settings` and `node --check site/dist/app.js` before review. Use synthetic invoices only; test card payments are not live funds.
