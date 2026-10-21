# Pages private operations and sandbox QA

All visible operations use https://frymastercheese.github.io/kiwikind-broadband-website/owner.html. Render remains API-only. Existing owner Google proof and authenticator MFA, server-side authorization and CSRF apply to every endpoint. Sessions/proofs are never stored in browser storage. Third-party cookie restrictions can prevent this split-host session; the client fails closed and explains the limitation. Do not disable browser protections globally.

## Operations

The owner can search and paginate customer records; edit permitted profile/activity fields; review linked requests, invoices, support and privacy cases; reply to support; update private supplier records; create/review private catalogue records; add immutable availability evidence; prepare orders/faults and record permitted transitions; inspect audit/history and TEST billing records. Model forms validate all writes. Signed edit versions reject stale changes, support replies and transitions use idempotency keys. No password, Google identity, staff privilege, secret, deletion, sales switch or arbitrary Django model is exposed. Privacy completion records manual fulfilment and lawful retention review; it does not delete account data. Customer export/deletion paths stay unchanged.

Catalogue approval remains private and requires the existing validation/confirmation. It never publishes prices. Preparation performs no supplier network call. Actual supplier submission, provisioning and activation remain blocked. Payment actions use only the existing pinned Stripe TEST account/key controls and explicit consent; no live payment path exists.

## Isolated Stripe exercises

Only the verified owner can create a fixture. Public intake and price publication must remain off. Each fixture creates a new synthetic clock-bound TEST customer and a reviewed NZD 100-cent monthly agreement with no setup fee or real customer email. Four fixtures/day maximum. Provider idempotency allows interrupted creation to resume for 23 hours. Existing customers and previous QA subscriptions are untouched.

From owner.html prepare a renewal exercise, open the generated Stripe TEST Checkout and use Stripe's standard test card. After the signed webhook has produced a paid application invoice, refresh the exercise and advance its TEST clock. Verify provider invoices against the application ledger after asynchronous clock processing. Prepare a second decline/3DS exercise, attempt the official declined test card and then the official 3DS-required test card, completing its simulated challenge. Never use real card details. Verify evidence and cancel each synthetic subscription at period end when finished.

Evidence is never inferred from button clicks: provider TEST events must match the fixture customer, paid invoices must match currency/amount/subscription and the signed-webhook ledger, and 3DS success must match the successful intent and charge. Only sanitized flags and a checked timestamp are saved. Event scans are bounded to the latest 100 events and explicitly report incomplete scans; absence is not proof of failure. Missing flags remain outstanding. No raw Stripe objects or credentials are sent to the frontend.

Hosted Checkout is the payment-provider page; all KiwiKind pages, including returns, stay on GitHub Pages. Browser tests use synthetic mocked accounts; real owner Google/MFA and actual Stripe lifecycle verification are separate evidence. No claim of physical Android testing follows from emulator success.
