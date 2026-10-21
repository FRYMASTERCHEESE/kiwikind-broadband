# GitHub Pages account migration — 21 October 2026

## Inspected state

The live Render service `kiwikind-backend` runs commit
`514b1fa2df58dab99c375a023ba411ddf68a1e1f` from
`feature/neon-postgres-config`, with automatic deploys off. `main` is not the
deployed application. This change builds on the deployed branch and keeps all
existing migrations, Google subject bindings, customer records and native APIs.
The existing Pages repository is `FRYMASTERCHEESE/kiwikind-broadband-website`.
Its URL must remain unchanged.

Google Cloud's existing KiwiKind web client was inspected read-only: its allowed
JavaScript origins already include `https://frymastercheese.github.io`.
No OAuth secret, Android client or allowed origin was changed.

## Iterations and release order

1. Backend PR: exact-origin CORS, secure cross-site session/CSRF cookies, JSON
   owner Google/MFA, private catalogue import/read, stored readiness and explicit
   read-only Stripe provider verification. No schema change. Deploy the reviewed
   backend commit with `PAGES_ENABLED=1`, `PAGES_API_ONLY=0` initially.
2. Website PR: account.html and owner.html with relative navigation; API calls
   remain on Render. Only public code is deployed to Pages. Deploy the reviewed
   frontend, then test real customer and owner authentication at the existing URL.
3. Set `PAGES_API_ONLY=1` and deploy: all non-API/non-health Render paths redirect
   to fixed Pages URLs for GET/HEAD and reject other methods. This includes old
   Django admin, billing HTML, CSS/JS and static HTML paths. No arbitrary `next`
   parameter is honoured. Google callback and Stripe webhook API paths remain.

No live key, sales switch, supplier operation or publication permission is added.
Do not merge incomplete older Stripe PRs #35/#36/#41 into this release.

## Session and security contract

Cookies remain host-only and HttpOnly. PAGES_ENABLED sets Secure and SameSite=None
for session and CSRF cookies. Bootstrap returns a masked CSRF token, kept only in
memory; every unsafe browser API call sends it and the backend cookie. Login
rotates the token; the frontend adopts the returned token. MFA rotates the session
key. Existing one-hour customer expiry and 30-minute owner Google proof remain.
No bearer session, Google credential or MFA key is persisted in browser storage.

Credentialed CORS permits only the exact Pages origin, GET/POST and the JSON/CSRF
headers. Rejected origins cannot perform writes even if they know a token.
CsrfViewMiddleware is not bypassed. The existing Google redirect callback and
Stripe signed-webhook exceptions remain specific to those APIs.

Origins do not include repository paths: **every page and repository published
under frymastercheese.github.io shares the same origin trust boundary**. Keep all
code served from that account trusted. Paths are not tenant isolation. Pages
cannot supply custom HTTP security headers; account/owner pages use meta CSP.
No client code can hide confidential information: catalogue/customer data is
returned only by authenticated, server-authorised no-store APIs.

Some browsers block third-party cookies even with SameSite=None. Both apps probe
the CSRF cookie and session cookie before enabling sign-in. They fail closed if
either is blocked. An explicit per-site cookie exception may work; browser
policies such as Safari ITP can make this architecture unavailable. Universal
cross-browser persistent login cannot be guaranteed with these unrelated domains.
No token-storage fallback or security setting is silently changed.

The Google SDK is loaded only in the owner sign-in document. A full document
reload follows Google proof; MFA setup keys and private catalogue content are
never displayed in a document that loaded that SDK. Owner identity is checked
server-side on every private read/write and expires independently of the UI.
Private owner DOM is cleared while hidden and on authentication failure.

## Scope and exact limitations

The Pages owner centre implements identity/MFA, readiness, private catalogue read
and draft CSV import, and read-only current Stripe TEST evidence. It does not
reimplement the full Django model editor, customer support operations, supplier
framework acknowledgement, sandbox checkout/refund actions or every legacy admin
workflow. API-only cutover makes those legacy HTML controls unavailable; complete
any required operator parity before relying on them. There is no hidden Render
admin-page fallback.

Customer exports, deletion-review requests, support, preferences, referrals and
connection preparation reuse existing APIs and database ownership checks. Android
code, OAuth clients, package IDs and data are unchanged. Native browser links to
legacy Render HTML redirect to Pages after cutover; real-device testing remains
required. Account sync is server-backed refresh on return, not offline/realtime.

CSV web uploads are limited to 12 KB and remain private, address-specific,
unverified drafts. No approval/publication endpoint exists in this frontend.

Historical repository documentation reports an actual TEST checkout, paid invoice,
cancel-at-period-end and full refund on 21 October. That is historical evidence,
not independent current provider verification. Stored readiness checks read the
existing database. The new explicit provider check uses only Stripe retrieve/list
operations, pins account/test mode, checks checkout/subscription/invoice/payment/
charge bindings and returns sanitised booleans. It does not reconcile or mutate
records. Real renewal, decline and authentication-challenge scenarios remain
outstanding. No check authorises real billing or a Vetta order.

## Authentication steps and verification

The owner must complete their existing Google sign-in and authenticator code;
never send the code or key in chat. After rollout, open owner.html, authenticate,
and choose Check current Stripe TEST evidence. Record only sanitised results.
If authentication/cookies fail, leave API-only cutover pending and investigate;
do not switch off CSRF, MFA or server authorisation.

Automated coverage includes hostile origins, preflight restrictions, missing
cookies/token, wrong owner, nonce replay, MFA gating/expiry, private draft import,
fixed redirects, and provider test-mode/binding failures. Website browser checks
use synthetic APIs at 390px and 1365px, including sign-in/restore/sign-out, signup,
owner MFA, private catalogue and blocked-cookie behavior. These do not replace
real Google, mobile-device or Stripe provider tests. PostgreSQL/Android builds run
in existing CI; local SQLite and Chromium results must be reported separately.

## Recovery

Record deployed SHAs and configuration before release. Preserve the existing
database; no migration rollback is needed. For a failed cutover restore the known
frontend commit and disable the Pages flags before restoring the prior backend
image. This may restore Render-hosted legacy pages temporarily, so it is a recovery
action requiring explicit acknowledgement of the hosting requirement. Do not
delete or rewrite accounts, Google identities, catalogue or Stripe test history.
