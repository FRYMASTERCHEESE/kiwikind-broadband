# KiwiKind release-capable AdMob — V8 (0.2.6-prelaunch)

V8 includes Google Mobile Ads 25.5.0 and UMP 4.0.0 as implementation dependencies
in the signed release. It uses KiwiKind App ID ca-app-pub-4051392846058327~4918264616
and banner unit ca-app-pub-4051392846058327/4480562173. MoneyMate was inspected
read-only as a reference (SDK24.5/UMP3.2, consent gating and destruction), not modified.

## Test-only enforcement

Every banner request requires fresh successful UMP handling, canRequestAds(), a
foreground activity, an attached public-Home placement and AdRequest.isTestDevice().
This applies identically to signed release and debug builds. There is no live-ad
runtime switch. The SDK recognises emulators as test devices. Unregistered phones
show an explanation and make no banner-unit request. An operator can supply actual
SDK test-device hashes through KIWIKIND_AD_TEST_DEVICE_IDS (comma-separated 32-digit
hex hashes) for a controlled test build. Do not guess hashes, substitute MoneyMate
IDs, remove the guard or request real inventory to discover a device ID.

The single adaptive banner is on public Home with spacing from controls. It is
never on auth/account/support/billing/privacy/deletion pages. The placement detaches
and destroys its AdView on navigation; generation checks reject stale callbacks.
Pause/resume/destroy are forwarded. Errors leave ads off with retry. Initialization
runs in the background and does not delay the account sign-in flow.

Consent information is updated before each Home advertising attempt. The official
UMP form supplies Consent, Do not consent and Manage options. A KiwiKind-only
European-regulations message is published for this test integration. No MoneyMate
message or account-wide vendor settings were changed. Advertising privacy choices
is available on Home and native Privacy policy. Opening it removes the banner;
there is no automatic reload after choices change. If Google does not require a
privacy-options form, the app explains that. UMP refusal may permit limited ads;
the independent test-device guard remains mandatory in every case.

AD_ID and AdServices ad ID/attribution/topics permissions are removed. This does
not imply no SDK collection: the public portal privacy policy and offline native
copy disclose IP/general location, interactions, diagnostics/crash information,
installation/device identifiers, Google processing, consent and privacy options.
No account emails/passwords/messages/records are included in AdRequest.

## Focused verification and signing

New AdPolicyTest covers all 16 combinations of consent/device/foreground/attachment
and rejects non-Home/sensitive placements. Existing Endpoint/account suites are
reused where their actual source is unchanged. The ad emulator fixture uses a fresh
API36 emulator, KiwiKind's real IDs, official UMP EEA test geography and refusal,
and requires a filled test banner plus navigation destruction. It creates no
customer account or database records. No physical phone result is implied.

The protected release workflow retains the existing upload key and checks the
public SHA256 certificate against the V7 baseline. It verifies SDK classes/real IDs
in the final signed APK and the merged manifest's non-debuggable, backup/cleartext
off and absent advertising permissions. A same-signature test harness can exercise
the actual signed release on a fresh emulator; it is not distributed to customers.
V6 is preserved. V7 remains an untouched earlier ad-free candidate; V8 is the next
code and must not be submitted until its focused checks, disclosures and Play
Contains ads/Data safety review are complete.

## Play disclosure requirements for V8

Contains ads: Yes (SDK/banner code is included, even though restricted to testing).
Advertising ID: No, provided the final merged manifest confirms removal and no
other SDK requests it. Retain existing account data. Add the SDK's applicable
approximate location, app interactions, crash logs/diagnostics and device/other ID
collection/sharing, purposes, encryption and deletion descriptions based on actual
behavior and Google's current SDK disclosure guide. Do not claim AD_ID removal
eliminates all other IDs. Do not submit a no-data-collection declaration.

## Website: free address found

The project-path URL itself is rejected by AdSense's Add site form. The owned free
root frymastercheese.github.io is accepted. Its existing public ads.txt already
contains the exact publisher record and Google verified site ownership using that
file; no root/project website files or ad scripts were changed. A site entry was
created in the existing publisher account. Approval/review is separate. Review
submission requires the owner's answer to the pending approval question after an
automatic approval review blocked that external submission. No paid service is
needed merely to reach Google's review. The root also hosts other owned content;
Google's review covers the root property, including the KiwiKind project path.

No website ad code is added before site approval and owner authorisation. Existing
inert placement and future website consent/privacy preparation remain available.
Actual content approval is Google's decision; an accepted address is not approval.
The approved KiwiKind website design/copy remains unchanged. The existing developer
website on Play is the Render portal; its /app-ads.txt remains the AdMob seller file.

## Activation boundary

KiwiKind app review/store linking and Google crawler verification remain separate
from account approval. No live inventory or paid services are authorised. No orders,
payments, provisioning, public admin, referral rewards or new customer intake are
enabled. Company name reservation pending; company not incorporated.

Official references:
https://developers.google.com/admob/android/test-ads
https://developers.google.com/admob/android/privacy
https://developers.google.com/admob/android/privacy/play-data-disclosure
https://support.google.com/admob/answer/9363762
