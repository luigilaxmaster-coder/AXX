# Milestone 2 Independent Review & Adversarial Challenge Report

**Reviewer**: Reviewer 2 (Adversarial Critic)  
**Milestone**: Milestone 2 — Floating Panels & Tentacle Dynamics  
**Target Files**: `src-tauri/src/resident.rs`, `1.AXX/Axx.html`  
**Worker Under Review**: Worker M2 (`worker_m2`)  
**Date**: 2026-10-21  

---

## 1. Review Summary

**Verdict**: **APPROVE**  
**Overall Risk Assessment**: **LOW**  
**Integrity Audit**: **PASS** (Zero integrity violations, no facade/mock implementations, no hardcoded test shortcuts, genuine native and frontend implementation).

Worker M2 has delivered a robust, high-performance solution for Milestone 2 that successfully eliminates Win32 drag jitter, suppresses anchor coordinate drift, isolates text selection from dragging, enables interactive panel resizing with hard minimum constraints ($\ge$ 320x400), expands the HWND tentacle margin to 72px to prevent Bezier curve clipping, and implements reliable layout recovery and boundary clamping.

---

## 2. Adversarial Integrity Check

| Integrity Check Item | Result | Evidence / Notes |
| :--- | :---: | :--- |
| **Hardcoded Test Results** | **NONE** | No mocked test values or artificial test shortcuts embedded in source code. |
| **Dummy / Facade Logic** | **NONE** | Real DOM event delegation, CSS transforms, Win32 atomic flags, and layout calculations. |
| **Bypassed Requirements** | **NONE** | All 6 scope items in Milestone 2 fully addressed and verified. |
| **Fabricated Logs / Attestation** | **NONE** | Independent compilation (`cargo check`), cargo unit tests, and Node script validations confirmed 100% genuine. |
| **Self-Certifying Code** | **NONE** | Fully reproducible independently via standard tooling (`cargo`, `node`). |

---

## 3. Findings & Observations

### [Minor] Finding 1: Defensive Object Validation in `loadPanelPositions()`
- **Where**: `1.AXX/Axx.html:18149`
- **What**: `loadPanelPositions()` does `JSON.parse(localStorage.getItem('axx.resident.panel-pos') || '{}')` without verifying that the parsed result is a non-null object.
- **Why**: While `savePanelPositions()` writes a valid object, external corruption or malformed localStorage entries (e.g. `"null"` or `"123"`) would result in `this.panelPositions` being `null`, causing `this.panelPositions[id]` to throw a TypeError.
- **Suggestion**: Ensure defensive validation: `const p = JSON.parse(...); return (p && typeof p === 'object' && !Array.isArray(p)) ? p : {};`.

### [Minor] Finding 2: Multi-Touch Pointer Overwrite Edge Case
- **Where**: `1.AXX/Axx.html:18409-18459`
- **What**: `pointerdown` on a panel header does not check if `this.panelDrag` or `this.panelResize` is already active before assigning the new gesture.
- **Why**: In multi-touch environments, pressing two panel headers concurrently causes the second pointer to overwrite `this.panelDrag`.
- **Mitigation / Risk**: In standard desktop usage with mouse input, concurrent primary pointer clicks are physically impossible. Pointer cleanup (`clear()`) handles blur and cancellation safely.

### [Good Practice] Positive Observation: Event Delegation & Zero-Leak Architecture
- **Where**: `1.AXX/Axx.html:18172-18186` (`ensureResizeHandles`) and `18394-18592` (`bindDrag`)
- **What**: Resize handles are appended without individual per-element event listeners; all drag, resize, and cancel events are handled via global delegation on `document` and `window`.
- **Impact**: Zero memory leaks or listener accumulation regardless of how many times panels or satellites are created, closed, or recreated.

### [Good Practice] Positive Observation: Hit-Test Map Registration for Resize Grips
- **Where**: `1.AXX/Axx.html:18703` (`interactiveRegions`)
- **What**: `.resident-resize-handle` is explicitly included in the Tauri interactive regions query selector.
- **Impact**: Ensures WebView2 and Win32 `set_ignore_cursor_events` permit cursor interaction over the 18px resize handle on transparent borders.

---

## 4. Adversarial Stress-Test Results

| Scenario / Attack Vector | Predicted / Expected Behavior | Actual Behavior Observed | Result |
| :--- | :--- | :--- | :---: |
| **1. 50 Rapid Pointer Move Events during Drag** | Zero synchronous IPC calls to Win32 `SetWindowPos`; pure GPU CSS transform. | Decoupled local `translate3d` transforms; zero IPC until `pointerup`. | **PASS** |
| **2. Pointer Leaves Window / OS Frame Blur** | Pointer capture holds; if capture lost or window blurs, gesture terminates cleanly without stuck state. | `lostpointercapture` and `window.blur` trigger `clear()`, resetting transform and signaling `panelDrag: false`. | **PASS** |
| **3. Shrink Panel Below Minimum Constraints** | Attempts to resize panel to 100x100 clamped to 320x400. | `Math.max(320, ...)` and `Math.max(400, ...)` strictly enforce bounds. | **PASS** |
| **4. Off-Screen Panel Boundary Recovery** | Panels placed beyond monitor bounds (e.g. multi-monitor disconnect) retrieved to visible area. | `panelBox()` clamps coordinates within visible workspace; `resetLayout()` restores defaults. | **PASS** |
| **5. Windows WM_MOVE Echo within 300ms** | Native window movement echoing from `SetWindowPos` does NOT displace avatar anchor. | `LAST_LAYOUT_INSTANT` drops any move events within 300ms of layout commit. | **PASS** |
| **6. Tentacle Arching Excursion** | Arched Bezier tendril tubes (104px–170px) enclosed by transparent window canvas. | HWND margin expanded to 72px on all sides, enclosing tendril crests without frame truncation. | **PASS** |

---

## 5. Verified Claims

1. **Rust Backend Check**:
   - Command: `cargo check --manifest-path src-tauri/Cargo.toml`
   - Verified: Finished `dev` profile with 0 errors and 0 warnings (1.58s). **PASS**.
2. **Rust Resident & Unit Tests**:
   - Command: `cargo test --manifest-path src-tauri/Cargo.toml`
   - Verified: 11 unit tests and 11 integration tests (total 22 tests) passed with 0 failures. **PASS**.
3. **Inline Script Syntax Validation**:
   - Command: `node .agents/teamwork/worker_m2/validate_html_js.js`
   - Verified: All script blocks syntax-valid in Node `vm.Script`. **PASS**.
4. **Milestone 2 Automated Verification Suite**:
   - Command: `node .agents/teamwork/worker_m2/verify_m2.js`
   - Verified: 45 / 45 tests passed covering backend flags, frontend CSS/DOM, ResidentDesktop logic, and simulation. **PASS**.
5. **Decoupled Drag & IPC Throttling**:
   - Verified: `pointermove` calls `style.setProperty('transform', ...)` and does NOT call `desktop_layout`. Single commit occurs on `pointerup`. **PASS**.
6. **Layout Recovery UI & Action**:
   - Verified: `#reset-desktop-layout` and `#reset-layout` exist, invoke `resetLayout()`, clear localStorage, remove inline styles, and toast user. **PASS**.

---

## 6. Coverage Gaps & Unverified Items

- **High-DPI Multi-Monitor Physical Switching**: Simulated and code-inspected. Physical switching across heterogeneous displays (e.g. 200% DPI laptop to 100% DPI monitor) depends on Tauri's Win32 monitor detection loop (`status.desktop`). Risk is LOW as fallback clamping is active.
- **Axx Connect / Plugins**: Out of scope for Milestone 2 as specified in `ORIGINAL_REQUEST.md` (no files in `evidence/axx-connect` were touched).

---

## 7. Conclusion

Milestone 2 implementation satisfies all functional, architectural, and quality criteria defined in `ORIGINAL_REQUEST.md` and `PROJECT.md`. The implementation exhibits high code hygiene, defensive event cleanup, and verified stability. Verdict: **APPROVE**.
