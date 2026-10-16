# Build verification — 16 October 2026

## Confirmed locally

- 18 Django workflow/security tests passed (isolated database and email outbox).
- Migration consistency: no changes detected after initial migration generation.
- JavaScript syntax check passed.
- Production Django deployment checks passed; one intentional silencing: HSTS preload W021, deferred until owned permanent domain approval.
- Backend migrated locally; health endpoint returned HTTP 200. Browser loaded the real backend website and confirmed intake-closed status.

Tests cover ownership isolation, authentication requirement, CSRF protection, email verification/reset link use, password validation, request idempotency and cancellation, invalid input, support messages, private read-only invoices, export/deletion requests, login throttling, admin/intake gates, supplier refusal and logout. They do not constitute penetration testing, supplier acceptance, device testing or legal certification.

## Implemented but external validation pending

Native Android client, Gradle build/CI, Docker deployment, admin support replies and operating runbooks. Backend and Android are not yet deployed as a synchronized public production service. SMTP, billing provider, wholesale API, MFA perimeter, backups, monitoring and real operational staff are not configured. Privacy and terms are pre-launch drafts. A live ISP company has not been created.

## Brand

Working name only. Search research found an unrelated KIWIKIND trademark listing outside the NZ official register; it is not a NZ clearance result. IPONZ and .nz registry/registrar checks are needed for exact/similar names and domains immediately before any purchase. No trademark/domain availability claim and no purchases.

See the chat handoff for verified remote repository/deployment/build outcomes; this report intentionally distinguishes implemented source from successful external publication.
