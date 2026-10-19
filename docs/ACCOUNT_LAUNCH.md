# Account-only launch — 20 October 2026

The owner approved opening free account/app features while broadband orders and payments remain closed.

- Set `REGISTRATION_ENABLED=1` independently of `INTAKE_ENABLED=0`.
- Keep `REFERRALS_ENABLED=0`; rewards, payments, live services and supplier transport remain disabled.
- Set the legal entity to KiwiKind Broadband Limited (NZBN 9429054036550), with the existing business/privacy contact kiwikindbroadband@gmail.com.
- Preserve DATABASE_URL, SECRET_KEY, Google OAuth, owner-only admin and existing customer records. Never copy production data into local tests.
- Website and Android use the same HTTPS backend. New Google accounts require server-verified identity; password accounts require emailed verification. Existing identities are not automatically linked by email.
- Registration mail transport failures give a controlled response; failed recipient delivery rolls back incomplete new accounts. Existing accounts are unchanged.
- Bootstrap returns session, CSRF, registration capability and public service state in one response. Website startup no longer makes serial status/CSRF/identity requests.
- Android V10 (0.2.8-prelaunch) reads the registration capability. V9 can use newly opened Google registration, but its email-signup button remains tied to intake and needs the update.

## Rollout

Run backend security/account-isolation tests on disposable SQLite and PostgreSQL, JavaScript tests, phone/desktop checks and Android unit/lint/build checks. Merge the reviewed branch into the existing Render source branch `feature/neon-postgres-config`, then deploy that exact verified revision. The only schema migration since the live d0a6748 is the additive wholesale preparation migration 0009.

Render configuration is managed directly on the existing service; the legacy blueprint is not applied for this release. Merge only the new non-secret settings, preserving all other keys. Verify `/healthz`, `/api/status` and anonymous `/api/bootstrap`, the sign-up screen, access controls and disabled orders after deployment. Do not create synthetic customers in production or send test mail without explicit authorization.

Build with the existing protected Android upload key; never substitute a new certificate. Upload to the existing Alpha track. Public Google Play distribution still requires its testing/production-access process. Keep tester groups and countries unchanged.

Update the separate public website copy only after the backend is live. Its account links continue to point to the same customer backend.

## Recovery and limits

To pause new accounts, set `REGISTRATION_ENABLED=0` and redeploy; existing customer access remains available. Keep intake at zero. A code rollback does not undo migrations; 0009 is additive and old code can ignore its tables. Do not reverse migrations or delete customer data.

The existing free Render instance can sleep when idle. Fewer startup requests improve warm-page loading but do not remove the host's cold-start delay. No paid hosting upgrade or keepalive automation is part of this launch.
