# Private manual price catalogue: safe editing

This improvement is based on the actual deployment branch `feature/neon-postgres-config`, not older Stripe drafts. No model/schema migration, authentication change, payment integration, supplier integration or customer-data rewrite is included.

## Owner workflow

Open the existing private admin, complete Google sign-in and the authenticator step, then choose **Price catalogue**. The form now includes a publication/evidence checklist. Enter only supported facts. A missing cost remains unknown rather than zero. Inclusive wholesale monthly/setup figures are calculated server-side at the existing 15% illustration rate from the exclusive figures; tampered browser totals are ignored.

Keep address-specific quotes as private drafts. Source references and notes are private: record the evidence/capture date separately from any supplier validity, the address or coverage scope, installation conditions, contract terms and outstanding supplier questions. Do not infer the network, handover type, validity or nationwide scope. Do not put actual addresses, ONT serials, private source documents or credentials into this public repository.

Saving a record as **Owner approved** requires a fresh explicit confirmation checkbox, plus all existing general-offer/source/network/speed/date/price validations. An older browser tab cannot overwrite a newer saved quote. Returning an approved record to draft/review clears the saved approver and approval time through the existing admin save workflow. Approval still does not enable publication.

## Deployment boundaries

Keep `PLAN_PUBLICATION_ENABLED=0`, `INTAKE_ENABLED=0`, `STRIPE_TEST_CHECKOUT_ENABLED=0`, and `STRIPE_TEST_PRICE_REVIEWED=0`. Never merge older Stripe PRs over this deployment branch. The public API still exposes only its restricted retail projection, never source references, notes or wholesale amounts. This change does not publish prices, claim live address availability, issue invoices or submit Vetta orders.

Supplier evidence is maintained in the private database, not in a new migration or test fixture. Conflicting Direct/Layer 2 wording must remain an explicit unresolved question until the supplier confirms the actual service. The supplier's quote validity, general resale scope and owner-selected retail prices remain separate approval tasks.

## Verification

Run `python manage.py test --settings=config.test_settings` on disposable SQLite and PostgreSQL, plus the existing web, Android and visual workflows. `portal.test_catalogue_editor` covers server-derived GST, missing vs zero costs, malformed prices, explicit confirmation, address/date checks, stale edits, owner-only admin rendering/writes, audit records and unpublished plans. Existing MFA, customer/session, support, supplier preparation and API tests must also pass. Do not claim deployment merely because a PR exists; verify Render's deployed commit separately.
