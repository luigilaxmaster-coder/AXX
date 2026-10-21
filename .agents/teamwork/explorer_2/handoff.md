# Handoff Report — Explorer 2 (Frontend Architecture, UI Panels, State Management & Tools UI Specialist)

- **Agent ID**: Explorer 2 (Conversation ID: `7793b67a-24cd-4664-a4a0-cad1dbde39b0`)
- **Recipient / Parent**: Orchestrator (ID: `4513c1ff-1817-48de-b3d4-90214475e7e6`)
- **Task**: Phase 0 Technical Investigation for Requirement R1 (Frontend Architecture, UI Panels, Root Cause of "Nothing Works on Click", Drag/Resize, Design System Comparison, R1 Inventory).
- **Status**: Completed (Hard Handoff)
- **Primary Deliverable**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_2\report.md`

---

## 1. Observation

Direct code observations from static analysis and execution of inspection scripts:

1. **Frontend Architecture & Bundler**:
   - `src-tauri/tauri.conf.json:34`: `"frontendDist": "../1.AXX"`. The frontend is served directly as an unbundled monolithic HTML file without Vite, Webpack, or framework compilation.
   - `1.AXX/Axx.html`: File size is 1.48 MB (18,520 lines). It defines 61 ES6 classes, 180 bindings on `window.Axx`, 789 distinct DOM element IDs, and 21 sub-views under the master container `#panel` (lines 1425–1498).
   - Scripts syntax validation: Running node syntax checks on `1.AXX/Axx.html` inline JS and external scripts (`native-voice.js`, `command-library.js`, `axx-connect.js`) returned zero syntax errors (clean parsing).

2. **Hit-Testing Mismatch & Click-Through in Native Host**:
   - `src-tauri/src/lib.rs:800–858`: A native Windows background thread polls cursor position every 30ms via `GetCursorPos` and `ScreenToClient`. When the cursor is outside `interactive_regions` or `avatar_mask`, it invokes:
     ```rust
     window.set_ignore_cursor_events(true);
     ```
   - `1.AXX/Axx.html:6543, 7228–7262`: `updateHitMap()` recomputes and dispatches `interactive_regions` through Tauri IPC with a throttle of **220ms**.

3. **Pointer Event Interception and Cancellation**:
   - `1.AXX/Axx.html:18305–18378` (`ResidentDesktop.bindDrag()`): Captures global pointer events on `document` with `capture = true`.
   - `1.AXX/Axx.html:18378`:
     ```javascript
     if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) {
         event.preventDefault();
         event.stopImmediatePropagation();
     }
     ```
     Because all mouse clicks have `event.detail >= 1`, clicks hitting the body or stage container are immediately canceled in the capture phase before reaching target child listeners.

4. **Avatar Tap Overwrite Chain & Hidden State Step**:
   - Five subsystems overwrite `companion.onAvatarTap` sequentially: `FlowExperience.js` (line 12079), `ActionDesk.js` (line 12862), `OrbitExperience.js` (line 13660), `HomeDock18.js` (line 16434), and `ResidentDesktop.js` (line 18118).
   - In `ResidentDesktop.tap()` (`Axx.html:18120`):
     ```javascript
     this.tap = function() {
         if (Axx.flow) {
             Axx.flow.nav.step = (Axx.flow.nav.step === 0 ? 1 : 0);
             Axx.flow.sync();
         }
     }
     ```
     `step = 1` only renders the hidden status pill `#flow-pill`, while `#flow-fan` (the radial tool menu) requires `step = 2`. Clicking the avatar toggles only between 0 and 1, never reaching 2.

5. **CSS Pointer-Events Disabling**:
   - `1.AXX/Axx.html:1346`:
     ```css
     body.native.axx-resident #flow-quick,
     body.native.axx-resident #flow-fan {
         pointer-events: none !important;
     }
     ```

6. **Panel Dragging, Resizing & Window Margin**:
   - `1.AXX/Axx.html:18331–18350`: Every `pointermove` calls `this.schedule()`, issuing a synchronous Win32 `SetWindowPos` call via Tauri IPC `desktop_layout` on every pixel move.
   - `1.AXX/Axx.html:18418`: Panel dimensions are hardcoded constants (`const panelBox = { width: 420, height: 560 };`). No resize handles or CSS resize rules exist.
   - `1.AXX/Axx.html:18097`: `ResidentDesktop.savePanelPositions()` persists only `{ screenX, screenY, relX, relY }` to `localStorage['axx.resident.panel-pos']`, omitting width and height.
   - `1.AXX/Axx.html:18449`: Window bounding box is calculated with `margin = 12`. WebGL tentacle Bezier curves extend up to 60px outside the avatar radius, causing the native Windows HWND border to clip the tentacles.

7. **Reference v20 Parity**:
   - `reference/Axx_reference_v20.html` and `1.AXX/Axx.html` share the exact 24 shapes (`Shapes`) and 9 palettes (`Palettes`). The core visual divergence stems from the injected `.native.axx-resident` CSS rules and floating window adaptations.

---

## 2. Logic Chain

1. **Premise 1 (Native Click-Through)**: The Tauri background thread sets Windows click-through (`set_ignore_cursor_events(true)`) whenever the cursor is outside cached interactive rectangles.
2. **Premise 2 (Hit-Map Latency)**: The frontend updates those rectangles only every 220ms. When a user moves their mouse to click an avatar button or newly opened panel, the click occurs within the 220ms window while Tauri still considers the cursor "outside", passing the click through to the desktop.
3. **Premise 3 (Event Cancellation)**: Even if hit-testing registers, the capture-phase listener on `document` checks `event.detail > 0` and invokes `stopImmediatePropagation()`, killing the click event before any child button can execute.
4. **Premise 4 (State Loop)**: Even when `onAvatarTap` fires, `ResidentDesktop.tap()` merely toggles `Axx.flow.nav.step` between 0 (idle) and 1 (invisible pill). The radial menu requires `step = 2`. Thus, the radial tools menu is never shown.
5. **Premise 5 (Native Win32 Saturation)**: Firing `desktop_layout` on every `pointermove` floods the Windows message loop with synchronous `SetWindowPos` requests, causing intense mouse lag and cursor disconnection during panel dragging.
6. **Premise 6 (OS-Level Clipping)**: A 12px margin around the avatar is smaller than the WebGL tentacle amplitude (~60px). Because clipping occurs at the OS HWND boundary, no CSS style can prevent the tentacles from being sliced.

**Deduction**: The perceived unresponsiveness ("nothing works on click") is not a single bug or missing JS file, but the compound result of Tauri v2 click-through race conditions, capture-phase event suppression, a flawed 3-step state machine toggling between 0 and 1, and CSS pointer-events blocking.

---

## 3. Caveats

- **Runtime Execution**: In accordance with the strictly read-only Phase 0 constraint, no Tauri application binaries or dev servers were launched (`cargo tauri dev` was not run). All findings are backed by static code analysis and Node.js script inspections.
- **External API Availability**: Actual LLM chat responses depend on the availability of a local Ollama service or remote API keys. The investigation isolated the UI handling and failure-state behavior, not the model quality.
- **Audio Hardware**: Web Audio and Speech Recognition behavior in WebView2 may vary depending on local Windows audio device configurations and microphone permissions.

---

## 4. Conclusion

1. The frontend structure is fully in place, containing rich implementations for all 21 views, 24 shapes, and 9 color palettes.
2. The core unresponsiveness issues are localized, fully understood, and have clear, direct fixes:
   - Synchronize Tauri hit-testing with immediate updates on panel open/close and add a 150ms hysteresis buffer.
   - Remove aggressive `stopImmediatePropagation()` from `ResidentDesktop.bindDrag()`.
   - Fix `ResidentDesktop.tap()` to toggle directly between `step = 0` and `step = 2`.
   - Throttle drag IPC calls to 60 FPS via `requestAnimationFrame`.
   - Increase native window margin in `ResidentDesktop.layout()` from `12px` to `72px` to prevent tentacle clipping.
   - Implement real resize handles and persist dimensions in `localStorage`.
3. The comprehensive R1 inventory for all 13 required areas has been fully documented with the 5 required fields in `report.md`.

---

## 5. Verification Method

To independently verify the observations and conclusions:

1. **Verify Hit-Testing and Capture Listener**:
   - Inspect `src-tauri/src/lib.rs` lines 800–858 to confirm the 30ms polling loop and `set_ignore_cursor_events`.
   - Inspect `1.AXX/Axx.html` line 18378 to confirm `event.stopImmediatePropagation()` when `event.detail > 0`.
2. **Verify Avatar Tap State Bug**:
   - Inspect `1.AXX/Axx.html` lines 18118–18130 to confirm `this.tap` toggles between 0 and 1, and lines 12050–12150 to confirm `#flow-fan` requires `step === 2`.
3. **Verify Window Margin**:
   - Inspect `1.AXX/Axx.html` line 18449 to confirm `const margin = 12;`.
4. **Verify R1 Inventory**:
   - Read the complete technical report at:
     `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_2\report.md`.

### Invalidation Conditions
- If running `updateHitMap(true)` immediately prior to click events does not restore click reception in Tauri, native Windows hit-testing flags (`WS_EX_TRANSPARENT`) in `src-tauri/src/lib.rs` would need further adjustment.
