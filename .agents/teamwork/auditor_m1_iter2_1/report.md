## Forensic Audit Report

**Work Product**: Milestone 1 Iteration 2 (`1.AXX/Axx.html`, `src-tauri/src/lib.rs`)  
**Profile**: General Project (Development Mode per `ORIGINAL_REQUEST.md`)  
**Verdict**: **CLEAN**

---

### Executive Summary

The Forensic Integrity Auditor conducted an independent, empirical verification of all changes delivered in Milestone 1 Iteration 2 by Worker M1-2. The audit covered:
1. **Cheating & Facade Audit**: In-depth inspection of `LiquidRenderer.hitMask()` alpha thresholding (`> 16`), the complete exclusion of `#stage` / `#avatar` bounding boxes from `interactiveRegions()`, and cursor event throttling (`point.x != last_x || point.y != last_y`) in `src-tauri/src/lib.rs`.
2. **Scope Boundaries**: Strict verification that `evidence/axx-connect` and `plugins` remain 100% untouched; verification that the user's Desktop and Documents directories outside the workspace remain completely unmodified; confirmation that zero installers or package bundles were built or executed.
3. **Compilation & Empirical Execution**: Execution of `cargo check` (dev profile only), `cargo test` across all 21 unit/integration/adversarial test suites, JavaScript syntax verification across all 5 `<script>` blocks in `1.AXX/Axx.html`, and full execution of the 27-check challenger harness.

All checks passed with 100% genuine implementations, zero mock bypasses, zero test-detector hacks, zero dead-zone regressions, and strict adherence to all ground-truth constraints specified in `ORIGINAL_REQUEST.md`.

---

### Phase Results

| Check / Domain | Phase | Status | Empirical Details |
|---|---|:---:|---|
| **1. Cheating & Facade Audit** | Source Analysis | **PASS** | `LiquidRenderer.hitMask()` uses real WebGL `gl.readPixels()` buffer readback with dynamic `> 16` alpha cutoff; `#stage` removed from `interactiveRegions()`; no hardcoded constants, mock responses, or test-detector hacks. |
| **2. Click-Through & Hit Testing** | Behavioral | **PASS** | 4 corners of 530×530 stage evaluate to `inside = false, ignore = true` (transparent click-through to Windows desktop). Avatar liquid body evaluates to `inside = true, ignore = false` (Axx captures clicks). |
| **3. Cursor IPC Throttling** | Behavioral | **PASS** | `src-tauri/src/lib.rs:849` checks `point.x != last_x || point.y != last_y` before `window.emit("axx-cursor", ...)`; 0 redundant events emitted while stationary. |
| **4. Drag Continuity** | Behavioral | **PASS** | Win32 `GetAsyncKeyState(VK_LBUTTON)` retains `ignore = false` during drag across transparent areas until release. |
| **5. Scope Boundaries (Axx Connect & Plugins)** | Boundary Audit | **PASS** | `evidence/axx-connect` and `plugins/` (mtime: 2026-10-20T20:44:51Z) remain 100% untouched. |
| **6. Scope Boundaries (Desktop & Documents)** | Boundary Audit | **PASS** | Independent scan of `c:\Users\luigi\Desktop` (outside workspace) and `c:\Users\luigi\Documents` revealed 0 modified files. |
| **7. Installer Prohibition** | Boundary Audit | **PASS** | Zero installer processes running. Zero bundles built during session (existing bundle timestamp: 2026-10-19T20:29:54Z). |
| **8. Portable/Dev Build (`cargo check`)** | Build & Test | **PASS** | `cargo check --manifest-path src-tauri/Cargo.toml` passed in 0.69s (dev profile, 0 errors, 0 warnings). |
| **9. Rust Unit & Integration Tests** | Build & Test | **PASS** | `cargo test --manifest-path src-tauri/Cargo.toml` executed 21 tests (10 unit, 6 cursor throttling, 5 transparent click-through): 21 passed, 0 failed, 1 ignored. |
| **10. Frontend Script Syntax Verification** | Build & Test | **PASS** | Node.js `vm.Script` validated all 5 `<script>` blocks in `1.AXX/Axx.html` (1.79 MB) with 0 errors. |
| **11. Challenger Adversarial Harness** | Adversarial Stress | **PASS** | `node scripts/challenger-m1-iter2-harness.cjs`: 27 passed, 0 failed. |
| **12. Process Hygiene** | System Audit | **PASS** | Exactly 0 orphan Python or background server processes active. |

---

### Detailed Findings & Forensic Evidence

#### 1. Code Authenticity: `LiquidRenderer.hitMask()`
- **Location**: `1.AXX/Axx.html:4273–4282`
- **Observed Code**:
  ```javascript
  const pixels = new Uint8Array(cols * rows * 4);
  gl.readPixels(0, 0, cols, rows, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  const bits = [];
  for (let y = 0; y < rows; y++)
      for (let x = 0; x < cols; x++)
          bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0);
  const r = this.canvas.getBoundingClientRect();
  return { width: r.width, height: r.height, cols, rows, bits };
  ```
- **Forensic Verification**:
  - The function binds offscreen framebuffers and reads actual GPU pixel data.
  - The threshold `> 16` operates on the alpha byte `pixels[... * 4 + 3]`.
  - No constant bit patterns or test environment branches are present.

#### 2. Code Authenticity: `#stage` Exclusion from `interactiveRegions()`
- **Location**: `1.AXX/Axx.html:18491–18500`
- **Observed Code**:
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
- **Forensic Verification**:
  - The square `#stage` bounding box (530×530) has been completely removed.
  - `regions` now contains only actual interactive UI elements.
  - The avatar is hit-tested purely through Tauri's `PixelMask` generated from WebGL alpha readback.

#### 3. Code Authenticity: Cursor Throttling & Click-Through in `src-tauri/src/lib.rs`
- **Location**: `src-tauri/src/lib.rs:809–879`
- **Observed Code**:
  ```rust
  let mut last_x = i32::MIN;
  let mut last_y = i32::MIN;
  ...
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
  let regions_empty = regions.is_empty();
  let mask_present = mask.is_some();
  let inside = regions.iter().any(|r| r.contains(x, y))
      || mask.as_ref().is_some_and(|m| m.contains(x, y));
  drop(mask);
  drop(regions);

  use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
  let lbutton_down = unsafe { GetAsyncKeyState(VK_LBUTTON as i32) } < 0;
  let mut current = state.is_ignoring_cursor.lock().unwrap();
  let ignore = if inside {
      false
  } else if lbutton_down && !*current {
      false
  } else {
      (!regions_empty || mask_present) && !inside
  };

  if *current != ignore && window.set_ignore_cursor_events(ignore).is_ok() {
      *current = ignore;
  }
  ```
- **Forensic Verification**:
  - Emits `axx-cursor` only on physical cursor position changes.
  - Correctly evaluates `inside` using genuine geometry and pixel mask containment.
  - Toggles OS-level cursor transparency (`set_ignore_cursor_events`) seamlessly.

#### 4. Scope & System Cleanliness
- **Protected directories**:
  - `evidence/axx-connect`: Untouched during Iteration 2.
  - `plugins/`: Untouched (mtime: `2026-10-20T20:44:51.625Z`).
  - `c:\Users\luigi\Desktop` (outside workspace): 0 modified files.
  - `c:\Users\luigi\Documents`: 0 modified files.
- **Installer prohibition**:
  - 0 installer processes active.
  - `src-tauri/target/release/bundle` was not modified (mtime: `2026-10-19T20:29:54.175Z`).
- **Process hygiene**:
  - 0 orphan Python / MCP server processes active.

---

### Raw Tool Evidence

#### 1. Dev Compilation (`cargo check`)
```
> cargo check --manifest-path src-tauri/Cargo.toml
Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.69s
(Exit code 0, 0 errors, 0 warnings)
```

#### 2. Test Suite Execution (`cargo test`)
```
> cargo test --manifest-path src-tauri/Cargo.toml
Finished `test` profile [unoptimized + debuginfo] target(s) in 0.76s
Running unittests src\lib.rs (src-tauri\target\debug\deps\app_lib-e909e5ec7589896c.exe)
running 11 tests
test tests::launch_explicit_breakaway_target_helper ... ignored
test resident::tests::expanding_to_left_preserves_global_avatar_anchor ... ok
test resident::tests::negative_dpi_monitor_clamps_content_inside_workarea ... ok
test tests::alpha_mask_preserves_transparent_click_through_holes ... ok
test resident::tests::legacy_rectangle_preferences_are_not_resident_v2 ... ok
test tests::hit_regions_validate_and_use_logical_coordinates ... ok
test tests::local_proxy_rejects_path_escape_and_non_api_routes ... ok
test tests::private_transport_authenticates_and_parses_real_loopback_response ... ok
test tests::private_transport_rejects_http_errors_instead_of_reporting_json_as_success ... ok
test tests::job_cleanup_terminates_owned_suspended_process ... ok
test tests::explicitly_escaped_user_target_survives_owned_job_cleanup ... ok
test result: ok. 10 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.88s

Running tests\cursor_throttling_test.rs
running 6 tests
test test_negative_coordinates_multi_monitor_support ... ok
test test_cursor_movement_emits_whenever_coordinates_change ... ok
test test_scale_factors_and_coordinate_scaling ... ok
test test_interleaved_stationary_and_movement_patterns ... ok
test test_stationary_cursor_emits_zero_events_across_repeated_iterations ... ok
test test_fuzz_property_transition_equivalence ... ok
test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

Running tests\transparent_clickthrough_challenge_test.rs
running 5 tests
test test_regression_dead_zone_eliminated_when_stage_rect_not_in_regions ... ok
test test_530x530_stage_four_corners_evaluate_to_click_through ... ok
test test_liquid_avatar_body_evaluates_to_axx_hit ... ok
test test_drag_continuity_across_transparent_boundaries ... ok
test test_fuzz_coordinate_stability_and_no_panics ... ok
test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

#### 3. Challenger Adversarial Harness (`challenger-m1-iter2-harness.cjs`)
```
=== CHALLENGER HARNESS: MILESTONE 1 ITERATION 2 ===
Target: Transparent Desktop Click-Through & Hit-Testing Precision
TOTAL TESTS: 27
PASSED: 27
FAILED: 0
```

#### 4. Scope Verification
```
Desktop outside workspace modified: []
Documents modified: []
plugins directory mtime: 2026-10-20T20:44:51.625Z (UNTOUCHED)
Installer processes: []
Active Python processes: 0 []
```

---

### Audit Verdict

**CLEAN**

The work product strictly complies with all integrity rules, contains zero mock or facade implementations, respects all scope boundaries, compiles cleanly in dev mode, and successfully passes all functional and adversarial tests.
