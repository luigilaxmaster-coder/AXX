# Windows input delay correction

## Reproduced cause

The native input owner installed global low-level mouse and keyboard hooks when the desktop first shared its material, before a remote lease was granted. Its message loop then slept for 50 ms while idle. Windows must deliver low-level hook callbacks before forwarding input, so this polling delay affected the physical PC mouse even without active remote control.

A 20-event Windows probe, using alternating one-pixel movements and a unique injected-event marker, measured delivery from `SendInput` to the corresponding hook callback:

| Metric | Before | After |
| --- | ---: | ---: |
| Median | 48.764 ms | 0.067 ms |
| Maximum | 49.607 ms | 0.776 ms |

This is a controlled synthetic Windows measurement, not physical finger-to-cursor latency, network latency or a general system performance benchmark. The post-fix probe deliberately enabled hooks only for measurement; production no longer installs them while idle.

## Correction

- Install hooks only when a control lease is granted. Remove them on release, expiry, physical intervention, cancellation and shutdown.
- Replace fixed sleeps with `MsgWaitForMultipleObjectsEx`, so Windows input messages wake the owner immediately.
- Wake the owner with `PostThreadMessageW` when commands or shutdown arrive. Drain queued commands without an extra timed wait.
- Preserve physical-input priority, lease validation, held-key/button release, event sequencing, material sharing and the native cursor.

Unit checks cover idempotent installation/removal and cleanup after partial hook installation. The full mobile backend suite has 27 passing tests. Existing backend regression tests are recorded in the delivery report. Live gesture, mixed-DPI and human-perceived smoothness acceptance remain separate checks.

Local measurement samples: `evidence/mobile-20261022/pairing-fix/input-hook-before.json` and `input-hook-after.json`. Updated Windows build evidence is under `evidence/mobile-20261022/input-performance/windows/`.

The updated installer exited with code 0 after a verified 500-file backup. The installed backend matches the built artifact, and the usual installed Axx executable reported `backendReady: true`. See [build hashes](PAIRING-VERIFICATION.md#build-identity). End-to-end physical smoothness remains to be confirmed by the user.
