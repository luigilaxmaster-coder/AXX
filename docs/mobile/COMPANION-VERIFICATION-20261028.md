# Mobile companion verification — 2026-10-28

Source: Windows 0.22.15, Android 0.2.0-companion / versionCode 21.
Review: self-review; dev-team personas supplied design analysis, not an independent
review of the implementation.

## Confirmed

| Check | Result | Scope |
| --- | --- | --- |
| `python -m unittest discover -s backend/mobile/tests -v` | 55 passed | Pairing, persistence, control/voice contracts, current grants, history consent |
| Command library, HTTP and language tests | 37 passed | Includes executable catalog authentication and removal of disabled records |
| Real TLS → desktop command service integration | Passed | System telemetry; same operation ID reused; disposable note written only after PC approval |
| `python -m unittest discover -s mobile/tests -v` | 7 passed | Browser fixtures: live state, catalog/search, parameter types, recovery, layout, existing trackpad and keyboard |
| `python scripts/test_release.py` | 16 passed | Existing version and publication gates |
| Android `assembleDebug testDebugUnitTest lintDebug` | Build successful | Existing dependency lint baselines retained; no physical Android attached |
| Windows build | NSIS installer generated | Packaged QR runtime smoke check passed; native installed feature acceptance pending |
| Frozen sidecar integration in disposable app-data | Passed | Actual generated QR decoded at 320 px by Android's ZXing 3.5.3 core; TLS claim; typed command → verified telemetry; retry keeps operation ID; rescan retains grants; unshared history omitted |

The frozen runtime exposed **67 executable commands** in its test configuration.
Enabled MCP and generated tools can change this count in a configured desktop.
Listing a command does not establish that it was executed or physically validated.

OpenCV failed to decode one generated QR while another succeeded. Verification was
therefore repeated with the same ZXing core used by the Android scanner. This is
image-decoding evidence, not a camera scan of a physical display.

## Local artifacts

- Android APK SHA-256:
  `32d06b05bfa4f5d4a83fa1a1d4840398106714f4919875fbb9e2dac5df90acd7`
- Windows installer SHA-256:
  `563877bccfae2beb4cc723ed37612a00ce8a1b687ddaf531bf3e33442a3cfa73`
- Local build and test receipts: `build/release-mobile-0.22.15/`,
  `build/mobile-android-final.log`, `build/mobile-ui-final-v2.log`.
- Native acceptance harness prepared locally at `build/verify_mobile_installed.py`.
  It has not run against 0.22.15 installed on this machine.

## Pending

The installed application was in use by another active voice-integration chat.
Its closure and replacement need coordination before installation and native
acceptance. The first backup attempt encountered an open WebView file; repeat the
verified backup after closing the identified app. Do not publish 0.22.15 until a
matching installed-runtime receipt and native acceptance exist. The confirmed
published Windows download remains 0.22.11.

The user deferred physical Android installation and acceptance. Camera permission,
camera-to-display scanning, suspension/reconnection and phone-to-Windows physical
effects remain pending. Browser fixtures and frozen-PC integration do not replace
those checks. iOS, an Internet relay and complete mobile Magic Pen/file-converter
flows are not provided by this revision.
