# Manual catalogue and owner MFA

This release extends the actual Render deployment branch, `feature/neon-postgres-config`, from `8af2508`. It retains PostgreSQL, Google customer sign-in, Brevo mail, customer preferences/referrals, shared applications/support and existing manual Vetta preparation.

PRs #35 and #36 target the older `main` branch. They must not replace the deployed branch: that would lose working authentication/database integration and conflict with migration history. Stripe work remains a separate disabled draft until reconciled and verified.

## Owner access

Open `https://kiwikind-backend.onrender.com/admin/` privately. Sign in with `kiwikindbroadband@gmail.com`. Google signature, audience, issuer, verified email, fresh timestamp and a browser-bound single-use nonce are checked server-side. The dedicated existing owner account is separate from the customer account. Its immutable Google subject and database identity are bound in a private allowlist after the first verified sign-in; subsequent subject changes are rejected. Ordinary email login, matching email fields and other staff/superusers grant no admin access.

On first sign-in, add the displayed private setup key to an authenticator as a time-based account, then enter its six-digit code. The owner must perform this step themselves. Never copy the key or code into chat, email, screenshots, issue/CI logs or source. Subsequent sign-ins require Google plus an authenticator code. The server enforces this for every admin route, including wholesale actions. Old Google-only sessions cannot access admin after this release. Customer sessions are preserved.

Authentication codes are rate-limited and cannot be replayed. Enrolment/verification locks the device during verification. Enrolled secrets are never displayed again. MFA pages are not cached and load no third-party scripts. Authenticator, identity, user and group editors are absent from admin.

Recovery requires independently verifying the owner through trusted infrastructure access, disabling admin access while recovering, revoking affected owner sessions/devices and enrolling a new device. There is no email-only or password fallback. Protect database backups, which contain authenticator secrets.

Required production configuration retains `ADMIN_ENABLED=1`, `OWNER_GOOGLE_ADMIN_ENABLED=1`, and the existing Google client ID. Mandatory application MFA replaces the obsolete perimeter-attestation flag; a flag cannot bypass the authenticator check.

## Catalogue

Admin → **Price catalogue** extends existing draft-plan records with source, verified network, speeds, wholesale monthly/setup amounts excluding and including 15% GST, validity, address scope, review/approval and retail prices. Approval requires a current verified general offer and records the owner and time. It does not itself enable publication.

Migration 0011 adds the user-supplied Direct UFB 500/100 quote only if absent: $69.92 / $80.41 monthly and $35.00 / $40.25 setup, excluding/including GST. It stays an address-specific private draft. Source screenshot, address, network and validity remain unconfirmed; no retail price is invented.

Keep `PLAN_PUBLICATION_ENABLED=0`. `/api/plans` then returns an empty list. If explicitly enabled in a future approved release, it returns only current, general, owner-approved retail fields; never wholesale prices, source references or private notes. Availability remains unverified. No Vetta API, live availability lookup, payment or supplier-order endpoint is added.

## Deployment and recovery evidence

- Service: `srv-db8qqgks728c73ao7lm0` (`kiwikind-backend`), Render workspace confirmed by owner.
- Existing Neon project: `hidden-frost-14323997`, main branch `br-lively-star-a72fm6bs`.
- Pre-deployment aggregate: 4 accounts, 2 Google identities, 0 broadband requests, 1 support ticket, 0 draft plans; one eligible dedicated owner account.
- Snapshot creation hit the existing account limit. No prior backup was deleted.
- Recovery branch `br-empty-glade-a7b8qs5v`, `kiwikind-before-catalogue-mfa-20261020`, preserved main at LSN `0/2343228`; Neon reports ready. It has no compute endpoint. This is a recovery copy, not evidence that a fresh restore drill was completed.
- Migrations are additive. Keep the prior application image and recovery branch. Do not restore over production or reverse migrations without evaluating newer customer writes.

Keep intake, live payments, supplier submissions and unapproved-plan publication disabled. `STRIPE_TEST_CHECKOUT_ENABLED=0` and `STRIPE_TEST_PRICE_REVIEWED=0` remain explicit deployment settings. GoCardless approval and Vetta integration access remain outstanding.
