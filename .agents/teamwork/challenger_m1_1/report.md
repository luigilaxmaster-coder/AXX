# Challenge Report — Milestone 1: Hit-Testing & Radial Interaction

**Challenger**: Challenger 1 (Milestone 1 Empirical Challenger)  
**Role**: Critic, Specialist  
**Target Files**: `1.AXX/Axx.html`, `src-tauri/src/lib.rs`  
**Test Harness**: `scripts/challenger-m1-adversarial-harness.cjs`  
**Date**: 2026-10-21T04:06:00Z  

---

## Challenge Summary

**Overall risk assessment**: **LOW**

Worker M1's modifications systematically address and resolve the critical interaction failure that rendered Axx unresponsive to touch and click. Through 22 automated adversarial test cases executed against the live webview runtime in Chromium headless shell and 10 Rust unit tests in Tauri, all core hypotheses concerning interaction discrimination, alpha cutoffs, state machine predictability, and drag suppression have been empirically validated.

---

## Challenges

### [Low] Challenge 1: Micro-Movement vs Drag Threshold Boundary

- **Assumption challenged**: User hand tremor or mouse sensor jitter when clicking the avatar could exceed small movement thresholds and inadvertently trigger window dragging instead of opening the radial menu.
- **Attack scenario**: Evaluated jitter movements at 1.41px, 2.83px, 3.54px, 4.0px, and 5.0px.
- **Observation & Empirical Result**:
  - Distances `<= 4.0px` (`Math.hypot <= 4`) evaluate `wasDrag = false` and invoke `this.tap()`, successfully toggling the radial menu (`step: 0 -> 2`).
  - Distances `> 4.0px` (`Math.hypot > 4`, e.g., dx = 5.0px) evaluate `wasDrag = true`, suppress `this.tap()`, and activate `this.suppressClickUntil = performance.now() + 800`.
- **Verdict**: PASS. The 4px hysteresis buffer provides an optimal compromise between click stability and immediate drag engagement.

### [Low] Challenge 2: Trailing Native Click Interference After Real Drags

- **Assumption challenged**: After a user completes an actual drag of the avatar or panel, the browser engine generates a synthetic or native `click` event at the pointer release coordinates. If this event is not actively suppressed, it could open or close the radial menu unintentionally upon finishing a drag.
- **Attack scenario**: Dispatched a full drag sequence (move dx = 25, dy = 20), followed immediately by an untrusted `click` event with `detail = 1` targeting `#avatar`.
- **Observation & Empirical Result**:
  - In `Axx.html:18383`: `document.addEventListener('click', event => { if (isBody(event.target) && (performance.now() < this.suppressClickUntil)) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);`.
  - The trailing click event was cancelled at the capture phase (`defaultPrevented = true`, stopped immediate propagation).
  - The radial dock remained in `step = 0`.
- **Verdict**: PASS. Trailing clicks are suppressed for 800ms post-release.

### [Low] Challenge 3: Multi-Click Detail Accrual (`detail = 1, 2, 3`)

- **Assumption challenged**: In the baseline code, `event.detail > 0` aborted every user click because standard single clicks have `detail = 1`. Removing this check might introduce unexpected behavior on rapid multi-clicks (`detail = 2` for double click, `detail = 3` for triple click).
- **Attack scenario**: Dispatched rapid consecutive pointer sequences generating `detail = 1`, `detail = 2`, and `detail = 3`.
- **Observation & Empirical Result**:
  - Cycle progression: `[0 -> 2 -> 0 -> 2]`.
  - Double click cleanly opens and then closes the radial menu without getting stuck.
  - Triple click cleanly re-opens the radial menu on the third strike.
- **Verdict**: PASS. State transitions strictly follow user intent without detail-dependent cancellation.

### [Low] Challenge 4: Alpha Cutoff Discrimination & Edge Sensitivity

- **Assumption challenged**: Changing the alpha cutoff from `> 96` / `> 100` down to `> 16` might cause transparent or near-invisible raster noise to intercept clicks, or conversely fail to register translucent rim pixels.
- **Attack scenario**: Synthetic raster pixel buffers evaluated across alpha values `0, 10, 16, 17, 20, 128, 255`.
- **Observation & Empirical Result**:
  - `alpha = 0` (transparent outside): `hitTest` returns `false`.
  - `alpha = 10` (faint sensor noise): `hitTest` returns `false`.
  - `alpha = 16` (boundary): `hitTest` returns `false`.
  - `alpha = 17` (strictly greater than 16): `hitTest` returns `true`.
  - `alpha = 20` (dark chrome translucent liquid meniscus): `hitTest` returns `true`.
  - `alpha = 255` (solid liquid core): `hitTest` returns `true`.
  - Live avatar inspection: Center of avatar returns `true`, outer corner (2, 2) returns `false`, external coordinates (-50, -50) return `false`.
- **Verdict**: PASS. The threshold `> 16` cleanly separates ambient render noise from organic liquid contours.

### [Low] Challenge 5: Rapid Radial Menu Toggle Cycle Under Stress

- **Assumption challenged**: Rapidly tapping the avatar 100 times in quick succession might desynchronize the navigation state or cause the menu to get locked in intermediate states (e.g., `step = 1`).
- **Attack scenario**: 100 sequential pointerdown/pointerup cycles on `#avatar`.
- **Observation & Empirical Result**:
  - 100 cycles executed without a single deviation:
    - Odd cycles (1, 3, 5... 99) reliably set `step = 2`.
    - Even cycles (2, 4, 6... 100) reliably set `step = 0`.
    - 0 cycle errors recorded; final state returned to `step = 0`.
- **Verdict**: PASS. State machine is deterministic and race-condition free.

### [Informational] Challenge 6: Desktop Click-Through vs `#stage` in `interactiveRegions`

- **Assumption challenged**: Adding `#stage` (a 530x530 box) to `interactiveRegions()` in `Axx.html:18493` could prevent Windows desktop click-through in the transparent corners of the avatar's bounding box.
- **Attack scenario**: Evaluated `interactiveRegions()` and Rust `start_cursor_hit_test_loop` logic.
- **Observation & Logic Chain**:
  - In Rust (`src-tauri/src/lib.rs:855`), `inside` checks `regions.iter().any(|r| r.contains(x, y)) || mask.as_ref().is_some_and(|m| m.contains(x, y))`.
  - Because `stage` is in `regions`, the Tauri window sets `set_ignore_cursor_events(false)` over the full 530x530 square.
  - When a click occurs in a corner (alpha = 0), `SoftwareRenderer.hitTest` in JavaScript drops it, but the click does not fall through to desktop windows underneath until the cursor moves outside the 530x530 rect.
  - *Trade-off assessment*: This trade-off was consciously made by Worker M1 to guarantee that the avatar responds instantly to user input upon launch without waiting for the 220ms asynchronous WebGL pixel mask to synchronize.
- **Mitigation / Next Milestone Note**: In Milestone 2 or 7, if click-through right at the extreme corner pixels is required, the stage rect in `interactiveRegions` can be replaced with an inscribed circle or rely on the cached `PixelMask`. For Milestone 1, this trade-off is acceptable and successfully eliminates the total interaction paralysis.

---

## Stress Test Results

Executed via `node scripts/challenger-m1-adversarial-harness.cjs` (Chromium Headless Shell via Playwright):

| ID | Test Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|---|
| **1.1** | Single click (`detail = 1`) | Radial menu opens (`step: 0 -> 2`) | `step = 2`, click not prevented | **PASS** |
| **1.2** | Double click (`detail = 2`) | Radial menu closes (`step: 2 -> 0`) | `step = 0`, click not prevented | **PASS** |
| **1.3** | Triple click (`detail = 1, 2, 3`) | Predictable toggling `[0, 2, 0, 2]` | Matches `[0, 2, 0, 2]` | **PASS** |
| **1.4** | Micro-movements (< 4px jitter: 1.41px, 2.83px, 3.54px) | Treated as click (`step = 2`) | `step = 2`, `wasDrag = false` | **PASS** |
| **1.5** | Exact boundary condition (dx = 4.0px, dy = 0) | Treated as click (`step = 2`) | `step = 2`, `wasDrag = false` | **PASS** |
| **1.6** | Threshold breach (dx = 5.0px, dy = 0) | Treated as drag (`step = 0`, suppress active) | `step = 0`, `suppressClickUntil > now` | **PASS** |
| **1.7** | Real drag (> 4px: dx = 25, dy = 20) | Suppresses trailing clicks, prevents toggle | `step = 0`, click defaultPrevented | **PASS** |
| **1.8** | Click after suppression window expires (> 800ms) | Subsequent click allowed normally | Immediate prevented, later allowed | **PASS** |
| **1.9** | Non-primary pointer buttons (middle/right) | Middle/right buttons do not drag or tap | No drag initiated, `step = 0` | **PASS** |
| **1.10** | Pointercancel / Window Blur | Cleanly resets active drag state | Drag active before, null after | **PASS** |
| **2.1a** | Alpha = 0 (transparent outside) | `hitTest` returns `false` | Returned `false` | **PASS** |
| **2.1b** | Alpha = 10 (ambient noise <= 16) | `hitTest` returns `false` | Returned `false` | **PASS** |
| **2.1c** | Alpha = 16 (cutoff boundary <= 16) | `hitTest` returns `false` | Returned `false` | **PASS** |
| **2.1d** | Alpha = 17 (above cutoff > 16) | `hitTest` returns `true` | Returned `true` | **PASS** |
| **2.1e** | Alpha = 20 (translucent rim > 16) | `hitTest` returns `true` | Returned `true` | **PASS** |
| **2.1f** | Alpha = 255 (solid center > 16) | `hitTest` returns `true` | Returned `true` | **PASS** |
| **2.2** | Live Avatar Hit-Test | Center = true, Corner = false, Outside = false | True / False / False | **PASS** |
| **2.3** | 64x64 HitMask Bit Generation | Generates >100 solid and >100 transparent bits | 64x64 grid validated | **PASS** |
| **2.4** | Stage/Avatar in `interactiveRegions` | Ensures immediate Rust responsiveness | Confirmed present in regions | **PASS** |
| **3.1** | 100 Rapid Avatar Clicks | Alternates strictly between 0 and 2 | 0 errors across 100 cycles | **PASS** |
| **3.2** | Radial Fan Buttons CSS | Buttons `pointer-events: auto`, sheet `none` | Confirmed `auto` and `none` | **PASS** |
| **3.3** | Orbital Button Click Execution | Clicking chat orbital button opens chat panel | Panel opened, visible | **PASS** |

Executed via `cargo test --manifest-path src-tauri/Cargo.toml --lib`:

| Test | Module | Result |
|---|---|---|
| `hit_regions_validate_and_use_logical_coordinates` | `tests` | **PASS** |
| `alpha_mask_preserves_transparent_click_through_holes` | `tests` | **PASS** |
| `local_proxy_rejects_path_escape_and_non_api_routes` | `tests` | **PASS** |
| `private_transport_authenticates_and_parses_real_loopback_response` | `tests` | **PASS** |
| `private_transport_rejects_http_errors_instead_of_reporting_json_as_success` | `tests` | **PASS** |
| `job_cleanup_terminates_owned_suspended_process` | `tests` | **PASS** |
| `explicitly_escaped_user_target_survives_owned_job_cleanup` | `tests` | **PASS** |
| `expanding_to_left_preserves_global_avatar_anchor` | `resident::tests` | **PASS** |
| `negative_dpi_monitor_clamps_content_inside_workarea` | `resident::tests` | **PASS** |
| `legacy_rectangle_preferences_are_not_resident_v2` | `resident::tests` | **PASS** |

---

## Unchallenged Areas

- **Physical Multi-Monitor Heterogeneous DPI Switching**: Physical hardware displays with differing DPI scalings (e.g. Monitor 1 at 100%, Monitor 2 at 175%) were verified via logical mathematical tests and unit tests (`negative_dpi_monitor_clamps_content_inside_workarea`), but could not be physically connected to the headless runtime test environment.

---

## Verdict

**APPROVE**
