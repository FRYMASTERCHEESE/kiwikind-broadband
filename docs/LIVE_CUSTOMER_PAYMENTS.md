# Live customer payments

This implementation keeps production payments separate from the tested sandbox
ledger and from broadband intake, catalogue publication and supplier ordering.
It seeds no offers or prices. It never places a Vetta order or provisions service.

## Prices and offers

The owner creates a private `payment-agreements` record in the existing Pages
owner interface after Google sign-in and MFA. Enter the combined confirmed
supplier monthly and setup amounts in integer cents, excluding GST. The server
calculates GST and the existing GST-inclusive baseline allowances once per
agreement, then applies the selected immutable `pricing_policy`: `legacy_v1`
for historic rates, `all_in_v2` for collection-inclusive prices, and `all_in_v3`
for the same full GST-inclusive pricing with an additional NZ$4/month (never
an extra setup fee). Current catalogue quotes use `all_in_v3` while the server
all-in release setting is enabled. See `docs/ALL_IN_RETAIL_PRICING.md`;
no processing surcharge is added later at checkout. An unknown
setup cost cannot be approved. The first invoice equals the displayed monthly
plus one-time setup amounts; renewals contain only the monthly amount.

Approval requires a real customer, confirmed supply, payment-start date, written
service terms and explicit owner confirmation. Do not create a dummy live offer
to test payments. Changes create a new terms version; after a checkout attempt,
the customer, prices, tax rate and terms are immutable. No customer is charged
without their own recurring-payment consent and Stripe confirmation.

## Configuration

Keep credentials exclusively in Render's private environment. Existing test keys
and sandbox switches are unchanged. Live configuration:

- STRIPE_LIVE_SECRET_KEY: restricted server key for the verified account.
- STRIPE_LIVE_ACCOUNT_ID: expected verified account ID.
- STRIPE_LIVE_WEBHOOK_SECRET: signing secret for `/api/payments/webhook`.
- STRIPE_LIVE_GST_RATE_ID: active NZ 15 percent inclusive tax rate ID.
- KIWIKIND_LIVE_BILLING_ENABLED=1 and KIWIKIND_LIVE_RELEASE_APPROVED=1 only after
  provider setup and validation. Set either to 0 to pause new checkouts.

The key needs Accounts and Balance read; Checkout Sessions write; Subscriptions
write for period-end cancellation; Customers, Products and Prices permissions
required by inline subscription Checkout; and Invoices, Invoice Payments,
PaymentIntents, Charges, Disputes and Tax Rates read for verification. Establish
the exact allowed resources in Stripe and test the same permission set in a
sandbox. No bank/payout/transfer/Identity writes, account writes, refund writes,
or customer portal permissions are used by this implementation. The operator
configures tax rates and webhook destinations separately through Stripe.

## Webhook

Deploy the handler with both release switches off first. Register **Your
account**, **Snapshot** events at API version `2026-09-30.endive` to:

`https://kiwikind-backend.onrender.com/api/payments/webhook`

Subscribe only to checkout.session.completed, customer.subscription.created,
customer.subscription.updated, customer.subscription.deleted, invoice.paid,
invoice.payment_failed, invoice.voided, invoice.marked_uncollectible,
invoice.finalized, charge.refunded, charge.dispute.created,
charge.dispute.updated, charge.dispute.closed. Copy its signing secret directly
to Render and apply settings. Never send it through chat, GitHub or screenshots.

The handler rejects unsigned/wrong-mode/account/version events. Receipts and
ledger writes are atomic; duplicate events are ignored. Current provider objects
are re-read under agreement locks, validating Checkout/customer/subscription,
monthly amount, tax configuration, invoice and payment intent bindings. Failed
reconciliation returns a retriable response. Payment records survive pausing
new checkout. Monitor delivery failures in Stripe; do not mark invoices paid
from browser returns or manually recreate an ambiguous payment attempt.

## Web and Android

GitHub Pages continues hosting every visible account/owner page. Render remains
API-only. Checkout returns to Pages; only exact live Stripe Checkout URLs open.
Web and native account screens show the same private API ledger. Customers can
request period-end cancellation; they must contact KiwiKind separately about
service cancellation and contractual obligations. Refunds are reviewed and
processed by the owner in Stripe; signed updates reconcile them here.

A signed V15 Android artifact (version code 15, 0.2.13 closed test) passed
unit, lint, signing and Android 36 emulator/ad checks in GitHub run
39829195047. This does **not** establish an upload or rollout in Play Console.
Before updating the existing Closed Alpha release, independently check the
actual Play track status and compare signing certificate/versionCode, then
follow the normal review process. Do not silently overwrite other tracks or
create a production release.
No ads are introduced on payment or private screens.

## Validation limits

`check_live_stripe_account --verify-provider --verify-payment-reads` verifies
the pinned live account, inclusive NZ GST rate and GET access to the resources
used by reconciliation. It discards provider records and logs only fixed status
labels. The owner status reflects the same release configuration as customers.

The time-limited `stripe_inclusive_checkout_smoke` command is disabled unless
`KIWIKIND_STRIPE_INCLUSIVE_QA=2026-10-22-inclusive-v1`, and refuses provider calls
after 07:00 UTC on 22 October 2026. It uses the existing pinned TEST account and
the same Checkout request builder as live billing. It creates a synthetic
inclusive tax rate and checkout for NZD 14.50 monthly plus NZD 12.30 setup once,
checks the NZD 26.80 total, expires checkout and archives the test tax rate.
It submits no payment and creates no customer, subscription, application record
or supplier order. Repeated runs use fixed idempotency keys. Turn the switch off
after verification. This validates provider request shape, not live write scope.

Unit/API and browser tests use synthetic accounts and provider objects. The
separate real owner NZ$1 verification confirmed live key/checkout and signed
webhook reception for a **one-time** payment. They do not prove real customer
recurring subscription permissions, subsequent live invoices and renewals,
customer cancellation/refunds or a published Android update. Do not claim activation until the
deployed configuration and provider setup are verified. Do not run automated
real-money charges as a readiness check.


## Isolated owner-only NZ$1 real payment verification

The optional **one-time** live NZ$1 website test is separate from approved
broadband customer agreements, subscriptions and supplier ordering. It requires
the owner to sign in at the existing Pages owner centre with their bound Google
account and MFA, explicitly tick consent, and submit their own card details on
Stripe-hosted Checkout. The server fixes the amount at 100 NZD cents, uses
Checkout mode \`payment\`, and never creates a recurring-price line item or a
Vetta order. The same verified owner can see this section in their signed-in
Pages account Billing view; ordinary customers cannot.

Set \`KIWIKIND_OWNER_DOLLAR_TEST_ENABLED=1\` **only on Render** after the
migration has been applied, \`STRIPE_LIVE_SECRET_KEY\`,
\`STRIPE_LIVE_ACCOUNT_ID\` and \`STRIPE_LIVE_WEBHOOK_SECRET\` are confirmed,
and the existing live \`/api/payments/webhook\` endpoint receives signed
\`checkout.session.completed\` and \`charge.refunded\` events. The test flag
is independent from production recurring-release switches and defaults OFF.
No Stripe credentials belong in GitHub, Pages, Android, messages or screenshots.

The owner test creates at most one persisted verification record. Repeated
submissions re-use its Checkout session rather than generating extra charges.
A returned browser redirect never marks the payment as paid: the signed webhook
retrieves the current live Checkout and succeeded PaymentIntent, checking exact
amount, currency, metadata and owner record. Stripe refunds are performed by
the owner from Stripe Dashboard and recorded when the signed refund webhook
arrives. Stripe processing fees may not be refunded.

Before enabling, run the synthetic test suite and verify the deployed backend
branch and Render migrations; the website can be published in advance because
the separate server flag stays OFF. To test:
1. Sign into \`owner.html\` using owner Google proof and authenticator.
2. In **Verify a real NZ$1 payment**, tick one-time consent and tap **Pay
   NZ$1 once securely**; only the owner can authorise the Stripe card payment.
3. Refresh verification; expect \`paid\` only after signed webhook delivery.
4. Find the same real payment in Stripe Dashboard, issue an owner-reviewed
   refund, and refresh to see \`refunded\`. There is no automatic subscription.
5. Turn \`KIWIKIND_OWNER_DOLLAR_TEST_ENABLED=0\` after verification. This
   does not deactivate refunds or webhook reconciliation.

Website verification does **not** by itself prove the Android navigation,
payment return flow or release has been tested.
