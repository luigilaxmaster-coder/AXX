# Handoff Report — Phase 0: Requirement R1 Investigation
**Agent**: Explorer 1 (Hit-Testing, Window Event Flow & Character Interaction Specialist)  
**Recipient**: Orchestrator (`4513c1ff-1817-48de-b3d4-90214475e7e6`)  
**Date**: 2026-10-21  
**Working Directory**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_1\`  
**Handoff Type**: Hard (Task Complete)

---

## 1. Observation
Direct, verified findings with exact file paths and line numbers:

1. **Destructive Click Suppression in DOM Listener**:
   - File: `1.AXX\Axx.html:18378`
   - Verbatim code:
     ```javascript
     document.addEventListener('click', event => { if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
     ```
   - In standard browser DOM events, regular mouse clicks always produce `event.detail === 1`. Because `event.detail > 0` is unconditionally true for all user clicks, all standard click events on `#avatar` are prevented and stopped before reaching any handler.

2. **Strict Alpha Cutoff Dropping Boundary Clicks**:
   - File: `1.AXX\Axx.html:5256`
   - Verbatim code:
     ```javascript
     hitTest(x, y) {
         if (!this.ctx)
             return false;
         const r = this.canvas.getBoundingClientRect(), px = Math.floor((x - r.left) / r.width * this.raster.width), py = Math.floor((y - r.top) / r.height * this.raster.height);
         return px >= 0 && py >= 0 && px < this.raster.width && py < this.raster.height && this.raster.pixels[(py * this.raster.width + px) * 4 + 3] > 96;
     }
     ```
   - If a click lands on the translucent organic rim of the liquid body (alpha <= 96), `hitTest` returns `false`. In `1.AXX\Axx.html:18326`:
     ```javascript
     if (!isBody(event.target) || !Axx.app.renderer.hitTest(event.clientX, event.clientY)) return;
     ```
     `pointerdown` aborts early without setting `this.drag`. On `pointerup` (line 18372), `if (!drag || event.pointerId !== drag.id) return;` exits without calling `this.tap()`.

3. **Hit-Testing Latency and Polling Drop in Win32 Event Loop**:
   - File: `src-tauri\src\lib.rs:802, 848-856`
   - Verbatim code:
     ```rust
     std::thread::sleep(Duration::from_millis(30));
     ...
     let lbutton_down = unsafe { GetAsyncKeyState(VK_LBUTTON as i32) } < 0;
     let mut current = state.is_ignoring_cursor.lock().unwrap();
     let ignore = if lbutton_down && !*current {
         false
     } else {
         (!regions_empty || mask_present) && !inside
     };

     if *current != ignore && window.set_ignore_cursor_events(ignore).is_ok() {
         *current = ignore;
     }
     ```
   - While the cursor is moving across transparent desktop space, `*current == true` (`set_ignore_cursor_events(true)`). When the user moves the cursor onto Axx and clicks rapidly within 0-30 ms, `*current` is still `true`. Thus `lbutton_down && !*current` evaluates to `false`. Windows passes the click through to the desktop/underlying window.
   - In addition, frontend `updateHitMap()` (`1.AXX\Axx.html:6543, 7228-7262`) only pushes interactive regions every 220 ms, leaving Rust with stale region coordinates.

4. **Radial Menu Intermediate Step Barrier**:
   - File: `1.AXX\Axx.html:2711`
   - Verbatim code:
     ```javascript
     class FlowDock {
         step = 0;
         category = 'create';
         tool = '';
         tap() { this.step = this.step ? 0 : 1; this.tool = ''; }
         expand() { this.step = 2; this.tool = ''; }
     ```
   - Tapping Axx toggles `this.step` between `0` and `1`. At `step = 1`, line 12338 sets `#flow-sheet` to hidden and line 12339 sets `#flow-quick` (the radial fan `#flow-fan`) to hidden. Only `#flow-pill` ("Herramientas +") is revealed. A second tap on Axx returns `step` to `0`, folding `#flow-pill`. The radial menu (`step = 2`) is never shown on character tap.

5. **Full-Window Transparent Overlay Swallowing Events**:
   - File: `1.AXX\Axx.html:18460` and CSS lines 295, 1346
   - Verbatim code:
     ```javascript
     if (step === 2) { const sheet = document.getElementById('flow-sheet'); for (const [property, value] of Object.entries({ left: '0px', top: '0px', width: width + 'px', height: height + 'px' })) sheet.style.setProperty(property, value, 'important'); }
     ```
   - In CSS, `#flow-sheet` has `pointer-events: auto; z-index: 45;`, while `#stage` (Axx) has `z-index: 8;`. In `ResidentDesktop.interactiveRegions()` (line 18478), `#flow-sheet` is queried and its bounding box (`0, 0, width, height`) is sent to Rust as a solid interactive rectangle. This blocks desktop click-through and blocks clicks on Axx.

6. **Tentacle Physical Clipping by Native Window Frame**:
   - File: `1.AXX\Axx.html:18404, 18448-18449` and `1.AXX\Axx.html:5326`
   - In `ResidentDesktop.layout()`:
     ```javascript
     const g = this.geometry, size = this.size, half = size / 2, margin = 12;
     ...
     const minX = Math.min(...boxes.map(b => b.x)) - margin, minY = Math.min(...boxes.map(b => b.y)) - margin;
     const width = Math.ceil(Math.max(...boxes.map(b => b.x + b.width)) - minX + margin);
     const height = Math.ceil(Math.max(...boxes.map(b => b.y + b.height)) - minY + margin);
     ```
   - In `OrganicTendrils.tube()`:
     ```javascript
     const pad = route ? 170 : 104, left = Math.floor(Math.min(link.a.x, end.x) - pad), top = Math.floor(Math.min(link.a.y, end.y) - pad);
     ```
   - The Bezier curve arches out into free space with a padding of 104 to 170 px. The native Win32 HWND is sized with a margin of only 12 px around the boxes. Any curved tube pixel extending beyond 12 px is outside the Win32 window HWND and is clipped by Windows DWM / WebView2 compositor.

7. **Asynchronous Panel Drag Feedback Loop Stutter**:
   - File: `src-tauri\src\resident.rs:362-375`
   - Verbatim code:
     ```rust
     pub fn record_move(app: &AppHandle, p: &tauri::PhysicalPosition<i32>) {
         let state = app.state::<HostState>();
         if state.layout_changing.load(Ordering::Relaxed) {
             return;
         }
         ...
         let mut g = state.resident.lock().unwrap();
         g.screen_x = p.x as f64 + g.anchor_x * scale;
         g.screen_y = p.y as f64 + g.anchor_y * scale;
         state.preferences_dirty.store(true, Ordering::Relaxed);
     }
     ```
   - During panel drag, `SetWindowPos` generates `WindowEvent::Moved` asynchronously after `apply()` completes and `layout_changing` has reverted to `false`. `record_move` executes and mutates `g.screen_x`, fighting with JS's simultaneous recalculation of `anchor_x` (`-minX`), causing window displacement and jitter.

---

## 2. Logic Chain
1. From Observation 1: Standard clicks generate `event.detail === 1`. Since the capturing listener cancels events where `event.detail > 0`, all DOM clicks on `#avatar` are unconditionally destroyed.
2. From Observation 2: If the user clicks on the outer 10-20% of the avatar canvas where the shader/raster alpha is <= 96, `hitTest` returns false. Therefore, `pointerdown` does not create `drag`, preventing `pointerup` from firing `tap()`.
3. From Observation 4: Even when `tap()` executes, `FlowDock.tap()` sets `this.step = 1`, which keeps `#flow-sheet` and `#flow-quick` hidden and only shows the small `#flow-pill`. Tapping Axx a second time resets `step = 0`. This makes the radial menu completely inaccessible through tapping the character.
4. From Observation 5: When `step = 2` is forced, `#flow-sheet` covers the entire client area with `z-index: 45` and `pointer-events: auto`, overlaying the character (`z-index: 8`) and registering the entire window as interactive, defeating both character interaction and click-through transparency.
5. From Observation 6: The native window HWND is tightly bounded to active boxes with `margin = 12px`. Because the tentacle curve extends 50-100+ px beyond direct box boundaries, pixels outside the HWND boundaries cannot be rendered by WebView2/Windows.
6. From Observation 3 & 7: Rust's 30 ms cursor polling sleep and stale 220 ms hit map create race conditions where mouse clicks pass through to desktop apps, and panel dragging triggers asynchronous `record_move` events that corrupt anchor coordinates.

---

## 3. Caveats
- **Axx Connect**: Not modified or deeply diagnosed pursuant to user constraints (scope is limited to desktop UI and Tauri core). Running orphan Python processes (`uvicorn axx_connect.app:app` and `backend\server.py`) were noted as external resource hogs but not modified.
- **Microphone / Web Speech API**: In Windows WebView2, browser `SpeechRecognition` is typically not supported natively without cloud credentials or native adapters (`1.AXX\scripts\native-voice.js`). Speech testing requires verified local SAPI or running Python backend.
- **Display Scale Testing**: Windows scaling at 125%/150%/200% was verified by inspecting mathematical formulas in `lib.rs` and `resident.rs` (`scale_factor`), but OS display resolution was not forcibly switched to prevent disrupting the user session.

---

## 4. Conclusion
The interaction breakdown is not caused by complex missing dependencies, but by **seven concrete, reproducible logic flaws**:
1. Capturing `click` cancellation on `event.detail > 0` (`Axx.html:18378`).
2. Overly restrictive alpha threshold `> 96` in `SoftwareRenderer.hitTest` (`Axx.html:5256`).
3. State machine bottleneck in `FlowDock.tap()` toggling `step = 1` instead of `step = 2` (`Axx.html:2711`).
4. Full-window overlay `#flow-sheet` with `pointer-events: auto` and `z-index: 45` (`Axx.html:18460`).
5. Window HWND margin of 12 px physically clipping 104-170 px curved tendril tubes (`Axx.html:18404, 5326`).
6. 30 ms polling latency in `start_cursor_hit_test_loop` and 220 ms `updateHitMap` interval (`lib.rs:802`, `Axx.html:6543`).
7. Asynchronous race condition between `desktop_layout` / `SetWindowPos` and `record_move` during panel dragging (`resident.rs:362`).

All root causes have been documented with actionable, isolated fix proposals in `report.md`.

---

## 5. Verification Method
To independently verify these findings:
1. **Inspect Click Suppression**:
   - Check line 18378 in `1.AXX\Axx.html`. Observe `(event.detail > 0 || performance.now() < this.suppressClickUntil)`.
2. **Inspect FlowDock State**:
   - Check line 2711 in `1.AXX\Axx.html`. Observe `tap() { this.step = this.step ? 0 : 1; }` and compare with lines 12338-12340 where `#flow-sheet` is hidden for `step === 1`.
3. **Inspect Tentacle Margin**:
   - Check line 18404 (`margin = 12`) and line 5326 (`pad = route ? 170 : 104`) in `1.AXX\Axx.html`.
4. **Inspect Hit Test Loop**:
   - Check `src-tauri\src\lib.rs:802, 848-856`.
5. **Inspect Panel Drag Race**:
   - Check `src-tauri\src\resident.rs:362-375` and `1.AXX\Axx.html:18348`.
