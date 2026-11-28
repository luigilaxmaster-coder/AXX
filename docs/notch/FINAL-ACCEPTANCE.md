# Obsidian — acta vigente de candidata, 2026-11-27

**Dictamen: candidata parcial revisable; NO aceptada para producción.** Flag opt-in apagado por defecto; sin versión nueva, instalación sobre producción, push ni publicación. Revisión propia, sin revisor independiente.

Evidencia: [diseño y arquitectura](OBSIDIAN-DESIGN-AND-DIRECT-CHAT.md), [ledger](EXECUTION-STATE.md), `build/obsidian/source-receipt.json` y los recibos privados referenciados abajo. Las capturas browser con `fixture` contienen cuotas/respuestas controladas; los saldos de la captura nativa proceden del runtime real de Codex.

| Gate | Estado actual | Evidencia o límite |
| --- | --- | --- |
| G00 Repository integrity | PARTIAL | Rama y cambios iniciales preservados, `git diff --check` PASS; árbol deliberadamente sin commit |
| G01 Original scope coverage | PARTIAL | Rediseño e incremento de chat; cartera completa original no cerrada |
| G02 Design system | PASS | Tokens, geometría central, preferencias normalizadas y capturas de variantes |
| G03 Signature visual identity | PARTIAL | Muñeco real implementado y capturado; aceptación subjetiva del propietario pendiente |
| G04 Optical quality | PARTIAL | Revisión propia de capturas; no todo el matrix físico/DPI |
| G05 Semantic composition | PASS | Vistas diferenciadas, Inicio completo, navegación y compositor; suite Obsidian |
| G06 Motion continuity | PARTIAL | Tests de springs, un reloj RAF, interrupción y reduced motion; medición perceptual física pendiente |
| G07 Docking | PARTIAL | Flujo programático probado; drag físico no certificado |
| G08 Zero tendrils | PASS | Core/UI/Phase II, captura del retrato sin llamadas a tentáculos, WebView2 suspendido y cero tentáculos |
| G09 Avatar preservation | PASS | Matriz 864, edición acoplada y restauración; offscreen portrait restaura su estado |
| G10 Real capability integration | PARTIAL | Codex real; Claude transporte controlado; Antigravity sin conexión |
| G11 Activity continuity | PASS | Estado y actividad sobreviven vistas, Stage y dock/undock en las suites |
| G12 Session continuity | PARTIAL | Mismo ID de Codex probado; borrador de compositor conservado en memoria; todos los escenarios de reinicio no certificados |
| G13 Native window behavior | PARTIAL | Host real, ACK y geometría; falta aceptación entre procesos |
| G14 Focus and input | PARTIAL | Escape/restauración y campos en browser; foco/hotkeys físicos pendientes |
| G15 Multimonitor | PARTIAL | Dos monitores enumerados; render capturado a 125%; sin drag físico entre ambos |
| G16 Accessibility | PARTIAL | Keyboard/forced colors/reduced motion y narrow layout; lector de pantalla físico no probado |
| G17 Privacy | PARTIAL | Curtain oculta compositor/respuesta; tokens quedan en proveedor, stdin y sin shell; auditoría integral no realizada |
| G18 Performance | PARTIAL | Muestra nativa UI ~0,37 ms y layout ~0,018 ms; no P95/P99 ni latencia física |
| G19 Memory stability | NOT_TESTED | Los ciclos sintéticos no sustituyen sesión larga del host |
| G20 Failure recovery | PARTIAL | Rechazo BUSY, pérdida tras admisión y GET de reconciliación sin duplicar POST; fallos externos exhaustivos pendientes |
| G21 Companion | PASS | Recibo final PASS: 15 contrato, 119 backend (1 omitido), 60 browser, 8 selector; sin cambiar baseline |
| G22 Regression | PASS | Regresión del alcance: JS, Connect 90 (1 omitido), Rust 45 (2 omitidos) y Companion PASS; las aceptaciones físicas permanecen separadas |
| G23 Advanced feature completion | PARTIAL | No se etiquetan todas las hipótesis de innovación como implementadas |
| G24 Visual review | PARTIAL | Capturas antes/después, tres exploraciones y revisión propia; falta aceptación del propietario |
| G25 Native acceptance | PARTIAL | WebView2 con backend fuente listo, chat habilitado, 16 conversaciones del proyecto y dos cuotas reales; no prueba física de dictado/envío |
| G26 Release candidate readiness | FAIL | Antigravity, Claude real y aceptación física pendientes; no publicar |

## Arranque de revisión

En la raíz: `powershell -ExecutionPolicy Bypass -File build/obsidian/Launch-Obsidian.ps1`.

El lanzador utiliza el config privado `com.axx.obsidian-candidate`, un perfil bajo `build/obsidian/native-profile` y el backend Python del checkout actual. Solo escucha su servidor de desarrollo en loopback. Puede recompilar la candidata; requiere las dependencias de desarrollo existentes. No usar el ejecutable debug directamente como sustituto del lanzador, ni redistribuir esta candidata como instalador.

La captura `native/native-obsidian.png` muestra la superficie real de Windows; los datos personales y runtime permanecen en `build/` y no deben publicarse. El atajo de restauración Ctrl+Alt+Espacio encontró una colisión del sistema en la candidata; la navegación por controles sigue disponible y esa colisión no se etiqueta como resuelta.

---

## Acta histórica Phase II (no certifica Obsidian)

# AXX Project Singularity — Phase II Final Acceptance & Quality Gates

- **Branch:** `feat/notch-singularity` (base `dd44ef2fe598ce593741a0c1ef92e30690e5474c`)
- **Opt-In Flag Default:** `axx.notch.v1` `enabled: false` (free 3D avatar behavior preserved intact)
- **Versions & Release Rule:** Desktop `0.23.5` and Android unchanged; no release published or pushed (`AGENTS.md` honored).

## Quality Gate Matrix (G0–G18)

| Gate | Requirement | Verdict | Verified Evidence / Scope Limit |
|---|---|---|---|
| G0 | Branch isolation & repository hygiene | `PASS` | `feat/notch-singularity` isolated; no version bump or credential leaks |
| G1 | Real source audit & design baseline lock | `PASS` | `validate_companion.py` passes `mobile/design-baseline.json` unchanged |
| G2 | Dual presentation, zero new parallel runtime (`INV-01`) | `PASS` | Shared `App`, `Companion`, `CommandLibrary`, `NativeMusic`, `NativeVoice`, `Transfer`, `Evolution3` |
| G3 | Zero tendrils when docked + renderer suspend (`INV-02`) | `PASS` | Verified in Playwright & live `Axx.exe` (`rendererSuspendedByNotch: true`, `tendrilVisible: false`) |
| G4 | Immutable `DockSnapshot` & docked edit preservation (`INV-03`) | `PASS` | `864×` matrix (`test-notch-core.cjs`) + docked `form/palette` edit survival (`test-notch-phase2.cjs`) |
| G5 | Vertical slice `FREE → APPROACH → RETRACTING → DOCKING → DOCKED → UNDOCKING → FREE` | `PASS` | End-to-end verified in `test-notch-ui.cjs` & `test-notch-phase2.cjs` |
| G6 | Adaptive Composition Engine 2.0 (`L0..L5`) | `PASS` | Distinct compositions inspected visually in `03`–`10` PNGs & live `native-window-expanded.png` |
| G7 | Approach Band & C0/C1 Motion | `PASS` | Trajectory-aware preview + `reducedMotion` instant snap verified |
| G8 | Native HWND click-through & cross-app non-steal (`INV-07`) | `PARTIAL` | Challenge tests (`5/5`), `allow_click_focus` & `hit_map` epoch guard verified on live `Axx.exe`; interactive `CopyFromScreen`/`GetCursorPos`/external-app mouse click **BLOCKED** in locked background WinSta0 session (`dictation` `--ignored` also failed at `GetForegroundWindow() == 0`) |
| G9 | Orbit 2.0 & Parallel 2.0 | `PASS` | Verified with timers, GSMTC media & agent projections |
| G10 | Portal 2.0 & Smart Shelf | `PASS` | Keyboard upload, individual removal, forwarding to Stage chat (`08-portal-shelf.png`) |
| G11 | Intent 2.0, Capability Passport & Safe Offline Queue | `PASS` | Live `Axx.exe` Intent view + `test-notch-phase2.cjs` Run 3 (`queuedAfterOffline: 1`, zero auto-replay) |
| G12 | Agent Observatory & DevPulse | `PASS` | `07-agent-observatory.png` + Approval Inbox explicit resolution |
| G13 | Stage 2.0 & Detachable Continuum | `PASS` | `09-stage-continuum.png`: shared session & attachments preserved across detach/reattach |
| G14 | P1/P2 Extensions (Media Panoramic, Voice, Resource Lens, Recall, Privacy) | `PASS` | Projections over real AXX controllers (`10-privacy-highcontrast.png`, `05-media-panoramic.png`) |
| G15 | Failure Injection & Corrupt Prefs Recovery | `PASS` | `test-notch-phase2.cjs` Runs 2–3 (`{broken_json`, offline queue, unplug fallback, stale `hit_map`, `Alt+Shift+N`) |
| G16 | Performance & Memory Baseline | `PASS` | Live `Axx.exe`: `48.96 MB`, `0.015 ms` layout, `0.144 ms` render; `500` cycles `0.9 ms`, `0 KB` heap delta |
| G17 | Accessibility (`forced-colors: active`, `reducedMotion`, keyboard) | `PASS` | `10-privacy-highcontrast.png` @150% DPI inspected visually |
| G18 | Visual Evidence Gallery + Regression + Companion Compatibility | `PASS` | `11` Playwright PNGs + live `PrintWindow` PNG + 10 JS suites + 45 Rust tests + Companion `15/119/60/8` OK |

## Pending Interactive Windows Desktop Checks (Blocked Only by Non-Interactive Session)
Before enabling `enabled: true` by default or scheduling any release build, perform in an unlocked interactive Windows 11 session:
1. Drag live 3D avatar slowly and quickly toward the top edge on `\\.\DISPLAY1` (`125%`) and `\\.\DISPLAY2` (`100%`) and confirm real desktop video capture (`CopyFromScreen` / Win11 Game Bar / OBS).
2. Click external desktop windows outside the notch pill to confirm live `WS_EX_TRANSPARENT` click-through and non-stealing focus return (`Alt+Tab` / Notepad / Explorer).
3. Physically trigger the Win32 system tray notch toggle menu item and live `Alt+Shift+N` global hotkey.
