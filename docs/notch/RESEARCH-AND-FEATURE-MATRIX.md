# AXX Project Singularity — Phase B Research & Feature Matrix

**Date:** 2026-11-27
**Primary Target:** Windows 11 (`Tauri 2.12.4`, `Win32`, `WebView2`, `Python` backend, `Android Companion /v1`)
**External Reference:** `JustKoal/Dynamic-releases` (public docs/releases/website only; no source code exposed — marked `OBSERVED` from public documentation, never claiming internal architecture).

---

## 1. Dynamic vs. AXX Capability Matrix

| ID | Group | Dynamic (Public Docs, 2026-11-27) | AXX Real Evidence (HEAD) | Parity & Decision | Priority |
|---|---|---|---|---|---|
| CMP-01 | Dock/Floating & Multi-monitor | Docked/floating pill, 4 compact styles, multi-monitor (`OBSERVED`) | `ResidentDesktop` (`Axx.html:19219`), `resident.rs` (`WorkArea`, negative coords + 1.5x DPI tests) | Extend `resident.rs` + `ResidentDesktop` for reversible FREE ↔ DOCKED | P0 |
| CMP-02 | Home & Activity Widgets | Persistent home + widget grid (`OBSERVED`) | `ActionDesk` (`Axx.html:13736`), `App.tick()`, `TimeStudio19` | Semantic adaptive composition (not permanent dashboard grid) | P1 |
| CMP-03 | Command Palette & Local Actions | Command launcher + favorites (`OBSERVED`) | `CommandLibrary` (`1.AXX/scripts/command-library.js`), `backend/commands.py` (`ADAPTERS`) | **AXX Intent** directly over `/axx-api/commands/resolve` & local intents | P1 |
| CMP-04 | Media & Audio Center | Cover/timeline & audio controls (`OBSERVED`) | `NativeMusic` (`1.AXX/scripts/native-music.js`), `system_media.rs` (WinRT GSMTC + Core Audio peak) | **Media Lens** reusing `NativeMusic` + real capability flags | P1 |
| CMP-05 | Voice & Editable Dictation | Local voice + editable dictation (`OBSERVED`) | `NativeVoice`, `dictation.rs`, `VoiceInk` (`#ink-review`) | **Voice Studio** reusing `NativeVoice` + `#ink-review` | P1 |
| CMP-06 | Timers & Tasks | Timers, alarms, notes (`OBSERVED`) | `App.store.data.timer`, `TimeStudio19`, `Companion.data.todos`, `App.store.data.notes` | **Golden Vertical Slice** target + Focus/Time lens | P1 |
| CMP-07 | Local File Sharing / Portal | File drop / QR local share (`OBSERVED`) | `ReachHub` (`Axx.html:10026`), `Transfer` (`transfer.js`), `Converter` (`converter.js`) | **Portal + Smart Shelf** over existing capabilities (no open LAN server) | P1/P2 |
| CMP-08 | Agent / Code Observatory | Claude Code / Codex hooks (`OBSERVED`) | `Evolution3` (`evolution3-runtime.js`), `/axx-api/agents/v1/*`, `/axx-api/code/v1/*` | **Agent Observatory** read-only over real Acts/Code Studio state | P2 |
| CMP-09 | Fullscreen Suppression | Auto-hide on fullscreen same monitor (`OBSERVED`) | `resident.rs` (`GetForegroundWindow` + monitor bounds extensible) | Per-monitor Win32 fullscreen policy without screen capture | P0 |
| CMP-10 | Companion Continuity | Companion deck/remote (`OBSERVED`) | `mobile/companion-contract.json` (`/v1/*`), `backend/mobile/http_api.py` | Keep `/v1` 100% intact; sync semantic activity state only | P2 |

---

## 2. Ten Differentiation Hypotheses (Evaluated)

| # | Hypothesis | Problem Solved | Real AXX Source | Decision & Kill Criterion |
|---|---|---|---|---|
| H01 | **Approval Inbox** | Pending approvals (`commands/prepare`, `learning/prepare`, `acts`) hidden across panels | `CommandLibrary.operation`, `Evolution3` | **ADOPT (P1):** Surface pending approvals cleanly with exact parameters & explicit Approve/Cancel buttons. Never auto-approve. |
| H02 | **Receipt Lens** | Users unsure if a command succeeded or failed | `CommandLibrary.lastOperation` (`postconditions_passed`, `evidence`) | **ADOPT (P1):** Show verified receipt summary & copy/open artifact action. |
| H03 | **Capability Passport** | Users try unavailable actions without knowing why | `/axx-api/feature-readiness`, `NativeMusic` capability flags, `BrainClient.connected` | **ADOPT (P1):** Inline badge explaining real status (`Disponible`, `Requiere modelo`, `Sin permiso`). |
| H04 | **Session Pin** | Switching active tasks causes layout jitter | `NotchLayoutResolver` + `pinnedActivityId` | **ADOPT (P1):** Pin a primary activity to the leading lane without stopping background ones. |
| H05 | **Context Freeze** | Switching windows changes suggested context mid-task | Explicit `contextFreeze` toggle in Intent/Stage | **ADOPT (P2):** Freeze selected context token until released. |
| H06 | **Transfer Queue Preview** | Dropping files risks unintended sends | `Transfer` (`/axx-api/mobile/*`) + `Portal` | **ADOPT (P1):** Show file name, size, MIME, and explicit destination choice before dispatch. |
| H07 | **Focus Return** | Opening Intent/Chat leaves focus trapped in overlay | `resident.rs` (`GetForegroundWindow` / `SetForegroundWindow`) | **ADOPT (P1):** Record prior HWND on explicit focus; restore on `Esc`/close only if valid and user didn't switch apps. |
| H08 | **Safe Offline Queue** | Backend disconnect drops user drafts | `Companion` drafts + `localStorage` | **ADOPT (P1):** Preserve drafts & show offline capability state; never auto-replay uncertain side effects. |
| H09 | **Visual Privacy Curtain** | Sensitive titles/snippets visible during calls | `VisibilityPolicy.privacySuppressed` + shortcut | **ADOPT (P1):** Redact titles/snippets in notch UI while keeping state & controls active. |
| H10 | **Performance Adaptive Surface** | Continuous 60Hz rendering on battery/hidden | `SoftwareRenderer.setHidden(true)` + reduced tick rate when `compact/idle` | **ADOPT (P0/P1):** Suspend 3D CPU mesh rasterization while settled in `DOCKED`; keep timer/backend alive. |
