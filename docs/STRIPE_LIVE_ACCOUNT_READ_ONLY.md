# KiwiKind Stripe live-account verification (READ ONLY)

The owner has already completed Stripe Identity checks; do not ask them to
repeat identity verification. Stripe Identity completion is not the same
technical state as whether a Stripe Payments merchant account reports
live charges_enabled and payouts_enabled.

The existing deployed Stripe code is explicitly test-only. This change
does NOT merge draft PR #41 or add production payment routes. No customer
can be charged by these diagnostics.

Private Render configuration, whenever the owner chooses to supply it:

- STRIPE_LIVE_SECRET_KEY: LIVE secret/restricted server key, from Stripe.
- STRIPE_LIVE_ACCOUNT_ID: expected LIVE account ID from Stripe.
- STRIPE_LIVE_WEBHOOK_SECRET: production signing secret; do not create a
  webhook pointing to a route that is not deployed.

Keep all secrets in the Render environment editor only, preserving existing
Google auth, Django, Neon and email settings. Never paste keys into chat,
issues, GitHub, Android, JavaScript or screenshots. Do not accidentally
replace all Render variables. The existing sandbox uses separate keys.

Private URL, after owner Google + TOTP MFA:
https://kiwikind-backend.onrender.com/admin/live-stripe-readiness/

The "Check live account status" button does two GET-like Stripe reads:
retrieve_current account and balance. No Checkout, PaymentIntent, subscription,
invoice, product, customer or refund is created. The pinned account ID and
balance must match live mode before reporting charges/payout flags. The response
contains no raw Stripe IDs, secret material or exception messages.

The startup management check has an explicit --verify-provider option and
prints only booleans. It never enables checkout and never affects live customer
sessions; a transient provider error is reported without stopping Django.

Production live billing remains blocked until independently tested live
models, consented per-customer agreements, current verified supplier terms,
stable idempotency, live webhooks/reconciliation, signed Android/web paths,
real-mode provider identity/permissions and owner release approval are complete.
The unfinished PR #41 is not safe to deploy as-is. Do not treat this
diagnostic as authority to flip switches.
