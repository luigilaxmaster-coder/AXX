# Review and Adversarial Critique Report — Milestone 1

**Reviewer**: Reviewer 1 (Archetype: reviewer_critic)  
**Date**: 2026-10-21  
**Milestone**: Milestone 1 (Core Window, Hit-Testing & Radial Interaction)  
**Target Codebase**: `1.AXX/Axx.html`, `src-tauri/src/lib.rs`  
**Integrator Reviewed**: Worker M1 (`worker_m1`)  

---

## 1. Review Summary

**Verdict**: **APPROVE**

Worker M1 has completely resolved the core window hit-testing, avatar interaction, DOM click suppression, alpha cutoff, CSS pointer-events blocking, radial menu state machine, and Rust cursor polling defects identified in the R1 audit inventory (`INVENTORY_R1.md`). All implementations are genuine, robust, and free of shortcuts or integrity violations. Independent builds, unit tests, and AST syntax checks passed with zero errors and zero warnings.

---

## 2. Integrity Audit (Anti-Cheating & Facade Verification)

As mandated by reviewer protocol, the codebase was thoroughly audited for adversarial integrity violations:
- **Hardcoded test results or expected outputs embedded in source code**: None found. All logic evaluates runtime state, DOM metrics, and Win32 cursor positions dynamically.
- **Dummy or facade implementations**: None found. The implementations in `Axx.html` and `lib.rs` contain real, production-ready logic with full mathematical derivations and complete state transitions.
- **Shortcuts bypassing the intended task**: None found. The integrator did not use external tool shortcuts or copy code from irrelevant sources.
- **Fabricated verification outputs or logs**: All claims in Worker M1's report were re-executed independently. Every single claim, build duration, and assertion verified 100% accurately against live code.
- **Self-certifying work without genuine independent verification**: Verified independently with clean compilation (`cargo check`), 10 passing unit tests (`cargo test`), Node JS script parsing (`vm.Script`), and a custom 7-point assertion suite.

---

## 3. Detailed Scope Verification

### Scope Item 1: Review Changes in `1.AXX/Axx.html` and `src-tauri/src/lib.rs`
- **Observations**:
  - `1.AXX/Axx.html`: Changes in CSS rules (lines 1345–1349), `FlowDock.tap` (line 2713), `LiquidRenderer.hitTest` (line 4093), `SoftwareRenderer.hitTest` & `hitMask` (lines 5258, 5267), `FlowExperience.tap` (lines 12261–12264), `ResidentDesktop.tap` (line 18294), `ResidentDesktop.bindDrag` (lines 18358, 18379, 18383), `ResidentDesktop.layout` (lines 18465–18475), and `ResidentDesktop.interactiveRegions` (lines 18493–18499).
  - `src-tauri/src/lib.rs`: Changes in `PixelMask::contains` (lines 55–81) with 2 px tolerance padding, and `start_cursor_hit_test_loop` (lines 803–876) with 10 ms interval, `current_monitor().scale_factor()` query, and explicit `ignore = false` when `inside`.
- **Status**: **PASS**

### Scope Item 2: Removal of `event.detail > 0` Click Suppression & Drag Threshold (> 4px)
- **Observations**:
  - Previously in `Axx.html:18378`: Any mouse click generated `event.detail >= 1` in compliance with W3C UI Events specifications, which caused `event.preventDefault()` and `event.stopImmediatePropagation()` to unconditionally suppress 100% of avatar clicks.
  - Verification: `event.detail > 0` has been completely eliminated from the entire codebase.
  - Movement threshold: In `pointermove` (`Axx.html:18358`), movement within 4 px (`Math.hypot(dx, dy) <= 4`) returns without setting `drag.moved = true`. In `pointerup` (`Axx.html:18379`), `wasDrag` is evaluated as `drag.moved || (distance > 4)`. If `!wasDrag`, `this.tap()` is cleanly invoked. If `wasDrag` is true, `this.suppressClickUntil = performance.now() + 800` suppresses synthetic click events resulting from dragging.
- **Status**: **PASS**

### Scope Item 3: `FlowDock.tap()` & `ResidentDesktop.tap()` Transition to Step 2 (Radial Fan `#flow-fan`)
- **Observations**:
  - Previously, `FlowDock.tap()` toggled `step` between `0` and `1` (collapsed pill).
  - Verification: In `Axx.html:2713`, `FlowDock.tap()` now executes `this.step = this.step ? 0 : 2; this.tool = '';`.
  - When `step === 2`, `FlowExperience.render()` renders `renderQuick()` creating orbital buttons in `#flow-fan`, and shifts focus to the first tool button (`fx('flow-fan')?.querySelector('button')?.focus(...)`).
  - In `ResidentDesktop.tap()` (`Axx.html:18294`), `isOpen = (Axx.flow.nav.step !== 0)` synchronizes `this.invoked` and toggles the `resident-invoked` class on `document.body`. A second tap cleanly toggles back to `step = 0`, closing the radial fan.
- **Status**: **PASS**

### Scope Item 4: CSS `pointer-events: none !important` Removed from `#flow-fan` & Orbital Buttons Interactivity
- **Observations**:
  - Previously, CSS rule `body.native.axx-resident #flow-fan { pointer-events: none !important; }` prevented all cursor events from reaching radial tools.
  - Verification: In `Axx.html:1347`, `#flow-fan` has `pointer-events: none` (without `!important`).
  - In `Axx.html:1348-1349`: `#flow-fan>button`, `#flow-fan [data-quick]`, `#flow-all`, and child SVGs/spans explicitly have `pointer-events: auto !important`.
  - In `ResidentDesktop.layout()` (`Axx.html:18471-18474`): Each orbital button dynamically receives `pointer-events: auto !important`.
- **Status**: **PASS**

### Scope Item 5: `#stage` / `#avatar` in `interactiveRegions()` & Backdrop Non-Swallowing
- **Observations**:
  - In `ResidentDesktop.interactiveRegions()` (`Axx.html:18493–18499`), the bounding rectangle of `#stage` (or `#avatar`) is retrieved via `getBoundingClientRect()` and validated against viewport bounds before being appended to `regions`.
  - In `ResidentDesktop.layout()` (`Axx.html:18468`), `#flow-sheet` has `pointer-events: none !important` when `step === 2`, preventing the full-screen transparent backdrop from intercepting or swallowing clicks meant for the avatar or underlying desktop windows.
- **Status**: **PASS**

### Scope Item 6: Rust `lib.rs` Hit-Testing Loop (10ms Sleep, DPI Calculation)
- **Observations**:
  - In `src-tauri/src/lib.rs:810`, the polling interval is set to `Duration::from_millis(10)` (100 Hz), matching high-frequency pointer responsiveness.
  - In `src-tauri/src/lib.rs:837–844`, DPI scale calculation queries `window.current_monitor().ok().flatten().map(|m| m.scale_factor())` with fallback to `window.scale_factor()` and ultimate fallback to `1.0`.
  - In `src-tauri/src/lib.rs:863–869`:
    ```rust
    let ignore = if inside {
        false
    } else if lbutton_down && !*current {
        false
    } else {
        (!regions_empty || mask_present) && !inside
    };
    ```
    If `inside` is true, `ignore` is guaranteed to be `false`.
    If the left button is held down while already interacting (`lbutton_down && !*current`), `ignore` remains `false`, preventing premature click-through during fast drags.
  - In `src-tauri/src/lib.rs:56-61`, `PixelMask::contains` includes a 2.0 px boundary pad (`padded.contains(x, y)`), eliminating boundary misses during rapid cursor transit.
- **Status**: **PASS**

### Scope Item 7: Independent Build & Test Execution
- **`cargo check --manifest-path src-tauri/Cargo.toml`**: Finished in 1.31s with **0 errors and 0 warnings**.
- **`cargo test --manifest-path src-tauri/Cargo.toml`**: 10 tests passed, 0 failed, 1 ignored helper.
- **JavaScript AST syntax check**: Both script blocks in `1.AXX/Axx.html` parsed via `vm.Script` with **0 syntax errors**.
- **Orphan Process Check**: `Get-Process -Name python*` returned 0 active processes. All 22 orphan Python MCP servers were successfully eliminated.
- **Status**: **PASS**

---

## 4. Adversarial Critique & Stress-Testing

### Challenge 1: Multi-Monitor Coordinate & Scale Mismatch
- **Stress Scenario**: Axx is dragged across a monitor boundary where Primary Monitor has scale factor 1.25 and Secondary Monitor has scale factor 1.50.
- **Investigation**: In `lib.rs:837`, `window.current_monitor()` dynamically queries the monitor bounding the current HWND position at 100 Hz. If `ScreenToClient` converts the cursor to client pixels, dividing by `current_monitor().scale_factor()` correctly maps to logical CSS pixels matching WebGL render targets.
- **Result**: PASS.

### Challenge 2: Rapid Click-and-Drag Jitter (Tremor Tolerance)
- **Stress Scenario**: A user clicks the avatar but slight physical hand tremor moves the mouse by 2 pixels between `pointerdown` and `pointerup`.
- **Investigation**: With the 4 px threshold (`Math.hypot <= 4`), movement under 4 px does not set `drag.moved = true`, and `wasDrag` evaluates to `false`. `this.tap()` is triggered normally without false drag cancellation.
- **Result**: PASS.

### Challenge 3: Loss of Pointer Capture during Drag
- **Stress Scenario**: The user initiates a drag on the avatar or a panel, and an OS popup, ALT+TAB, or window blur occurs.
- **Investigation**: Handlers for `window.addEventListener('blur', clear)` and `document.addEventListener('pointercancel', clear, true)` immediately release pointer capture, reset `this.drag = null`, and call `Axx.app.renderer.releaseDrag()`.
- **Result**: PASS.

### Challenge 4: Outside Click Pass-Through vs Radial Dismissal
- **Stress Scenario**: Radial menu `#flow-fan` is open. The user clicks on a blank area of the screen outside the orbital buttons and outside the avatar.
- **Investigation**: Because `#flow-sheet` has `pointer-events: none !important`, the click passes through to the underlying Windows desktop. To close the radial menu, the user taps the avatar again, which immediately toggles `step` from 2 to 0. (Note: Milestone 2 / 7 will consider whether an optional dismiss zone is desired, but desktop pass-through strictly complies with the transparent window requirement).
- **Result**: PASS.

---

## 5. Coverage Gaps & Forward Look to Milestone 2

- **Panel Drag Decoupling**: Currently panel drag updates `this.panelPositions` and calls `this.schedule()`. Milestone 2 is planned to decouple panel dragging to 60 FPS `requestAnimationFrame` with local CSS transforms and throttle Win32 `desktop_layout` calls.
- **HWND Margin Expansion**: The margin in `ResidentDesktop.layout()` is currently 12 px; Milestone 2 is scheduled to increase this to 72 px to accommodate the full 104–170 px arc of the organic Bezier tentacles without native clipping.
- Neither of these items are part of Milestone 1 scope; they are clearly partitioned for Milestone 2.

---

## 6. Verdict

**Verdict**: **APPROVE**  
Milestone 1 is verified, correct, robust, and ready for integration. Orchestrator may proceed to Milestone 2.
