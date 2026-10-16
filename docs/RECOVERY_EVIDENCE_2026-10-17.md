# KiwiKind recovery evidence — 17 October 2026

This document records **read-only** verification, not a production release or proof of email delivery.

## Isolated Neon snapshot restore: PASS

- Project: `hidden-frost-14323997`
- Manual snapshot: `snap-long-glade-a7k97m29` (`kiwikind-main-free-backup-2026-10-17`)
- Isolated branch: `br-cold-rain-a7cd0m2h` (`kiwikind-restore-drill-20261017`)
- Neon reported `restore_status=restored` and the isolated branch became `ready`.
- Production branch `br-lively-star-a72fm6bs` remained `ready`.
- Read-only aggregate checks:

| Table | Production | Isolated restored |
| --- | ---: | ---: |
| django_migrations | 20 | 20 |
| auth_user | 1 | 1 |
| django_session | 2 | 2 |

No account data, password, session contents, or customer identifiers were exported. No production restore was performed.

**Important:** The isolated branch remains present; do not delete it without explicit owner approval. Confirm Neon Free-plan resource usage before keeping it long term. This check establishes basic restore viability, not a full disaster-recovery rehearsal.

## Email verification and password reset: DELIVERY UNVERIFIED

- Source reviewed: `portal/views.py`, `config/settings.py`, and `portal/tests.py`.
- Existing automated test `test_verification_and_password_reset` covers verification, replay rejection, reset, and replay rejection; it was **not rerun**.
- SMTP depends on `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, and a working authorized test mailbox.
- No outbound email was sent, no production account modified, and no email delivery result is claimed.
- A real end-to-end test must use a synthetic account and authorized mailbox, with no customer-facing intake or orders enabled.

## Release gates

Do not enable intake, payments, provisioning, or administrative access until independent legal, commercial, security and operational gates are met. No percentage of launch readiness is certified by this document.
