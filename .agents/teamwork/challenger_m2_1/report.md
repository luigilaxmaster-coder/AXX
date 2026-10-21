# Empirical Challenge Report: Milestone 2 — Panel Dynamics & Tentacle Integrator

**Challenger**: Challenger 1 (Adversarial Empirical Reviewer)  
**Target Code**: `1.AXX/Axx.html` (lines 18131–18711), `src-tauri/src/resident.rs`  
**Worker Handoff Evaluated**: `.agents/teamwork/worker_m2/handoff.md`  
**Date**: 2026-10-21  
**Verdict**: **APPROVE**  

---

## 1. Challenge Summary

**Overall risk assessment**: **LOW**

Worker M2 claimed to have solved the drag jitter, anchor drift, interactive input isolation, minimum resize constraints ($\ge 320\times 400$), Win32 tentacle HWND clipping margin (72px), and layout recovery. Rather than trusting the worker's simulation mock, Challenger 1 built an empirical test harness (`tests/m2_empirical_challenge.js`) that directly extracts and executes the real, uncompiled JavaScript AST of `ResidentDesktop` from `1.AXX/Axx.html` in a V8 runtime environment, coupled with native compilation and unit tests of `src-tauri/src/resident.rs`.

Across 26 empirical challenge tests spanning 6 adversarial dimensions (input non-interference, extreme resize clamping, off-screen recovery, multi-panel isolation, Rust synchronization flags, and corruption/interruption handling), **all 26 assertions passed without regressions or failure modes**.

---

## 2. Adversarial Challenges & Findings

### Challenge 1 (Low Risk): Panel Drag vs Input & Text Selection Conflict
- **Assumption Challenged**: User clicking interactive controls or selecting text inside panels must NEVER trigger accidental dragging.
- **Attack Scenario**:
  - Pointerdown dispatched directly on `<input id="chat-input">` inside `#panel`.
  - Pointerdown dispatched on `<textarea id="chat-textarea">`.
  - Pointerdown on `<button class="wide-button">` and header `<button id="flow-detail-close">`.
  - Pointerdown on text/content containers (`.conversation`, `<pre>`, `<code>`, `.panel-view`).
- **Blast Radius**: If drag starts or `preventDefault()` is called on input controls, typing focus is lost, buttons fail to click, and text selection is completely broken.
- **Empirical Result**:
  - In `1.AXX/Axx.html:18396-18404`, `isInteractiveOrContent(target)` checks `button, input, select, textarea, summary, a, [role=button], [contenteditable="true"], label, .resident-resize-handle, [data-resize-handle], .panel-view, pre, code, .conversation, .response, [data-scrollable]`.
  - If target matches any of these, `isPanelHead` immediately returns `null`.
  - **Empirical result**: `panelDrag` remained strictly `null`, `panelResize` remained `null`, and `preventDefault()` was NOT called on any of the interactive controls. Native selection and click events propagate unhindered. **PASS**.

### Challenge 2 (Low Risk): Extreme Boundary Resizing Clamping
- **Assumption Challenged**: Panel dimensions cannot be corrupted into zero/negative size or expanded beyond the desktop workspace.
- **Attack Scenario**:
  - Dragging resize handle with extreme negative coordinates ($\Delta x = -300\text{px}$, $\Delta y = -400\text{px}$, and $\Delta x = -9999\text{px}$).
  - Dragging resize handle with extreme positive coordinates ($\Delta x = +5000\text{px}$, $\Delta y = +5000\text{px}$).
- **Blast Radius**: Window could collapse into an unclickable 0-pixel artifact or stretch outside the desktop screen, causing graphic buffer exhaustion or unrecoverable layout.
- **Empirical Result**:
  - In `1.AXX/Axx.html:18472-18473`:
    `const newW = Math.max(320, Math.min(pr.initialWidth + dx, maxW));`
    `const newH = Math.max(400, Math.min(pr.initialHeight + dy, maxH));`
  - When shrinking by $-9999\text{px}$, dimensions were strictly clamped to $320\text{px}$ width and $400\text{px}$ height.
  - When expanding by $+5000\text{px}$, dimensions were strictly clamped to $(workWidth - 40)\text{px} = 1880\text{px}$ and $(workHeight - 40)\text{px} = 1040\text{px}$.
  - On pointer release, custom dimensions were correctly written to `localStorage['axx.resident.panel-pos']`. **PASS**.

### Challenge 3 (Low Risk): Layout Recovery & Off-Screen Clamping
- **Assumption Challenged**: If custom positions are saved off-screen or monitor resolution changes, panels are recovered within the visible work area.
- **Attack Scenario**:
  - Injected off-screen coordinates: $x = -99999, y = -99999$ and $x = +99999, y = +99999$.
  - Ran `resident.layout()`.
  - Triggered `resident.resetLayout()` via `#reset-desktop-layout` button.
- **Blast Radius**: Floating panel could become permanently lost off-screen with no way for the user to reach it.
- **Empirical Result**:
  - `panelBox()` enforces boundary clamping:
    `minXBound = -g.spaceLeft + margin; maxXBound = g.spaceRight - width - margin;`
    `x = Axx.clamp(x, minXBound, maxXBound);`
    `minYBound = -g.spaceAbove + margin; maxYBound = g.spaceBelow - height - margin;`
    `y = Axx.clamp(y, minYBound, maxYBound);`
  - In a $1920\times 1080$ workspace with margin $72\text{px}$, the $-99999\text{px}$ overflow was clamped to $-828\text{px}$ (left bound) and $-428\text{px}$ (top bound).
  - Executing `resetLayout()` flushed `localStorage['axx.resident.panel-pos']`, stripped inline transforms/dimensions, and restored default centering. **PASS**.

### Challenge 4 (Low Risk): Win32 Drag Decoupling & Anchor Stabilization
- **Assumption Challenged**: Panel drag must not trigger Win32 IPC calls on each mouse move, and native backend must suppress avatar anchor drift during panel repositioning.
- **Attack Scenario**:
  - Dispatched 100 consecutive `pointermove` events during active panel drag.
  - Monitored IPC bridge invocations to `desktop_layout` and `desktop_activity`.
  - Verified Rust atomic checks in `resident.rs:record_move`.
- **Blast Radius**: Window jitter and anchor coordinate drift causing violent window shaking on Windows WebView2.
- **Empirical Result**:
  - 100 `pointermove` events triggered **0** IPC calls during movement. Movement was completely handled locally via CSS `transform: translate3d(dx, dy, 0) !important`.
  - Only on `pointerup` was `transform` reset to `none` and `desktop_layout` scheduled once.
  - In `src-tauri/src/resident.rs:396-407`, `record_move()` explicitly checks `is_panel_drag_active()` and a 300ms `LAST_LAYOUT_INSTANT` stabilization window, preventing false avatar repositioning. **PASS**.

### Challenge 5 (Low Risk): Non-Primary Clicks & Unexpected Event Interruption
- **Assumption Challenged**: Right-clicks, middle-clicks, window blur, or cancelled touches must not leave sticky drag state or orphaned CSS transforms.
- **Attack Scenario**:
  - Dispatched `pointerdown` with `button: 2` (right-click) and `button: 1` (middle-click).
  - Triggered `pointercancel` mid-drag after moving $60\text{px}$.
  - Dispatched conflicting events with mismatched `pointerId: 99`.
  - Poisoned `localStorage` with `NaN`, strings, and thrown errors.
- **Empirical Result**:
  - Non-primary clicks were ignored (`if (event.button !== 0) return;`).
  - `pointercancel` cleared `panelDrag` and reset `transform` to `'none'`.
  - Conflicting pointer IDs were ignored (`if (pd && event.pointerId === pd.id)`).
  - Poisoned localStorage fell back to safe defaults without runtime exceptions. **PASS**.

---

## 3. Stress Test Results Summary

| # | Test Case | Target Component | Expected Behavior | Observed Result | Status |
|---|---|---|---|---|---|
| 1 | Input click isolation | `#chat-input` | `panelDrag === null`, no `preventDefault` | `null`, unhindered focus | **PASS** |
| 2 | Textarea click isolation | `#chat-textarea` | `panelDrag === null`, no `preventDefault` | `null`, unhindered focus | **PASS** |
| 3 | View button isolation | `#chat-send` | `panelDrag === null`, no `preventDefault` | `null`, normal click | **PASS** |
| 4 | Header close button isolation | `#flow-detail-close` | `panelDrag === null`, no `preventDefault` | `null`, normal click | **PASS** |
| 5 | Text selection isolation | `.conversation`, `<code>` | `panelDrag === null`, no `preventDefault` | `null`, text selectable | **PASS** |
| 6 | Header drag initiation | `.panel-head` | `panelDrag` active, `panelDrag: true` IPC | `panelDrag` set, IPC sent | **PASS** |
| 7 | Decoupled drag gesture | `pointermove` x100 | CSS transform updated, 0 IPC calls | Local transform only, 0 IPC | **PASS** |
| 8 | Resize handle installation | `.resident-resize-handle`| Created in `#panel` with `se` grip | Handle installed with grip | **PASS** |
| 9 | Min size constraint (-300px) | `panelResize` | Clamped to $\ge 320\times 400\text{px}$ | Clamped to $320\times 400\text{px}$ | **PASS** |
| 10 | Extreme shrinking (-9999px) | `panelResize` | Clamped to $\ge 320\times 400\text{px}$ | Clamped to $320\times 400\text{px}$ | **PASS** |
| 11 | Screen bounds constraint | `panelResize` | Clamped to $\le workArea - 40\text{px}$ | Clamped to $1880\times 1040\text{px}$ | **PASS** |
| 12 | Resize localStorage sync | `localStorage` | Persisted on pointerup | Saved accurately on release | **PASS** |
| 13 | Negative off-screen recovery | `layout()` | Clamped $\ge -spaceLeft + margin$ | Clamped to $-828\text{px}$ | **PASS** |
| 14 | Positive off-screen recovery | `layout()` | Clamped $\le spaceRight - w - margin$| Clamped to $528\text{px}$ | **PASS** |
| 15 | resetLayout() execution | `ResidentDesktop` | Flushes storage, removes styles | Clean memory & storage reset | **PASS** |
| 16 | Reset button click binding | `#reset-desktop-layout` | Triggers `resetLayout()` | Function invoked | **PASS** |
| 17 | Multi-panel drag isolation | `panel` vs `flow-sheet` | Panel A moved, Panel B unchanged | Panel B position intact | **PASS** |
| 18 | Multi-panel resize isolation | `panel` vs `flow-sheet` | Panel A resized, Panel B unchanged | Panel B dimensions intact | **PASS** |
| 19 | Rust anchor drift check | `resident.rs` | `record_move` checks drag flag | Flag checked in Rust | **PASS** |
| 20 | Rust IPC layout parameter | `desktop_layout` | Accepts & sets `panel_drag` | Flag handled in Rust | **PASS** |
| 21 | Tentacle margin expansion | `layout()` | Margin = 72px for Bezier curves | Exactly 72px | **PASS** |
| 22 | Right/Middle click rejection | `button !== 0` | Drag/resize ignored | Strict rejection | **PASS** |
| 23 | Abrupt cancellation recovery | `pointercancel` | Transform reset to `'none'` | Transform reset cleanly | **PASS** |
| 24 | Conflicting pointerId reject | `pointerId !== pr.id` | Stream ignored | Strict rejection | **PASS** |
| 25 | Poisoned localStorage values | Corrupted types | Safe fallback without crashing | Handled safely | **PASS** |
| 26 | Throwing localStorage | Security/Quota error | Operations survive exceptions | No unhandled throws | **PASS** |

---

## 4. Unchallenged Areas

- **Native Multi-Monitor Dynamic DPI Hot-Plug**: Dynamic DPI transition across physical monitors with mismatched scale factors (e.g., dragging avatar between 100% and 200% scaling monitors) requires live physical hardware and Windows WM_DPICHANGED events. The algorithmic geometry logic was verified, but live multi-monitor hot-plugging remains an OS-level physical verification item.

---

## 5. Verdict

**APPROVE**  
All Milestone 2 requirements have been rigorously and empirically verified. The solution provides robust drag decoupling, strict constraint enforcement, input non-interference, and clean recovery mechanisms.
