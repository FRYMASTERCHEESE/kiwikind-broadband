# Free HTTPS password-reset delivery

Implemented from merged PR #19 (`4c87a8e`) on `feature/neon-postgres-config`.

## Provider and cost boundary

The default Django email backend now uses Brevo's HTTPS API on port 443. It
does not connect to Gmail SMTP or fall back to SMTP. The existing `requests`
dependency is reused; no SDK, database migration, queue or paid service is added.

Brevo currently offers a Free allowance of 300 emails per day, without a credit
card. Account approval and sender verification are still required. The backend
checks `/account` before account lookup and only proceeds with a `free` email
plan, positive credits and enabled transactional relay. Paid or unknown email
plans, exhausted credits, unavailable credentials and unverified senders fail
closed. The API never buys credits, upgrades a plan or retries a send. The
provider's remaining allowance is authoritative; concurrent sends or other apps
can exhaust it between the preflight and send.

Use a dedicated Free Brevo account for KiwiKind and do not add a payment method,
paid subscription, prepaid credits or automatic top-ups. If the Free allowance
is exhausted, wait for its daily reset. Do not raise a tier to make a test pass.

Sources checked 17 October 2026:

- [Brevo Free plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan)
- [Transactional Free API, no card required](https://www.brevo.com/products/transactional-email/)
- [Account API and plan/relay fields](https://developers.brevo.com/reference/get-account)
- [Sender verification API](https://developers.brevo.com/reference/get-senders)
- [Transactional send API](https://developers.brevo.com/reference/send-transac-email)

## Setup the owner must complete

1. Create or use a **Free** Brevo account for KiwiKind. Use
   `kiwikindbroadband@gmail.com` for account contact where accepted. Complete
   account verification and any requested transactional-email activation.
2. Add the sender **KiwiKind Broadband**, `kiwikindbroadband@gmail.com`, in
   Brevo's Senders settings. Complete its verification using the mailbox. It
   must appear active in the sender list. Do not attempt to authenticate or
   change DNS for `gmail.com`, which you do not own.
3. Gmail senders cannot authenticate the Gmail domain through Brevo. Brevo may
   replace the visible From domain with `brevosend.com`. The backend keeps
   `kiwikindbroadband@gmail.com` as Reply-To. If Brevo declines this sender,
   delivery stays blocked until an approved sender is available; do not buy a
   domain or upgrade automatically.
   [Brevo's Gmail/domain rewriting explanation](https://help.brevo.com/hc/en-us/articles/16045394674066-Troubleshooting-Domain-authentication).
4. Generate a Brevo **API key**, not an SMTP key. Paste it directly into the
   KiwiKind Render backend's secret environment settings as `BREVO_API_KEY`.
   Never paste it into chat, source control, a command argument, the website,
   Android resources or Gradle properties. Restrict access and rotate it in
   Brevo if exposed. Do not send or reuse the Gmail password/app password.
5. Set the following non-secret values on the existing KiwiKind backend:

   ```text
   EMAIL_BACKEND=portal.email_backend.BrevoEmailBackend
   DEFAULT_FROM_EMAIL=KiwiKind Broadband <kiwikindbroadband@gmail.com>
   EMAIL_REPLY_TO=kiwikindbroadband@gmail.com
   RESET_EMAIL_UNAVAILABLE=0
   INTAKE_ENABLED=0
   ADMIN_ENABLED=0
   ```

   Retain the existing HTTPS `PUBLIC_ORIGIN`, allowed hosts, CSRF settings,
   dedicated database, Google OAuth values and Android signing configuration.
   Remove obsolete Gmail SMTP username/password variables from the service's
   secret settings when no longer needed; the HTTPS backend never reads them.
   Environment changes in Render can cause a restart/deploy. Apply them together
   with an owner-approved deployment after this PR is merged into the service's
   integration branch, not as an automatic action from this work.
6. Review Brevo transactional retention/tracking settings for password-reset
   mail. Use plain-text delivery without click/open tracking where available.
   Recipient addresses and message content necessarily pass to the provider;
   do not export reset tokens or mail bodies into analytics or public logs.
7. After setup and an approved deployment, verify actual receipt with an
   authorized synthetic account/mailbox in an isolated environment. Request a
   reset once from the website and once from Android, follow the browser link,
   set a new password, then return to Android to sign in. Also confirm invalid
   links and provider failures display safe errors. Do not modify production
   accounts for this exercise without authorization.

No provider account/key was created, live secret changed, message sent or
deployment performed by this PR. The code is implemented; actual receipt and
provider onboarding remain unverified until the steps above are complete.

## Shared website and Android behavior

Both clients retain `/api/password-reset` and the existing CSRF/session contract.
The backend verifies provider availability before looking up the supplied email,
then submits eligible mail through `POST https://api.brevo.com/v3/smtp/email`.
The email contains the existing short-lived `PUBLIC_ORIGIN/#reset=...` link.
Android users finish in the website's reset form and return to the app to sign
in. No new APK or Google sign-in configuration is needed for this transport swap.

Preflight failure produces the same HTTP 503 and safe message for known and
unknown accounts. Recipient/send-specific failures remain a generic HTTP 202
with safe operational logging, preserving PR #19's account-privacy behavior.
202 means requested, not guaranteed inbox delivery. A provider HTTP 201 with a
message ID means accepted by Brevo, not delivered to a mailbox.

HTTPS requests use TLS certificate verification, a fixed provider origin,
bounded connect/read timeouts, no redirects and no send retries. Provider
response bodies and exception details are not included in public errors or
application logs. Missing setup fails closed, while Google sign-in stays usable.

## Focused evidence

11 **new** tests passed with mocked HTTPS responses and an isolated SQLite test
database:

```text
python manage.py test portal.test_https_email --settings=config.test_settings
```

They cover the HTTPS payload/Gmail Reply-To; missing key; paid/unknown/empty
allowance and disabled relay; inactive sender; redirects and HTTP errors;
timeouts/malformed JSON; missing send receipt; browser and simulated Android
reset requests; browser confirmation followed by Android-session password login;
preserved Google identity; closed intake; and private errors with no client key.

No previously passing test module, physical-phone Google sign-in test, signed
Android build or full backend suite was rerun. The commit skips existing CI to
avoid automatically repeating those suites. These checks do not prove actual
mailbox delivery or a physical Android test.
