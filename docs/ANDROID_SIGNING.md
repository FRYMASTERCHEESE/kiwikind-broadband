# Repeatable Android signing

Package: `nz.kiwikind.broadband`. Never reuse another app's key. Release APK/AAB tasks now fail if signing material is missing or incomplete, or the API origin is blank. Debug tests/builds remain available without release secrets.

## Protected setup

Use the existing KiwiKind upload keystore if one exists. Its owner must retain an encrypted backup and recovery credentials outside GitHub and source control. Do not generate a replacement for a distributed app without reviewing update continuity. No key or password was invented or created by this change.

Configure the GitHub environment `android-release`, restrict it to reviewed release branches, and set these environment secrets:

- `KIWIKIND_KEYSTORE_BASE64`: base64 encoding of the existing keystore file.
- `KIWIKIND_STORE_PASSWORD`: store password.
- `KIWIKIND_KEY_ALIAS`: upload alias.
- `KIWIKIND_KEY_PASSWORD`: alias password.

The manual **Android signed prelaunch release** workflow validates the keystore, runs unit tests and release lint, builds signed APK and AAB, verifies both signatures and exports public certificate evidence plus SHA-256 checksums and source commit. It does not upload to Play, publish a release, enable intake, or change the backend. Secrets are removed from the runner even after failure. Protect artifact access: these are private prelaunch builds.

Local builds use the four `KIWIKIND_*` environment variables in `android/app/build.gradle`, with `KIWIKIND_KEYSTORE` set to a local file path instead of base64. Run `gradle testDebugUnitTest lintRelease assembleRelease bundleRelease` from `android/`.

## Certificate register (public fingerprints only)

| Certificate | SHA-1 | Evidence/status |
| --- | --- | --- |
| Previous debug APK from PR #13 | `B9:00:75:5C:B2:E2:07:44:CC:6A:BF:97:6B:FA:B0:BF:44:67:90:0A` | Previous Work report, APK SHA-256 `f13e8bf6590a83723ff56743bf48014acdbdf195fc4f5660f3e4b51dd6a5afc8`; debug key may vary across CI builds. |
| Stable upload/release key | Unknown until protected keystore is supplied | Read `APK-CERTIFICATE.txt` and `BUNDLE-CERTIFICATE.txt` from a successful signed workflow; never substitute the debug fingerprint. |
| Google Play app signing key | Unknown until Play setup | Read App integrity in the KiwiKind Play Console app. Play-delivered installs use this certificate, which may differ from the upload key. |

For each distributed signing certificate, the Google Android OAuth client must match both package and actual signing SHA-1. Record registration evidence here after inspecting Google Cloud; registration has not been verified by this change. Web client/audience is configured separately. A release-signed APK cannot update an installed debug-signed APK; do not tell testers to uninstall until considering saved-session continuity. Existing server account data must be preserved.

The user has already confirmed successful Android Google sign-in, reopening/session restore and backend connectivity. Do not repeat those tests as a release prerequisite for the same tested build. A future certificate change still requires verifying that new certificate's OAuth configuration.
