# Review & Adversarial Challenge Report: Milestone 2

**Milestone**: Milestone 2 — Floating Panels & Tentacle Dynamics  
**Reviewer**: Reviewer 1 (`reviewer_m2_1`)  
**Target Files**: `src-tauri/src/resident.rs`, `1.AXX/Axx.html`  
**Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**  
**Date**: 2026-10-21  

---

## 1. Executive Summary

Worker M2 has implemented all six requirements of Milestone 2 (Panel Drag Decoupling, Drag Isolation, Interactive Resizing, Position/Size Persistence, HWND Tentacle Margin Expansion to 72px, and Rust Anchor Stability with `ACTIVE_PANEL_DRAG`).

An exhaustive independent audit, static analysis, unit test run, and adversarial stress testing were conducted. All 22 Rust tests in `src-tauri` pass (100%), all inline JavaScript blocks compile cleanly without syntax errors in Node's V8 VM, the worker's 45-point test suite passes 100%, and Reviewer 1's independent 31-point adversarial test suite passes 100%.

No integrity violations, facade implementations, hardcoded test tricks, or regressions were detected.

---

## 2. Review Dimensions & Verified Claims

### 2.1 Panel Drag Decoupling & 60 FPS Fluidity
- **Claim**: Pointermove applies hardware-accelerated local DOM CSS transforms (`translate3d(dx, dy, 0) !important`) with zero synchronous Win32 IPC layout calls.
- **Verification**: Verified via AST/regex inspection of `ResidentDesktop.bindDrag` in `1.AXX/Axx.html` (lines 18490–18517). In `pointermove`, `pd.el.style.setProperty('transform', ...)` is updated directly; no `desktop_layout` or `desktop_activity` calls occur. On `pointerup`, the transform is reset to `none`, `this.savePanelPositions()` commits coordinates, and `desktop_layout` is invoked exactly once via `this.schedule()`.
- **Status**: **PASS**

### 2.2 Drag Isolation & Text Selection
- **Claim**: Clicking inputs, textareas, buttons, or selecting text inside panel content does not initiate panel dragging.
- **Verification**: Verified in `1.AXX/Axx.html:18396–18404`. `isInteractiveOrContent(target)` checks for `button, input, select, textarea, summary, a, [role=button], [contenteditable], label, .resident-resize-handle, .panel-view, pre, code, .conversation, .response, [data-scrollable]`. If matched, `isPanelHead` returns `null` and drag initiation is aborted. Draggable headers have `user-select: none !important`, while content areas have `user-select: text !important`.
- **Status**: **PASS**

### 2.3 Interactive Resizing & Persistence
- **Claim**: Corner resize handles (`.resident-resize-handle`) support smooth resizing with hard minimum constraints ($\ge$ 320px width, $\ge$ 400px height), and geometry persists to `localStorage['axx.resident.panel-pos']`.
- **Verification**: Verified in `1.AXX/Axx.html:18172–18186` (`ensureResizeHandles`), lines 18461–18489 (`panelResize`), lines 18148–18153 (`loadPanelPositions` / `savePanelPositions`), and lines 18628–18629 (`panelBox`). Hard constraints `Math.max(320, ...)` and `Math.max(400, ...)` are enforced at both gesture time and layout evaluation. `localStorage` reads/writes are wrapped in `try/catch`. "Restablecer distribución" (`#reset-desktop-layout` / `#reset-layout`) clears custom dimensions, strips inline styles, and recalculates default bounds.
- **Status**: **PASS**

### 2.4 Tentacle Margin & Clipping Elimination
- **Claim**: Native HWND margin in `ResidentDesktop.layout()` is expanded from 12px to 72px, enclosing dynamic 104px–170px Bezier tendril tubes.
- **Verification**: Verified in `1.AXX/Axx.html:18608` (`margin = 72`). Bounding box min/max coordinates add 72px padding on all sides (`Math.min(...boxes.map(b => b.x)) - margin`, `Math.max(...) + margin`). Tendril tube anchor `link.b` dynamically tracks `panelEl.getBoundingClientRect()`, keeping tendrils connected to panels during drag.
- **Status**: **PASS**

### 2.5 Rust Anchor Stability (`resident.rs`)
- **Claim**: `ACTIVE_PANEL_DRAG` atomic flag and `LAST_LAYOUT_INSTANT` 300ms layout stabilization window prevent avatar anchor coordinate drift.
- **Verification**: Verified in `src-tauri/src/resident.rs:5–16`, lines 146, 215, 230–234, 274–283, and lines 394–407 (`record_move`). When `is_panel_drag_active()` is true or `instant.elapsed() < 300ms`, `record_move()` immediately returns without updating `g.screen_x` or `g.screen_y`. Unit test `active_panel_drag_state_toggle` passed.
- **Status**: **PASS**

### 2.6 Independent Build & Test Verification
- `cargo check --manifest-path src-tauri/Cargo.toml`: **Finished with 0 errors, 0 warnings** (Finished dev profile).
- `cargo test resident::tests --manifest-path src-tauri/Cargo.toml`: **4 passed, 0 failed**.
- `cargo test --manifest-path src-tauri/Cargo.toml`: **11 passed, 1 ignored (breakaway helper), 0 failed** in `lib.rs`; **6 passed** in `cursor_throttling_test.rs`; **5 passed** in `transparent_clickthrough_challenge_test.rs`. Total: **22 passed, 0 failed**.
- `node .agents/teamwork/worker_m2/validate_html_js.js`: **All inline scripts valid syntax** (Node vm.Script).
- `node .agents/teamwork/worker_m2/verify_m2.js`: **45 / 45 tests passed**.
- `node .agents/teamwork/reviewer_m2_1/independent_test.js`: **31 / 31 tests passed**.

---

## 3. Adversarial Challenges & Edge Case Mining

### Challenge 1: Multi-Monitor Coordinate Translation & Off-Screen Panel Recovery
- **Assumption Challenged**: If a user runs Axx on a 4K display, moves a panel to coordinates $(x: 2500, y: 1400)$, and subsequently launches Axx on a 1080p display, will the panel be permanently lost off-screen?
- **Stress Test**: Simulated 1080p geometry with saved 4K coordinates through `panelBox()` clamping logic:
  ```javascript
  const minXBound = -g.spaceLeft + margin;
  const maxXBound = g.spaceRight - width - margin;
  x = Axx.clamp(x, minXBound, maxXBound);
  const minYBound = -g.spaceAbove + margin;
  const maxYBound = g.spaceBelow - height - margin;
  y = Axx.clamp(y, minYBound, maxYBound);
  ```
- **Result**: **PASS**. The panel is automatically clamped inside the available work area on the active monitor. In addition, the `#reset-desktop-layout` button immediately purges `localStorage` and restores canonical layout.

### Challenge 2: HWND Envelope During Continuous Long-Distance Drag
- **Assumption Challenged**: Does dragging a panel further than 72px from its start position cause canvas clipping during the gesture?
- **Analysis**: During pointermove, the Win32 HWND remains fixed to prevent Win32 message loop feedback and pointer jitter. The 72px margin provides buffer space. If the user drags a panel extremely far in a single gesture, the panel DOM element moves via CSS transform while the HWND bounds remain static until `pointerup`, at which point `desktop_layout` expands the HWND to fully enclose the final position + 72px margin.
- **Verdict**: **Acceptable & Optimal Trade-Off**. Resizing the Win32 HWND synchronously on every pointermove in transparent WebView2 on Windows 11 causes severe OS compositor stutter and pointer displacement.

### Challenge 3: Pointer Cancellation & Focus Loss
- **Assumption Challenged**: If a user drags a panel and the application loses focus (`blur`, `pointercancel`, or `lostpointercapture`), does the UI remain stuck in an active drag state with `ACTIVE_PANEL_DRAG = true`?
- **Stress Test**: Checked cleanup bindings in `ResidentDesktop.bindDrag`:
  ```javascript
  window.addEventListener('blur', clear);
  document.addEventListener('pointercancel', clear, true);
  window.addEventListener('lostpointercapture', clear, true);
  ```
  The `clear()` function releases pointer capture, resets DOM transforms to `'none'`, signals `panelDrag: false` to Rust, saves positions if moved, and schedules a layout commit.
- **Result**: **PASS**. Stuck drag states are completely prevented.

---

## 4. Minor Findings (Informational / Non-Blocking)

### [Minor] Finding 1: Redundant CSS Rule for Resize Handle
- **Location**: `1.AXX/Axx.html:1355` vs `1.AXX/Axx.html:1392`
- **What**: There are two declarations for `.resident-resize-handle`. Line 1355 specifies `cursor: se-resize!important`, while line 1398 specifies `cursor: nwse-resize`.
- **Impact**: None. Both cursors map to the standard bidirectional diagonal resize pointer in Windows WebView2.
- **Recommendation**: Clean up redundant rule in Milestone 7 (Design System Polish).

---

## 5. Verdict

**VERDICT**: **APPROVE**

Milestone 2 implementation is correct, resilient, fully verified, and ready for integration into the master workflow.
