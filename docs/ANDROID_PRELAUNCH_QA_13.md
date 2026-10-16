# KiwiKind Android 0.2.0 pre-launch QA

This is a **debug APK for private testing**, not a Play Store release, signed production build, or permission to accept broadband orders. The backend remains on the current Render service; no new backend deploy is needed for this Android-only package.

## 13-point acceptance checklist

1. GitHub Actions backend tests pass.
2. GitHub Actions Android unit tests pass.
3. GitHub Actions Android debug compilation passes.
4. The APK is nonempty and published as a GitHub Actions artifact.
5. Verify the APK's SHA-256 against the bundled SHA256SUMS.txt.
6. Download the artifact from the successful **android-compile** run and unzip it to find app-debug.apk.
7. Install only on an Android test device you control; this is a debug-signed build, not a Play Store build.
8. Open the app and confirm the pre-launch notice appears.
9. Sign in using an existing test account or Google sign-in.
10. Force-close and reopen the app; confirm the server restores the account without another sign-in.
11. Temporarily disable internet, reopen, then reconnect; confirm the app keeps the saved session and can retry.
12. Sign out and reopen; confirm it does not silently restore a signed-out account.
13. Check that website and Android show the same account, while new broadband requests, payments, and live service promises remain disabled.

## Important boundaries

The app and website share the backend, not the same local cookie jar; you may need to sign in once on each device. A successful GitHub compile does not verify device Google OAuth, cookie restoration, or data sync. Never upload test account credentials or session cookies to GitHub issues. On Render's free instance, initial requests can be delayed by cold starts.

The artifact is retained for seven days. GitHub may require signing in to access artifacts from this private repository. Production distribution will require a separate release signing and Google Play testing process.
