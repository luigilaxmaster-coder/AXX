# Pairing correction — 2026-10-22

## Cause and changes

Generating a new QR did not reset the gateway availability window. A previously claimed gateway could stop after 30 seconds without phone polling, even though its new QR advertised 120 seconds. Opening the Android scanner puts the main WebView in the background, making this failure reachable during pairing. The gateway now retains a separate monotonic pairing deadline. Renewing a code gives a full 120-second window and invalidates the previous code; claiming it returns to the normal contact watchdog. Old server connections remain unauthorized after shutdown.

On the physical Samsung, camera permission was not granted. Axx Mobile now requests it explicitly before launching the scanner, describes recovery after denial, preserves the alternate paste-link route and opens the scanner in portrait. The previous library manifest forced landscape. Opening an external `axx://pair` link previews the PC and still requires confirmation. URI validation rejects duplicate fields, fragments, user info, unexpected paths, non-LAN addresses and malformed identity/code values.

The operational mobile screens, Android messages and desktop mobile settings cards were translated to English. Full-screen controls retain large keys and touch area; settings overlay the pad. The root README now uses English and a compact update table with collapsed older notes.

## Executed checks

| Check | Result |
| --- | --- |
| Existing backend regression suite | 99 passed |
| Backend mobile unit/integration suite | 27 passed, including new-QR deadline renewal, TLS pairing, revocation, input and voice contracts |
| Isolated browser contracts | 4 passed: scan denial/retry/confirmation/deep links, shared appearance, input order/stop/no retry, large-text layout |
| Android JVM tests | 4 transport tests, 1 voice test and 1 template test passed |
| Android assemble/lint | Debug APK built; lint: 0 errors, 32 warnings |
| Samsung install | APK versionCode 16, Android 12/API 31, install `-r`: Success; existing data retained |
| Native camera permission | Denial showed recovery guidance; granting while-in-use opened the native scanner |
| Scanner orientation | Portrait scanner observed on installed versionCode 16 |
| Installed Windows → physical Samsung | Real pairing using the QR link succeeded through native pinned TLS; conversation and character synchronized |
| Optical QR read | User confirmed that scanning the displayed QR and connecting succeeded on the physical Samsung |
| Gesture/voice full acceptance | Deferred; no new input-injection or spoken-command acceptance claimed in this revision |

Browser tests use a fixture transport and are not hardware acceptance. The physical connection used the installed Windows executable and the real Android transport; no simulated backend was involved. Preview screenshots at 339×673 with enlarged text verified a pad taller than 380 CSS pixels and key height of at least 60 CSS pixels.

The user confirmed optical pairing on APK 16 (`b28746dd…`). The final APK 16 was repackaged after whitespace-only cleanup in the shared stylesheet; the scanner and transport source were unchanged. The user also confirmed that desktop closures during verification were manual.

## Windows input delay follow-up

The subsequent PC lag report exposed a 50 ms sleep in the low-level input hook owner. Hooks now exist only during remote control, and Windows messages wake the owner immediately. The synthetic callback median fell from 48.764 ms to 0.067 ms. See [measurement scope and implementation](INPUT-PERFORMANCE.md). The final Windows build below was installed successfully and its installed backend hash matched the build artifact; the usual Axx executable reported `backendReady: true`. Human-perceived smoothness after this update has not yet been confirmed.

## Build identity

| Artifact | SHA-256 |
| --- | --- |
| Android debug APK, versionCode 16 | `7b588332186de4380243efd3bf9742343f6e632105ce70c3e9241aaaec0b21ed` |
| Windows NSIS installer, 0.20.11 local revision | `cdf0d0bf9155f79431859c2af24793359ef2e2cc96a58e216894e33f2fb7df30` |
| Installed Axx executable | `30050ac97b0caf8ad7f69efbd7beebb248dd381bc1521da189a18d9706a8d586` |
| Installed backend | `c22eafef15106300a1f239a497f99fe122c9b60092e738b086708fbed59924b9` |

Windows installer exited with code 0. Existing and incoming desktop binaries are unsigned. A verified backup of 500 installation/data/WebView files was made before the upgrade. The Android debug certificate matches the preceding installed build. No uninstall or data reset was used.

The final Windows hashes identify the input-performance follow-up; optical QR pairing was confirmed on the preceding Windows pairing revision. Local detailed build logs, receipts and screenshots are under `evidence/mobile-20261022/pairing-fix/`. The published receipt omits credentials, one-use QR contents, local user paths and conversation screenshots. The root download link still points to the earlier public release; this source update does not publish a new release.

## Remaining limits

MO-1–MO-7 are not closed. API 37, mixed-DPI physical acceptance, complete remote input interruption scenarios, spoken command-to-result and remaining feature flows are tracked separately. Existing desktop screens and historical specifications are not fully translated. Automatic reconnection after the gateway changes endpoint remains pending; use a fresh PC QR.
