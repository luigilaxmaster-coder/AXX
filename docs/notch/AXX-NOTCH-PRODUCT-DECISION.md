# ADR-001: AXX Notch Product & Visual Architecture (`AXX Identity Accent`)

**Status:** ACCEPTED (Phase B)
**Date:** 2026-11-27

## 1. Context & Architectural Decision
AXX is a resident Windows 11 assistant (`Tauri 2.12.4` / `Win32` / `WebView2`) featuring a custom 3D software-rendered avatar (`SoftwareRenderer`, 24 forms × 9 palettes × 4 finishes) and organic swept-tube connections (`OrganicTendrils`).
We evaluated three visual directions for the top-edge docked state:
1. **Neutral Monolith:** Constant dark neutral pill. High legibility, low connection to user's customized AXX avatar.
2. **Theme Adaptive:** Fully follows `interface-theme.js` light/dark surfaces. Risk of low silhouette separation against bright wallpapers.
3. **AXX Identity Accent (SELECTED):** Stable high-contrast dark obsidian shell anchored cleanly to the monitor top seam, paired with controlled chromatic accents, status glow, and an abstract geometric identity mark derived from the user's active `Axx.PALETTES[palette]` and `Axx.FORMS[form]`—with **zero 3D mesh deformation** and **zero tentacles** while docked.

## 2. Structural Decisions
1. **Single Native Window Authority (`main` in `resident.rs`):**
   - Extend `resident.rs` and `ResidentDesktop` rather than spawning a competing second native window controller for the notch.
   - When `physical === 'free'`, `ResidentDesktop` owns full-work-area transparent layout + `SoftwareRenderer` + `OrganicTendrils`.
   - When `physical` enters `retracting -> docking -> docked`, `OrganicTendrils` is gated off (`tendrilsEnabled = false`), `SoftwareRenderer` is hidden/suspended cleanly once settled, and the top-edge notch shell owns `interactiveRegions` with monotonic `(dockEpoch, geometryRevision)`.
   - `Stage` reuses `#panel` (or existing `OrganicDesk` / `ActionWindows` surface bounds) positioned cleanly below the notch while keeping the exact same `sessionId` / `conversation_id` / `timer` state.
2. **Protected Baseline Preservation:**
   - `mobile/design-baseline.json` protects `1.AXX/Axx.html#inline-styles`. Therefore all notch CSS resides in `1.AXX/scripts/notch/notch.css` and all notch logic in `1.AXX/scripts/notch/*.js`.
3. **Opt-in Feature Flag:**
   - Controlled by `axx.notch.v1` (`enabled: false` by default until P0 gates complete, toggleable in Settings → `Windows e inicio` or via `Axx.notch.setEnabled(true)`).
4. **Golden Vertical Slice Capability:**
   - Wire `App.store.data.timer` / `TimeStudio19` (100% local, deterministic progress, pause/resume/cancel, native `set_timer` due event) + `CommandLibrary` / `Intent` + `System Media` so the first slice demonstrates real end-to-end AXX business execution across `FREE -> APPROACH -> RETRACTING -> DOCKING -> DOCKED -> EXPANDED -> COLLAPSE -> UNDOCKING -> FREE`.
