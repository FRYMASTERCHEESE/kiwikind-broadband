# Android and Google Play release checklist

Existing account verified in browser: **FryMasterCheese Studios**. MoneyMate NZ is present and must remain untouched. KiwiKind has separate source and proposed application ID `nz.kiwikind.broadband`. Package availability must be checked in Console; the identifier is not a domain-ownership claim. Do not reuse MoneyMate signing material or app listing.

## Build

Native Java Activity screens (no WebView), shared HTTPS API, encrypted persistent session cookies, native requests/support/replies/billing views, privacy export to Android document picker and deletion-request flow. No ads, analytics SDK, camera, location, phone or storage permission. INTERNET only. Android backups are disabled; screenshot capture is not blocked, so avoid including private customer data in screenshots. Verification/reset emails open website flows. No offline data cache or push notifications. Refresh/reopen lists to see website changes.

Use JDK 17, Gradle 9.6.0, Android Gradle plugin 9.4.0 and installed Android SDK 36. AGP compatibility source: https://developer.android.com/build/releases/gradle-plugin . No Gradle wrapper binary is bundled; use installed Gradle or the included GitHub Actions workflow. Installing SDKs may require you to accept their licence.

```text
cd android
gradle testDebugUnitTest lintDebug assembleDebug -PKIWIKIND_API_ORIGIN=https://YOUR-DEDICATED-HOST
```

Blank API origin builds a disconnected debug shell for source review. Release tasks require a connected HTTPS origin and complete protected signing configuration. See [ANDROID_SIGNING.md](ANDROID_SIGNING.md) for secret setup, certificate register and the manual signed release pipeline. No upload key has been invented or copied. A signed artifact is not established until that workflow succeeds.

The manual **Android pre-launch build** workflow produces debug review artifacts only. **Android signed prelaunch release** produces verified signed APK/AAB artifacts after protected environment secrets are configured; it does not publish to Play.

## Before internal testing

- Deploy the backend and approve synthetic staging tester access. Configure legal/privacy/support contacts before real users. Verify same account and requests from website and Android, after logout/login and across two devices.
- Compile, lint and run unit tests; install on Android 8+ and API 36 physical/emulated devices. Test network failures, TLS errors, expiry, process death, rotation, large fonts, TalkBack, keyboard navigation and edge-to-edge layouts. The user has confirmed Android Google sign-in, session restore/reopening and backend connectivity on their phone; retain that evidence without requiring repeats. Other device acceptance scenarios remain unverified.
- Explicitly test registration/email verification/reset, request retry and cancellation, two-account isolation, support reply, export save/cancel and deletion review. This checklist is not evidence that those Android scenarios already passed.
- Prepare a properly signed AAB and verify with `jarsigner -verify`. Run Play pre-launch reports, address crashes/ANRs and check all native library/16 KB compatibility obligations if native SDKs are ever introduced.
- Create a separate Console app; free, app category, NZ English where available. Account owner must review Developer Program Policy and US export declarations. Do not certify an unfinished/unreviewed release on their behalf.
- Current target requirement checked against official Android docs: API 36 for new phone app submissions. Recheck at release: https://developer.android.com/google/play/requirements/target-sdk

## Store and compliance

Working title: KiwiKind Broadband. Draft short description: “Manage your KiwiKind account, broadband requests and support conversations.” This must not imply live service until available. No invented speeds, prices, awards or coverage. Supply approved 512px icon, 1024×500 feature graphic and screenshots from the actual functioning app; the source vector launcher icon is not a complete store asset pack.

Publish an accessible, truthful privacy policy and account-deletion web route (the current website privacy section describes the process but needs an actual unauthenticated contact before release). Complete Data safety based on the deployed build: account email/name/address/optional phone, support messages and user IDs; encrypted transport, user-requested deletion, required/optional fields and processing/sharing purpose must match reality. Passwords are hashed; hashing does not make the account anonymous. No ads/analytics in this version. Do not declare “no data collected” for the connected client.

Provide review access with a dedicated synthetic test account, monitored support contact, content rating/target audience declarations and app-access instructions. Review account type/verification requirements with Google when the business exists. Do not publish billing or service-management claims unsupported by the build.

Start internal testing, then required closed testing. Google requires affected personal developer accounts created after 13 November 2023 to have at least 12 continuously opted-in testers for 14 days before production access; verify the actual account's Console requirements: https://support.google.com/googleplay/android-developer/answer/14151465 . Google review and production-access approval are external decisions, not guaranteed by uploading an AAB.
