# Companion verification — Windows 0.22.16 / Android 0.2.1

Date: 2026-10-28. Review: self-review. The dev-team session supplied design
perspectives; it did not independently review the final diff.

## Installed Windows

The final installer completed with exit 0. Installed binaries, 36 license notices,
registry and shortcuts matched the build receipt. The native host reported a
visible surface and its authenticated backend; an unauthenticated query returned
401. The installed voice panel was also observed on the Windows desktop.

Eleven installed integration checks passed:

- QR rendered by the native app decoded to its actual one-use URI using ZXing
  **3.4.1**, the core selected by this Android build.
- The certificate SHA-256 matched the QR identity and the authenticated TLS
  gateway reached the installed backend.
- A desktop material change reached the browser companion, then the original
  material was restored.
- The companion catalog matched the desktop's **69 executable commands** in this
  configured profile. This is inventory, not evidence that all 69 were executed.
- Typed commands in Actions and the main shared chat reached the real executor
  and passed postconditions. The main-chat case used a separate test conversation,
  which was archived after restoring the user's conversation.
- Rescanning preserved the phone identity and Work grant. Revoking that grant on
  the PC reached the open client.
- Active voice text measured **10.38:1** contrast against its native background.

The companion was a browser client connected to real installed PC services through
TLS. Its transport bridge was supplied by the verification harness. This does not
establish Android camera, Keystore, installation or physical phone acceptance.

CarlFM and Ald each completed two real local syntheses and Web Audio playback
cycles, with playing and ended events. These checks used the same frozen backend
hash as the final installer. The original Xxx default selection was restored.
Acoustic output, physical microphone and subjective voice quality remain unverified.

## Automated checks and recovery

- Mobile backend: **56 passed**; browser UI contracts: **8 passed**.
- Piper, delivery and command HTTP integration: **31 passed**.
- Desktop frontend contracts and all 30 embedded script syntax checks passed.
- The dictation suite passed when repeated without concurrent compilation. A run
  under compilation/backup load failed its steady-noise check; no VAD improvement
  or physical noise-rejection guarantee is claimed.
- Release checks: **16 passed**. Recovery-copy regression: **1 passed**.
- Android `assembleDebug testDebugUnitTest lintDebug`: successful. Existing
  dependency lint baselines were retained.
- Frozen sidecar QR/TLS/command/rescan checks passed in disposable data.
- The recovery copy verified **8,420 files**. Historical backups, npm dependencies,
  Python bytecode caches and temporary directories were omitted and recorded.
  Private models, voices, credentials, databases, WebView storage and the previous
  installation were retained. An earlier incomplete full-cache copy has no
  successful manifest and is not the recovery receipt.

## Artifact identity

- Final Windows installer SHA-256:
  `48e28b669852ce5c502cd3bd8d3e8feb3865f515e3387381b054934c9b445aa6`
- Frozen backend SHA-256:
  `f4e34dcf5d9db7107788e6d0e2e71872a1c728d437d9a66e225bcbbac1f3d2bb`
- Android **0.2.1-companion / versionCode 22** APK SHA-256:
  `d2934b7e84c409475b013dfedb671ed79499c435c548cdc624a671c84f32f0e4`

Local final build, installation and integration receipts are in
`build/release-mobile-0.22.16-final/`. Earlier 0.22.15 and first-candidate 0.22.16
receipts do not identify this final installer.

Physical Android acceptance is deferred: no device was attached. iOS, Internet
relay and complete phone Magic Pen/file-converter workflows remain outside this
revision. Published status and the public installer digest are recorded separately
in `release.json` only after GitHub confirmation.
