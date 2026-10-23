# Axx Mobile — Android integration

Android is a client of the existing Windows Axx instance. It shares the desktop character renderer, conversation, tool catalog and operation records. Remote voice uses the existing local Whisper service. Magic Pen and the converter remain desktop services; their full mobile operation flows are still pending.

## Latest revision

- Windows 0.20.22 executes recognized commands from phone chat through Work,
  retaining per-operation PC approval for sensitive actions and retry protection.
- Android 0.1.4/build 20: **Hablar con Axx** starts recording on the phone; choose
  Spanish or English, finish, edit the transcript and send it to the PC. Grant
  Android microphone permission first. If permanently denied, enable it in
  Android Settings → Apps → Axx Mobile → Permissions → Microphone.
- Moving/rotating the avatar uses independent input transport and desktop long
  polling; accumulated deltas are preserved. Input control still stops on local
  PC input, disconnect, leaving the pad or explicit Stop.

- Windows 0.20.21 fixes the missing QR renderer in the packaged backend. Pairing
  errors now stay visible across status refreshes; QR display no longer waits for
  history sync. The build verifies actual SVG generation from the packaged EXE.
- Full-screen trackpad and keyboard, larger touch targets and keys, compact settings overlay and input transport reuse.
- Pairing camera permission is requested explicitly, with recovery instructions after denial. The scanner opens in portrait orientation.
- Scanning or opening an `axx://pair` link previews the PC address and requires confirmation. External camera links can open Axx Mobile; availability of custom-link actions depends on the camera app.
- A new QR now keeps the gateway available for its full 120-second validity, even if an earlier device stopped polling. Previously, the old idle timer could close the gateway during the new scan.
- Desktop pairing shows a countdown and a larger high-contrast QR. Pairing links and device management are collapsible. The desktop context menu opens a new QR directly.
- The operational mobile UI combines English controls with Spanish Work and voice guidance. Existing desktop screens and historical specifications retain their original language. The original mobile prototype is preserved but excluded from the operational APK.

- Windows input monitoring now wakes immediately on messages and only installs global input hooks during a granted lease. A synthetic local hook-delivery probe improved from 48.8 ms median to 0.07 ms; this is not an end-to-end phone latency measurement.

## Pair your phone

1. Open the current Axx desktop build. In conversation settings, enable **Keep history** to allow sharing that conversation.
2. Right-click Axx → **Connect phone · QR**, or open Settings → **Connect your phone** → **Show new QR**.
3. Keep both devices on the same private LAN. On Android, open Axx Mobile → **Pair PC** → **Scan PC QR**.
4. Allow the camera while using the app. Aim it at the PC QR. Check the displayed PC address, then tap **Connect**.
5. Wait for **Your Axx is synchronized**. The character and conversation come from this PC.

If camera access was denied permanently, allow it in Android Settings → Apps → Axx Mobile → Permissions. Alternatively, expand **Use a pairing link instead** on the PC and **Paste a pairing link instead** on the phone.

For expired or already-used codes, generate a new QR on the PC. If the PC cannot be reached, keep Axx open, check the same LAN and Windows Firewall private-network access. Do not disable TLS verification. PC identity is pinned to the QR certificate fingerprint.

The gateway is opt-in and shuts down after phone contact is lost; a fresh unclaimed QR reserves a two-minute pairing window. Restarting the gateway can change its port. This revision requires a new QR after that change; automatic discovery/reconnection across endpoint changes is not yet implemented.

## Remote input and voice

- On the PC, explicitly authorize **Mouse and keyboard** for the paired device.
- On Android, choose **Desktop → Trackpad / Keyboard → Take control**. Settings overlay the pad rather than shrinking it. **STOP CONTROL** clears the phone queue and releases the PC lease.
- Physical PC input always takes priority. Local Escape cancels independently of the network. If disconnected, the native lease expires within three seconds and releases held inputs. Events are never automatically replayed.
- Grant microphone permission separately. With the phone app visible, **Ctrl + Alt + Shift + V** on the PC starts/stops capture. Final audio is transcribed on the PC. Review mode requires confirmation before desktop processing; sensitive operations retain Axx approvals. Voice does not acquire an input lease.
- The cursor contour samples the current desktop material table. It does not replace the native cursor or intercept clicks. Final physical visual acceptance of the contour and all gestures is still pending.

## Build and install

Requirements: project Windows build dependencies, Python mobile requirements, Node/npm, JDK 21, Android SDK 36. Minimum Android API is 29; target API is 36.

```powershell
python -m pip install -r requirements-mobile.txt
npm --prefix mobile ci
npm --prefix mobile run sync
mobile\android\gradlew.bat -p mobile/android assembleDebug testDebugUnitTest lintDebug
python -m unittest discover -s backend/mobile/tests -v
python -m unittest discover -s mobile/tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1
```

Browser tests require Python Playwright and Chromium. The APK is `mobile/android/app/build/outputs/apk/debug/app-debug.apk`. Install with `adb install --no-streaming -r <apk>`; preserve the existing signing certificate and app data. The Windows installer is generated under `src-tauri/target/release/bundle/nsis/`. Before upgrading Windows Axx, close it and run `python scripts/backup-mobile-upgrade.py` to preserve and verify data, WebView storage and the previous installation.

The debug APK and unsigned Windows installer are local artifacts. Source push does not publish a GitHub release or update the older installer linked in the root README.

## Contracts and evidence

- [Pairing correction verification](PAIRING-VERIFICATION.md)
- [Windows input delay correction](INPUT-PERFORMANCE.md)
- [Existing input contracts](CONTROL-REMOTO.md)
- [Existing voice contracts](VOZ-REMOTA.md)
- [Integration map](INTEGRACION.md)
- [M01–M34 / V01–V72 traceability](TRAZABILIDAD.md)

The full MO-1–MO-7 acceptance plan is not complete. Physical multi-monitor/DPI, all input gestures and interruption cases, spoken command-to-result, file/media flows, mobile Magic Pen/converter control and administrative flows remain open. iOS and MO-8 Internet access are outside this execution; API 37 acceptance remains pending by platform. No simulated test is described as physical Android acceptance.
