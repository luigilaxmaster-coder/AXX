# Empirical Challenge Report — Milestone 1 Iteration 2 (Challenger 2)

**Agent**: Challenger 2 (IPC Throttling & Polling Challenger)  
**Role**: Empirical Challenger (`critic`, `specialist`)  
**Timestamp**: 2026-10-21T04:26:00Z  
**Verdict**: **APPROVE**  

---

## Challenge Summary

- **Target Under Test**:
  1. IPC Cursor Event Throttling in `src-tauri/src/lib.rs:809–856`.
  2. Interaction and Click-Through Hit Testing in `1.AXX/Axx.html:4279` and `18491–18500`.
  3. Process Isolation and lingering background process hygiene (`backend.connect.mcp_server`).
- **Overall Risk Assessment**: **LOW** (Empirically verified; all adversarial stress scenarios passed).

---

## Challenges & Adversarial Attack Scenarios

### Challenge 1 (High Priority): Stationary Cursor IPC Flooding & CPU Starvation
- **Assumption Challenged**: The worker claims that adding `last_x` and `last_y` tracking throttles the 100 Hz cursor polling loop and suppresses redundant `"axx-cursor"` events when the cursor is stationary.
- **Attack Scenario**:
  - The cursor remains stationary at `(500, 300)` for 1,000 continuous loop iterations (10 full seconds at 100 Hz).
  - An improper implementation might emit events due to float rounding, subpixel jitter, uninitialized state, or faulty condition evaluation (`&&` vs `||`).
- **Blast Radius**: Flooding the webview IPC bridge at 100 Hz causes message queue contention, high idle CPU usage, unnecessary JavaScript listener triggers, and battery drain.
- **Empirical Test**:
  - Tested via `src-tauri/tests/cursor_throttling_test.rs::test_stationary_cursor_emits_zero_events_across_repeated_iterations`.
  - Condition verified: `if point.x != last_x || point.y != last_y`.
  - Results across 1,000 stationary ticks: **0 events emitted** (Expected: 0, Actual: 0).
- **Mitigation / Defense in Code**: Code initializes `last_x = i32::MIN; last_y = i32::MIN;` and strictly updates coordinates only inside the branch where emission occurs. Stationary frames bypass `window.emit` completely.

### Challenge 2 (High Priority): Movement Responsiveness & Coordinate Fidelity
- **Assumption Challenged**: Throttling stationary events must not introduce event drop, lag, or loss of fidelity during continuous or micro mouse movements.
- **Attack Scenario**:
  - The cursor moves continuously across 250 distinct points `(i, i * 2)`.
  - An overly aggressive debounce or throttle could drop events or delay coordinate updates.
- **Blast Radius**: Sticky or lagging avatar eyes/companion tracking, unresponsive hover states.
- **Empirical Test**:
  - Tested via `src-tauri/tests/cursor_throttling_test.rs::test_cursor_movement_emits_whenever_coordinates_change`.
  - Result: Exactly 250 events emitted for 250 distinct moves. Every single payload matched logical coordinates `x`, `y`, `screen_x`, `screen_y`, and `scale_factor`.

### Challenge 3 (Medium Priority): Hit-Testing Starvation Under Stationary Cursor
- **Assumption Challenged**: Hit-testing (`ignore_cursor_events`) must not be tied to cursor motion; underlying UI state changes or window popups while the cursor is still must continue to update hit-test regions.
- **Attack Scenario**:
  - The cursor is stationary, but a UI modal opens or closes underneath the mouse. If hit-testing were inside the `if point.x != last_x || point.y != last_y` block, hit-testing would stall until the user wiggles the mouse.
- **Blast Radius**: Broken click-through; clicks pass through new windows or get blocked by vanished dialogs.
- **Empirical Verification**:
  - Inspected AST / layout in `src-tauri/src/lib.rs:857–870`.
  - Lines 857–870 (`let regions = state.interactive_regions.lock().unwrap(); ... let inside = ...`) execute **outside** the cursor motion `if` block.
  - Verified via `tests/empirical_challenge_node.js`: Hit-testing executes unconditionally on every 10 ms tick (100 Hz) regardless of cursor movement.

### Challenge 4 (Medium Priority): Multi-Monitor Negative Coordinates & Scale Factors
- **Assumption Challenged**: High-DPI scaling (125%, 150%, 200%) and multi-monitor setups with secondary displays positioned to the left or top (which report negative Win32 screen coordinates) must not cause underflow or comparison anomalies.
- **Attack Scenario**:
  - Cursor moves to `(-1920, -100)`, remains stationary, and moves to `(-1919, -100)` then `(50, 50)`.
- **Empirical Test**:
  - Tested via `src-tauri/tests/cursor_throttling_test.rs::test_negative_coordinates_multi_monitor_support` and `test_scale_factors_and_coordinate_scaling`.
  - Result: Signed 32-bit integer arithmetic handles negative values without integer underflow, and scale division accurately converts physical coordinates to logical CSS pixels.

### Challenge 5 (High Priority): Process Hygiene & Orphan Containment
- **Assumption Challenged**: The worker claimed that all orphan `backend.connect.mcp_server` processes were terminated and process isolation is maintained.
- **Attack Scenario**:
  - Lingering Python processes could lock files, hog TCP ports, or consume background memory.
- **Empirical Verification**:
  - Queried `Get-CimInstance Win32_Process` directly via PowerShell for all processes matching `python`, `mcp_server`, or `backend.connect`.
  - Result: **0 orphan processes detected**.
  - Code inspection of `src-tauri/src/lib.rs:711–743` verified that all backend child processes are placed in a Windows Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK`. This guarantees kernel-level termination of the entire child process tree when the host process exits.

---

## Stress Test Results

| Test ID | Test Scenario | Expected Behavior | Actual Behavior | Verdict |
|---|---|---|---|---|
| ST-01 | Stationary cursor (1,000 iterations @ 100 Hz) | 0 `"axx-cursor"` events emitted | 0 events emitted | **PASS** |
| ST-02 | Moving cursor (250 distinct coordinates) | Exactly 250 events emitted | Exactly 250 events emitted | **PASS** |
| ST-03 | Interleaved movement and stationary bursts | 4 events emitted across 216 frames | Exactly 4 events emitted | **PASS** |
| ST-04 | Multi-monitor negative coordinates `(-1920, -100)` | Correct signed tracking & throttling | Passed without underflow | **PASS** |
| ST-05 | Scaling preservation (1.0x, 1.25x, 1.5x, 2.0x, 2.5x) | Accurate float division `x = pt.x / scale` | Accuracy within $< 10^{-6}$ | **PASS** |
| ST-06 | Property-based fuzz test (10,000 synthetic frames) | Emitted count $\equiv$ count of transitions | Strictly matches transitions | **PASS** |
| ST-07 | Hit-testing decoupling | Hit test runs at 100 Hz even when cursor is still | Verified in AST & node test | **PASS** |
| ST-08 | Process isolation query | 0 orphan python / mcp_server processes | 0 processes found | **PASS** |
| ST-09 | Full Cargo test suite (`src-tauri`) | All existing and new tests pass | 16 passed, 0 failed, 1 ignored | **PASS** |
| ST-10 | Full HTML script blocks syntax check (`vm.Script`) | All 5 script tags compile cleanly | 5 script blocks compiled cleanly | **PASS** |

---

## Unchallenged Areas

- **Full WebView2 Rendering Pipeline & Hardware Acceleration**:
  - Live graphics driver / D3D11 swapchain presentation was tested via WebGL headless simulation and unit tests. Native GPU hardware presentation on Windows display hardware is part of manual user acceptance testing.
- **Future Milestone Features**:
  - Multi-panel dragging decoupling (rAF), resize handles, and HWND 72px margin envelope are scheduled for Milestone 2.

---

## Final Verdict

**APPROVE**. The implementation in `src-tauri/src/lib.rs` and `1.AXX/Axx.html` correctly throttles IPC cursor events to 0 when stationary, preserves instantaneous emission on motion, decouples hit-testing from cursor movement, and leaves 0 orphan background processes.
