# KiwiKind website ↔ Android: 16-step prelaunch acceptance

**Target:** one account and one server-backed set of records, not one shared device cookie. A website login and Android login each establish their own session. This checklist is not evidence that live device sync has passed.

1. Confirm Django `/health/` returns healthy over HTTPS.
2. Confirm `/api/status` reports prelaunch and intake disabled.
3. Confirm website sign-in with the existing verified Google account.
4. Confirm website reload retains the account.
5. Confirm Android build compiles and unit tests pass.
6. Install a debug APK signed by a known test signing key; do not uninstall the existing build unless necessary.
7. Verify Android Google sign-in; if credential selection fails, record the error class only (no tokens).
8. Verify Google Cloud **Android** OAuth client uses package `nz.kiwikind.broadband` and SHA-1 of the actual APK signing certificate; this is separate from the web client ID.
9. Verify Android and backend use the same Google **web** OAuth client ID as the token audience.
10. Confirm Android `/api/me` shows the same email as the website.
11. Close and reopen Android; confirm a server-verified session restores.
12. Disconnect and reconnect; confirm temporary network failure does not erase saved login.
13. Create a *non-sensitive* support conversation in the website, then refresh Android and confirm it appears.
14. Reply in Android; refresh website and confirm the reply appears once.
15. Sign out of Android; confirm Android no longer shows the account, while website's separate session remains valid.
16. Confirm no real broadband ordering, plan sale, payment or service activation is possible; get explicit business/legal and wholesale readiness review before enabling intake.

## Current engineering boundaries

Both clients target the same Render/Django API and server-side records. Their sessions are intentionally device-specific. Google Credential Manager depends on the installed app's package/signature being registered in Google Cloud; changing a web OAuth client ID alone does not register a debug APK. GitHub Actions debug APK signing SHA-1 may differ from locally built APKs, and can change with ephemeral CI keys. For repeatable OAuth, use a securely held stable signing key and register its SHA-1; do not commit keystores, passwords, client secrets or tokens.

The prelaunch test build must not enable intake, payments, admin access or imply an operating ISP. Website/app parity must be tested on real devices; a successful compile is insufficient.
