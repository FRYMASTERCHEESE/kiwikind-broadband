# Stripe on the current KiwiKind stack

## Scope and limits

This integration targets `feature/neon-postgres-config`, including owner Google/MFA, PostgreSQL, customer/session fixes and the manual catalogue. It does NOT merge older PRs #35/#36 or rewrite their conflicting migrations. It introduces a separate `payments` app with three new **test-only** tables and preserves the existing invoice/order tables. No supplier quotes, addresses, private contracts, actual card details or secrets belong in this public repository.

Live payments are **not implemented or enabled by this release**. A successful CLI login or unit-test suite does not prove a Stripe sandbox exercise or production readiness. Public plan publication and supplier order submission remain separate and disabled. Customer retail prices, plan speed, GST treatment, setup charge, contract/cancellation terms, service availability and charge-start date require explicit owner decisions and supplier confirmation before a real sales release. No price from the owner's screenshots is published or inserted into Stripe.

## Shared customer flow

Existing customer portal Billing links to `/billing/`; the Android Billing screen links to its native test-billing screen. Both use the same session-protected `/api/billing/summary`, `/api/billing/checkout` and `/api/billing/cancel` APIs. A customer only sees agreements assigned to that authenticated account and explicitly reviewed by the owner. Inactive testing shows no payable amount/due demand.

An explicit consent action sends an agreement ID and its terms version, not a browser-supplied amount or arbitrary price ID. A concurrent owner edit invalidates previously displayed terms. Once an attempt starts, its inputs are locked against admin edits. The first attempt is persisted before network access and uses a deterministic Stripe idempotency key. Old attempts require reconciliation instead of silent recreation after the provider's idempotency retention window.

The server verifies the expected Stripe account and test-mode access. Only exact Stripe test Checkout URLs may open. Returning from Stripe is not proof of payment. Verified, account/mode/version-checked webhooks reconcile the provider's current state under agreement locks; invoices, refunds and dispute status stay in the isolated test ledger. No callback activates broadband. Customer-owned test records are included in account export and the existing manual deletion-review process.

The owner can review full test refunds from the private sandbox invoice admin. That action requires the existing verified Google/OTP session, CSRF and explicit confirmation. Test refunds do not cancel subscriptions. Live keys, live objects, altered amounts, mismatched customers, unknown checkout bindings and stale forms are rejected.

## Private configuration (required before provider testing)

Create/select a dedicated Stripe sandbox in the actual KiwiKind Stripe Dashboard. Never paste keys into ChatGPT, issues, logs, screenshots or PowerShell history. CLI credentials on a developer computer are not automatically present on Render. Use the hosting dashboard's private environment editor, preserving all current database, Google, email and Django secrets.

- `KIWIKIND_STRIPE_SANDBOX=0` initially. Leave off during deployment.
- `STRIPE_TEST_SECRET_KEY`: the server-side test key (secret or correctly permissioned restricted key) for the chosen sandbox.
- `STRIPE_TEST_ACCOUNT_ID`: the account ID for that sandbox/key, independently confirmed in Stripe.
- `STRIPE_TEST_WEBHOOK_SECRET`: signing secret for the sandbox webhook endpoint, NOT an API key and NOT a CLI listener secret unless testing a local listener.
- API version for endpoint events: **2026-09-30.endive**, matching pinned `stripe==16.0.0`.
- Endpoint on the deployed server: `https://kiwikind-backend.onrender.com/api/billing/webhook`. Do not configure it before the candidate is deployed.
- Events: checkout.session.completed; customer.subscription.created/updated/deleted; invoice.paid/payment_failed/voided/marked_uncollectible/finalized; charge.refunded; charge.dispute.created/updated/closed.
- Keep `PLAN_PUBLICATION_ENABLED=0`, `INTAKE_ENABLED=0` and old Stripe checkout flags at zero. This change does not use or override the old draft's flags.

Restricted-key access needs account and balance reads plus the test resources used here: Checkout sessions, subscriptions, invoices/invoice payments, PaymentIntents, charges, disputes and refunds. Do not solve a permission failure by switching to a live key. The operator command `python manage.py check_stripe_sandbox --verify-provider` checks identity/mode without payment mutations and prints no secrets. The owner-only `/admin/billing-readiness/` reports only configuration booleans and outstanding release tasks.

After private configuration is verified, explicitly enable the sandbox switch, create ONE reviewed synthetic agreement from the private admin for a controlled test account, and use Stripe test payment details only. Do not seed test customers into existing real customer accounts by migration. Displayed test amounts are totals, not proof of GST registration or an approved retail offer.

## Provider tests still required

Record actual results from Stripe: successful initial recurring checkout, renewal (including test clocks when supported), declined payment, authentication-required payment, closing/reopening Checkout, duplicated and out-of-order webhooks, interruption/retry with the same agreement, cancellation, full refund and dispute notification. Confirm actual API payloads match the pinned SDK/API version. Verify both the browser and Android use the same account/ledger. Test with the Google-enabled signed Android build separately; a CI debug APK is not a Play release and may use a different certificate.

This implementation reconciles synchronously. Before a live release, validate webhook response times and failure/retry handling under realistic load, and use a durable queue if required. Unmatched financial events fail closed for operator review; a dedicated sandbox prevents unrelated test traffic from being mistaken for KiwiKind activity. Proration, manual invoice adjustments, credits, multiple invoice-payment allocations, partial refund requests and production billing are deliberately unsupported here rather than silently guessed.

## Rollout and rollback

Review the PR and require SQLite, PostgreSQL, web, Android and synthetic browser CI. Preserve a recoverable database checkpoint before applying the additive migration. No destructive migration or account rewrite is included. Existing backend startup applies migrations and collects static assets. Deploy only the reviewed commit onto the existing deployment branch; keep all new switches off. Verify health, empty public plans, owner-only admin and closed intake. Configuration is an independent private step; do not claim it was performed merely because code deployed.

Rollback: disable `KIWIKIND_STRIPE_SANDBOX` and retain the new records for reconciliation. A previous code image can ignore these extra tables. Do not reverse migrations, drop test records or restore over newer customer activity to roll back UI changes.
