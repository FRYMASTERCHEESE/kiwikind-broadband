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

Working name only. On 16 October 2026 the official DNC availability search showed `kiwikind.co.nz` and `kiwikind.nz` as available. Search: https://dnc.org.nz/whois/search/?domain_name=kiwikind.co.nz#availabilityList . Availability can change and does not confer trademark rights. No purchase was made.

IPONZ Trade Mark Check for “KiwiKind” returned 77 similar-looking/sounding marks across all classes. These are fuzzy matches, not 77 exact conflicts; they require review. An initial result included “be kiwi be kind, be kind be kiwi”. The brand is not cleared. Relevant telecom/software classes and possible unregistered rights must be reviewed before purchase or public launch. Official tool: https://app.iponz.govt.nz/app/TradeMarkCheck

## Remote outcomes

Separate private source repository created and source committed: https://github.com/FRYMASTERCHEESE/kiwikind-broadband . Browser and connector authentication worked; local GitHub CLI authentication remains expired and was not replaced with any shared password/key.

Private static design preview deployment succeeded: https://kiwikind-broadband.sugary-egret-2367.chatgpt.site . It requires owner ChatGPT sign-in, has no connected customer backend and accepts no customer submissions. The Python backend needs its own dedicated persistent host. No existing app infrastructure was changed.

Android build workflow was dispatched for an unsigned, disconnected pre-launch review artifact. Consult the workflow's actual conclusion before treating an AAB as built: https://github.com/FRYMASTERCHEESE/kiwikind-broadband/actions/workflows/android.yml . No Play upload or release was submitted. Console's separate app creation form was prepared but not submitted: it includes owner policy/export certifications requiring review. No signing key was generated or reused.

See the chat handoff for verified remote repository/deployment/build outcomes; this report intentionally distinguishes implemented source from successful external publication.
