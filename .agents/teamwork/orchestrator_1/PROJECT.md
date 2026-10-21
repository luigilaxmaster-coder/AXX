# Project: Axx Desktop Application Restoration

## Architecture
- **Desktop Host**: Tauri v2 (`src-tauri/`) hosting WebView2 on Windows 11 with transparent, borderless window configuration, custom hit-testing cursor thread (`set_ignore_cursor_events`), and Win32 interop (`resident.rs`).
- **Frontend Resident**: Monolithic web resident (`1.AXX/Axx.html` + helper scripts in `1.AXX/scripts/`) rendering a liquid organic 3D dark-chrome iridescent avatar (Three.js/WebGL), radial tools launcher (`#flow-fan`), organic tentacle tendrils (`OrganicTendrils`), and movable floating panels.
- **Backend Services**: Local Python service (`backend/server.py`, `backend/actions/tools.py`, `backend/speech/offline_asr.py`) providing offline speech-to-text (faster-whisper), LLM routing (local Ollama on port 11434 / fallback), and secure file actions confined to `%LOCALAPPDATA%\Axx\artifacts`.
- **Approved Visual Reference**: `reference/Axx_reference_v20.html` (24 liquid shapes, 9 iridescent palettes, liquid chrome styling, organic tentacles, radial tool fan).

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Transparent Window Hit-Testing | Fix 30ms polling vs 220ms hit-map desync, include `#avatar` in interactive regions, fix multi-monitor DPI scaling | M1 | Survey (R1, R2, R4) |
| 2 | Avatar Click & Drag Unblocking | Remove `event.detail > 0` destructive click cancellation; adjust alpha threshold in `hitTest`; restore fluid avatar tap & drag | M1 | Survey (R1, R2) |
| 3 | Radial Menu Fan Navigation | Fix `FlowDock.tap()` and `ResidentDesktop.tap()` to transition directly to `step = 2` (radial fan `#flow-fan`), remove `pointer-events: none !important`, fix `#flow-sheet` event swallowing | M1 | Survey (R1, R2) |
| 4 | Independent Movable Panels | Decouple panel dragging from Win32 message flooding; throttle `desktop_layout` IPC to 60 FPS; fix `record_move` anchor drift; ensure dragging never moves Axx or other panels | M2 | Survey (R1, R3) |
| 5 | Panel Resizing & Bounds Recovery | Add interactive resize handles, minimum dimensions (320x400), multi-monitor bounds recovery, and "Reset Layout" action | M2 | Survey (R1, R3) |
| 6 | Position & Size Persistence | Persist panel `(x, y, w, h)` in `localStorage` without writing to disk on every frame | M2 | Survey (R1, R3) |
| 7 | Tentacle Tube Clipping Resolution | Increase native HWND margin from 12px to 72px or dynamic envelope matching 104-170px Bezier curves; fix clipping at OS frame | M2 | Survey (R1, R4) |
| 8 | Conversation Pipeline | End-to-end chat flow from input to model response, clear execution status, and visible tool outcomes | M3 | Survey (R1, R6) |
| 9 | Command Execution | System commands execution with observable results, error boundaries, and no decorative-only text | M3 | Survey (R1, R6) |
| 10 | Voice & Dictation (Offline ASR) | Fix model search path for `faster-whisper-tiny` in `resources/models/`; handle mic lifecycle and cancellation cleanly | M4 | Survey (R1, R6) |
| 11 | Translation Engine | Bidirectional translation with source/target preservation, language switcher, and copy action | M4 | Survey (R1, R6) |
| 12 | Screen & Audio Recording | Implement native screen/audio capture (avoiding unsupported `getDisplayMedia` in WebView2); generate real playable media in `evidence/` | M5 | Survey (R1, R6) |
| 13 | Precision Stopwatch / Timer | Exact real-time timer independent of CSS animations; background sound/visual notification on completion | M5 | Survey (R1, R6) |
| 14 | Music Playback Integration | Honest music state (not configured / local audio player / Spotify); real audio playback controls without fake animation | M5 | Survey (R1, R6) |
| 15 | File Explorer & Safe Actions | Safe file browsing with read-only protection for Desktop/Documents; write operations strictly in dedicated test folders | M6 | Survey (R1, R6) |
| 16 | Settings & Persistence | Register missing IPC commands (`request_notifications`, `set_autostart`); persist settings in `%LOCALAPPDATA%\Axx\`; reset defaults button | M6 | Survey (R1, R6) |
| 17 | Visual Polish & v20 Parity | Apply approved liquid dark chrome aesthetic (`reference/Axx_reference_v20.html`), iridescent shaders, micro-tooltips, clean surfaces | M7 | Survey (R2, R5) |
| 18 | Accessibility & Reduced Motion | Static tentacles and halted animations under `prefers-reduced-motion`; keyboard focus indicators; contrast check; emergency stop | M7 | Survey (R4, R7) |
| 19 | Zombie Process Cleanup & Management | Terminate 22 orphan `mcp_server.py` processes; attach child processes to Windows Job Object (`KILL_ON_JOB_CLOSE`) | M1 / M6 | Survey (R1, R7) |
| 20 | Comprehensive E2E Verification | Complete 4-tier test suite + Tier 5 adversarial stress testing; screenshots, video recording, and reversion guide in `evidence/` | M8 | Survey (R8) |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Window, Hit-Testing & Radial Interaction | Tauri cursor loop synchronization, `#avatar` in interactive regions, click suppression removal, avatar tap/drag, radial menu `#flow-fan` launch, zombie process termination | none | DONE |
| M2 | Floating Panels & Tentacle Dynamics | Panel drag decoupling (60 FPS rAF), resize handles, position/size persistence, window HWND margin expansion to 72px (no tentacle clipping), desktop reset | M1 | DONE |
| M3 | Conversation & Commands Engine | End-to-end chat input/output, tool calling integration, command execution feedback, error state notifications | M2 | IN_PROGRESS |
| M4 | Voice, Dictation & Translation | Offline ASR model path fix, mic lifecycle (listen, process, cancel), translation panel with dual-text preservation | M2 | PLANNED |
| M5 | Media Tools: Recorder, Timer & Music | Native screen/audio recording to `evidence/`, drift-free timer with alarms, local audio player / honest music status | M2 | PLANNED |
| M6 | File System, Settings & Process Isolation | Read-only safety guardrails for user files, test folder confinement, settings persistence, missing IPC handlers (`set_autostart`, `request_notifications`), Job Object isolation | M2 | PLANNED |
| M7 | Design System, Visual Polish & Accessibility | Alignment with `reference/Axx_reference_v20.html`, micro-tooltips, reduced motion mode (static tentacles), keyboard navigation, emergency stop | M3, M4, M5, M6 | PLANNED |
| M8 | E2E Testing, Adversarial Hardening & Evidence | 4-Tier test suite execution, Tier 5 adversarial validation, evidence compilation (screenshots, video, audit logs) | M7 | PLANNED |

---

## Interface Contracts

### 1. Frontend ↔ Tauri IPC (`src-tauri/src/lib.rs`)
- `hit_map(regions: Vec<InteractiveRegion>, mask: Option<AvatarMask>) -> Result<(), String>`
  - Dispatched immediately on panel open/close/move.
  - `InteractiveRegion`: `{ id: String, x: f64, y: f64, width: f64, height: f64 }`
  - Scale factor corrected for active monitor.
- `desktop_layout(layout: ResidentLayout) -> Result<(), String>`
  - Throttled to 60 FPS via `requestAnimationFrame`.
  - Mutates Win32 window position with margin buffer (72px) without triggering asynchronous anchor drift.
- `set_autostart(enabled: bool) -> Result<(), String>`
  - Handles autostart preference gracefully.
- `request_notifications() -> Result<bool, String>`
  - Handles notification permissions without throwing unhandled promise rejections.

### 2. Frontend ↔ Python Backend (`backend/server.py`)
- `POST /axx-api/speech/transcribe`: Audio payload -> `{ text: String, language: String, status: "success" | "error" }`
- `POST /axx-api/translate`: `{ text: String, source_lang: String, target_lang: String }` -> `{ translation: String, status: "success" }`
- `GET /axx-api/spotify/status`: -> `{ status: "not_configured" | "ready", current_track: null }`
- `POST /axx-api/actions/execute`: Confined to test directory and `%LOCALAPPDATA%\Axx\artifacts`.

### 3. Panel Dragging & Geometry Contract
- Dragging header: emits local CSS `transform: translate3d(...)` during pointermove.
- Drag release (`pointerup`): calculates final bounding box and updates Tauri window bounds once.
- Minimum panel dimensions: `320px` width, `400px` height.
- Bounding box margin: minimum `72px` around avatar and panels to prevent clipping of Bezier tentacle tubes.

---

## Code Layout & Write Boundaries

- `1.AXX/Axx.html`: Master web resident (DOM, Three.js shaders, radial tools, panel layouts).
- `1.AXX/scripts/`: Helper scripts (`native-voice.js`, `command-library.js`).
- `src-tauri/src/lib.rs`: Tauri command registration, window hit-test loop, IPC handlers.
- `src-tauri/src/resident.rs`: Win32 resident desktop window management, layout calculations.
- `backend/speech/offline_asr.py`: Offline Whisper speech recognition service.
- `backend/server.py`: Local backend server.
- `backend/actions/tools.py`: File & system tools.
- `evidence/`: Artifacts destination (screenshots, video recordings, test logs, reversion guide).
- **Protected Areas (Strict Read-Only / Do Not Touch)**:
  - `evidence/axx-connect/`, `plugins/` (Axx Connect).
  - User desktop/documents (`Desktop/`, `Documents/`).
