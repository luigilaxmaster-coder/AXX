# Quality & Adversarial Review Report — Milestone 1 Iteration 2

**Reviewer**: Reviewer 1 (`reviewer_m1_iter2_1`)  
**Roles**: Reviewer & Adversarial Critic  
**Date**: 2026-10-21  
**Target Work Product**: Milestone 1 Iteration 2 (Hit-Testing Precision, Desktop Click-Through & Cursor Throttling)  
**Modified Files**:
- `1.AXX/Axx.html`
- `src-tauri/src/lib.rs`

---

## 1. Executive Review Summary

**Verdict**: **APPROVE**

Worker M1-2 (`worker_m1_2`) has completely and cleanly addressed all defects and concerns raised during Milestone 1 Iteration 1 by `reviewer_m1_2`. The implementation contains no shortcuts, facades, hardcoding, or integrity violations. The code compiles cleanly with zero warnings or errors, passes all unit tests, passes JavaScript parsing across all 5 script blocks, enforces strict process hygiene (0 orphan processes), and restores full organic hit-testing precision while preserving genuine desktop click-through.

---

## 2. Review Findings & Verification of Specific Focus Areas

### 2.1. Focus 1: `LiquidRenderer.hitMask()` Alpha Cutoff (`1.AXX/Axx.html:4279`)
- **Requirement**: Verify threshold is `> 16` (not `> 96`).
- **Observation**:
  `1.AXX/Axx.html`, line 4279:
  ```javascript
  bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0);
  ```
  Verified that `> 96` and `> 100` are absent.
- **Analysis**:
  `LiquidRenderer` is the primary WebGL renderer for Windows. Previously, `LiquidRenderer.hitTest` was using `v[3] > 16`, but `hitMask()` remained at `> 96`. This discrepancy meant the 64×64 bitmask sent to Tauri truncated the translucent iridescent liquid boundary of the avatar, causing near-edge clicks to miss the mask. Setting the threshold to `> 16` brings `hitMask()` into exact parity with `hitTest` and with `SoftwareRenderer.hitMask()` (line 5267: `this.raster.pixels[...] > 16 ? 1 : 0`).
- **Status**: **VERIFIED / PASS**

### 2.2. Focus 2: Exclusion of `#stage` / `#avatar` from `interactiveRegions()` (`1.AXX/Axx.html:18491–18500`)
- **Requirement**: Confirm `#stage` / `#avatar` are NOT present in the list of solid rectangular regions, ensuring Rust relies on `avatar_mask` (`PixelMask`) for organic contour precision.
- **Observation**:
  `1.AXX/Axx.html`, lines 18491–18500:
  ```javascript
  interactiveRegions() {
      const regions = [];
      for (const n of document.querySelectorAll('#panel,#dock-shell,#flow-pill,#flow-fan>button,#flow-all,#reach-tray,#reach-preview,#ink-review,#v13-dock,#v13-settings,#v13-pad,#reader-mini,.organic-satellite,dialog[open],button,input,textarea,select,summary')) {
          if (n.id === 'a11-main-button' || n.hidden || !n.getClientRects().length) continue;
          const style = getComputedStyle(n); if (style.visibility === 'hidden' || style.pointerEvents === 'none' || Number(style.opacity) === 0) continue;
          const r = n.getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.x < innerWidth && r.y < innerHeight) regions.push({ x: r.x, y: r.y, width: r.width, height: r.height });
      }
      return regions;
  }
  ```
- **Analysis**:
  In Milestone 1 Iteration 1, `#stage` (a 530×530 rectangle) was queried and pushed into `regions`. In `src-tauri/src/lib.rs:861`, Tauri computes:
  `inside = regions.iter().any(|r| r.contains(x, y)) || mask.as_ref().is_some_and(|m| m.contains(x, y));`
  When `#stage` was present in `regions`, `inside` was `true` across the entire 530×530 square box, including the four transparent corners outside the circular avatar (~28,000 pixels). This set `ignore_cursor_events(false)` over transparent desktop space, preventing clicks on underlying Windows icons and apps.
  With `#stage` and `#avatar` completely removed from `interactiveRegions()`, `regions` holds strictly rectangular UI controls (panels, dock buttons, modals). The avatar contour is governed solely by `mask` (`PixelMask`), allowing clicks in the transparent corners to evaluate to `inside = false` and set `ignore_cursor_events(true)`.
- **Status**: **VERIFIED / PASS**

### 2.3. Focus 3: Throttling `window.emit("axx-cursor", ...)` (`src-tauri/src/lib.rs:807–856`)
- **Requirement**: Confirm `window.emit("axx-cursor", ...)` is throttled so it only emits when `point.x != last_x || point.y != last_y`.
- **Observation**:
  `src-tauri/src/lib.rs`, lines 809–810 & 849–856:
  ```rust
  let mut last_x = i32::MIN;
  let mut last_y = i32::MIN;
  loop {
      ...
      let x = point.x as f64 / scale;
      let y = point.y as f64 / scale;
      if point.x != last_x || point.y != last_y {
          let _ = window.emit(
              "axx-cursor",
              json!({"x":x,"y":y,"screenX":screen_x,"screenY":screen_y,"scaleFactor":scale}),
          );
          last_x = point.x;
          last_y = point.y;
      }
      let regions = state.interactive_regions.lock().unwrap();
      let mask = state.avatar_mask.lock().unwrap();
      ...
  ```
- **Analysis**:
  Previously, the background thread polled every 10 ms (100 Hz) and unconditionally serialized a JSON payload and dispatched a Tauri webview event even when the cursor had not moved. This generated 100 IPC dispatches per second of redundant traffic to WebView2.
  Tracking `last_x` and `last_y` ensures that `window.emit` is invoked exclusively when the cursor coordinates change. Crucially, the 100 Hz hit testing logic (`inside`, `lbutton_down`, `ignore_cursor_events`) continues to run on every 10 ms tick, ensuring responsive click-through toggling even if UI elements move or close under a resting cursor.
- **Status**: **VERIFIED / PASS**

### 2.4. Focus 4: Independent Compilation, Unit Tests & Static Verification
- **Rust Compilation**: `cargo check --manifest-path src-tauri/Cargo.toml` passed in 1.03s with 0 errors and 0 warnings.
- **Rust Unit Tests**: `cargo test --manifest-path src-tauri/Cargo.toml` executed 11 tests: **10 passed, 0 failed, 1 ignored** (helper test). Specifically, `alpha_mask_preserves_transparent_click_through_holes` and `hit_regions_validate_and_use_logical_coordinates` passed.
- **JavaScript Syntax**: Validated all 5 `<script>` blocks in `1.AXX/Axx.html` via `vm.Script` in Node.js. Zero syntax or evaluation errors.
- **System Hygiene**: Verified via `Get-CimInstance Win32_Process` that zero orphaned `backend.connect.mcp_server` Python processes remain active.
- **Integrity Check**: No hardcoded test outputs, no facade implementations, no shortcuts, no fabricated logs. Real implementations verified directly in source code.
- **Status**: **VERIFIED / PASS**

---

## 3. Adversarial Review & Stress-Testing

### Challenge 1: Startup Hit-Testing Race Condition
- **Assumption Challenged**: If `#stage` is omitted from `interactiveRegions()`, what happens before the first `hit_map` IPC payload arrives from the WebView2 renderer? Does the window ignore all clicks, leaving the app unresponsive on boot?
- **Analysis**:
  In `src-tauri/src/lib.rs:859–875`:
  ```rust
  let regions_empty = regions.is_empty();
  let mask_present = mask.is_some();
  let inside = regions.iter().any(|r| r.contains(x, y))
      || mask.as_ref().is_some_and(|m| m.contains(x, y));
  ...
  let ignore = if inside {
      false
  } else if lbutton_down && !*current {
      false
  } else {
      (!regions_empty || mask_present) && !inside
  };
  ```
  On cold startup before the first `hit_map` is received: `regions_empty` is `true` and `mask_present` is `false`.
  Therefore, `(!regions_empty || mask_present)` evaluates to `false`.
  Consequently, `ignore` evaluates to `false`!
  `set_ignore_cursor_events(false)` is maintained until the frontend actually delivers its interactive layout and mask. Once the initial frame renders and `updateHitMap()` fires, `mask_present` becomes `true`, gracefully activating selective click-through without any startup lockout.
- **Verdict**: **ROBUST / DEFENSE CONFIRMED**

### Challenge 2: Fast Drag Out-of-Bounds Disruption
- **Assumption Challenged**: When dragging the avatar rapidly across the screen, if the mouse cursor outpaces the avatar rendering and moves outside the avatar contour, does `mask.contains(x, y)` become `false` and cause `ignore_cursor_events(true)` to terminate the drag?
- **Analysis**:
  In `src-tauri/src/lib.rs:866–872`:
  ```rust
  let lbutton_down = unsafe { GetAsyncKeyState(VK_LBUTTON as i32) } < 0;
  let mut current = state.is_ignoring_cursor.lock().unwrap();
  let ignore = if inside {
      false
  } else if lbutton_down && !*current {
      false
  } else {
      (!regions_empty || mask_present) && !inside
  };
  ```
  When a drag begins over the avatar, `inside` is `true`, so `ignore` is `false` and `*current` is `false`. If the user moves the mouse rapidly into transparent space while holding the left button down, `inside` becomes `false`. However, `lbutton_down` is `true` and `!*current` is `true`. The branch `else if lbutton_down && !*current` evaluates to `false` (meaning do not ignore cursor events).
  Thus, `ignore` remains `false` throughout the entirety of the drag operation until the mouse button is released (`lbutton_down` becomes `false`).
- **Verdict**: **ROBUST / DEFENSE CONFIRMED**

### Challenge 3: Multi-DPI & Scale Factor Invariance
- **Assumption Challenged**: Does removing `#stage` and relying on `PixelMask` introduce coordinate desynchronization on high-DPI displays (e.g., 125%, 150%, 200% scale)?
- **Analysis**:
  1. In `1.AXX/Axx.html:7247`, `stageRect = this.renderer.canvas.getBoundingClientRect()`. In WebView2, `getBoundingClientRect()` returns coordinates in CSS logical pixels.
  2. In `src-tauri/src/lib.rs:514–530`, `PixelMask.bounds` is initialized directly from `stageRect` (logical pixels).
  3. In `src-tauri/src/lib.rs:847–848`, the Win32 `ScreenToClient` cursor position (physical pixels) is divided by the monitor DPI scale factor:
     `let x = point.x as f64 / scale; let y = point.y as f64 / scale;`
  4. In `PixelMask::contains(&self, x, y)`:
     `let column = (((clamped_x - self.bounds.x) / self.bounds.width * self.cols as f64).floor() as usize).min(self.cols - 1);`
     Both `(clamped_x - self.bounds.x)` and `self.bounds.width` are in logical pixels. The ratio is scale-invariant.
  5. Furthermore, `PixelMask::contains` includes a 2.0 px padding envelope and a 3×3 neighbor kernel tolerance (`saturating_sub(1)..=(row+1)`), which absorbs any sub-pixel floating point rounding jitter between 10 ms cursor polling ticks.
- **Verdict**: **ROBUST / DEFENSE CONFIRMED**

---

## 4. Final Recommendation & Verdict

All criteria for Milestone 1 Iteration 2 have been satisfied:
1. `LiquidRenderer.hitMask()` alpha threshold is verified at `> 16`.
2. `#stage` and `#avatar` are confirmed absent from `interactiveRegions()`, returning desktop click-through to Windows in all transparent areas.
3. Cursor IPC dispatch is verified as throttled to cursor movement.
4. All automated builds and tests pass cleanly.
5. No integrity violations, shortcuts, or facades detected.

**Final Verdict**: **APPROVE**
