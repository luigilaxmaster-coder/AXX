# AXX Notch Integration — Phase A Code Archaeology & Baseline Audit

**Date:** 2026-11-27
**Base HEAD (at branch creation):** `dd44ef2fe598ce593741a0c1ef92e30690e5474c` (`feat/mobile-3`)
**Working Branch:** `feat/notch-singularity`
**Platform:** Windows 11 · Tauri `2.12.4` · Rust `1.96.0` · Node `v24.14.1` · Python `3.12.10`
**Observed Hardware/Displays:**
- GPU: `Intel(R) Iris(R) Xe Graphics` (`30.0.101.1369`)
- `\\.\DISPLAY1` (Primary): Bounds `{X=0,Y=0,Width=1536,Height=864}`, WorkingArea `{X=0,Y=0,Width=1536,Height=816}`
- `\\.\DISPLAY2`: Bounds `{X=1920,Y=0,Width=1920,Height=1080}`, WorkingArea `{X=1920,Y=0,Width=1920,Height=1032}`

---

## 1. Real Symbol & Authority Inventory (Verified on HEAD)

| Symbol / Module | Location (HEAD) | Responsibility & Authority | Extension Strategy |
|---|---|---|---|
| `Axx.FORMS` | `1.AXX/Axx.html:1825` | 24 avatar SDF/parametric forms (`Core`..`Ripple`) | Read-only reference for identity snapshot & accent glyph |
| `Axx.PALETTES` | `1.AXX/Axx.html:1839` | 9 4-stop color palettes (`Obsidian`..`Void`) | Read-only source for `AXX Identity Accent` notch tokens |
| `Axx.normalizeSettings` / `identityForm20` | `1.AXX/Axx.html:1858,1873` | Persistent avatar settings (`form`, `palette`, `scale`, `keepForm`, `actionMorph`, `motionStyle`, `quality`, `reducedMotion`, `staticMode`, `alwaysOnTop`, `showLabel`, `shortcut`) | Preserve untouched; snapshot on dock, restore exact on undock |
| `Axx.Spring` | `1.AXX/Axx.html:1880` | Substepped (`1/120` s) spring physics (`value`, `velocity`, `stiffness`, `damping`, `step`, `reset`) | Reuse or mirror pattern for retargetable `NotchMotionController` |
| `Axx.AvatarMachine` | `1.AXX/Axx.html:1904` | Resolves `activity`, `conversation`, `lab`, `transient` states | Read-only projection input; never mutate identity |
| `Axx.createTimer` / `reconcileTimer` / `adjustTimer19` | `1.AXX/Axx.html:1932,1948,2025` | Single authoritative local timer/focus task (`App.store.data.timer`) | Golden Vertical Slice capability #1: observe & control without cloning timer |
| `Axx.ShapeTransition` / `LivingMotion` | `1.AXX/Axx.html:2230,2460` | Morph weights and living motion dynamics | Paused/suspended when `hidden === true` (`DOCKED`) |
| `Axx.CpuRaster` / `SoftwareRenderer` | `1.AXX/Axx.html:4846,4935` | CPU 3D mesh renderer (`112x72`, upgraded to `144x96` by `optical-glass.js`), `setHidden`, `hitTest`, `hitMask`, `materialTable`, `setReach` | Suspend draw when `DOCKED` settled; `setReach(null)` before docking; `hitMask` returns all-zero bits when `hidden` |
| `Axx.OrganicTendrils` | `1.AXX/Axx.html:5543` | Analytic CPU 3D swept-tube canvas (`tendrils.draw`, `fitTendrilLink`, `organicCurve`, `flowArmRadius`) | **INV-02 Gate:** Hard-gate `render`/`draw` when docked; clear canvas & buffers; zero links/roots/hit regions when `physicalMode === 'docked'` |
| `Axx.NativeBridge` | `1.AXX/Axx.html:6891` | IPC wrapper over `window.__TAURI__` (`native_status`, `window_action`, `set_timer`, `hit_map`, `desktop_layout`, `desktop_move_body`, `desktop_activity`, `backend_request`) | Extend with revisioned notch/window geometry & dock-mode IPC without breaking existing commands |
| `Axx.App` | `1.AXX/Axx.html:6940` | Owns `store`, `bridge`, `machine`, `renderer`, `updateHitMap()` (220 ms interval + event calls), `startTimer/pauseResume/cancelCurrent`, `tick()` (100 ms) | Wire `updateHitMap()` and `tick()` to `Axx.notch` projection & hit-region publishing |
| `Axx.Companion` | `1.AXX/Axx.html:7957` | Chat, voice, todos, `DockMachine` (`level 0..3`), `BrainClient`, `exportExtra`/`importExtra`/`clearExtra` | Projection source for chat/pending/todos; keep `DockMachine` free-mode compatible |
| `Axx.ReachHub` | `1.AXX/Axx.html:10026` | Resource tray, `ReachSequence` (`setReach`), drag-and-drop on `#avatar` and `#reach-tray` | Stop `ReachSequence` before docking; reuse file/app capability resolution in Portal |
| `Axx.OrganicDesk` | `1.AXX/Axx.html:12172` | `tendrils = new Axx.OrganicTendrils()`, pinned surfaces, `frame(dt)` calling `this.tendrils.draw(links, ...)` | **INV-02 Gate:** When docked/retracted, `links` must be empty and `tendrils.draw` must clear & skip draw |
| `Axx.FlowExperience` | `1.AXX/Axx.html:12930` | `delivery = new Axx.OrganicTendrils()`, `#flow-pill`/`#flow-sheet`/`#ink-review`, `frame(dt)` calling `this.delivery.draw(...)` | **INV-02 Gate:** Gate `delivery.draw` in `DOCKED`; `Stage` / `Intent` reuse tool catalog & review flows |
| `Axx.ActionDesk` | `1.AXX/Axx.html:13736` | Contextual actions (`music`, `screen`, `dictation`, `reader`, `timer`, `stopwatch`), `activities()` | Projection source for active running/paused background actions |
| `Axx.OrbitExperience` | `1.AXX/Axx.html:14414` | Free-mode radial fan around avatar | Suppressed in `DOCKED`; replaced by internal notch Orbit rail |
| `Axx.TimeStudio19` | `1.AXX/Axx.html:17498` | Extends `App.store.data.timer` with presets, routines, history | Reused directly by Notch Timer/Focus card |
| `Axx.HomeDock18` | `1.AXX/Axx.html:17351` | Saved corner home / `Alt+Shift+A` wake (overridden by `ResidentDesktop`) | Free-mode home preserved |
| `Axx.Stability20` | `1.AXX/Axx.html:18277` | 24-form identity UI, presets, `axx-studio-v2` persistence | Preserved untouched; read for snapshot |
| `Axx.ResidentDesktop` | `1.AXX/Axx.html:19219` | Native window geometry owner on desktop (`desktop_layout`, `desktop_move_body`, `desktop_activity`, `bindDrag`, `interactiveRegions`) | Extend drag gesture to detect top-edge `approach` band; delegate `DOCKED` layout/hit regions cleanly |
| `Axx.DesktopRuntime` | `1.AXX/Axx.html:19875` | Backend initialization, `/axx-api/identity` sync, `/axx-api/actions/execute`, `/axx-api/recipes` | Keep single authority for identity & backend readiness |
| `1.AXX/scripts/optical-glass.js` | External script | V7 volumetric SDF, `144x96` mesh, `Optical Glass` finish, hooks `OrganicTendrils` | **INV-02:** Must respect `tendrilsEnabled === false` when docked |
| `1.AXX/scripts/interface-theme.js` | External script | Light/dark themes (`axx.interface.theme`), custom colors, `--accent`, `--surface`, `--ink`, `--interface-font`, `--interface-scale` | Notch CSS consumes these CSS custom properties + avatar palette accent |
| `1.AXX/scripts/quick-reply.js` | External script | `#quick-actions`, `#quick-compose`, `#quick-reply`, `nativeVoice` integration | Projection source / reference for non-stealing focus (`open_panel` / `close_panel`) |
| `1.AXX/scripts/native-music.js` | External script | Bridges `system_media_status` / `system_media_control` (WinRT GSMTC + Core Audio peak) | Reused directly by Notch Media lens |
| `1.AXX/scripts/command-library.js` | External script | Typed command resolver/prepare/execute/cancel/reconcile over `/axx-api/commands/*` | Reused directly by Notch Intent & Approval Inbox |
| `1.AXX/scripts/magic-pen.js` | External script | Screen capture, annotation, spatial vision session (`/axx-api/pen/*`) | Reused by Notch Magic Lens |
| `1.AXX/scripts/transfer.js` | External script | Companion file transfers (`/axx-api/mobile/*`) | Reused by Notch Portal / Transfer Queue |
| `1.AXX/scripts/phase7-ui.js` | External script | Groups `#view-settings` controls into `#p7-windows`, `#p7-personal`, etc. | Mount Notch settings card cleanly in `#view-settings` |
| `src-tauri/src/resident.rs` | Rust host (754 lines) | `Geometry`, `WorkArea`, `constrained_origin`, `desktop_layout`, `desktop_move_body`, `desktop_activity`, `show_passive` (`SWP_NOACTIVATE`), `recover_display`, `persist`/`restore` (`native-window.json` v2), tray icon, `move_to_foreground_desktop` | Extend with revisioned geometry ack, top-edge monitor work-area clamp, fullscreen detection query, and tray/menu recovery for docked notch |
| `src-tauri/src/lib.rs` | Rust host (1693 lines) | `HostState`, `hit_map`, `start_cursor_hit_test_loop` (10ms cursor + `set_ignore_cursor_events`), `mouse_hook` (`WH_MOUSE_LL` synchronous `WS_EX_TRANSPARENT` toggle), `keyboard_hook` (`WH_KEYBOARD_LL`), `window_action`, `set_timer`, `backend_request` | Extend `hit_map` with `revision` / `epoch` validation, and optional `set_always_on_top` / fullscreen suppression policy without breaking existing click-through |
| `src-tauri/src/system_media.rs` | Rust host (291 lines) | WinRT GSMTC sessions + Core Audio `IAudioMeterInformation` peak | Already exposes `system_media_status` & `system_media_control` |
| `backend/server.py` & `backend/commands.py` | Python backend | Loopback HTTP API (`/axx-api/*`), `CommandService`, `ActionExecutor`, `ChatStore`, `IdentityStore`, `MobileHTTP`, `EvolutionHTTP` | No second runtime; reuse existing endpoints |

---

## 2. Protected Surfaces & Compatibility Constraints

1. **`mobile/design-baseline.json`:**
   - Protects SHA-256 hashes of `1.AXX/Axx.html#inline-styles`, `1.AXX/scripts/chat-workspace.css`, `1.AXX/scripts/interface-theme.css`, `1.AXX/scripts/transfer.css`, and mobile assets.
   - **Rule:** Do NOT edit any inline `<style>` block inside `1.AXX/Axx.html` or the protected CSS files. All notch styles MUST live in an isolated external stylesheet (`1.AXX/scripts/notch/notch.css`), and all notch scripts in `1.AXX/scripts/notch/`.
2. **`mobile/companion-contract.json` (`/v1`):**
   - Retain all 35+ `/v1/*` routes, payloads, and `snapshot_required` fields (`conversation_id`, `messages`, `appearance`, `pc_name`, `scopes`, `inference`).
3. **Existing `localStorage` & Native Preferences:**
   - `axx-studio-v2`, `axx.companion.v4`, `axx.windows11`, `axx.time19`, `axx.resident.panel-pos`, `native-window.json` (version 2) must remain 100% backward compatible. Notch preferences will use additive versioned key `axx.notch.v1` (with feature flag `enabled: false` by default during P0 hardening or opt-in toggle in Settings).

---

## 3. Capability Graph (Input → Resolve → Authorize → Execute → State/Receipt → Presentation)

1. **Timer / Focus (Golden Vertical Slice Candidate — `READY / LOCAL_VERIFIED`):**
   - `App.startTimer` / `TimeStudio19.startConfigured` → `App.store.data.timer` (`id`, `kind`, `status`, `durationMs`, `deadline`, `remainingMs`, `revision`) → `NativeBridge.timer()` (`set_timer` Rust thread emits `axx-timer-due`) → `App.tick()` reconciles and updates `ActionDesk` + `TimeStudio19` → **Notch Projection** (`ActivityProjection`: determinate `fraction = 1 - remaining / durationMs`, pause/resume/cancel real handlers).
2. **Typed Commands & Intent (`READY / BACKEND_VERIFIED`):**
   - Input → `/axx-api/commands/resolve` (`CommandService`) → `/axx-api/commands/prepare` (approval gate for `requires_approval`) → `/axx-api/commands/execute` (`ActionExecutor`) → receipt (`operation_id`, `state`, `postconditions_passed`, `output`, `evidence`) → `CommandLibrary` / Notch Intent & Approval Inbox.
3. **System Media (`READY / NATIVE_WINRT`):**
   - `NativeMusic` polls `system_media_status` (`system_media.rs` WinRT GSMTC) → dispatches `system_media_control` (`play`, `pause`, `next`, `previous`, `seek` gated by `canPlay`/`canPause`/`canNext`/`canPrevious`/`canSeek`) → Notch Media Lens.
4. **Chat & Quick Reply (`READY / LOCAL+BRIDGE`):**
   - `Companion.send` / `BrainClient.chat` → local `parseIntent` or `/axx-api/chat` / `ollama_realtime_chat` → `ChatStore` persisted messages & receipts → Notch Chat / Stage (`#panel` or dedicated workspace view sharing `Axx.chatWorkspace.active`).
5. **Voice / Dictation (`READY / NATIVE+WEB`):**
   - `NativeVoice` (`dictation_control`, `dictation.rs`) + `VoiceInk` (`#ink-review`) → editable review before commit → Notch Voice Studio.
6. **Magic Pen (`READY / NATIVE+BACKEND`):**
   - `MagicPen` (`magic_pen_capture`, `magic_pen_session`, `/axx-api/pen/*`) → Notch Magic Lens trigger + session continuity.
7. **Companion Transfers (`READY / TLS+BACKEND`):**
   - `Transfer` (`/axx-api/mobile/files/*`, `/axx-api/mobile/transfers/*`) → Notch Transfer Queue / Portal destination.
8. **Acts / Code Studio / Workspaces (`READY_IN_EVOLUTION3`):**
   - `Evolution3` (`/axx-api/agents/v1/*`, `/axx-api/code/v1/*`, `/axx-api/workspaces/v1/*`) → Agent Observatory & Stage.

---

## 4. Initial Baseline Run Status

*(In progress during Phase A: Cargo test + Companion validation + Node frontend tests + Pytest backend suite — results recorded in `EXECUTION-STATE.md` upon task completion.)*
