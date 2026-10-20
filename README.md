# KiwiKind Broadband

A separate pre-launch NZ broadband retail-provider platform. **Not an operating ISP, comparison service or referral site. No wholesale agreement, retail plans, coverage claims, supplier orders or charges.**

## Built

- Private Vetta onboarding dashboard, draft plan/GST calculations, verified manual availability evidence, and audited order/fault preparation. Real supplier processing remains disabled. See [Vetta onboarding](docs/VETTA_ONBOARDING.md).

- Django 5.2 LTS backend and database shared by responsive website and native Android client.
- Email verification, password login/reset, expiring server sessions, CSRF checks, password hashing and database-backed request throttles.
- Owned customer request records, idempotent submission/cancellation, support/complaint/privacy tickets and replies.
- Existing customer invoice ledger is preserved. A separate Stripe sandbox integration adds reviewed test agreements, recurring Checkout, verified webhooks and isolated test invoices/refunds. No live payments; see docs/STRIPE_CURRENT_STACK.md.
- Dedicated owner administration requires verified Google identity plus application-enforced authenticator MFA on privileged requests. Other staff identities cannot access it. Audit events record key changes without message content.
- Account export and password-confirmed deletion **request**. Human review and fulfilment are still needed.
- Supplier interface and unconfigured implementation that cannot provision anything.
- Draft pre-launch privacy/terms, compliance and operating checklists.
- Docker deployment, migrations, backend CI and manually triggered Android bundle CI.

## Run locally

Python 3.12+, Node for the JavaScript syntax check. No third-party accounts are needed for local tests.

```powershell
python -m venv .venv
.venv/Scripts/Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(64))")
$env:DEBUG = '1'
python manage.py migrate
python manage.py runserver
```

Intake stays closed by default. For **synthetic local testing only**, set `INTAKE_ENABLED=1`, `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`, `DEFAULT_FROM_EMAIL=test@example.invalid`. Verification/reset links are printed locally: never use console email for customer data. The local database is empty and ignored by Git. No sample passwords or seeded admin accounts ship.

```powershell
python manage.py test --settings=config.test_settings
python manage.py makemigrations --check --dry-run
node --check site/dist/app.js
```

Test settings use an isolated test database and local email outbox. Do not deploy `config.test_settings`.

## Architecture / separation

`config/` + `portal/` serve both clients. A dedicated PostgreSQL database is configured by the backend host; local tests use an isolated database. `site/dist/` is the website source served directly by Django; a Sites deployment of these same assets is a **private disconnected design preview**, not the backend. Customer records never live in browser local storage. Android uses HTTPS JSON and encrypted session-cookie persistence in Android Keystore, then verifies the saved session with the backend. Browser and Android use separate sessions for the same customer account and fetch shared records on refresh; there is no real-time/offline synchronization.

The private GitHub repo, Sites project, database path and Android package are separate from MoneyMate NZ/Bebo/PumpLite. No connections to those systems are implemented. Do not reuse their database, keys, OAuth clients, signing keys, package names or hosting project.

## Deploy

Password-reset and verification email now use the backend-only Brevo HTTPS API. Complete the [Free email setup](docs/HTTPS_EMAIL_SETUP.md) before expecting delivery; Gmail SMTP is blocked on Render Free. Website and Android keep the same shared reset endpoint.

See [deployment](docs/DEPLOYMENT.md), [Google Play](docs/GOOGLE_PLAY.md), [launch gates](docs/LAUNCH_GATES.md), [costs](docs/COSTS.md) and [verification report](docs/BUILD_REPORT.md). This is a tested foundation with explicit launch blockers, not production ISP software certification.
