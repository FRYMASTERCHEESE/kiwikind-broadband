# Dedicated backend deployment

The private Sites preview hosts static assets only. Sites Workers cannot run this Python server. A separate Python/Docker host is required for the shared customer backend. No existing app's host or database is authorised for reuse.

1. Select a dedicated host with HTTPS and a persistent encrypted volume; validate NZ privacy and offshore-processing arrangements. Do not buy a plan automatically. Start with a single process and SQLite for low-volume pre-launch testing. Ephemeral free disks lose data and are unsuitable for customers.
2. Copy `.env.example` into the host's secret manager. Generate a fresh secret, set the exact dedicated origin and allowed host, keep intake/admin off. Mount `/data` owned by UID 10001. Do not publish SQLite or backups as web assets.
3. Build the Dockerfile. Route HTTPS to port 8000. Only set `TRUST_PROXY_HTTPS=1` if your proxy strips client-supplied forwarding headers and sets the protocol itself. Enforce client-IP request limits at the proxy; the app deliberately does not trust forwarded IPs. Restrict direct origin access and request bodies (16 KB for JSON routes).
4. Start: `deploy/start.sh` applies migrations, collects static assets and starts Gunicorn. Back up before migrations; use a maintenance window for incompatible updates. Health check `/healthz`. Do not use the Django development server publicly.
5. Verify secure cookies, HTTPS redirects, CSRF, HTTPS email delivery and reset/verify URLs on the deployed origin. Run the tests in a staging environment with synthetic data. Use `python manage.py check --deploy --fail-level WARNING`. HSTS preload check W021 is intentionally silenced until a permanent owned domain is approved.
6. Owner Google administration: set `ADMIN_ENABLED=1`, `OWNER_GOOGLE_ADMIN_ENABLED=1` and the existing `GOOGLE_WEB_CLIENT_ID`. Open `/admin/` and sign in as `kiwikindbroadband@gmail.com`. A verified Google token for that exact Gmail address, the configured client ID and a single-use session nonce creates a separate password-disabled owner operator; existing customer accounts are never elevated. Admin access expires after 30 minutes. Other accounts and ordinary customer/password sessions cannot enter. This delegates authentication to Google; it does not claim to enforce Google two-step verification. The owner should manage their Google account security in Google. No paid hosting or email service is needed. The legacy password-admin mode, if selected instead, still requires an independently enforced MFA perimeter and `ADMIN_MFA_PERIMETER_CONFIRMED=1`; that flag does not implement MFA. The user/group editor remains unregistered and invoice/audit records remain read-only.
7. Add approved entity/contact details and SMTP only after business and privacy readiness. Production refuses intake without these values, but configuration checks cannot replace actual legal review. Test operational support ownership before opening intake. No wholesale/billing enable flag exists: those integrations require deliberate new implementation and tests.
8. Build Android with `-PKIWIKIND_API_ORIGIN=https://YOUR-DEDICATED-HOST`. The website is served from that same host, so no permissive CORS is needed. Never point Android at the private Sites static preview.

## Backups / recovery

Schedule encrypted daily SQLite online backups (`sqlite3.Connection.backup`) to access-controlled off-host storage. Do not copy a live database file without an online backup/consistent snapshot. Proposed pre-launch target: 24-hour recovery point, one business day recovery time; not yet achieved or promised. Restore a backup to staging and check row counts, ownership and sign-in monthly. Keep 30 days of backups unless an approved policy changes that. Document keys, restore owners and deletion propagation. No backup scheduler is deployed by this build.

After restores invalidate sessions and review outstanding privacy requests. Rotate compromised secrets; this invalidates sessions and verification links. On incidents close intake, preserve restricted evidence, assess notifiable harm and follow the privacy runbook.

## Remaining engineering before live ISP operations

Verified supplier credentials and contract, catalog/quote acceptance with versioned terms, provisioning state machine, supplier reconciliation, authenticated/replay-safe webhooks, payments and invoice tax details, credits/refunds, switches/fault handling, monitoring/on-call, load and penetration tests. The current interface prevents accidental supplier actions. Do not represent an admin `reviewing` status as provisioning or activation.

## HTTPS mail on Render Free

Use [Brevo Free setup](HTTPS_EMAIL_SETUP.md) for the implemented HTTPS transport. SMTP ports are blocked on Render Free; adding or correcting a Gmail SMTP password cannot fix that restriction. Keep `INTAKE_ENABLED=0`. Provider keys belong only in the backend secret environment. This guide does not authorize automatic deployment.
