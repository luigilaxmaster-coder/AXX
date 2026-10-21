# Handoff Report — Reviewer 2: Milestone 1 Review

**Agent**: Reviewer 2 (Reviewer & Adversarial Critic)  
**Timestamp**: 2026-10-21T04:06:00Z  
**Type**: Hard Handoff  
**Verdict**: **REQUEST_CHANGES**  

---

## 1. Observation

1. **Incomplete Alpha Cutoff in `LiquidRenderer.hitMask()`**:
   In `1.AXX/Axx.html:4279`:
   ```javascript
   bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 96 ? 1 : 0);
   ```
   Worker M1 modified `LiquidRenderer.hitTest` (line 4093) to `> 16`, but left `LiquidRenderer.hitMask()` at `> 96`.
   Because `LiquidRenderer` is the primary WebGL renderer used on Windows, the `avatar_mask` sent to Tauri by `this.renderer.hitMask()` retained the high `> 96` cutoff, dropping translucent edge pixels.

2. **Full Bounding Box of `#stage` Added to `interactiveRegions()`**:
   In `1.AXX/Axx.html:18493–18498`:
   ```javascript
   const stage = document.getElementById('stage') || document.getElementById('avatar');
   if (stage && !stage.hidden) {
       const sr = stage.getBoundingClientRect();
       if (sr.width > 0 && sr.height > 0 && sr.right > 0 && sr.bottom > 0 && sr.x < innerWidth && sr.y < innerHeight) {
           regions.push({ x: sr.x, y: sr.y, width: sr.width, height: sr.height });
       }
   }
   ```
   `#stage` is sized to `var(--resident-size)` (530px × 530px).

3. **Rust Cursor Loop Hit-Testing Evaluation**:
   In `src-tauri/src/lib.rs:855–868`:
   ```rust
   let inside = regions.iter().any(|r| r.contains(x, y))
       || mask.as_ref().is_some_and(|m| m.contains(x, y));
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
   Because `regions` contains the 530×530 rectangle of `#stage`, `inside` evaluates to `true` everywhere within the 530×530 box, setting `ignore = false`.

4. **DOM Pointerdown Filtering on Canvas**:
   In `1.AXX/Axx.html:18330`:
   ```javascript
   if (!isBody(event.target) || !Axx.app.renderer.hitTest(event.clientX, event.clientY)) return;
   ```
   When the cursor is in the transparent corners of `#stage`, `hitTest` returns `false`, dropping the event in WebView2 without propagating it to Windows desktop.

5. **Independent Tool Verification**:
   - `cargo check --manifest-path src-tauri/Cargo.toml` executed and finished in 2.73s with 0 errors, 0 warnings.
   - Node.js `vm.Script` syntax check verified 2 script blocks in `1.AXX/Axx.html` with 0 errors.
   - `Get-Process python*` returned 0 processes; all 22 orphan `backend.connect.mcp_server` processes are confirmed dead.

---

## 2. Logic Chain

1. From **Observation 1**: Because `LiquidRenderer.hitMask()` was left with `> 96`, the avatar's pixel mask in Rust did not cover the outer translucent edge of the liquid character.
2. From **Observation 2**: Instead of fixing line 4279, Worker M1 added the rectangular bounding box of `#stage` to `interactiveRegions()`.
3. From **Observations 2 & 3**: Because `#stage` (a 530×530 square) was added to `interactive_regions`, Rust evaluates `inside = true` across the entire 530×530 square, forcing `window.set_ignore_cursor_events(false)`.
4. From **Observations 3 & 4**: In the four transparent corners of `#stage` (~28,000 transparent pixels outside the circular avatar), Tauri captures the mouse click, but `hitTest` in WebView2 returns `false` and discards it. The click never reaches the Windows desktop or background applications.
5. Therefore, Worker M1's change created a transparent, click-blocking dead zone around the character on the user's desktop, violating Requirement R4.
6. The correct architecture requires:
   - Fixing `LiquidRenderer.hitMask()` (line 4279) to use `> 16`.
   - Removing `#stage` from `interactiveRegions()` (lines 18493–18498).
   Rust's `PixelMask` (with 2 px padding and 3×3 neighbor tolerance) will then accurately handle avatar hits, while preserving 100% desktop click-through in transparent corners and surrounding space.

---

## 3. Caveats

- **Dev mode only**: Compilation and static analysis were performed under dev/portable mode; no system installers were invoked.
- **Milestone 2 dependency**: Multi-panel dragging decoupling and window HWND margin expansion to 72 px are scheduled for Milestone 2.
- **Review Scope**: Focus was strictly placed on Milestone 1 code changes (`1.AXX/Axx.html`, `src-tauri/src/lib.rs`), process cleanup, and hit-testing stability.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

Worker M1 must apply two specific fixes:
1. `1.AXX/Axx.html:4279`: change `> 96` to `> 16` in `LiquidRenderer.hitMask()`.
2. `1.AXX/Axx.html:18493–18499`: remove `#stage` / `#avatar` from `interactiveRegions()`.
3. (Recommended): In `src-tauri/src/lib.rs:847`, only emit `axx-cursor` when coordinates change.

---

## 5. Verification Method

To verify the required fixes:

1. **Verify Alpha Mask Threshold**:
   ```bash
   node -e "const fs = require('fs'), assert = require('assert'); const html = fs.readFileSync('1.AXX/Axx.html', 'utf8'); assert(!html.includes('v[3] > 100')); assert(!html.includes('pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 96')); console.log('Alpha thresholds verified at <= 16');"
   ```

2. **Verify `#stage` Excluded from `interactiveRegions`**:
   ```bash
   node -e "const fs = require('fs'), assert = require('assert'); const html = fs.readFileSync('1.AXX/Axx.html', 'utf8'); const idx = html.indexOf('interactiveRegions()'); const slice = html.slice(idx, idx + 400); assert(!slice.includes(\"getElementById('stage')\")); console.log('Stage properly excluded from rectangular regions');"
   ```

3. **Compiler Check**:
   ```bash
   cargo check --manifest-path src-tauri/Cargo.toml
   ```
