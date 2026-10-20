# Owner security and production readiness — 20 October 2026

Review candidate extending Stripe PR #35. No production deployment or provider activation is performed. Additive migrations preserve existing customers, authentication, requests, support and ledger entries.

## Owner setup by a trusted operator

Only `kiwikindbroadband@gmail.com` can administer the service. The server additionally requires a bound database identity (`OWNER_USER_ID`), exact matching username/email, active/staff flags, a mailbox verification record and a current MFA-authenticated session. Other staff/superusers are denied. Customer login alone does not satisfy admin MFA. Public registration ignores role fields. User, group and authenticator management are unavailable in the web admin. No administrator is seeded or promoted automatically.

1. Back up the existing database and test restoring it. Run migrations without replacing the database or changing authentication models.
2. Independently identify the existing owner account and set its database ID as server-only `OWNER_USER_ID`. Give that account the required Django model permissions through trusted operations, retaining any existing legitimate owner role. Email matching alone must never grant a role.
3. Run `python manage.py prepare_owner verify-email`. The owner follows the mailbox link. Existing account activation alone is insufficient evidence for owner access, so existing owners need this fresh check.
4. Run `python manage.py prepare_owner enrol-mfa` on a private console. Add the generated secret URI to the owner's authenticator and enter its current code. Never put the URI in source, CI output, tickets or chat. Protect database backups containing TOTP secrets.
5. Enable `ADMIN_ENABLED=1` only after staging checks. The existing production perimeter gate remains additional protection: configure the independent MFA perimeter before setting `ADMIN_MFA_PERIMETER_CONFIRMED=1`.

MFA recovery requires independently verifying the owner, revoking sessions/lost devices from trusted console access and enrolling a replacement. There is no public bypass. Actual production enrolment, recovery and deployed access checks remain unverified.

## Price catalogue and Vetta

The owner manages source, network, speed, wholesale monthly/setup ex/incl GST, validity, address scope, review status and separately chosen retail prices in admin. Approval records the owner and time. `/api/plans` projects retail fields only and excludes drafts, address-specific quotes, expired records and missing owner approvals. `PLAN_PUBLICATION_ENABLED` defaults off. Both websites and Android fetch this endpoint. Only this public retail response allows CORS, without credentials; customer endpoints are unchanged.

Run `python manage.py prepare_vetta_quote` to stage the supplied Direct UFB 500/100 quote: monthly $69.92 ex / $80.41 incl GST; setup $35.00 ex / $40.25 incl GST. It stays a private address-specific draft with no retail price or validity date. Re-running does not overwrite it. The original screenshot was not attached here; the figures are transcribed from the user's request. Confirm the original source, service address, LFC/network, effective date and publication rights before considering any general plan. Address-specific drafts cannot be approved for general publication.

[Vetta's official wholesale page](https://vetta.nz/wholesale/) describes white-label delivery and a partner portal for provisioning, testing and faults. A [client login](https://portal.vetta.nz/login) exists. Public information reviewed did not establish a supported wholesale API or sandbox. The user's report that Phil enabled access and authorised branding is recorded as user-supplied evidence, not independently verified contract documentation. No login scraping or invented integration is implemented. Obtain the supported integration specification, sandbox access, scopes, price export rights and ordering authority from the authorised Vetta contact. Supplier provisioning and availability checks remain unconfigured.

## Stripe sandbox operations

The official SDK is used. All billing paths reject live keys/events. Required server-only variables: `STRIPE_TEST_CHECKOUT_ENABLED=1`, `STRIPE_TEST_PRICE_REVIEWED=1`, `STRIPE_TEST_SECRET_KEY=sk_test_…`, `STRIPE_TEST_WEBHOOK_SECRET=whsec_…`. Defaults are disabled. No live-mode switch is implemented. Keep secrets out of website, Android, source and logs.

- Checkout accepts only existing unpaid NZD invoices marked `sandbox=True`. Existing invoices default false, so test funds cannot settle real ledger entries. Server amounts, persistent session ownership and deterministic retry keys prevent client amount changes and repeated session creation. Expired/changed checkouts require reconciliation.
- The owner creates reviewed synthetic billing agreements with explicit monthly/setup cents. The customer sees those amounts and consents to synthetic monthly billing. Stored sessions and retry keys prevent repeated checkout from creating another subscription. Cancellation requests set period-end cancellation only.
- Register `/api/billing/stripe/webhook` in an isolated Stripe sandbox. Raw signatures and five-minute timestamp tolerance are verified by the official SDK. Live events/objects are rejected. Event receipts and settlement updates commit atomically; duplicates cannot repeat settlement. Mismatches roll back and return retryable responses.
- Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`, `invoice.voided`, `charge.refunded`. Subscription/invoice/refund processing retrieves current provider state to resist stale event regressions. Invoices preceding their subscription return 503 for retry. Monitor delivery failures. Use a dedicated sandbox: unrelated subscription invoices also retry because they are not mapped locally.
- Recurring invoices enter a separate synthetic ledger. No return URL marks an invoice paid; payments never activate broadband. Exact NZD amounts are enforced. Discounts, tax adjustments, prorations and plan changes require further implementation and are rejected for review.
- Full synthetic refunds are available through the owner-only admin payments action or MFA-protected `/api/admin/billing/test-refund`. Clients cannot supply amounts. Submission does not mark a refund settled; `charge.refunded` reconciles the provider amount. Partial refund initiation and dispute/chargeback case management remain unimplemented.

Sources: [Checkout](https://docs.stripe.com/api/checkout/sessions/create), [webhook security](https://docs.stripe.com/webhooks), [subscription events](https://docs.stripe.com/billing/subscriptions/webhooks), [refunds](https://docs.stripe.com/api/refunds/create). Local tests mock provider calls. Actual sandbox checkout, renewal, failed payment, retry, cancellation, refund and API-version compatibility must still be verified with the approved account.

## GoCardless, applications and faults

GoCardless is explicitly `pending_approval`; no NZ mandate or collection path is enabled. There is no provider fallback that can double-charge a Stripe invoice. Scheme/account approval, supported provider documentation, signed mandates, sandbox tests and reconciliation remain required.

Existing applications/requests, order status and support messages remain shared across website and Android through the same authenticated backend. Fault is now a separate ticket category with investigating/supplier-review statuses and owner replies. These internal records do not claim that Vetta has accepted a fault or order. Actual provisioning, address checks and operational activation remain blocked on supported supplier access and approved offers.

## Remaining production gates

Verified deployment, database backup/restore, real owner MFA enrolment/access checks; provider approvals and secrets; Stripe sandbox end-to-end evidence; disputes and reconciliation operations; supported Vetta integration or authorised manual procedures; approved general retail catalogue and publication approval; service contracts/contact/compliance review; signed Android release, physical-device and Play closed testing. Keep live payments, supplier orders and publication of unapproved plans disabled.
