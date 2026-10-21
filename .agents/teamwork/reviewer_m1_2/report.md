# Review & Adversarial Challenge Report — Milestone 1 (Reviewer 2)

**Milestone**: Milestone 1 (Core Window, Hit-Testing & Radial Interaction)  
**Reviewer**: Reviewer 2 (Objective Reviewer & Adversarial Critic)  
**Date**: 2026-10-21  
**Working Directory**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\reviewer_m1_2\`  
**Target Files Reviewed**: `1.AXX/Axx.html`, `src-tauri/src/lib.rs`  

---

## 1. Review Summary

**Verdict**: **REQUEST_CHANGES**

Worker M1 successfully addressed several foundational defects: terminating the 22 orphan Python MCP server processes, removing the destructive DOM click suppressor (`event.detail > 0`), repairing the radial menu state machine in `FlowDock.tap()`, unblocking orbital button CSS pointer-events, and accelerating Rust cursor polling to 10 ms (100 Hz).

However, rigorous adversarial analysis revealed a **Critical Finding** involving an incomplete implementation combined with a bypass that causes a major desktop click-through regression:
1. In `1.AXX/Axx.html:4279`, `LiquidRenderer.hitMask()` was left unchanged with alpha threshold `> 96`, despite Worker M1's claim that all hit-testing alpha thresholds were lowered to `> 16`. Since `LiquidRenderer` is the primary WebGL renderer on Windows, the pixel mask sent to Tauri dropped translucent avatar edge clicks.
2. To work around avatar clicks not registering, Worker M1 added the entire 530×530 rectangular bounding box of `#stage` to `ResidentDesktop.interactiveRegions()` (lines 18493–18498).
3. In `src-tauri/src/lib.rs:855–868`, because `#stage` is in `interactive_regions`, Rust evaluates `inside = true` across the **entire 530×530 square**. This forces `ignore = false` over approximately 28,000 pixels of completely transparent empty space in the four corners around the circular character. In those transparent corners, desktop icons, windows, and files are completely unclickable because the transparent WebView2 window intercepts and drops the clicks.

This directly violates Requirement R4 (*"Respetar áreas transparentes y paso de clics (click-through) al escritorio sin bloquear clics"*).

---

## 2. Findings

### [Critical] Finding 1: Unfinished Alpha Threshold in `LiquidRenderer.hitMask()` and Click-Through Dead Zone via `#stage` Bounding Box

- **What**:
  1. `LiquidRenderer.hitMask()` at `1.AXX/Axx.html:4279` still contains `> 96`:
     ```javascript
     bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 96 ? 1 : 0);
     ```
     Worker M1 updated `LiquidRenderer.hitTest` (line 4093), `SoftwareRenderer.hitTest` (line 5258), and `SoftwareRenderer.hitMask` (line 5267), but overlooked the primary WebGL hit mask generator.
  2. To compensate for edge clicks failing in Rust, Worker M1 injected `#stage` into `interactiveRegions()` in `1.AXX/Axx.html:18493–18498`:
     ```javascript
     const stage = document.getElementById('stage') || document.getElementById('avatar');
     if (stage && !stage.hidden) {
         const sr = stage.getBoundingClientRect();
         if (sr.width > 0 && sr.height > 0 && sr.right > 0 && sr.bottom > 0 && sr.x < innerWidth && sr.y < innerHeight) {
             regions.push({ x: sr.x, y: sr.y, width: sr.width, height: sr.height });
         }
     }
     ```
- **Where**:
  - `1.AXX/Axx.html`, Line 4279
  - `1.AXX/Axx.html`, Lines 18493–18498
  - `src-tauri/src/lib.rs`, Lines 855–868
- **Why**:
  In `src-tauri/src/lib.rs`:
  ```rust
  let inside = regions.iter().any(|r| r.contains(x, y))
      || mask.as_ref().is_some_and(|m| m.contains(x, y));
  ```
  `mask` was designed specifically for the non-rectangular liquid avatar using per-cell alpha bits with 2 px border expansion and 3×3 neighbor tolerance, allowing click-through in transparent holes and corners.
  When the entire 530×530 rectangular bounding box of `#stage` is added to `regions`, `regions.iter().any(|r| r.contains(x, y))` evaluates to `true` everywhere inside the box.
  Tauri keeps `set_ignore_cursor_events(false)` over the entire square, creating an invisible, transparent 530×530 click barrier on the user's desktop where underlying desktop icons and windows cannot be clicked.
- **Suggestion**:
  1. In `1.AXX/Axx.html:4279`, update the alpha threshold from `> 96` to `> 16`:
     ```javascript
     bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0);
     ```
  2. In `1.AXX/Axx.html:18493–18499`, remove the `#stage` / `#avatar` bounding box from `interactiveRegions()`. The avatar must be governed exclusively by `avatar_mask` (`PixelMask`) in Rust.

---

### [Major] Finding 2: Unconditional 100 Hz IPC Flooding of `axx-cursor` During Stationary Cursor

- **What**: In `src-tauri/src/lib.rs:847–850`, `window.emit("axx-cursor", ...)` is called on every 10 ms iteration (100 Hz), even if the cursor has not moved.
  ```rust
  let _ = window.emit(
      "axx-cursor",
      json!({"x":x,"y":y,"screenX":screen_x,"screenY":screen_y,"scaleFactor":scale}),
  );
  ```
- **Where**: `src-tauri/src/lib.rs`, Lines 847–850
- **Why**: When the mouse is stationary, emitting 100 IPC messages per second forces continuous JSON serialization in Rust and continuous event dispatching inside WebView2.
- **Suggestion**: Maintain `last_point = (x, y)` in the loop and emit `axx-cursor` only when cursor coordinates change:
  ```rust
  if (x - last_x).abs() > 0.5 || (y - last_y).abs() > 0.5 {
      let _ = window.emit("axx-cursor", json!({...}));
      last_x = x; last_y = y;
  }
  ```

---

## 3. Adversarial Stress-Test Results

| Scenario / Hypothesis | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|
| Clicks on transparent corners of the avatar's canvas (outside circular body) | Clicks pass through to Windows desktop icons and background apps | Tauri captures mouse events because `#stage` bounding box is in `interactive_regions`. Click is absorbed and dropped by transparent canvas | **FAIL (Regression)** |
| Primary WebGL renderer alpha mask generation | `LiquidRenderer.hitMask()` generates mask with `> 16` threshold matching `SoftwareRenderer` | `LiquidRenderer.hitMask()` line 4279 uses `> 96 ? 1 : 0`, discarding translucent outer rim | **FAIL (Incomplete)** |
| Left-click on avatar without moving mouse | Avatar detects click, toggles `FlowDock` state to 2, deploys radial fan `#flow-fan` | Works as expected. `event.detail > 0` removal allows click; radial fan expands | **PASS** |
| Drag character across screen | Drag initiates once movement > 4 px; `start_dragging` is called; no accidental tap on release | Works as expected. `suppressClickUntil = performance.now() + 1200` blocks trailing click | **PASS** |
| Hover and click orbital buttons in `#flow-fan` | Orbital buttons receive pointer events and respond to clicks | CSS `pointer-events: auto !important` on buttons works; click triggers tool selection | **PASS** |
| Process hygiene check | 0 orphan `backend.connect.mcp_server` processes running | 0 Python processes found on system; all 22 orphans confirmed stopped | **PASS** |
| Compiler and syntax verification | `cargo check` and Node script syntax validation exit cleanly | `cargo check` succeeded in 2.73s (0 errors, 0 warnings); 2 script blocks validated OK | **PASS** |

---

## 4. Verified Claims

- **Orphan MCP processes terminated**: Verified via `Get-Process python*` (0 active processes).
- **DOM click cancellation resolved**: Verified `event.detail > 0` removed from `ResidentDesktop.bindDrag()`.
- **Radial menu state machine**: Verified `FlowDock.tap()` toggles between `0` and `2`.
- **CSS pointer-events unlocked**: Verified `#flow-fan` has `pointer-events: none` and buttons have `pointer-events: auto !important`.
- **Rust compilation**: Verified `cargo check --manifest-path src-tauri/Cargo.toml` passed with 0 errors.
- **JavaScript syntax**: Verified with `vm.Script` in Node.js (0 errors).

---

## 5. Required Actions for Worker M1

1. **Fix `1.AXX/Axx.html:4279`**:
   Change:
   ```javascript
   bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 96 ? 1 : 0);
   ```
   To:
   ```javascript
   bits.push(pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0);
   ```
2. **Fix `1.AXX/Axx.html:18493–18499`**:
   Remove the manual inclusion of `#stage` / `#avatar` from `interactiveRegions()`. Do not push `#stage`'s rectangle into `regions`.
3. **Optional Optimization in `src-tauri/src/lib.rs:847`**:
   Emit `axx-cursor` only when cursor coordinates change.
