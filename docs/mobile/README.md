# Axx Mobile — Android integration

Android is a client of the existing Windows Axx instance. It shares the desktop character renderer, conversation, tool catalog and operation records. Remote voice uses the existing local Whisper service. Magic Pen and the converter remain desktop services; their full mobile operation flows are still pending.

## Latest revision

[Encrypted file transfers, phone dictation and cross-network setup in 0.2.5](TRANSFER.md). Physical phone and cross-network acceptance for this revision were not performed.

[Themes, GPU and two-way character customization in 0.2.4](PERSONALIZATION-20261028-024.md).

[Previous 0.2.3 physical checks](VISUAL-REVISION-20261028-023.md).

[Previous 0.2.2 verification](MINIMAL-UI-20261028-022.md).


### Existing companion behavior and 0.2.4 validation

Android **0.2.4-companion / build 25** improved the existing Windows-linked
companion rather than introduce a separate assistant. The phone follows the PC's
appearance, active shared conversation, model selection and current grants. Active
snapshots poll every two seconds while the phone is visible. Commands use the
desktop's resolver and executor; the searchable executable catalog also includes
enabled MCP and approved generated capabilities. Disabled and documentary records
are not advertised as executable. New tools appear on reopening Actions or within
the ten-second catalog refresh while that pane remains visible.

The interface uses four focused tabs, light/black surfaces and a single home entry to chat. Character settings include a local theme/accent and shared PC color, shape and finish. Shared changes require the existing PC control grant and remain pending until the PC receipt and actual snapshot agree; uncertain changes are never automatically resubmitted. The same desktop mesh and material are rasterized on the GPU, with the original CPU renderer as fallback. The physical A21s test measured a median 50 FPS at 420 × 550; this is not a guarantee for other scenes or devices. Character gestures and remote microphone controls live in the same sheet. The app defaults to standard text sizing (100%); PC → Tamaño del texto → Del teléfono follows Android accessibility sizing instead. Both modes were checked on the physical Samsung, including its 299-point viewport with the keyboard open. Remote input surfaces follow the chosen theme.
Microphone controls are collapsible and open automatically during recording.
Work output distinguishes approval, execution, verified postconditions and an
uncertain effect. Polling checks pending operations without resubmitting them.
Browser tests use declared transport fixtures and do not replace Android acceptance.

- Windows 0.20.21 fixes the missing QR renderer in the packaged backend. Pairing
  errors now stay visible across status refreshes; QR display no longer waits for
  history sync. The build verifies actual SVG generation from the packaged EXE.
- Full-screen trackpad and keyboard, larger touch targets and keys, compact settings overlay and input transport reuse.
- Pairing camera permission is requested explicitly, with recovery instructions after denial. The scanner opens in portrait orientation.
- Scanning or opening an `axx://pair` link previews the PC address and requires confirmation. External camera links can open Axx Mobile; availability of custom-link actions depends on the camera app.
- A new QR now keeps the gateway available for its full 120-second validity, even if an earlier device stopped polling. Previously, the old idle timer could close the gateway during the new scan.
- Desktop pairing shows a countdown and a larger high-contrast QR. Pairing links and device management are collapsible. The desktop context menu opens a new QR directly.
- The mobile shell and remote input controls are in Spanish; some native transport and legacy voice errors remain in English. The original mobile prototype is preserved but excluded from the operational APK.

- Windows input monitoring now wakes immediately on messages and only installs global input hooks during a granted lease. A synthetic local hook-delivery probe improved from 48.8 ms median to 0.07 ms; this is not an end-to-end phone latency measurement.

## Pair your phone

1. Open the current Axx desktop build. **Guardar historial** is optional for pairing; enable it in the chat to share that conversation. With sharing off, the phone receives no conversation history and uses Actions with its separate Work grant.
2. Right-click Axx → **Connect phone · QR**, or open Settings → **Connect your phone** → **Show new QR**.
3. In PC Settings choose **Misma red** for LAN, or **Redes distintas · Tailscale** after connecting both devices to the same private Tailscale network. On Android open Axx Mobile → **Pair PC** → **Scan PC QR**.
4. Allow the camera while using the app. Aim it at the PC QR. Check the displayed PC address, then tap **Connect**.
5. Wait for **Your Axx is synchronized**. The character and conversation come from this PC.

If camera access was denied permanently, allow it in Android Settings → Apps → Axx Mobile → Permissions. Alternatively, expand **Use a pairing link instead** on the PC and **Paste a pairing link instead** on the phone.

For expired or already-used codes, generate a new QR on the PC. If the PC cannot be reached, keep Axx open, check the selected LAN/Tailscale route and Windows Firewall private-network access. Do not disable TLS verification. PC identity is pinned to the QR certificate fingerprint.

The gateway is opt-in. Without persistent access it shuts down after phone contact
is lost; a fresh QR reserves two minutes. Enable **Mantener la conexión disponible
al reiniciar Axx** on the PC to reconnect after a desktop restart without scanning.
The saved port and certificate identity persist. A changed LAN address still needs
a fresh QR. Rescanning the same PC now preserves the authenticated phone's device
ID and grants; a revoked credential cannot recover them. Cross-network connectivity uses Tailscale direct/relay networking with the Axx TLS pin intact; it requires Tailscale active on both devices. There is no Axx file mailbox or automatic LAN discovery.

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

The recovery copy includes credentials, databases, custom voices/models and the
previous installation. It omits historical backups, downloaded `node_modules`,
Python bytecode caches and temporary directories inside Axx data. Omitted paths
are recorded in `excluded-directories.json`; a full profile restoration may need
to recreate those dependency caches. Updating the installed app does not remove
the original caches or private voice files.

The debug APK and unsigned Windows installer are local artifacts. Source push does not publish a GitHub release or update the older installer linked in the root README.

## Contracts and evidence

- [Installed companion 0.22.16 / Android 0.2.1 verification](COMPANION-VERIFICATION-20261028-02216.md)
- [Companion 0.22.15 / Android 0.2.0 verification](COMPANION-VERIFICATION-20261028.md)

- [Pairing correction verification](PAIRING-VERIFICATION.md)
- [Windows input delay correction](INPUT-PERFORMANCE.md)
- [Existing input contracts](CONTROL-REMOTO.md)
- [Existing voice contracts](VOZ-REMOTA.md)
- [Integration map](INTEGRACION.md)
- [M01–M34 / V01–V72 traceability](TRAZABILIDAD.md)

The full MO-1–MO-7 acceptance plan is not complete. Physical multi-monitor/DPI, all input gestures and interruption cases, spoken command-to-result, file/media flows, mobile Magic Pen/converter control and administrative flows remain open. iOS and MO-8 Internet access are outside this execution; API 37 acceptance remains pending by platform. No simulated test is described as physical Android acceptance.
