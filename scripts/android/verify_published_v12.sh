#!/usr/bin/env bash
set -euo pipefail
mkdir -p diagnostic-evidence
capture_logs() {
  adb logcat -d -s AndroidRuntime:E > diagnostic-evidence/runtime-crashes.txt || true
  adb logcat -d -s KiwiKindAds:W Ads:E UserMessagingPlatform:E '*:S' > diagnostic-evidence/ads-sdk.txt || true
}
trap capture_logs EXIT
adb install published-v12/android/app/build/outputs/apk/release/app-release.apk
adb install "$RUNNER_TEMP/diagnostic-tests.apk"
adb logcat -c
adb shell am instrument -w -e geography other nz.kiwikind.broadband.test/nz.kiwikind.broadband.AdPlacementVerification | tee diagnostic-evidence/other-geography.txt
adb pull /sdcard/Android/data/nz.kiwikind.broadband/files/advertising-other diagnostic-evidence/advertising-other || true
grep -q AD_OTHER_GEOGRAPHY_PASS diagnostic-evidence/other-geography.txt
adb shell am force-stop nz.kiwikind.broadband
adb shell am instrument -w nz.kiwikind.broadband.test/nz.kiwikind.broadband.AdPlacementVerification | tee diagnostic-evidence/eea.txt
adb pull /sdcard/Android/data/nz.kiwikind.broadband/files/advertising-v8 diagnostic-evidence/advertising-eea || true
grep -q AD_PLACEMENT_PASS diagnostic-evidence/eea.txt
