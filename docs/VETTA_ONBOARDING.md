# Vetta onboarding preparation

KiwiKind Broadband Limited · NZBN 9429054036550. Contact: Phil Wright, Vetta Group. Meeting: 20 October 2026, 11:00 AM NZDT.

This release prepares internal workflows. It does **not** activate broadband service. Vetta supports new Layer 3 resellers, but a signed NDA or an onboarding discussion is not a wholesale service agreement or a retail launch approval.

## Inspection and release boundary

- Work starts at `8692524` on `feature/neon-postgres-config`, the current Android V9 release source. `main` diverges and lacks much of the shared backend/authentication work; this PR targets the existing backend branch.
- Render inspection on 19 October 2026: `kiwikind-backend` follows `feature/neon-postgres-config`, auto-deploy is off, live commit is `d0a6748`. The current head also includes subsequent Android/account-loading work. The separate Google preview follows `feature/google-auth-prelaunch` and has auto-deploy off.
- Live `/api/status` reports intake disabled, live services false, billing disabled, availability unverified. No production settings, supplier records, data, credentials or release tracks are changed by this PR.
- `site/dist` is the Django website. `public-site/index.html` and the separate public site are not the customer database or an alternative backend.
- Native Android retains package `nz.kiwikind.broadband`, its existing Google client, API origin, encrypted session storage and release-signing configuration. The review APK is a debug artifact, not a Play update. Its debug signing certificate may require a separately registered Google OAuth Android credential; the production credential must not be replaced.

## Owner tools

Open `/admin/wholesale/` from the existing owner administration. Existing admin enablement, owner identity, Google proof expiry, session and CSRF protections apply. No new admin passwords, roles, credentials or public wholesale APIs are introduced.

1. **Draft plans:** enter only prices actually supplied by Vetta or explicitly labelled internal scenarios. No plans or invented prices are seeded. Wholesale and retail prices are in NZD excluding GST. Optional setup cost is separate. Decimal arithmetic calculates illustrative 15% GST, rounded half-up to cents, and the GST-inclusive amount. Missing amounts remain unknown, not free. The monthly retail-minus-wholesale difference is before all other costs, not profit. KiwiKind's GST registration and tax treatment must be confirmed before any invoice or retail offer; the illustration does not assert GST registration.
2. **Availability evidence:** manually check the exact address in Vetta's authenticated portal, then record the source reference, result, check time and a recheck deadline. Evidence is append-only in admin. Rechecks require a new record. Expired, future, wrong-address, wrong-postcode or practice evidence cannot establish real availability. There is no public coverage claim or automatic address-check integration.
3. **Order preparation:** either link one existing customer request or create a synthetic practice case. Practice cases cannot link customers. A real preparation case stops at “Prepared — launch approval required”; it cannot be marked submitted/provisioning/active. The actual customer's request record is not rewritten by the preparation workflow. A cancellation blocks further preparation except closure.
4. **Fault preparation:** link an existing support ticket or use a synthetic practice case. Privacy and complaint tickets cannot be passed into supplier fault preparation. Record service reference and first-line diagnostics. Real fault escalation is blocked; practice cases can exercise escalation, investigation and resolution. Customer ticket status and messages are managed separately through existing support tools.
5. **Processing history:** each status change requires an internal note, records actor/time, and uses a submission key and revision check. A retry cannot create a duplicate event; stale tabs must reload. Supplier-stage practice updates also require a practice reference. Events cannot be edited or deleted in admin.

Draft/triage case fields can be edited; identity and practice/real classification cannot be changed after creation. Return an order from availability review to draft to replace expired evidence, then repeat the reviews. Faults can return to triage. Do not put credentials, signed portal URLs, payment details or identity documents in notes.

## Supplier boundary

`VettaManualSupplier` reads supplied manual evidence only. It inherits disabled submit/status/cancel/fault methods from the existing unconfigured supplier. There is no HTTP transport, API URL, API key, portal scraping, unattended login or fabricated sandbox. A portal URL is deliberately not guessed: use the address Vetta supplies after onboarding.

After separate approval and a future launch release, the human process is:

1. Confirm exact-address availability, speed tier, current quote, equipment and installation requirements.
2. Obtain the customer's accepted retail terms and switching/order authority. Check for existing orders before entering another in the portal.
3. Enter the order manually, then record the actual portal reference and confirmed status. Do not confuse a KiwiKind request with a supplier order.
4. Check provisioning/service state in the portal and send accurate customer updates. KiwiKind handles billing, first-line support, payments and cancellations.
5. Diagnose faults first, run permitted portal line tests, record the findings, escalate manually, and verify resolution before closing the customer issue.

This PR intentionally cannot perform steps 2–5 for live services. Practice statuses are simulations, not supplier acknowledgements.

## Shared customer view and recovery

`GET /api/connection-progress` uses the existing authenticated account on both clients. It returns only that customer's preparation stage, related request/ticket ID and update time. It excludes practice cases, draft prices, evidence, supplier references and internal notes. Public launch flags remain false. Unknown/practice status codes display a neutral waiting message rather than claiming an active connection.

The website loads this read-only view on demand and rejects responses from an older signed-in account. Android adds the same view and a recovery control that retries a read instead of replaying an interrupted write. Network failures retain existing credentials; actual session expiry still clears private state. No customer data is cached offline or copied to a second account system. Existing Google sign-in, password recovery and encrypted session restoration remain in place.

## Migration and deployment review

Migration `0009_wholesale_preparation` creates five new tables with foreign keys and constraints. It does not alter/delete customer rows, rename auth tables or reset sessions. Apply through the existing Django migration process only after review. Test on a disposable PostgreSQL environment with representative synthetic records first; use a direct connection for a future Neon migration. No live database migration is performed by this work.

Before a future deployment, verify a recoverable database backup/restore point, run checks against the intended commit, collect static files, apply the additive migration, and keep `INTAKE_ENABLED=0`. Keep the existing owner admin security settings. Merge does not authorize a Render deploy or Play upload. Rolling back application code can leave the additional tables in place; do not reverse/drop them after recording real preparation history without a retention review.

## Items to confirm with Phil and advisers

- Wholesale agreement, startup eligibility and any credit checks, deposits, minimum spend or commitments.
- Complete per-connection and setup price schedule, GST, regional/product differences, router and installation costs, cancellation/change fees and quote validity.
- Verified availability and order status meanings, accepted switching authority, lead times and order-duplicate handling.
- Portal access, training and permissions; official reference formats; actual automation/API roadmap if one becomes available.
- First-line responsibilities, fault escalation contacts, after-hours coverage and service-level commitments.
- Customer billing/refunds, privacy/data sharing, retail terms, complaints, tax treatment and operational sign-off.
- Any subsidised offer, its funding, eligibility and permission to market it. No subsidy or affordability guarantee is implemented here.

There is no launch toggle in the wholesale dashboard. A reviewed follow-up release is required before real supplier processing or public sales.

## Reproducible verification

The backend workflow runs the full Django suite against both isolated SQLite and disposable PostgreSQL, website JavaScript tests, migration drift/deployment checks, Docker build, and Android unit tests/lint/debug APK assembly. New coverage includes owner permissions and session expiry, CSRF, customer isolation, GST rounding, evidence validation, duplicate/stale processing, concurrent PostgreSQL operators, and preservation of existing accounts/Google identities/sessions/requests across the additive migration.

The `wholesale-visual` job runs `site/tests/wholesale-visual.cjs` against a disposable local Django server at 360px and 1280px. `scripts/prepare_wholesale_visual.py` refuses any database except the named local SQLite fixture and refuses to alter existing accounts. Screenshots alone are uploaded; the local test session/database are excluded. Tests verify closed intake, connection failure recovery, retained account identity, owner forms and absence of horizontal overflow.

GST reference: [Inland Revenue — Charging GST](https://www.ird.govt.nz/gst/charging-gst), checked 19 October 2026. The draft calculator illustrates standard-rate GST; final tax treatment remains an approval item.
