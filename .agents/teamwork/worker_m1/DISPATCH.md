## 2026-10-21T03:44:00Z
You are Worker M1 (Hit-Testing & Radial Interaction Integrator).
Your working directory is: c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m1\

MANDATORY FIRST STEP: Read the authoritative user request at:
c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\ORIGINAL_REQUEST.md
Also inspect:
- c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\orchestrator_1\PROJECT.md
- c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\orchestrator_1\INVENTORY_R1.md
- c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_1\report.md
- c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_2\report.md
- c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_3\report.md
- Approved visual reference: c:\Users\luigi\Desktop\Axx assistant\reference\Axx_reference_v20.html

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

CONSTRAINTS:
- Single-integrator discipline: dev/portable mode compilation only, ZERO installations.
- Do NOT touch Axx Connect (evidence/axx-connect, plugins).
- User files (Desktop/Documents) are strictly read-only.
- You exclusively own: `1.AXX/Axx.html` and `src-tauri/src/lib.rs`.

MISSION FOR MILESTONE 1:
1. Clean up orphan/zombie background processes:
   - Terminate the 22 orphan `python.exe -m backend.connect.mcp_server` processes safely in Windows powershell.
2. Fix Avatar Click Cancellation in DOM:
   - In `1.AXX/Axx.html:18378`: Eliminate destructive `event.detail > 0` click cancellation. Replace it with real drag threshold detection (only suppress clicks if pointer moved > 4px between pointerdown and pointerup).
3. Fix Alpha Hit-Testing Cutoff:
   - In `1.AXX/Axx.html:5256`: Adjust alpha cutoff in `SoftwareRenderer.hitTest` to `> 16` so organic translucent outer rim clicks register properly.
4. Fix Radial Menu Opening State Machine:
   - In `1.AXX/Axx.html:2711` (`FlowDock.tap`) and line `18120` (`ResidentDesktop.tap`): Ensure tapping the avatar transitions cleanly to `step = 2` (opening radial menu `#flow-fan`), and tapping again closes it back to `0`.
5. Fix CSS Pointer-Events Blocking on Radial Fan:
   - In `1.AXX/Axx.html:1346`: Remove `pointer-events: none !important` from `#flow-fan` so tool buttons receive pointer events and hover/clicks.
6. Fix Overlay Swallowing & Hit Map Registration:
   - In `1.AXX/Axx.html:18460` and `18478`: Ensure `#flow-sheet` backdrop is `pointer-events: none`, while active radial buttons have `pointer-events: auto`. Add `#avatar` / `#stage` bounding box to `interactiveRegions()` sent to Rust.
7. Fix Rust Tauri Cursor Polling & DPI Synchronization:
   - In `src-tauri/src/lib.rs:800-858`: Optimize cursor hit-testing and DPI scaling so clicks on the avatar do not pass through to background desktop apps.
8. Verify Implementation:
   - Run verification checks (compile check `cargo check` in `src-tauri/`, node syntax check on `1.AXX/Axx.html`).
   - Confirm all tests/builds pass cleanly without errors.
   - List every file modified and exact reversion instructions.

DELIVERABLE:
Write your implementation report to:
`c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m1\report.md`
and write your handoff summary to:
`c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m1\handoff.md`
When done, notify the orchestrator with `send_message`.
