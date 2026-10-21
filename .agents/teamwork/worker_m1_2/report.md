# Implementation Report — Milestone 1 Iteration 2: Hit-Testing Precision & Click-Through Restoration

**Integrator**: Worker M1-2 (Hit-Testing Precision Integrator)  
**Date**: 2026-10-21  
**Working Directory**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m1_2\`  
**Target Files Modified**:
- `1.AXX/Axx.html`
- `src-tauri/src/lib.rs`

---

## 1. Executive Summary

In Milestone 1 Iteration 1, Reviewer 2 identified an incomplete alpha mask generator implementation in `LiquidRenderer.hitMask()` alongside a workaround where Worker M1 had added the entire rectangular bounding box of `#stage` (530×530 px) to `interactiveRegions()`. In `src-tauri/src/lib.rs:855`, this forced Tauri to capture mouse clicks across all ~28,000 transparent corner pixels outside the circular avatar, creating a desktop click-blocking dead zone in violation of Requirement R4. Additionally, stationary cursors were triggering redundant 100 Hz `axx-cursor` IPC emissions.

Worker M1-2 has systematically resolved all three issues:
1. Updated `LiquidRenderer.hitMask()` alpha threshold from `> 96` to `> 16`, ensuring the WebGL hit mask faithfully captures the organic translucent outer rim of the avatar.
2. Removed `#stage` / `#avatar` from `interactiveRegions()`, returning the avatar's hit detection strictly to Tauri's `PixelMask` (with 2 px padding and 3×3 neighbor tolerance) and immediately restoring genuine desktop click-through across all transparent corners and surrounding workspace.
3. Throttled `axx-cursor` IPC dispatch in `src-tauri/src/lib.rs` by checking `point.x != last_x || point.y != last_y`, eliminating redundant 100 Hz event serialization and WebView2 dispatch when the cursor is stationary.
4. Cleaned up lingering orphan `backend.connect.mcp_server` Python background processes, confirming 0 remaining.

---

## 2. Detailed Modifications

### 2.1. Lowering `LiquidRenderer.hitMask()` Alpha Cutoff to `> 16`
- **File**: `1.AXX/Axx.html`, Line 4279
- **Diff / Code Change**:
  ```diff
              const bits = [];
              for (let y = 0; y < rows; y++)
                  for (let x = 0; x < cols; x++)
  -                    bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 96 ? 1 : 0);
  +                    bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0);
              const r = this.canvas.getBoundingClientRect();
  ```
- **Rationale**: `LiquidRenderer` is the primary WebGL renderer for Windows. Worker M1 had previously lowered `LiquidRenderer.hitTest` and `SoftwareRenderer` thresholds to `> 16` but left `LiquidRenderer.hitMask()` at `> 96`. Aligning `hitMask` to `> 16` ensures the `PixelMask` sent to Tauri encompasses the translucent liquid boundary.

### 2.2. Removing `#stage` / `#avatar` from `interactiveRegions()`
- **File**: `1.AXX/Axx.html`, Lines 18491–18507
- **Diff / Code Change**:
  ```diff
          interactiveRegions() {
              const regions = [];
  -            const stage = document.getElementById('stage') || document.getElementById('avatar');
  -            if (stage && !stage.hidden) {
  -                const sr = stage.getBoundingClientRect();
  -                if (sr.width > 0 && sr.height > 0 && sr.right > 0 && sr.bottom > 0 && sr.x < innerWidth && sr.y < innerHeight) {
  -                    regions.push({ x: sr.x, y: sr.y, width: sr.width, height: sr.height });
  -                }
  -            }
              for (const n of document.querySelectorAll('#panel,#dock-shell,#flow-pill,#flow-fan>button,#flow-all,#reach-tray,#reach-preview,#ink-review,#v13-dock,#v13-settings,#v13-pad,#reader-mini,.organic-satellite,dialog[open],button,input,textarea,select,summary')) {
  ```
- **Rationale**: In `lib.rs:855`, `inside = regions.iter().any(|r| r.contains(x, y)) || mask.as_ref().is_some_and(|m| m.contains(x, y))`. When `#stage` (a 530×530 rectangle) was present in `regions`, `inside` was permanently true throughout the entire square, disabling `ignore_cursor_events` and preventing clicks from reaching background apps in the four corners around the circular avatar. Removing `#stage` ensures `regions` only contains actual UI controls (buttons, panels, dialogs), leaving the avatar's circular shape governed by `mask` (the `PixelMask`), which passes through clicks on transparent pixels.

### 2.3. Throttling Stationary Cursor IPC (`axx-cursor`)
- **File**: `src-tauri/src/lib.rs`, Lines 803–855
- **Diff / Code Change**:
  ```diff
  #[cfg(windows)]
  fn start_cursor_hit_test_loop(app: AppHandle) {
      std::thread::spawn(move || {
          use windows_sys::Win32::{
              Foundation::POINT, Graphics::Gdi::ScreenToClient, UI::WindowsAndMessaging::GetCursorPos,
          };
          let mut last_display_check = Instant::now();
  +        let mut last_x = i32::MIN;
  +        let mut last_y = i32::MIN;
          loop {
  ...
              let x = point.x as f64 / scale;
              let y = point.y as f64 / scale;
  -            let _ = window.emit(
  -                "axx-cursor",
  -                json!({"x":x,"y":y,"screenX":screen_x,"screenY":screen_y,"scaleFactor":scale}),
  -            );
  +            if point.x != last_x || point.y != last_y {
  +                let _ = window.emit(
  +                    "axx-cursor",
  +                    json!({"x":x,"y":y,"screenX":screen_x,"screenY":screen_y,"scaleFactor":scale}),
  +                );
  +                last_x = point.x;
  +                last_y = point.y;
  +            }
              let regions = state.interactive_regions.lock().unwrap();
  ```
- **Rationale**: Polling at 10 ms (100 Hz) unconditionally emitted `axx-cursor` even when the mouse was idle, causing 100 JSON serializations and WebView2 events per second. Tracking `last_x` and `last_y` ensures `window.emit` only fires when the cursor moves, while hit testing against `regions` and `mask` continues smoothly on every tick.

### 2.4. Cleanup of Residual Background Python Processes
- Terminated 20 lingering `backend.connect.mcp_server` processes using `Process.kill`.
- Verified via `Get-CimInstance Win32_Process` that exactly 0 orphaned Python processes remain active on the system.

---

## 3. Verification & Test Results

| Check / Test | Command | Result | Notes |
|---|---|---|---|
| Rust compilation | `cargo check --manifest-path src-tauri/Cargo.toml` | **PASS** (0 errors, 0 warnings, 4.50s) | Clean dev profile build |
| Rust unit tests | `cargo test --manifest-path src-tauri/Cargo.toml` | **PASS** (10 passed, 0 failed, 1 ignored) | All hit region, alpha mask, and process tests passed |
| HTML / JS syntax check | `new vm.Script(...)` in Node.js on all `<script>` tags in `1.AXX/Axx.html` | **PASS** (5 blocks verified, 0 errors) | No JS syntax regressions |
| Alpha mask verification | Node assertion script checking `pixels[...] > 16` and absence of `> 96` / `> 100` | **PASS** | `LiquidRenderer.hitMask()` matches `hitTest` |
| Stage exclusion verification | Node assertion script verifying `#stage` and `#avatar` are absent from `interactiveRegions()` | **PASS** | Rectangular bounding box completely removed |
| Cursor throttling check | Node assertion verifying `last_x`, `last_y`, and `point.x != last_x \|\| point.y != last_y` in `lib.rs` | **PASS** | Verified in source AST/text |
| Process hygiene | Node WMI process verification | **PASS** | 0 active Python processes |

---

## 4. Reversion Guide
To revert these changes:
1. In `1.AXX/Axx.html:4279`: change `pixels[...] > 16` back to `pixels[...] > 96`.
2. In `1.AXX/Axx.html:18491`: re-insert `#stage` bounding box into `interactiveRegions()`.
3. In `src-tauri/src/lib.rs:807` and `847`: remove `last_x` / `last_y` and restore unconditional `window.emit`.
