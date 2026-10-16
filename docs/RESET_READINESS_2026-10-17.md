# Password reset and technical prelaunch evidence — 17 October 2026

## Source and live evidence

Base: feature/neon-postgres-config at 164f6ac, including merged PRs 17 and 18. Main is older and does not contain the current Google/session integration. New work targets the integration branch.

Read-only live GET /api/status returned 200: intake_enabled=false, billing_enabled=false, live_services=false. GET /app.js returned 200 and confirmed the destructive reset-form replacement is deployed. Render metadata confirms kiwikind-backend is on plan free, tracks feature/neon-postgres-config, and automatic deployment is off.

Render application logs contain POST /api/password-reset -> HTTP 400 from Android at 2026-10-16T10:51:47Z (16 October, 23:51 NZDT). This proves an Android request reached the route, not that it passed validation or sent mail. Available filtered logs show no successful website reset or SMTP delivery. No new live POST was submitted: reset throttling writes database records, and production record changes are prohibited.

Render Free blocks outbound ports 25, 465 and 587. Gmail SMTP using the repository's STARTTLS/587 configuration cannot deliver from that tier. Source: https://render.com/docs/free#other-limitations (checked 17 October 2026). No upgrade was made. Live secret values were neither retrieved nor displayed; credential correctness cannot be certified. No mailbox receipt is claimed.

## Fixed in this branch

- Backend opens the mail transport before looking up the account, returning the same safe HTTP 503 on connection/authentication failures for existing and unknown addresses. Logs omit recipient, token, exception text and credentials.
- Recipient-specific failures and zero-message sends are logged without changing the generic public response; HTTP 202 means a request, not guaranteed delivery. This avoids exposing account existence through recipient errors.
- Optional RESET_EMAIL_UNAVAILABLE=1 allows an operator to fail all reset requests immediately during a known outage. It is not enabled remotely by this work.
- Website uses a dedicated reset form, preserving Google and password sign-in elements and listeners. Successful reset clears the password/token, restores sign-in and retains the success notice. API validation errors retain the form for retry. Navigation out clears the token.
- Website reset validates the email field without requiring the unrelated password field.
- Android validates and captures the email on the UI thread before making the same shared API call. It explains that the emailed link completes in the browser and the user then returns to sign in.
- Existing Google implementation, API cookie/session code and Android signing configuration were preserved.

## New focused checks

PASS: 4 new Django tests in portal.test_reset_delivery, using an isolated test database and local email/mocks: uniform SMTP authentication failure, blocked transport before account lookup, Google-only account reset email without changing its password, and private recipient failure handling.
PASS: 4 new Node tests in site/tests/reset.test.cjs: reset link rendering, return to sign-in, successful confirmation/cleanup, validation-error retry.
PASS: node --check site/dist/app.js and git diff --check.

No full backend suite, previous regression tests, physical-phone Google test or signed Android build was repeated. Android reset UI changes were reviewed in source, not compiled/device-tested. Existing CI is intentionally skipped on this commit to avoid automatically repeating those suites. These are focused unit/DOM-stub checks, not visual browser QA.

## Separate platform assessments

Website: confirmed reset UI/navigation and transport error defects are corrected in source, with focused tests passing. The live website is unchanged until an approved merge/deployment. End-to-end reset delivery is blocked; live website button-to-request evidence is incomplete. Mobile layout and other forms were reviewed in source; no additional confirmed defect was established or comprehensive visual certification performed. 92% readiness is not substantiated.

Android: shared reset endpoint and browser completion link are consistent with the website. Email validation and browser-return guidance are corrected in source. Prior successful Google phone test and signed release are preserved as prior evidence, not repeated here. New UI changes still need focused device verification after deployment, and real reset delivery remains blocked. 92% readiness is not substantiated.

## Remaining blockers and safe next step

A free HTTPS mail transport or an approved free host permitting Gmail SMTP is required before mailbox delivery can work; neither has been selected/configured. No existing credentials should be pasted into chat. After an approved deployment and free transport setup, use an authorized synthetic mailbox to verify actual receipt, expiry/replay, new-password login on both platforms and old-session invalidation. That live exercise requires permission to create/modify the synthetic records.

No deployment, production record change, Neon query/restore/deletion, backup deletion, paid service, order, payment, provisioning or admin enablement was performed. Intake remains closed. The existing Neon backup and restore drill were left untouched.
