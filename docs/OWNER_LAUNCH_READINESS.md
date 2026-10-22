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

Real customer recurring payments are not commercially released. Stripe TEST subscription, paid invoice, refund, cancellation, renewal, declined card and 3D Secure evidence have signed provider records. The separate owner-only LIVE NZ$1 one-time charge verified live keys/webhooks but does not certify recurring customer payments. The signed Android V15 APK/AAB and emulator tests passed in GitHub run 39829195047 (22–23 October 2026); the bundle has not been independently confirmed as uploaded to Google Play. Physical signed-Play install and customer acceptance are separate gates.

The evidence count is not a production-readiness percentage. Neither this page
nor the signed framework alone authorises live internet service.
