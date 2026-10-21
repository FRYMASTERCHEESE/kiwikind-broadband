# V12 consented live banners

Owner explicitly requested live AdMob ads. V12 (0.2.10-prelaunch, code12) removes the V8–V11 release-only test-device restriction. Ordinary release devices can request the existing KiwiKind banner after UMP permits ads. Google controls readiness limits/fill; an unpublished/closed-only store link can prevent full readiness approval without prohibiting every limited request. Do not claim guaranteed revenue/fill or bypass Google review.

Debug builds remain test-only. Emulators and registered test devices retain SDK test status, including in the signed live-capable release. Automated signed instrumentation refuses to proceed unless the SDK recognizes its device as a test device, verifies the actual signed live capability without making live requests, then checks consent refusal, test fill, privacy reopening and lifecycle/account exclusions. Unit tests cover every combination of consent, test/live mode, foreground and attachment. No real ad impressions/clicks are used for QA.

Home remains the only advertising placement. Account/support/billing/privacy/deletion stay ad-free. Existing UMP failure handling, consent checks, privacy choices, no automatic reload after choice changes, lifecycle and stale-callback guards remain. AD_ID/AdServices permissions remain removed. No customer data is added to requests. Native offline and GitHub Pages privacy disclosures describe version-specific behavior.

Preserve Closed Alpha enrollment/groups/countries. Do not cancel an existing review to speed this update. Check actual Play status before uploading the next verified bundle. Existing upload key and all optimization/layout safeguards remain. No live payments, public prices, supplier orders or backend deployment are authorized by advertising activation.

Google: https://support.google.com/admob/answer/9989980?hl=en ; https://developers.google.com/admob/android/test-ads
