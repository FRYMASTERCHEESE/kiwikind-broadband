# Private owner launch-readiness dashboard

This feature is strictly owner-only via the existing Google identity, server session,
Django staff check and TOTP MFA, with a no-store response.

Read-only page: /admin/launch-readiness/
Optional owner action: /admin/launch-readiness/framework/ (explicit POST + CSRF)

The page reads aggregate records and booleans only; it does not expose wholesale
amounts, customer emails, Stripe IDs, tokens, signed agreements or addresses.
The framework action records the existing private Vetta Provider stage only after
an explicit owner acknowledgement and appends one immutable AuditEvent. It does
not claim individual Product Terms or commercial order approval, does not
create a supplier record, and never publishes unapproved prices.

Real customer payments remain disabled; the test payment, refund and cancellation
have actual Stripe webhook receipts. The external tests for renewal, declined card
and authentication challenges are still outstanding. Likewise a signed Android
release build and real-device tests require their own workflow/evidence.

The evidence count is not a production-readiness percentage. Neither this page
nor the signed framework alone authorises live internet service.
