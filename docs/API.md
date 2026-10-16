# Shared customer API

The Django host serves the website and JSON API. Android uses the same host, account database and operations. Authentication is a server-side Django session cookie, not a hard-coded client API key. There is no admin secret in the browser or Android app. HTTPS only in production. Cross-origin access is not enabled.

Fetch `GET /api/csrf` before a write. Preserve cookies and send `X-CSRFToken` from its `csrfToken` value. Android additionally sends the configured same-origin `Origin` and `Referer`. A successful login rotates CSRF and returns the updated token. Use that token for subsequent writes. Cookies are in memory in Android; web sessions expire after an hour. Existing sessions are invalidated by password changes through Django's session-auth hash check.

| Endpoint | Method | Access / behaviour |
|---|---|---|
| `/api/status` | GET | Pre-launch mode and configured public contacts; never claims availability or live billing |
| `/api/csrf` | GET | CSRF bootstrap; sets cookie |
| `/api/register` | POST | Intake gate, email/password/consent_version; sends verification email; generic 202 |
| `/api/verify` | POST | Signed token from verification email; expires in 24 hours; one activation |
| `/api/login` | POST | Verified email/password; session cookie + updated CSRF |
| `/api/password-reset` | POST | Email; generic 202, sends a link if eligible |
| `/api/password-reset/confirm` | POST | Token + password; one use; expires after one hour |
| `/api/me` | GET | Signed-in customer account |
| `/api/logout` | POST | Signed-in; destroys current session |
| `/api/orders` | GET / POST | Customer's own requests; POST requires current consent and intake open |
| `/api/orders/{uuid}/cancel` | POST | Owner only; local cancellation, no supplier cancellation |
| `/api/tickets` | GET / POST | Own tickets; category support, complaint or privacy |
| `/api/tickets/{uuid}/messages` | GET / POST | Own conversation and replies; staff reply through protected admin |
| `/api/invoices` | GET | Own ledger only; payments disabled; no customer writes |
| `/api/privacy/export` | GET | Owner data download; no password/hash included |
| `/api/privacy/deletion` | POST | Current password confirmation; human review request, 202 |
| `/healthz` | GET | Minimal health response without customer or database details |

JSON writes use `Content-Type: application/json`, maximum 16 KB after reverse-proxy body limits. Enforce the documented edge body/rate limits. Most validation errors return JSON 400; unauthenticated calls return 401, CSRF failures 403, non-owned UUIDs 404, changed idempotency payload 409, throttles 429 and closed intake 503. Framework 403/404 responses can be HTML; clients show generic errors without rendering it. No automatic supplier or payment endpoint is exposed.

Example request fields (synthetic data only):

```json
{
  "contact_name": "Synthetic Tester",
  "address": "12 Test Street, Wellington",
  "postcode": "6011",
  "phone": "",
  "consent_version": "prelaunch-2026-10-16",
  "idempotency_key": "437d0252-3fb7-412e-a86c-ef7999704dd3"
}
```

POST `/api/orders` records status `requested`, returns 201, creates an audit event and cannot create an invoice or supplier order. Retry the identical payload and key after a timeout; it returns the existing request. Reusing a key for different content returns 409. Only a deliberate new request uses a new key. Request IDs are UUIDs; authorization checks still apply, independent of ID secrecy.

Lists are currently bounded (100 requests/tickets; 200 messages per conversation) and are refreshed explicitly. Pagination, real-time synchronization, quote acceptance, service management and supplier/billing reconciliation need implementation before operational scale. This API is a pre-launch foundation, not a supplier integration certification.
