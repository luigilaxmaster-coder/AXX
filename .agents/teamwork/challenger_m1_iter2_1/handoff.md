# Handoff Report — Milestone 1 Iteration 2: Transparent Desktop Click-Through Challenge

**Agent**: Challenger 1 (Transparent Desktop Click-Through Challenger)  
**Timestamp**: 2026-10-21T04:28:00Z  
**Type**: Hard Handoff (Evaluation Complete)  
**Verdict**: **APPROVE**  
**Parent / Recipient**: `4513c1ff-1817-48de-b3d4-90214475e7e6`  

---

## 1. Observation

1. **`LiquidRenderer.hitMask()` Alpha Threshold**:
   - Location: `1.AXX/Axx.html:4279`.
   - Verbatim code:
     ```javascript
     bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0);
     ```
   - Confirmed that `> 96` is completely absent.
   - Parity confirmed with `LiquidRenderer.hitTest` (line 4093) and `SoftwareRenderer.hitTest` / `hitMask` (lines 5258, 5267), which all use `> 16`.

2. **Exclusion of `#stage` and `#avatar` from `interactiveRegions()`**:
   - Location: `1.AXX/Axx.html:18491–18501`.
   - Verbatim code:
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
   - `#stage` and `#avatar` are omitted. Only legitimate actionable controls and surfaces populate `regions`.

3. **Rust Hit-Testing Loop & Cursor Throttling**:
   - Location: `src-tauri/src/lib.rs:809–879`.
   - Verbatim code:
     ```rust
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

4. **Empirical Browser & Renderer Test Results**:
   - Executed: `node scripts/challenger-m1-iter2-harness.cjs`
   - Output:
     ```
     === CHALLENGER HARNESS: MILESTONE 1 ITERATION 2 ===
     Target: Transparent Desktop Click-Through & Hit-Testing Precision

     --- 1. EMPIRICAL TEST: 4 CORNERS OF 530x530 STAGE ---
     [PASS] 1.1 Stage bounding box matches expected dimensions (530x530)
     [PASS] 1.2 Neither #stage nor #avatar rectangle is present in interactiveRegions
     [PASS] 1.3.1 Corner Top-Left (rel: 10, 10): direct hit is false, mask bit is 0, neighborhood is clear, regionHit is false
     [PASS] 1.3.2 Corner Top-Right (rel: 520, 10): direct hit is false, mask bit is 0, neighborhood is clear, regionHit is false
     [PASS] 1.3.3 Corner Bottom-Left (rel: 10, 520): direct hit is false, mask bit is 0, neighborhood is clear, regionHit is false
     [PASS] 1.3.4 Corner Bottom-Right (rel: 520, 520): direct hit is false, mask bit is 0, neighborhood is clear, regionHit is false

     --- 2. EMPIRICAL TEST: RUST ORACLE ON 4 CORNERS (CLICK-THROUGH) ---
     [PASS] 2.1 Corner Top-Left Rust PixelMask.contains evaluates to false
     [PASS] 2.2 Corner Top-Left Rust hit-test evaluates inside=false, ignore=true (CLICK-THROUGH PASSED TO DESKTOP)
     [PASS] 2.1 Corner Top-Right Rust PixelMask.contains evaluates to false
     [PASS] 2.2 Corner Top-Right Rust hit-test evaluates inside=false, ignore=true (CLICK-THROUGH PASSED TO DESKTOP)
     [PASS] 2.1 Corner Bottom-Left Rust PixelMask.contains evaluates to false
     [PASS] 2.2 Corner Bottom-Left Rust hit-test evaluates inside=false, ignore=true (CLICK-THROUGH PASSED TO DESKTOP)
     [PASS] 2.1 Corner Bottom-Right Rust PixelMask.contains evaluates to false
     [PASS] 2.2 Corner Bottom-Right Rust hit-test evaluates inside=false, ignore=true (CLICK-THROUGH PASSED TO DESKTOP)

     --- 3. EMPIRICAL TEST: AVATAR BODY HIT-TESTING (ALPHA > 16) ---
     [PASS] 3.1 Center of avatar body (265, 265 relative) hitTest evaluates to true
     [PASS] 3.2 Center of avatar body: Rust PixelMask.contains evaluates to true
     [PASS] 3.3 Center of avatar body: Rust hit-test evaluates inside=true, ignore=false (CLICKS CAUGHT BY AXX)
     [PASS] 3.4 Inner liquid body samples (radius <= 60px) all register hitTest=true and mask bit=1

     --- 4. EMPIRICAL TEST: ALPHA THRESHOLD RIGOROUS BOUNDARY CHECK (> 16) ---
     [PASS] 4.1 Alpha <= 16 (0, 15, 16) produces hitTest=false and mask bit=0 (transparent / click-through)
     [PASS] 4.2 Alpha = 17 (just above threshold > 16) produces hitTest=true and mask bit=1 (hit caught)
     [PASS] 4.3 Alpha = 96 (previous LiquidRenderer threshold) now produces hitTest=true and mask bit=1
     [PASS] 4.4 Alpha = 255 (solid body) produces hitTest=true and mask bit=1
     [PASS] 4.5 LiquidRenderer.hitMask() in Axx.html uses > 16 and DOES NOT use > 96

     --- 5. EMPIRICAL TEST: DRAG CONTINUITY & THROTTLING ---
     [PASS] 5.1a While mouse button is held down, moving outside body retains ignore=false (drag does not drop)
     [PASS] 5.1b Once mouse button is released outside, ignore reverts to true (restoring click-through)
     [PASS] 5.2 src-tauri/src/lib.rs implements cursor IPC throttling on point.x != last_x || point.y != last_y

     --- 6. EMPIRICAL TEST: VERIFY NO TRANSPARENT DEAD ZONE REMAINS ---
     [PASS] 6.1 10x10 Grid over #stage reveals zero dead zone violations across all transparent samples

     TOTAL TESTS: 27
     PASSED: 27
     FAILED: 0
     ```

5. **Empirical Rust Integration Test Results**:
   - Executed: `cargo test --manifest-path src-tauri/Cargo.toml`
   - Output: 21 tests passed (10 unit tests, 6 cursor throttling integration tests, 5 transparent click-through challenge integration tests), 0 failed, 1 ignored.

---

## 2. Logic Chain

1. From **Observation 2**: By removing `#stage` and `#avatar` from `interactiveRegions()`, `regions` no longer forces `inside = true` over the entire 530×530 rectangular bounding box. The ~220,000 px transparent area outside the circular avatar is no longer blocked by rectangular hit testing.
2. From **Observation 1**: By updating `LiquidRenderer.hitMask()` alpha threshold to `> 16`, any translucent pixels of the avatar's organic rim (alpha between 17 and 255) produce bit `1`, ensuring the avatar boundary in Tauri matches exactly what is rendered visually.
3. From **Observations 1, 2, and 4**: When cursor coordinates fall into any of the 4 transparent corners of the 530×530 stage area ((10, 10), (520, 10), (10, 520), (520, 520)), `regions.iter().any(...)` is `false` and `mask.contains(x, y)` is `false`. Therefore, `inside` evaluates to `false`, and `ignore` evaluates to `true`. Tauri calls `window.set_ignore_cursor_events(true)`, allowing clicks to pass through to desktop applications with zero dead zones.
4. From **Observations 1, 3, and 4**: When cursor coordinates fall on the avatar body (center (265, 265) or radial body points), `mask.contains(x, y)` evaluates to `true`. Therefore, `inside` evaluates to `true`, and `ignore` evaluates to `false`. Tauri calls `window.set_ignore_cursor_events(false)`, ensuring clicks, double clicks, and drags are caught by Axx.
5. From **Observation 3 and 4**: When a user drags the avatar, `lbutton_down` is `true`. Even if the cursor rapidly passes over transparent corners outside the mask, `lbutton_down && !*current` keeps `ignore = false`, preventing the drag from dropping. Once released, `ignore` reverts to `true`.
6. From **Observation 3 and 5**: Cursor coordinates are tracked via `last_x` and `last_y`, preventing 100 Hz event emission over Tauri IPC when the cursor is stationary.
7. From **Observation 5**: All 21 Rust tests and 27 browser/DOM tests execute and pass with 0 failures, providing concrete empirical proof that the solution is robust and correct.

---

## 3. Caveats

1. **Development Mode**: Testing was conducted in dev mode with zero global system installations or registry modifications.
2. **Untouched Axx Connect**: `evidence/axx-connect` and `plugins` were untouched.
3. **Milestone 2 Scope Separation**: Multi-panel rAF drag decoupling, panel resizing handles, and the HWND 72px margin envelope are scheduled for Milestone 2 in the project roadmap.

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone 1 Iteration 2 completely fulfills all requirements:
- The 4 corners of the 530×530 stage pass clicks directly to desktop apps via `set_ignore_cursor_events(true)`.
- The avatar body reliably captures clicks and drags via `set_ignore_cursor_events(false)`.
- The transparent dead zone is completely eliminated.
- The alpha threshold parity across renderers is verified at `> 16`.
- Stationary cursor IPC flooding is throttled.

---

## 5. Verification Method

To independently verify the empirical results:

1. **Run the Milestone 1 Iteration 2 Browser/DOM/WebGL/Oracle Test Suite**:
   ```powershell
   node scripts/challenger-m1-iter2-harness.cjs
   ```
   *Expected outcome*: 27 passed, 0 failed.

2. **Run the Rust Transparent Click-Through Challenge Integration Test**:
   ```powershell
   cargo test --manifest-path src-tauri/Cargo.toml --test transparent_clickthrough_challenge_test
   ```
   *Expected outcome*: 5 passed, 0 failed.

3. **Run the Complete Rust Test Suite**:
   ```powershell
   cargo test --manifest-path src-tauri/Cargo.toml
   ```
   *Expected outcome*: 21 passed, 0 failed, 1 ignored.

4. **Verify Static Code Properties**:
   ```powershell
   node -e "const fs = require('fs'), assert = require('assert'); const html = fs.readFileSync('1.AXX/Axx.html', 'utf8'); assert(html.includes('pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0')); assert(!html.includes('pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 96 ? 1 : 0')); const idx = html.indexOf('interactiveRegions()'); const slice = html.slice(idx, idx + 400); assert(!slice.includes('stage')); assert(!slice.includes('avatar')); const rs = fs.readFileSync('src-tauri/src/lib.rs', 'utf8'); assert(rs.includes('if point.x != last_x || point.y != last_y {')); console.log('PASS: All code invariants statically confirmed');"
   ```
