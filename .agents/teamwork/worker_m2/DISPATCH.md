## 2026-10-21T04:34:46Z

You are Worker M2 (Panel Dynamics & Tentacle Integrator for Milestone 2).
Your working directory is: c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m2\

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\ORIGINAL_REQUEST.md
Also inspect:
- Master Project: c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\orchestrator_1\PROJECT.md
- R1 Audit Inventory: c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\orchestrator_1\INVENTORY_R1.md
- Approved visual reference: c:\Users\luigi\Desktop\Axx assistant\reference\Axx_reference_v20.html

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

CONSTRAINTS:
- Single-integrator discipline: dev/portable mode compilation only, ZERO installations.
- Do NOT touch Axx Connect (evidence/axx-connect, plugins).
- User files (Desktop/Documents) are strictly read-only.
- Exclusive file ownership: `1.AXX/Axx.html` and `src-tauri/src/resident.rs`.

MISSION FOR MILESTONE 2 (Floating Panels & Tentacle Dynamics):
1. Panel Drag Decoupling & 60 FPS Throttling:
   - In `1.AXX/Axx.html:18331–18350`: Replace synchronous Win32 `desktop_layout` IPC on every `pointermove` with smooth local CSS transforms / position updates. Throttle IPC window layout updates to 60 FPS via `requestAnimationFrame` or commit final window bounds on `pointerup`.
   - In `src-tauri/src/resident.rs:362-375`: Ensure `record_move` suppresses anchor displacement during active panel drag to prevent anchor coordinate drift and window jitter.
2. Drag Isolation & Text Selection Protection:
   - Ensure clicking or selecting text in inputs, textareas, buttons, or scrollable content inside panels NEVER triggers accidental panel dragging.
3. Interactive Panel Resizing & Persistence:
   - Add resize handles to floating panels with minimum size constraints (width >= 320px, height >= 400px).
   - Persist both position `(x, y)` and dimensions `(width, height)` in `localStorage['axx.resident.panel-pos']` without writing to disk on every frame.
4. Expand Native HWND Tentacle Margin:
   - In `1.AXX/Axx.html:18404, 18449` (`ResidentDesktop.layout()`): Increase bounding box margin from `12px` to `72px` so the Win32 window HWND completely encloses the 104-170px arched Bezier tentacle tubes without physical edge clipping.
5. Layout Recovery ("Restablecer distribución"):
   - Implement layout reset / clamp function that retrieves any panel outside visible screen bounds back inside the desktop workspace.
6. Verification:
   - Run `cargo check --manifest-path src-tauri/Cargo.toml` (0 errors).
   - Validate JS syntax with Node `vm.Script` across all script blocks in `1.AXX/Axx.html`.
   - Execute verification tests confirming panel drag decoupling, resize handles, margin = 72, and position/dimension persistence.

DELIVERABLE:
Write implementation report to `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m2\report.md` and handoff to `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m2\handoff.md`.
Notify orchestrator via `send_message`.
