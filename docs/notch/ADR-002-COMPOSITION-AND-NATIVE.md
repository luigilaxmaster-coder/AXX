# ADR-002 — Phase II Adaptive Composition Engine, Native Click-Through & Focus Return

- **Status:** Accepted (Implemented on `feat/notch-singularity`, Phase II)
- **Extends:** Phase I core architecture (`notch-state.js`, `notch-motion.js`, `notch-snapshot.js`, `notch-projections.js`, `resident.rs`, `lib.rs`)

## Context
Phase I proved deterministic dock/undock state transitions and zero tendrils while docked, but lacked:
1. Distinct visual layouts per activity (`Media Panoramic`, `Intent Palette`, `Agent Observatory`, `Portal Smart Shelf`, `Resource Lens`, `Recall & Offline Queue`, `Stage Detachable Continuum`).
2. Selective Win32 click-focus activation (avoiding focus steal on passive compact hover while allowing typing in Intent/Stage).
3. Unified `dockEpoch` + `geometryRevision` verification inside Rust `hit_map` IPC alongside `desktop_layout`.
4. Explicit trajectory-aware approach band gating and `L0..L5` semantic budget control.

## Decisions
1. **Isolated Adaptive Layout Module ([notch-layout.js](file:///c:/Users/luigi/Desktop/axx2/1.AXX/scripts/notch/notch-layout.js)):** Pure geometry resolver mapping `(state, context, workArea, density)` to discrete compositions across `L0..L5` without mutating runtime state or CSS inline baselines (`mobile/design-baseline.json`).
2. **Focus-Safe Native Overlay (`src-tauri/src/lib.rs`):** Added `HostState.allow_click_focus: AtomicBool` controlled by `notch_focus(acquire, restore_focus, allow_click_focus)`. Passive hover/compact pills leave external apps focused; clicking into `expanded` / `stage` inputs records `prior_focus_hwnd` cleanly for deterministic restoration on collapse/undock.
3. **Epoch-Locked `hit_map` & Signature Non-Caching (`src-tauri/src/lib.rs`, `1.AXX/Axx.html`):** Rust `hit_map` verifies `epoch >= resident.dock_epoch` before replacing `interactive_regions`; frontend inspects `{ accepted }` and leaves `lastHitSignature` uncached when `accepted === false` while incrementing `perfStats.droppedAcks`.
4. **Reversible Identity Preservation Under Deliberate Edits:** `buildLiveSnapshot()` captures `identityRevision: state.explicitIdentityEditRevision` (`0` at dock time). Explicit customization while `docked` increments `explicitIdentityEditRevision` via wrapped `applySettings()`, ensuring `restoreSnapshot` preserves deliberate user edits on undock without drifting unmodified fields.
5. **Opt-In Flag & Baseline Isolation:** `axx.notch.v1` remains `enabled: false` by default and all notch styling lives in [notch.css](file:///c:/Users/luigi/Desktop/axx2/1.AXX/scripts/notch/notch.css), keeping `1.AXX/Axx.html#inline-styles`, `/v1` Companion endpoints, and version `0.23.5` untouched.
