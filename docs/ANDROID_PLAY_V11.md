# Android Play warning remediation (code11)

0.2.9-prelaunch retains package nz.kiwikind.broadband and the existing protected upload signer. No API/database, identity, sales, public price, supplier-order or website URL changes.

The app uses WindowCompat.enableEdgeToEdge and ViewCompat/WindowInsetsCompat for system bars, cutouts and IME. The root uses the union of inset types (maximum per edge, not summed), preserving keyboard-safe space in portrait/landscape. adjustResize enables compatible keyboard inset delivery. Deprecated app-owned system UI flags, platform inset getters and bar-color theme settings were removed. AndroidX Core1.17.0 supplies the stable API for compile/target36 and min26.

AGP9.4 release optimization enables code/resource shrinking and obfuscation. Narrow keep rules preserve only reflection used by existing same-signature release instrumentation; no package-wide keep or dontoptimize/dontobfuscate is added. Mapping is required and exported for deobfuscation. SDK consumer rules remain in force for Google credentials/Ads/UMP.

The protected signed workflow checks signatures and manifest safeguards, requires an R8 mapping, tests portrait, IME avoidance and landscape recreation against the optimized signed APK, and reruns consent refusal, filled SDK TEST ads, privacy reopening/lifecycle and account/privacy ad exclusion. It records screenshots and failures as well as successful evidence. It never accesses a real Google/customer account or charges a card.

Play delivery uses the existing Closed testing Alpha track and tester group. Do not opt existing testers into Internal testing or reset closed-test enrollment. Upload code11 only after signed checks pass, inspect Play warnings and mapping, and submit only that closed track. Historical warnings attached to code10 are distinct from code11 analysis. Google pre-launch reports run automatically on new artifact upload subject to device-lab capacity; inspect the actual report state and do not claim an unstarted/uncompleted test passed. No owner credentials should be supplied to the crawler. Existing Google sign-in can be used by the crawler; coverage must be established by the report.

References:
- https://developer.android.com/develop/ui/views/layout/edge-to-edge
- https://developer.android.com/topic/performance/app-optimization/enable-app-optimization
- https://support.google.com/googleplay/android-developer/answer/9842757
