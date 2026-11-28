# AXX Project Singularity — Phase II Performance Baseline & Budget Report

## Measured Runtime Benchmarks

### 1. Native Windows 11 Overlay (`Axx.exe` + WebView2, Isolated Candidate `com.axx.singularity-candidate`)
- **Monitor & Scale:** `\\.\DISPLAY1`, logical work area `1536 × 816`, physical `1920 × 1020`, Windows DPI `120` (`1.25x` scale factor).
- **Working Set Memory (`WorkingSet64`):** `48.50–48.96 MB` measured across expanded Intent mode on live `Axx.exe` (`pid: 10548` / `pid: 2612`).
- **Settled CPU 3D Renderer Suspend (`DOCKED`):** `Axx.app.renderer.hidden === true` (`rendererSuspendedByNotch: true`), `tendrilVisible: false`.
- **Coordinator Frame Budget (Live WebView2):**
  - `avgLayoutMs`: `0.015 ms` (`budget < 2.0 ms`)
  - `avgRenderMs`: `0.144 ms` (`budget < 15.0 ms`)
  - `droppedAcks`: `0` (verified live; stale epoch=0 test explicitly rejected by Rust `hit_map` returning `{ accepted: false, epoch: 1, revision: 7 }`).

### 2. Automated Chromium / Playwright & Pure Reducer Stress (`test-notch-phase2.cjs`)
- **50 Live DOM + Motion + Coordinator Dock/Undock Cycles:** `22 ms` total (`avgLayoutMs: 0.002 ms`, `avgRenderMs: 0.018 ms`, `droppedAcks: 0`).
- **500 State Machine Transition Cycles (`DOCK_COMMAND -> RETRACT_COMPLETE -> NATIVE_GEOMETRY_ACK -> UNDOCK_REQUEST -> UNDOCK_COMPLETE`):** `0.9 ms` total, zero epoch leakage (`dockEpoch === 1000`), `0 KB` JS heap delta (`heapDeltaKb: 0`).
- **Renderer Suspend While Docked + Resume on Undock:** `Axx.app.renderer.hidden === true` upon entering `docked`; `Axx.app.renderer.hidden === false` immediately upon transitioning to `free`.
- **3D Renderer Opt-in Default Overhead:** With `axx.notch.v1` `enabled: false` (default), `notch-coordinator.js` stays inactive and free-mode 3D animation/tendrils run unchanged.

## Observed Environment Scope Note
- Continuous GPU frame-time profiling across unlocked interactive desktop multi-monitor drags requires an interactive unlocked Windows desktop session (not measurable inside a background agent WinSta0 session).
