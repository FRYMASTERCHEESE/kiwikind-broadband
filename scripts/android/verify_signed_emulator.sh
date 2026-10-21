#!/usr/bin/env bash
set -euo pipefail
mkdir -p release-evidence
capture_crash_log() {
  adb logcat -d -s AndroidRuntime:E > release-evidence/ANDROID-CRASHES.txt || true
  cat release-evidence/ANDROID-CRASHES.txt
}
trap capture_crash_log EXIT
adb install android/app/build/outputs/apk/release/app-release.apk
adb install "$RUNNER_TEMP/kiwikind-layout-tests.apk"
adb shell pm list instrumentation | tee release-evidence/layout-runner.txt
adb logcat -c
adb shell settings put secure show_ime_with_hard_keyboard 1
adb shell am instrument -w nz.kiwikind.broadband.test/nz.kiwikind.broadband.LayoutVerification | tee release-evidence/layout-signed-emulator.txt
grep -q SIGNED_LAYOUT_PASS release-evidence/layout-signed-emulator.txt
adb pull /sdcard/Android/data/nz.kiwikind.broadband/files/layout-v11 release-evidence/layout-v11
adb shell am force-stop nz.kiwikind.broadband
adb uninstall nz.kiwikind.broadband.test
adb install "$RUNNER_TEMP/kiwikind-ad-tests.apk"
adb shell pm list instrumentation | tee release-evidence/consent-runner.txt
adb shell am instrument -w nz.kiwikind.broadband.test/nz.kiwikind.broadband.AdPlacementVerification | tee release-evidence/advertising-signed-emulator.txt
adb pull /sdcard/Android/data/nz.kiwikind.broadband/files/advertising-v8 release-evidence/advertising-v8 || true
adb logcat -d -s KiwiKindAds:W Ads:E UserMessagingPlatform:E '*:S' > release-evidence/ads-sdk-log.txt
grep -q AD_PLACEMENT_PASS release-evidence/advertising-signed-emulator.txt
