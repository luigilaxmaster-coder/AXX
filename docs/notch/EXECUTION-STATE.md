# Incremento 2026-11-28 · suscripciones, música y tamaño

Base revisada: `07c6880`; rama `codex/notch-provider-polish`. Se conservan los cambios publicados previamente por Antigravity. Contratos, fuentes, límites y ejecución: [SUBSCRIPTIONS-AND-COMPACT-POLISH.md](SUBSCRIPTIONS-AND-COMPACT-POLISH.md).

Este incremento añade monitor de planes por cliente, dos herramientas de consulta, puente statusLine, reproducción local pausada/reanudable, selección completa de sesiones y tamaño separado de panel/barra. No cambia 0.23.5 ni sustituye su instalador publicado. La instalación y aceptación nativa de este incremento no se afirman como realizadas.

La revisión de fuente usa suites Core/UI/Phase II/Obsidian, backend Connect y Companion. Capturas privadas: `build/obsidian-rework/after`; recibo de compatibilidad: `build/subscription-polish/companion-validation.json`. Los planes y cuotas de las capturas browser son fixtures.

Validación de este incremento: Core/UI/Phase II/Obsidian PASS; 101 pruebas Connect (1 omitida), 78 URLs de assets, `git diff --check` y compatibilidad Companion PASS (15 contrato, renderer, 119 backend móvil con 1 omitida, 60 navegador y 8 selector). Sin aceptación física nueva ni instalación de este incremento.

---

# Project Obsidian — estado vigente (2026-11-27)

- Rama: `feat/notch-singularity`; base `dd44ef2fe598ce593741a0c1ef92e30690e5474c`. Se preservó el trabajo local previo. No hay commit, push, incremento de versión, instalador ni publicación nuevos.
- Implementado: identidad con el muñeco real, sistema visual grafito, navegación simplificada, perfiles de apariencia, ajustes en vivo, reloj de movimiento único, revelación de contenido, compositor directo, selección proyecto/conversación, cuotas verificables y recuperación de envío incierto.
- Codex: descubrimiento y cuotas reales; respuesta real `AXX_NOTCH_SESSION_OK` en sesión efímera sin herramientas y con el mismo ID. No se escribió en conversaciones ajenas de trabajo para probar.
- Claude Code: CLI 2.1.111, login `claude.ai` y conversaciones locales detectadas; transporte dentro del lifecycle existente y pruebas controladas. Falta inferencia real y cuota expuesta por esta versión.
- Antigravity: conexión CLI/ACP ausente; se solicitó al propietario la ruta de `agy`. Envío bloqueado, sin simulación ni redirección.
- Candidata: `build/obsidian/Launch-Obsidian.ps1`, perfil privado `build/obsidian/native-profile/com.axx.obsidian-candidate/Axx`. Usa el backend Python actual con `AXX_DEV_SOURCE_BACKEND=1`, que solo funciona en debug; evita validar por accidente un backend empaquetado antiguo. No reemplaza el perfil instalado.

## Evidencia del incremento

- `node 1.AXX/scripts/test-static-assets.cjs`: PASS, 77 URLs.
- `node 1.AXX/scripts/notch/test-notch-core.cjs`: PASS, estados/interrupciones/500 ciclos y matriz de identidad 864.
- `node 1.AXX/scripts/notch/test-notch-ui.cjs`: PASS, incluida expansión sin doble clic, timer real local, aprobación, archivos, privacidad y restauración.
- `node 1.AXX/scripts/notch/test-notch-phase2.cjs`: PASS, 11 capturas, fallo inyectado, Stage y estilos accesibles.
- `node 1.AXX/scripts/notch/test-notch-obsidian.cjs`: PASS, retrato real sin llamadas a tentáculos, perfiles, foco, tres exploraciones sobre el mismo Inicio, 13 comprobaciones de layout, envío una vez, rechazo BUSY, desconexión tras admisión y reconciliación GET sin otro POST.
- `python -m unittest backend.connect.tests.test_desktop_sessions backend.connect.tests.test_provider backend.connect.tests.test_http -q`: PASS, 90 tests, 1 omitido existente.
- `node scripts/test-optical-glass.cjs`, `test-tendril-geometry.cjs`, `test-quick-reply.cjs`: PASS.
- `python scripts/validate_companion.py --output build/obsidian/companion-validation.json`: PASS, contrato 15, backend 119 (1 omitido), navegador 60, selector de archivo 8. Baseline protegido sin regenerar.
- `cargo build --manifest-path src-tauri/Cargo.toml --no-default-features`: PASS. Pruebas Rust finales: PASS, 45 aprobadas y 2 omitidas existentes (30 lib + 4 ancla + 6 cursor + 5 click-through).
- `build/obsidian/native/native-report-expanded.json`: Tauri/WebView2 real, backend actual listo, DPI 125%, dos monitores enumerados, renderer suspendido, cero tentáculos, ACK obsoleto rechazado; compositor habilitado, 16 conversaciones del proyecto seleccionado y dos ventanas reales de cuota. Promedio de la muestra: layout ~0,018 ms, UI ~0,37 ms; no son P95/P99 ni medida de latencia física.
- `build/obsidian/live-session-probe.json`: PASS real; `live-readonly.json`: consulta real sin inferencia. Las capturas con sufijo `fixture` usan respuestas/saldos de prueba y están identificadas como tales.
- `git diff --check`: PASS. Huellas locales: `build/obsidian/source-receipt.json`.

## Fallos encontrados y resolución

1. Reemplazar el SVG del botón durante `click` hacía que el listener de cabecera perdiera el ancestro y alternase dos veces. Corregido con `composedPath`; suite UI repetida y aprobada.
2. Una aprobación resuelta retenía el botón por el bloqueo de foco. Se separó el host de aprobación del compositor y se ajustó el bloqueo a campos editables.
3. El primer arranque nativo agotó los 60 s mientras compilaba. Se compiló la candidata y se amplió el plazo del harness; los arranques posteriores aportan backend listo y captura nativa.
4. El experimento con hilo efímero mostró que `thread/resume` no encuentra un rollout persistido. Un hilo efímero ya cargado continúa directamente; el segundo experimento real pasó.
5. Una prueba espacial de Connect agotó su espera bajo carga; pasó sola y luego en la suite completa de 90.
6. La primera regresión Companion tuvo un timeout de navegación en una variante legacy. El caso pasó por separado; la repetición completa pasó sin ampliar timeouts ni modificar el baseline.
7. El primer test de la CLI detectó un cierre doble en el double de stdin. Se hizo idempotente el double y se repitió la suite.
8. La primera ejecución de Rust final encontró el binario de la propia candidata abierto y bloqueado por Windows. Se cerró únicamente ese proceso privado verificado y la repetición pasó (45 tests, 2 omitidos).
9. La reconciliación quedaba deshabilitada por el refresh de controles. Se modeló explícitamente su estado; la prueba con pérdida después de admisión pasó sin un segundo envío.
10. Abrir el compositor antes de que termine el arranque del backend podía dejar un error inicial hasta pulsar Actualizar. El evento nativo de backend listo ahora recarga únicamente metadatos; su prueba confirma recuperación sin enviar el borrador.

## Límites y siguiente cierre concreto

No hay aceptación física de micrófono, clics entre procesos, arrastre multimonitor ni sesión larga. El estado ocupado de Codex es el informado por su transporte; la escritura simultánea desde varios procesos al mismo hilo requiere una prueba específica y no está certificada.

Siguiente dependencia: aportar/conectar la CLI/ACP de Antigravity y validar sus contratos reales; después probar Claude Code con una conversación de prueba autorizada, validar exposición real de su cuota y completar la aceptación física. No habilitar por defecto ni publicar por inferencia.

Especificación técnica: [OBSIDIAN-DESIGN-AND-DIRECT-CHAT.md](OBSIDIAN-DESIGN-AND-DIRECT-CHAT.md).

---

## Registro histórico Phase II (anterior a Obsidian)

# AXX Project Singularity — Phase II Execution State Ledger

- **Branch:** `feat/notch-singularity`
- **Base SHA:** `dd44ef2fe598ce593741a0c1ef92e30690e5474c`
- **Status:** Phase II Implementation, Visual Verification Lab, Failure Injection, Isolated Win32/WebView2 Audit, and Regression Suite Complete (Unpacked Candidate; Not Version-Bumped or Released)
- **Last Updated:** 2026-11-27

## Key Modules Added / Upgraded in Phase II
- `1.AXX/scripts/notch/notch-layout.js` (Adaptive Composition Engine 2.0, `L0..L5`, trajectory-aware approach band)
- `1.AXX/scripts/notch/notch-state.js` (`resources`, `recall`, `agents`, `contextFrozen`, `stageDetached`, `explicitIdentityEditRevision`)
- `1.AXX/scripts/notch/notch-snapshot.js` (Sensitivity, dwell, density, motion intensity, suspend toggle, safe corrupt JSON fallback)
- `1.AXX/scripts/notch/notch-projections.js` (WinRT `time`/`duration`/`canSeek`/`peak`/`sessions`, Agent Observatory, DevPulse, Recall, Telemetry)
- `1.AXX/scripts/notch/notch-ui.js` & `1.AXX/scripts/notch/notch.css` (Distinct activity layouts, fixed footer navigation, Stage Continuum chrome, `forced-colors: active` rules)
- `1.AXX/scripts/notch/notch-coordinator.js` (Renderer suspension on settle, live metrics, Safe Offline Queue, Focus Return params, `Alt+Shift+N` hidden recovery, dropped ACK tracking)
- `1.AXX/scripts/notch/test-notch-phase2.cjs` (Visual gallery + 150% DPI + `forced-colors` + `reducedMotion` + 50/500 cycle stress + Failure Injection suite)
- `src-tauri/src/resident.rs` & `src-tauri/src/lib.rs` (`primary`/`active` monitor resolution, `allow_click_focus`, `hit_map` epoch validation, global `Alt+Shift+N`)

## Final Verified Suite Outputs (Post Final Edit)
- `node 1.AXX/scripts/test-static-assets.cjs`: PASS (`76` URLs)
- `node 1.AXX/scripts/notch/test-notch-core.cjs`: PASS
- `node 1.AXX/scripts/notch/test-notch-ui.cjs`: PASS
- `node 1.AXX/scripts/notch/test-notch-phase2.cjs`: PASS (`11` PNGs, `stress50CyclesMs: 22`, `cycles500Ms: 0.9`, `heapDeltaKb: 0`, `avgLayoutMs: 0.002`, `avgRenderMs: 0.018`, Failure Injection all green)
- `node scripts/test-tendril-geometry.cjs`: PASS
- `node scripts/test-optical-glass.cjs`: PASS
- `node scripts/test-quick-reply.cjs`: PASS
- `node 1.AXX/scripts/test-window-content.cjs`: PASS
- `node 1.AXX/scripts/test-command-library.cjs`: PASS (`34 passed, uncaught: []`)
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: PASS (`42 passed, uncaught: []`)
- `cargo test --manifest-path src-tauri/Cargo.toml`: PASS (`30` lib passed + `2` ignored, `4` `anchor_stability`, `6` `cursor_throttling`, `5` `transparent_clickthrough` = `45` passed)
- `python scripts/validate_companion.py --output build/companion-validation.json`: PASS (`contract: 15`, `backend_tests: 119 / skipped=1`, `browser_tests: 60`, `desktop file selector: 8`)

## Isolated Native Windows Audit Evidence (`build/notch-evidence/native/`)
- Binary: `src-tauri/target/debug/Axx.exe` (`com.axx.singularity-candidate`, isolated `build/native-isolated-appdata`, port `47831`)
- Audited Win32 HWND (`pid: 2612`): `visible: true`, `wsExTopmost: true`, `dpi: 120` (`1.25x`), `rect: 1920x1020`, `workingSetMb: 48.96`
- Captured real WebView2 surface (`PrintWindow`): `build/notch-evidence/native/native-window-expanded.png`
- Detected monitors via Rust `notch_monitors`: `\\.\DISPLAY1` (`1536×816 @1.25x`) & `\\.\DISPLAY2` (`1920×1032 @1.0x`)
- Verified live `hit_map` epoch guard: `epoch: 0 -> { accepted: false, epoch: 1, revision: 7 }`
- Verified OS-level background session limits explicitly documented in `FINAL-ACCEPTANCE.md` (`CopyFromScreen` & `GetCursorPos` return invalid handle/0 when WinSta0 interactive desktop is locked).
