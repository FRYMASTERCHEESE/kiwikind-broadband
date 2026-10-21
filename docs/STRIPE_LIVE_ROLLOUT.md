# Customer-facing Stripe billing: release candidate

## What is implemented

Visible `/payments/` customer page; Android Payments & invoices screen using the same authenticated live-billing API; separate real customer agreement/invoice/webhook tables; server-owned final NZD totals; verified-owner approval and dated service-supply confirmation; immutable terms after consent; hosted recurring Stripe Checkout; signed and account/mode/version-pinned webhook reconciliation; cancellation at period end; owner-MFA full refunds; optional restricted customer portal. Existing sandbox billing, authentication, MFA, customer records, supplier workflows and unapproved catalogue records are preserved.

This is implementation, NOT proof of successful real Stripe testing or permission to charge customers. No customer agreement or retail price is seeded. Keep live switches, public plan publication and supplier ordering off until the owner authorises a verified release. The public website/app must not say real payments work merely because the new screens exist.

## Private configuration

Open owner-only `/admin/stripe-setup/` after Google sign-in plus MFA. It shows presence booleans and links to the existing Render environment editor. Do not share keys or screenshots of values in chat. `report_billing_config` safely reports only booleans in deployment logs.

Sandbox settings remain those in STRIPE_CURRENT_STACK.md. Live settings are `STRIPE_LIVE_SECRET_KEY` (dashboard-issued server/restricted live key), `STRIPE_LIVE_ACCOUNT_ID`, `STRIPE_LIVE_WEBHOOK_SECRET`. API/event version stays pinned to the installed Stripe SDK's existing version. Live endpoint: `/api/billing/live/webhook`. Test endpoint: `/api/billing/webhook`. Register them in their respective Stripe environments. Never reuse a CLI listener signing secret.

Checkout requires BOTH `KIWIKIND_LIVE_BILLING_ENABLED=1` and `KIWIKIND_LIVE_RELEASE_APPROVED=1`, valid live configuration, matching activated Stripe account, and a reviewed per-customer agreement. Each agreement must record the actual service, final monthly/setup totals, tax treatment, written contract/cancellation/refund terms and earliest billing date. Only the fixed verified owner may approve it. The customer accepts the versioned terms before being redirected to Stripe. No raw card details are collected by KiwiKind.

Card management optionally uses `STRIPE_LIVE_PORTAL_CONFIG_ID`. Its configuration must be active/live, forbid subscription plan changes, and allow cancellation only at period end. Billing cancellation and supplier-service cancellation are separate; tell customers this accurately. Stripe invoices require the merchant's own accurate tax/identity configuration. Do not infer GST registration from the company name.

## Safety and operational limits

Test and live tables and provider identities remain isolated. Amounts never come from a client request. A successful redirect is never recorded as payment. Existing attempts use the same idempotency key; old/expired/ambiguous attempts stop for reconciliation, rather than silently create another charge. Review such cases in Stripe and the private ledger before replacing an agreement. No checkout or supplier activation is automatic.

Webhooks fetch current provider state to tolerate reordered notifications. Receipt and ledger changes commit atomically; failures return non-2xx so Stripe retries. Endpoint processing is synchronous with bounded individual Stripe timeouts. Load/latency and retry tests are still a release prerequisite; add a durable worker before scale requires it. Do not assume a failed UI request means no transaction occurred.

Full refunds only; partial refunds, manual invoice adjustments, credits and multiple payment allocations require manual reconciliation and are not silently accepted. A refund does not cancel a subscription or broadband. Plan changes via the Stripe portal are disabled because they would bypass owner/customer consent. New checkout can be paused without blocking authenticated management or signed updates for existing transactions.

## Required release evidence

CI covers simulated live provider objects, real webhook signature verification, account separation, wrong mode/host/amount rejection, consent/version checks, duplicate retries, cancellation/refund ownership and deployment defaults. CI never uses live Stripe keys. Successful CI is not an actual Stripe transaction.

Before enabling: real Stripe sandbox checkout, renewal, declined/authentication-required payment, interruption/retry, duplicate/out-of-order webhook, cancellation, refund, card management; signed Android + browser testing; supplier supply/service-start confirmation; owner-approved customer terms/pricing; merchant charges/payout readiness; separate live release approval. Retain a recoverable database branch before the additive migration. Do not reverse migrations or restore over newer customer data to roll back UI changes. Disable new checkout and retain the ledger instead.

References: https://docs.stripe.com/api/checkout/sessions/create ; https://docs.stripe.com/webhooks ; https://docs.stripe.com/api/invoice-payment/object ; https://docs.stripe.com/api/customer_portal/configurations/object
