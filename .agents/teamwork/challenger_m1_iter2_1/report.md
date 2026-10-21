# Adversarial Challenge Report — Milestone 1 Iteration 2

**Agent**: Challenger 1 (Transparent Desktop Click-Through Challenger)  
**Timestamp**: 2026-10-21T04:27:00Z  
**Verdict**: **APPROVE**  
**Working Directory**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\challenger_m1_iter2_1`

---

## Challenge Summary

**Overall risk assessment**: **LOW**

The goal of this adversarial challenge was to empirically stress-test the changes introduced in Milestone 1 Iteration 2:
1. **Desktop Click-Through vs Avatar Hit-Testing**: Testing coordinates in the 4 corners of the 530×530 `#stage` area ((10, 10), (520, 10), (10, 520), (520, 520)) where pixels are transparent (alpha < 16) to verify that `mask.contains(x, y)` evaluates to `false` and Tauri's `set_ignore_cursor_events(true)` is activated, allowing clicks to pass through to desktop applications.
2. **Avatar Body Hit-Testing**: Testing coordinates within the liquid avatar body (alpha > 16) to verify `mask.contains(x, y)` evaluates to `true` and `set_ignore_cursor_events(false)` is activated, ensuring clicks and drags are reliably captured by Axx.
3. **Dead Zone Elimination**: Verifying that removing `#stage` and `#avatar` from `interactiveRegions()` eliminates the previous ~220,000 px transparent blocking dead zone around the circular avatar.
4. **Drag Continuity & IPC Throttling**: Verifying drag continuity when cursor passes over transparent zones, and confirming cursor IPC throttling (`point.x != last_x || point.y != last_y`).

### Empirical Test Execution Summary
- **Browser/DOM/WebGL/Oracle Test Suite** (`scripts/challenger-m1-iter2-harness.cjs`):
  - Total Tests: 27
  - **Passed: 27 (100%)**
  - Failed: 0
- **Rust Integration Test Suite** (`src-tauri/tests/transparent_clickthrough_challenge_test.rs`):
  - Total Tests: 5
  - **Passed: 5 (100%)**
  - Failed: 0
- **Overall Rust Test Suite** (`cargo test --manifest-path src-tauri/Cargo.toml`):
  - Total Tests: 21 (10 unit, 6 cursor throttling, 5 transparent click-through)
  - **Passed: 21 (100%)**, 1 ignored helper, 0 failed.

---

## Challenges

### [Low] Challenge 1: Risk of Avatar Drag Dropping when Moving Quickly across Transparent Stage Corners
- **Assumption challenged**: If the user begins dragging the avatar and rapidly moves the cursor through one of the 4 transparent corners of the 530×530 stage, could `set_ignore_cursor_events(true)` be erroneously triggered mid-drag, dropping the window or terminating the pointer capture?
- **Attack scenario**: The cursor starts at center (265, 265) with `lbutton_down = true`, transitioning to outside the `PixelMask` (e.g. (10, 10)). If `ignore` were computed purely as `!inside`, `ignore` would become `true`, passing mouse events to Windows desktop and terminating the drag.
- **Empirical verification**:
  - We verified the Rust decision logic in `src-tauri/src/lib.rs:869-875`:
    ```rust
    let ignore = if inside {
        false
    } else if lbutton_down && !*current {
        false
    } else {
        (!regions_empty || mask_present) && !inside
    };
    ```
  - In `test_drag_continuity_across_transparent_boundaries` and JS test 5.1a, when `lbutton_down` is `true` and `*current` is `false` (drag originated inside), moving to corner (10, 10) evaluates `ignore = false`. Pointer events are NOT ignored, and the drag does not drop.
  - When `lbutton_down` becomes `false` at (10, 10), `ignore` immediately reverts to `true` (JS test 5.1b and Rust test 4), restoring click-through to the desktop.
- **Blast radius**: None; the drag state machine is sound.
- **Mitigation**: Already built into `src-tauri/src/lib.rs:871-872`.

---

### [Low] Challenge 2: Risk of Edge Bleed from 3×3 Tolerance Neighborhood in PixelMask
- **Assumption challenged**: `PixelMask::contains` includes a 1-sample neighbor tolerance loop (`for r in row.saturating_sub(1)..=(row + 1)` and `for c in column.saturating_sub(1)..=(column + 1)`). Could this 1-sample tolerance reach all the way into the corners of the 530×530 stage, blocking click-through near the outer edges?
- **Attack scenario**: On a 64×64 grid over a 530×530 canvas, each cell represents $530 / 64 \approx 8.28$ px. A 1-cell tolerance expands the hit radius by ~8.3 px. If the avatar filled the entire canvas, corners might be touched by the tolerance.
- **Empirical verification**:
  - The avatar body is circular with radius ~130–150 px centered at (265, 265).
  - Distance from center (265, 265) to corner (10, 10) is $\sqrt{255^2 + 255^2} \approx 360.6$ px.
  - The avatar boundary ends at $\sim 150$ px, leaving $> 200$ px of clear transparent margin to the corners.
  - In tests 1.3.1 through 1.3.4, the 3×3 neighborhood around all 4 corners was verified to contain zero solid bits (`neighborhoodSolid == false`).
  - Rust tests verified `mask.contains(x, y) == false` for all 4 corners.
- **Blast radius**: None. The 1-sample tolerance provides smooth tracking around the moving organic rim without polluting the corners.
- **Mitigation**: No change required; margin is far larger than tolerance radius.

---

### [Low] Challenge 3: Invariant Consistency between LiquidRenderer and SoftwareRenderer
- **Assumption challenged**: Does `LiquidRenderer.hitMask()` match `SoftwareRenderer.hitMask()` and `hitTest()` thresholds after Worker M1-2's fix?
- **Attack scenario**: If `LiquidRenderer.hitMask()` retained `> 96`, translucent rims with alpha between 17 and 96 would register as hits in direct browser DOM events (`hitTest`), but would be absent from the Tauri alpha mask, causing clicks on the outer translucent rim to pass through to the desktop instead of interacting with Axx.
- **Empirical verification**:
  - Inspected `1.AXX/Axx.html:4279`: verified `pixels[((rows - 1 - y) * cols + x) * 4 + 3] > 16 ? 1 : 0`.
  - Verified `> 96` is completely absent from `LiquidRenderer.hitMask()`.
  - Tested synthetic buffers with alpha = 16, 17, 32, 96, 255: alpha 16 produces 0; alpha 17, 96, and 255 produce 1.
  - Live WebGL / SoftwareRenderer outputs match `> 16` threshold uniformly.
- **Blast radius**: None; threshold parity is completely restored.
- **Mitigation**: Verified via automated test 4.1–4.5.

---

## Stress Test Results

| Test ID | Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|
| **1.1** | Stage dimensions at 530 sizing | `#stage` bounding box is 530×530 px (±5 px) | 530×530 px | **PASS** |
| **1.2** | Stage/Avatar exclusion from regions | Neither `#stage` nor `#avatar` in `interactiveRegions()` | `stageInRegions: false`, `avatarInRegions: false` | **PASS** |
| **1.3.1** | Corner Top-Left (10, 10) hit test | `hitDirect=false`, `maskBit=0`, `neighborhood=clear` | All evaluated false / 0 | **PASS** |
| **1.3.2** | Corner Top-Right (520, 10) hit test | `hitDirect=false`, `maskBit=0`, `neighborhood=clear` | All evaluated false / 0 | **PASS** |
| **1.3.3** | Corner Bottom-Left (10, 520) hit test | `hitDirect=false`, `maskBit=0`, `neighborhood=clear` | All evaluated false / 0 | **PASS** |
| **1.3.4** | Corner Bottom-Right (520, 520) hit test | `hitDirect=false`, `maskBit=0`, `neighborhood=clear` | All evaluated false / 0 | **PASS** |
| **2.1** | Rust `PixelMask.contains` on 4 corners | Evaluates to `false` in all 4 corners | Evaluated `false` for all 4 corners | **PASS** |
| **2.2** | Rust hit-test decision on 4 corners | `inside=false`, `ignore=true` (desktop click-through enabled) | `inside=false`, `ignore=true` for all 4 corners | **PASS** |
| **3.1** | Avatar center direct `hitTest` | `renderer.hitTest(265, 265)` evaluates to `true` | `hitTest=true` | **PASS** |
| **3.2** | Avatar center Rust `PixelMask.contains` | `rustMask.contains(265, 265)` evaluates to `true` | `contains=true` | **PASS** |
| **3.3** | Avatar center Rust hit-test decision | `inside=true`, `ignore=false` (caught by Axx) | `inside=true`, `ignore=false` | **PASS** |
| **3.4** | Radial body samples (r <= 60px) | `hitTest=true`, `maskBit=1` across 8 angles | All evaluated `true` / 1 | **PASS** |
| **4.1** | Alpha boundary: alpha <= 16 | `hitTest=false`, `maskBit=0` | Evaluated `false` / 0 | **PASS** |
| **4.2** | Alpha boundary: alpha = 17 | `hitTest=true`, `maskBit=1` | Evaluated `true` / 1 | **PASS** |
| **4.3** | Alpha boundary: alpha = 96 | `hitTest=true`, `maskBit=1` | Evaluated `true` / 1 | **PASS** |
| **4.4** | Alpha boundary: alpha = 255 | `hitTest=true`, `maskBit=1` | Evaluated `true` / 1 | **PASS** |
| **4.5** | Static check on `hitMask` source | Uses `> 16 ? 1 : 0`, does not use `> 96` | Verified in `1.AXX/Axx.html:4279` | **PASS** |
| **5.1a** | Active drag continuity across boundary | Moving to (10, 10) with `lbutton_down=true` retains `ignore=false` | `inside=false`, `ignore=false` | **PASS** |
| **5.1b** | Releasing mouse button outside | `lbutton_down=false` at (10, 10) restores `ignore=true` | `inside=false`, `ignore=true` | **PASS** |
| **5.2** | Rust cursor IPC throttling gating | `src-tauri/src/lib.rs` checks `point.x != last_x \|\| point.y != last_y` | Verified present and active | **PASS** |
| **6.1** | 10×10 Grid dead zone scan | Zero dead zone violations across all transparent samples in stage | 0 violations across 100 sampled points | **PASS** |
| **R-1** | Rust integration: 4 corners click-through | `transparent_clickthrough_challenge_test::test_530x530_stage_four_corners_evaluate_to_click_through` | Passed in 0.01s | **PASS** |
| **R-2** | Rust integration: avatar body hit | `transparent_clickthrough_challenge_test::test_liquid_avatar_body_evaluates_to_axx_hit` | Passed in 0.01s | **PASS** |
| **R-3** | Rust integration: dead zone regression test | `transparent_clickthrough_challenge_test::test_regression_dead_zone_eliminated_when_stage_rect_not_in_regions` | Passed in 0.01s | **PASS** |
| **R-4** | Rust integration: drag continuity across boundaries | `transparent_clickthrough_challenge_test::test_drag_continuity_across_transparent_boundaries` | Passed in 0.01s | **PASS** |
| **R-5** | Rust integration: coordinate stability fuzzing | `transparent_clickthrough_challenge_test::test_fuzz_coordinate_stability_and_no_panics` (10,000 points) | Passed in 0.01s (0 panics) | **PASS** |

---

## Unchallenged Areas

- **Multi-panel rAF drag decoupling & HWND 72px margin envelope**: Explicitly scheduled for Milestone 2 in the project roadmap (`ROADMAP.md` / `PROJECT.md`).
- **Physical Multi-Monitor Hardware Scale Switching**: Multi-monitor scaling logic was verified via simulated scale factor tests in Rust (`test_scale_factors_and_coordinate_scaling` and `negative_dpi_monitor_clamps_content_inside_workarea`), but physical monitor reconfiguration was omitted to avoid altering the user's desktop display settings without restoration.

---

## Verdict

**APPROVE**

Milestone 1 Iteration 2 successfully meets all empirical acceptance criteria:
1. Transparent desktop click-through is 100% functional in all 4 corners of the 530×530 stage area.
2. Avatar body hit-testing reliably captures clicks and drags without dead zones.
3. The alpha threshold is harmonized at `> 16`.
4. `#stage` and `#avatar` are correctly excluded from `interactiveRegions()`.
5. Cursor IPC flooding is suppressed when stationary.
6. All 27 empirical harness tests and 21 Rust tests pass with zero failures.
