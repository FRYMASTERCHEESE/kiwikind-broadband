# Advertising preparation — 18 October 2026

Live advertising is disabled. No publisher account, live ad unit, commercial
agreement or purchase was created. The app remains free to download.

## AdSense

The existing public site is a prelaunch brand/vision page, with no established
service offering or body of original broadband editorial content. Its approved
design and wording are preserved. Approval cannot be inferred from technical
validity, traffic or possession of source code.

The supplied URL contains a project path under `github.io`. Google's current
[site URL rules](https://support.google.com/adsense/answer/2784438) require a
standard domain without a path and limit accepted subdomains to host partners.
The exact project URL is therefore not a suitable ordinary application URL.
Do not submit `github.io`, imply ownership of it, purchase a domain, or claim
GitHub is an approved host partner. A separately approved owned domain with root
file control is the practical next step, subject to the owner's approval.

Prepare one responsive inline slot after original public informational content,
before the footer. Exclude authentication, account dashboards, support messages,
privacy, deletion, billing, forms, navigation and error screens. Label it
Advertisement, reserve space to avoid layout shift, keep it away from buttons,
and ensure the ad never obscures content. No empty visible slot or ad script is
inserted into the approved public site now.

`advertising/ads.txt` is a comment-only preparation file, not an authorization.
After publisher approval, publish only the exact seller record supplied by the
publisher account at the approved domain root. Add publisher verification/meta
or script only after the real account and owner authorize it. Do not fabricate
publisher IDs or reuse Google's Android sample IDs on the website.

Before activation: original useful content, operator/contact accuracy, publisher
verification, domain approval, approved privacy disclosures, retention and user
choices. Inventory cookie/local-storage use; essential account cookies do not
authorize advertising cookies. Configure a Google-certified CMP where required
(including EEA/UK/Switzerland), withdrawal/privacy choices and applicable regional
messages; block ad requests until the required consent decision permits them.
Do not build an imitation consent popup and call it Google certified.

References: [eligibility](https://support.google.com/adsense/answer/9724),
[privacy content](https://support.google.com/adsense/answer/1348695).

## AdMob

An optional internal debug build uses `-PKIWIKIND_TEST_ADS=true`, the official
sample application ID `ca-app-pub-3940256099942544~3347511713` and adaptive banner
unit `ca-app-pub-3940256099942544/9214589741`. SDKs are debug-only and absent from
the ordinary debug/release runtime dependency graph. No publisher ID is invented.
The optional preview is opened manually from the public Home information screen,
never during sign-in or sensitive account workflows. AD_ID is removed in that
debug manifest; this does not imply all other SDK collection is disabled.

The preview requests UMP consent information, shows a required form when available
and requests a banner only after `canRequestAds()`. Missing consent configuration
or a service error leaves ads off. No assurance of a filled ad or configured UMP
message is made from compilation alone. Sample IDs may not have the publisher's
consent message configured. No app-open, interstitial or rewarded ads are added.

Live-ad preparation still needs: an authorized AdMob account/app, real application
and banner IDs, policy/readiness review, approved consent messages and privacy
options entry point, publisher verification and explicit owner authorization.
The debug preview must never be the Play release. Before embedding a production
SDK, audit its initialization/provider behavior, lifecycle and network collection.

`advertising/app-ads.txt` is comment-only preparation. The actual seller line must
be published at the ROOT of the developer website linked from the Play listing,
not assumed discoverable beneath the current project path. Do not alter a shared
root site or another project to achieve this without authorization.

## Google Play declarations

The V7 release prepared here does not contain the advertising SDK, serve ads or
request Advertising ID. Preserve truthful declarations for the distributed binary;
do not mark live ads as present merely because an internal debug preview exists.
Review the current Console form against the final merged manifest and actual SDKs
before V7 upload. Referral relationships/status and account notification preferences
now need review alongside existing email/account/support data, purposes, encryption,
deletion pathway and optional collection choices. Nothing is automatically filed.

If a later binary includes production advertising, review Contains ads, Advertising
ID, Data safety, age/target-audience and consent declarations before distributing it.
Google's [SDK disclosure guide](https://developers.google.com/admob/android/privacy/play-data-disclosure)
describes IP/general location, interactions, diagnostics and device identifiers.
Removing AD_ID alone is not a basis to declare no data collection.

References: [SDK setup](https://developers.google.com/admob/android/quick-start),
[test banner](https://developers.google.com/admob/android/banner),
[UMP](https://developers.google.com/admob/android/privacy),
[app-ads.txt](https://support.google.com/admob/answer/9363762).
