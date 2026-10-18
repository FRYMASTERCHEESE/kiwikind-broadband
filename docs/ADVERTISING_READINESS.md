# Advertising setup — 18 October 2026

Live advertising remains OFF. No paid service or new publisher account was created.

## Verified account and identifiers

Authenticated Google console account: coreyedge123@gmail.com.
Publisher: pub-4051392846058327. AdMob Home reports the account approved.
The full app list and apps-to-confirm list contained MoneyMate only before this
work. One separate Android entry, KiwiKind Broadband, was created without changing
MoneyMate. Real Google-assigned IDs are recorded in advertising/account-inventory.json:

- App: ca-app-pub-4051392846058327~4918264616
- Banner: ca-app-pub-4051392846058327/4480562173
- Banner name: KiwiKind Public Home Banner
- Intended package: nz.kiwikind.broadband (not yet linked to a public store listing)

These IDs are documentation inventory only, absent from runtime manifests/code.
Account approval does not establish app approval. The unlisted Android entry still
needs a supported, publicly discoverable store link, verification and app review.

## Public seller records

Both prepared files contain the real publisher seller record:
`google.com, pub-4051392846058327, DIRECT, f08c47fec0942fa0`.
The Django routes serve it as plain text at /app-ads.txt and /ads.txt. Publishing
these files does not initialize ads or request live inventory. The developer
website in the Play listing must use the same hostname where app-ads.txt is hosted:
https://kiwikind-backend.onrender.com/ (existing free KiwiKind portal).

The file under the GitHub project path alone would not satisfy root discovery.
Google ignores the path when deriving app-ads.txt from a developer website URL.
Public HTTP success and Google verification are separate checks; allow crawl delay.
Do not modify another project or shared root to achieve verification.

## Android test placement and release

Only the optional internal debug variant (-PKIWIKIND_TEST_ADS=true) includes
Google Mobile Ads 25.5.0 and UMP 4.0.0. It uses official sample app ID
ca-app-pub-3940256099942544~3347511713 and sample adaptive banner unit
ca-app-pub-3940256099942544/9214589741. AD_ID is removed in debug.
The manual preview is restricted to public Home. A dedicated child layout detaches
on navigation; all delayed success callbacks check that it remains attached before
showing consent, initializing the SDK or loading an ad. Repeated presses in the
same Home instance do not start duplicate requests. Detached AdViews are destroyed.
Login, privacy, deletion, support, billing and account screens have no placement.

UMP errors or canRequestAds=false leave the preview off. Compilation does not
prove consent-message configuration or filled banners. No actual fill, physical
phone or production consent check is claimed. The debug preview is never uploaded
to Play. Release SDK dependencies and signing keys are unchanged; the already
signed V7 ad-free candidate remains the next safe release, pending physical-device
acceptance and declaration review. No live IDs are substituted in test builds.

## AdSense and website preparation

Authenticated AdSense Sites initially lists only bebo.nz, Getting ready, ads.txt
Authorized. It is unrelated and was not changed. KiwiKind site approval is not
established. The approved GitHub Pages design and wording remain untouched.
The supplied project URL includes a path and is unsuitable under ordinary AdSense
site URL rules. An eligible owned site/domain with root control and substantial
original useful content is needed; no domain purchase is authorized or made.
Render root hosting solves app-ads.txt hosting, not AdSense domain eligibility.

The existing inert placement preview is suitable only after public informational
content before the footer, labeled Advertisement, with reserved responsive space
and distance from controls. No scripts, live calls or empty visible slots are added.

Before activation publish accurate disclosures of Google advertising, device/IP
and interaction/diagnostic data, cookies/local storage, purposes, recipients,
retention and privacy choices. Current public privacy notice accurately states
that distributed releases do not contain ads and describes internal test builds.
A Google-certified CMP and applicable regional consent/privacy choices must be
configured before required-region requests; a home-made popup is not sufficient.
AdMob UMP messages and a privacy-options entry point need verification using the
real app configuration before any production SDK release.

## Play declarations

Current V6 and prepared V7 release do not contain the advertising SDK or request
AD_ID. Do not mark Contains ads=yes or advertise SDK data collection solely because
an internal debug preview exists. Before a production advertising binary, update
Contains ads, Advertising ID, Data safety, target audience and consent declarations
to match actual behavior, including collection not eliminated by removing AD_ID.
Referral/account data in V7 still requires the broader release declaration review.
No new advertising binary is distributed by this setup.

## Activation gate

Require app/store verification and approval, eligible approved website for AdSense,
reviewed privacy/consent messages, tested privacy choices, exact declaration review,
physical-phone acceptance and explicit owner authorization before live advertising.
Keep customer intake, broadband orders, provisioning, payments and public admin off.
Company name reservation is pending; the company is not incorporated.

## Official references

- https://support.google.com/admob/answer/9363762
- https://support.google.com/adsense/answer/12171612
- https://support.google.com/adsense/answer/2784438
- https://support.google.com/adsense/answer/9724
- https://support.google.com/adsense/answer/1348695
- https://developers.google.com/admob/android/quick-start
- https://developers.google.com/admob/android/banner
- https://developers.google.com/admob/android/privacy
- https://developers.google.com/admob/android/privacy/play-data-disclosure
