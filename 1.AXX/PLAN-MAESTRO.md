# Axx Desktop · Plan maestro de implementación

> Este es un plan para implementar; las rutas NUEVAS y tests nombrados todavía deben crearse. No son funciones disponibles por incluirse en este documento.

**Objetivo:** convertir Axx20 en aplicación real de Windows sin perder identidad, herramientas ni datos.
**Arquitectura:** Tauri2/Rust como runtime; UI TypeScript existente; IPC tipado; SQLite y adaptadores Windows; procesos ASR/encoder aislables.
**Spec:** ../docs/01-REQUISITOS.md y ../docs/03-ARQUITECTURA.md.

## Restricciones globales

- Conservar 24 IDs de forma, nueve paletas, configuración manual y catálogo radial.
- No reducir calidad silenciosamente ni simular ASR/servicios en producción.
- Una autoridad por ajustes/tarea/micrófono; no Node obligatorio en release.
- Sin elevación por defecto, secretos en frontend ni shell libre para LLM.
- Probar en Windows lo que se anuncia como integración de Windows.

## Riesgos transversales que deben aparecer en tests

Cambio de foco/DPI; permiso tardío tras cancelación; reinicio entre transacciones; datos importados inválidos; recursos de audio o captura abiertos después de salir.

## Orden

M0 → M1 → M2 → M3 → M4 → M5. M6 manos libres se habilita después de evaluar sus riesgos; no bloquea un release que lo anuncie como pendiente. Dentro de cada milestone respetar las dependencias. T24 es opcional para M5.

## T00 · M0 · Congelar y reproducir Axx20

**Depende de:** ninguna. **Requisitos:** R01, R36.

**Archivos:**
- Revisar/modificar existente: `package.json`.
- Revisar/modificar existente: `package-lock.json`.
- Revisar/modificar existente: `scripts/build.cjs`.
- NUEVA PROPUESTA: `evidence/baseline/manifest.json`.

**Interfaz/entregable:** `BaselineManifest { archiveSha256, htmlSha256, commands, toolVersions, exitCodes }`.

- [ ] Escribir primero el caso `baseline_original_hash_and_all_tests`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T00/red.log`.
- [ ] Implementar: Auditoría de SOURCE-INVENTORY; build sin modificar fuentes; salida completa de npm test.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** El mismo origen produce HTML reproducible; no se cuentan tests de documentación como tests del producto.

## T01 · M0 · Contratos y puertos tipados

**Depende de:** T00. **Requisitos:** R31, R32.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src/ports/runtime.ts`.
- NUEVA PROPUESTA: `src/ports/settings.ts`.
- NUEVA PROPUESTA: `src/ports/commands.ts`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/contracts.rs`.

**Interfaz/entregable:** `CommandEnvelope / RuntimeEvent / SettingsSnapshot / CapabilityDescriptor`.

- [ ] Escribir primero el caso `command_rejects_expired_unknown_and_duplicate`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T01/red.log`.
- [ ] Implementar: Copiar contratos aceptados y generar DTO TS/Rust; validadores estrictos; origen decidido por transporte.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Payload desconocido, expirado o con origen falsificado se rechaza antes de ejecutar.

## T02 · M1 · Shell Tauri e instancia única

**Depende de:** T01. **Requisitos:** R06, R09, R34.

**Archivos:**
- Revisar/modificar existente: `scripts/build.cjs`.
- Revisar/modificar existente: `package.json`.
- NUEVA PROPUESTA: `src-tauri/Cargo.toml`.
- NUEVA PROPUESTA: `src-tauri/tauri.conf.json`.
- NUEVA PROPUESTA: `src-tauri/src/lib.rs`.
- NUEVA PROPUESTA: `src-tauri/capabilities/main.json`.

**Interfaz/entregable:** `DesktopShell.start() / show() / request_exit()`.

- [ ] Escribir primero el caso `second_instance_signals_first_and_exits`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T02/red.log`.
- [ ] Implementar: Crear host con dist existente, bandeja, cierre/ocultar y error recuperable; sin permisos amplios de shell.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Dos lanzamientos dejan una instancia; cerrar panel no termina tareas; salir libera recursos.

## T03 · M1 · Ventanas e input selectivo

**Depende de:** T02. **Requisitos:** R09, R10, R11, R35.

**Archivos:**
- Revisar/modificar existente: `src/ui/action-windows.ts`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/overlay.rs`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/input_regions.rs`.
- NUEVA PROPUESTA: `tests/windows/overlay.md`.

**Interfaz/entregable:** `WindowPort.publish_regions(frameId, bounds, dpi, regions) / move_panel(panelId, desiredBounds)`.

- [ ] Escribir primero el caso `outside_avatar_clicks_reach_underlying_window`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T03/red.log`.
- [ ] Implementar: Implementar ventanas visuales pass-through y proxy/región de input; ensayo físico antes de consolidar.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** 100 puntos fuera no bloquean apps; dentro funciona primer clic, drag y foco; brillo no se recorta.

## T04 · M1 · Atajos globales y monitor de origen

**Depende de:** T03. **Requisitos:** R06, R07, R08, R10.

**Archivos:**
- Revisar/modificar existente: `src/ui/home18.ts`.
- Revisar/modificar existente: `src/ui/companion.ts`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/hotkeys.rs`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/monitors.rs`.

**Interfaz/entregable:** `Presence.summon(CursorSnapshot) / return_home() / stop_follow()`.

- [ ] Escribir primero el caso `double_a_returns_home_without_mutating_base`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T04/red.log`.
- [ ] Implementar: Registrar Alt+Shift+A, doble A sin autorepeat, Escape solo durante follow, monitor físico y DPI.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Desde Bloc de notas, una A llama; dos devuelven; Esc no cancela timer y no se secuestra fuera de follow.

## T05 · M2 · SQLite y migración de datos

**Depende de:** T01, T02. **Requisitos:** R01, R02, R11, R31.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src-tauri/src/storage/mod.rs`.
- NUEVA PROPUESTA: `src-tauri/src/storage/settings.rs`.
- NUEVA PROPUESTA: `src-tauri/migrations/0001.sql`.

**Interfaz/entregable:** `SettingsStore.snapshot() / patch(expectedRevision, patch) / import_preview(bytes)`.

- [ ] Escribir primero el caso `settings_conflict_rejected_and_restart_restores_identity`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T05/red.log`.
- [ ] Implementar: Transacciones versionadas, import preview/apply de Axx20 y backup coherente; secretos separados.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Proceso nuevo restaura exactamente revisión; import duplicado no duplica notas; disco lleno no pierde anterior.

## T06 · M2 · Conectar UI a preferencias nativas

**Depende de:** T05, T04. **Requisitos:** R01, R02, R04, R05, R06, R11, R12.

**Archivos:**
- Revisar/modificar existente: `src/ui/app.ts`.
- Revisar/modificar existente: `src/ui/experience.ts`.
- Revisar/modificar existente: `src/ui/stability20.ts`.
- Revisar/modificar existente: `src/ui/orbit12.ts`.
- NUEVA PROPUESTA: `src/adapters/native/settings.ts`.

**Interfaz/entregable:** `IdentitySnapshot → renderer; LayoutDesired → WindowPort; PreviewSession local`.

- [ ] Escribir primero el caso `task_states_do_not_overwrite_saved_form`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T06/red.log`.
- [ ] Implementar: Sustituir autoridad localStorage por SettingsPort sin cambiar nodos ni IDs; mantener borradores/preview.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Música/focus/success no cambian forma guardada; regreso oculta herramientas; tamaños sobreviven reinicio.

## T07 · M2 · Aislar renderer y perf sin degradación

**Depende de:** T06. **Requisitos:** R03, R04, R29, R33.

**Archivos:**
- Revisar/modificar existente: `src/render/software-core.ts`.
- Revisar/modificar existente: `src/render/software-renderer.ts`.
- NUEVA PROPUESTA: `src/render/worker-entry.ts`.
- NUEVA PROPUESTA: `tests/perf/render-equivalence.ts`.

**Interfaz/entregable:** `RenderRequest(snapshot, frameId) → FrameResult(bitmap, regions, timing)`.

- [ ] Escribir primero el caso `worker_reference_rgba_and_input_p95`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T07/red.log`.
- [ ] Implementar: Cache/buffers y worker feature-detected; conservar fallback y calidad fijada; no introducir PNG de avatar.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Fotograma equivalente conserva RGBA para optimización exacta; UI no espera raster para procesar clic.

## T08 · M2 · TaskRegistry y dispatcher nativo

**Depende de:** T01, T05. **Requisitos:** R14, R15, R32.

**Archivos:**
- Revisar/modificar existente: `src/ui/action11.ts`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/tasks.rs`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/dispatcher.rs`.
- NUEVA PROPUESTA: `src/adapters/native/commands.ts`.

**Interfaz/entregable:** `dispatch(CommandEnvelope) → CommandResult; subscribe(afterSeq) → EventStream`.

- [ ] Escribir primero el caso `repeated_command_id_never_repeats_external_effect`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T08/red.log`.
- [ ] Implementar: Un dueño por tarea, resultados aceptados/completados distintos, secuencias/snapshots y cancelación.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Doble clic/retry no duplica tarea; evento antiguo no pisa estado actual; animación no ejecuta herramienta.

## T09 · M2 · Tiempo y cronómetro nativos

**Depende de:** T08. **Requisitos:** R15, R16, R28.

**Archivos:**
- Revisar/modificar existente: `src/ui/time19.ts`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/timers.rs`.

**Interfaz/entregable:** `Timer.start(durationMs,label) / pause(id) / resume(id) / extend(id,deltaMs)`.

- [ ] Escribir primero el caso `new_duration_after_completion_and_pause_survives_suspend`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T09/red.log`.
- [ ] Implementar: Portar semántica de TimerTask, h/m/s, intervalos, deadline monotónico/reconciliación e historial.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Duración actual respetada; mismo ID; dígitos9→1 reales; una sola finalización; intervalos finitos.

## T10 · M3 · AudioRuntime y medidor físico

**Depende de:** T08. **Requisitos:** R17, R20, R23.

**Archivos:**
- Revisar/modificar existente: `src/ui/dictation13.ts`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/audio.rs`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/audio_bus.rs`.

**Interfaz/entregable:** `AudioSession.start(deviceId, grant) / subscribe(kind) / stop(); AudioFrame(seq,rate,pts,samples)`.

- [ ] Escribir primero el caso `mic_pause_releases_capture_and_silence_is_zero`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T10/red.log`.
- [ ] Implementar: Dueño único WASAPI, mezcla/ruteo explícitos, resampling correcto y subcripciones con permiso.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Mic real mide señal; no se escucha por altavoces; disconnect limpia recursos; sin entrada ficticia.

## T11 · M3 · Motor ASR real aislado

**Depende de:** T10. **Requisitos:** R17, R19.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `workers/asr/README.md`.
- NUEVA PROPUESTA: `workers/asr/model-manifest.json`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/asr.rs`.

**Interfaz/entregable:** `ASR.prepare(modelRef) / start(sessionId) / push(frame) / cancel(generation)`.

- [ ] Escribir primero el caso `asr_final_unique_and_late_result_discarded`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T11/red.log`.
- [ ] Implementar: Fijar whisper.cpp/binario/modelo, comprobar licencia/hash, wrapper de proceso y segmentos parciales/finales.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Reconocer audio humano real, medir precisión/latencia; no anunciar model ready antes de verificarlo.

## T12 · M3 · Destino externo UIA y lease

**Depende de:** T03, T08. **Requisitos:** R17, R18, R30.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/target.rs`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/target_lease.rs`.

**Interfaz/entregable:** `TargetBroker.capture() → TargetLease; validate(lease) → TargetStatus`.

- [ ] Escribir primero el caso `foreground_or_selection_change_invalidates_lease`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T12/red.log`.
- [ ] Implementar: Detectar control bajo foco/clic, selección/capacidades, excluir credenciales y invalidar referencias.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Cambio de ventana, texto o control bloquea inserción y conserva borrador; app elevada no se fuerza.

## T13 · M3 · Inserción transaccional y Morph Reach

**Depende de:** T11, T12. **Requisitos:** R18, R29.

**Archivos:**
- Revisar/modificar existente: `src/core/flow.ts`.
- Revisar/modificar existente: `src/ui/flow.ts`.
- Revisar/modificar existente: `src/ui/dictation13.ts`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/insertion.rs`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/paste_fallback.rs`.

**Interfaz/entregable:** `Insertion.preview(lease,text) / commit(approvalId) / undo(transactionId)`.

- [ ] Escribir primero el caso `approved_partial_replace_does_not_submit_or_duplicate`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T13/red.log`.
- [ ] Implementar: Adaptadores de texto nativo/DOM y pegado opt-in; before/after, uso único y undo protegido.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Selección parcial exacta; no Enter; portapapeles concurrente no se destruye; brazo solo representa commit.

## T14 · M3 · Traducción y lector real

**Depende de:** T11, T13. **Requisitos:** R19, R20.

**Archivos:**
- Revisar/modificar existente: `src/services/voice-translation18.ts`.
- Revisar/modificar existente: `src/ui/dictation13.ts`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/translation.rs`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/reader.rs`.

**Interfaz/entregable:** `translate(segment, languages, provider) / Reader.play(source) / pause() / resume()`.

- [ ] Escribir primero el caso `translation_order_conflict_and_reader_stops_mic`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T14/red.log`.
- [ ] Implementar: FIFO24, cancelación45s por defecto, original/resultado, TTS progresivo half-duplex; adaptadores reales.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Idioma/destino nuevo no acepta resultado tardío; texto original nunca se vende como traducción.

## T15 · M3 · IA conectada y herramientas autorizadas

**Depende de:** T08, T05. **Requisitos:** R12, R13, R14, R32.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src-tauri/src/runtime/llm.rs`.
- NUEVA PROPUESTA: `src-tauri/src/storage/secrets.rs`.
- NUEVA PROPUESTA: `src/adapters/native/brain.ts`.

**Interfaz/entregable:** `Chat.send(message,attachments,providerRef) → stream; ToolProposal → Dispatcher`.

- [ ] Escribir primero el caso `provider_error_never_becomes_simulated_answer`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T15/red.log`.
- [ ] Implementar: Mover secretos/HTTP al runtime; comandos locales primero, modelo real y tool proposals con validación.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Pregunta real y contexto, cancelación/429, secreto ausente del DOM y herramienta no permitida rechazada.

## T16 · M4 · Control musical de sesiones Windows

**Depende de:** T08, T10. **Requisitos:** R15, R22, R23.

**Archivos:**
- Revisar/modificar existente: `src/ui/music15.ts`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/media_sessions.rs`.

**Interfaz/entregable:** `Media.list() / select(sessionId) / control(op) / snapshot()`.

- [ ] Escribir primero el caso `selected_session_only_and_unavailable_next_disabled`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T16/red.log`.
- [ ] Implementar: GSMTC y capacidades por sesión; señal loopback opcional separada; conservar archivos locales.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Dos apps de música, pause dirigido, sesión desaparece y stale no permanece como control exitoso.

## T17 · M4 · Extensión y host real

**Depende de:** T12, T15. **Requisitos:** R17, R18, R20, R22, R32.

**Archivos:**
- Revisar/modificar existente: `extension/`.
- NUEVA PROPUESTA: `native-messaging/`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/browser_bridge.rs`.

**Interfaz/entregable:** `BrowserTarget / MediaTarget / NativeMessage{session,id,operation,payload}`.

- [ ] Escribir primero el caso `revoked_tab_and_wrong_extension_cannot_insert`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T17/red.log`.
- [ ] Implementar: Framing, IDs reales, grants por sitio, DOM controlado y pipe SID; instalar con registro reversible.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Host/serviceworker reales; tab autorizada funciona; otro origen y contraseñas rechazados.

## T18 · M4 · Proveedores musicales y estado externo

**Depende de:** T16, T17. **Requisitos:** R22, R23.

**Archivos:**
- Revisar/modificar existente: `src/ui/media16.ts`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/providers/spotify.rs`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/providers/youtube.rs`.

**Interfaz/entregable:** `ProviderDescriptor{controls,signal,requirements}; OAuthSession`.

- [ ] Escribir primero el caso `disconnect_invalidates_pending_provider_events`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T18/red.log`.
- [ ] Implementar: Adaptar control existente, OAuth/PKCE y scopes; revisar política antes de habilitar; no scraping/audio inventado.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Autorizar cuenta/video real; requisito ausente deshabilita integración, no toda la app.

## T19 · M4 · Captura física y reloj audio/vídeo

**Depende de:** T08, T10. **Requisitos:** R15, R24.

**Archivos:**
- Revisar/modificar existente: `src/ui/capture19.ts`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/capture.rs`.
- NUEVA PROPUESTA: `src-tauri/src/media/encoder.rs`.

**Interfaz/entregable:** `Capture.choose() / start(config,grant) / pause(id) / resume(id) / stop(id)`.

- [ ] Escribir primero el caso `physical_capture_pause_excluded_and_tracks_released`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T19/red.log`.
- [ ] Implementar: WGC selector, timestamps, audio opcional, cuenta previa y pausa confirmada; un encoder.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Ventana real con voz; reloj excluye pausas y archivo se reproduce; cancelación tardía libera fuente.

## T20 · M4 · Segmentos durables y guardar carpeta

**Depende de:** T19, T05. **Requisitos:** R26, R27.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src-tauri/src/media/segments.rs`.
- NUEVA PROPUESTA: `src-tauri/src/media/recovery.rs`.
- NUEVA PROPUESTA: `src-tauri/src/media/export.rs`.

**Interfaz/entregable:** `SegmentWriter.commit(segment) / RecordingManifest / Export.finalize(sessionId)`.

- [ ] Escribir primero el caso `crash_recovers_completed_segments_and_disk_full_not_saved`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T20/red.log`.
- [ ] Implementar: Segmentos finalizados10s, manifiesto atómico, ruta/grant, remux y recuperación; no concat bytesMP4.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Matar proceso, recuperar segmentos; disco lleno preserva; guardado solo tras close/verificación.

## T21 · M4 · Halo físico por monitor

**Depende de:** T03, T19. **Requisitos:** R25, R33.

**Archivos:**
- Revisar/modificar existente: `src/ui/capture19.ts`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/halo.rs`.

**Interfaz/entregable:** `Halo.update(monitorId,recordState,materialSnapshot) / close()`.

- [ ] Escribir primero el caso `halo_pauses_does_not_intercept_and_exclusion_measured`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T21/red.log`.
- [ ] Implementar: Ventana decorativa pass-through, paleta/material compartido, DPI, estado y exclusión condicionada.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Monitor correcto; pausa congela; no bloquea clics; inclusión/exclusión se verifica en vídeo real.

## T22 · M4 · Archivos y aplicaciones autorizadas

**Depende de:** T08, T12. **Requisitos:** R29, R30, R32.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src-tauri/src/runtime/files.rs`.
- NUEVA PROPUESTA: `src-tauri/src/platform/windows/apps.rs`.

**Interfaz/entregable:** `FileRef / AppRef; search(query,rootGrant) / open(ref,approval)`.

- [ ] Escribir primero el caso `path_escape_and_ambiguous_app_are_rejected`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T22/red.log`.
- [ ] Implementar: Indexar raíces autorizadas y appIDs, iconos reales, resolver homónimos, no comandos libres.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** No sale de raíz con reparse; dos presupuestos requieren selección; abrir informa estado real.

## T23 · M4 · Herramientas conservadas y accesibilidad

**Depende de:** T06, T09, T14, T15. **Requisitos:** R11, R12, R35, R36.

**Archivos:**
- Revisar/modificar existente: `src/ui/`.
- Revisar/modificar existente: `src/core/`.
- NUEVA PROPUESTA: `tests/windows/tools-matrix.md`.

**Interfaz/entregable:** `ToolCatalog → existing editors + native ports`.

- [ ] Escribir primero el caso `all_tools_keep_drafts_and_zoom_controls_accessible`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T23/red.log`.
- [ ] Implementar: Portar notas/tareas/texto/imágenes sin clonar editores; keyboard/foco/zoom y recuperación.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Todas las herramientas anteriores tienen prueba, guardado y retorno; cerrar no pierde borrador.

## T24 · M6 · Hey Axx y barge-in evaluado

**Depende de:** T10, T11, T14, T15. **Requisitos:** R21, R32, R33.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `src-tauri/src/runtime/wake.rs`.
- NUEVA PROPUESTA: `workers/wake/manifest.json`.
- NUEVA PROPUESTA: `tests/windows/wake-evaluation.md`.

**Interfaz/entregable:** `WakeState / WakeEvent / CommandSession; disable() releases resources`.

- [ ] Escribir primero el caso `wake_false_activation_budget_and_sensitive_confirmations`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T24/red.log`.
- [ ] Implementar: Detector elegido por evaluación/licencia; opt-in, ventana de orden y eco; half-duplex primero.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Medir mic real, TV/ruido, falsa alarma, latency y consumo; voz no autentica ni envía sin permiso.

## T25 · M5 · Instalador, actualización y operación

**Depende de:** T20, T21, T22, T23, T07. **Requisitos:** R31, R34.

**Archivos:**
- Revisar/modificar existente: `src-tauri/`.
- NUEVA PROPUESTA: `release/`.
- NUEVA PROPUESTA: `docs/operations/`.
- NUEVA PROPUESTA: `src-tauri/src/runtime/updates.rs`.

**Interfaz/entregable:** `ReleaseManifest{hash,version,contractVersion,dataSchemaVersion,signature}`.

- [ ] Escribir primero el caso `upgrade_rollback_and_uninstall_preserve_user_data`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T25/red.log`.
- [ ] Implementar: Bundle por usuario, firma, updater, backup/migrations/rollback, uninstall sin borrar vídeos.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Instalación usuario nuevo; update con datos y captura protegida; rollback compatible; firmas verificadas.

## T26 · M5 · Aceptación física final y cierre

**Depende de:** T25, T18. **Requisitos:** R01, R07, R09, R18, R24, R33, R34, R35.

**Archivos:**
- Sin modificación de fuentes existentes en esta tarea hasta revisar el inventario.
- NUEVA PROPUESTA: `evidence/release/`.
- NUEVA PROPUESTA: `docs/acceptance-final.md`.

**Interfaz/entregable:** `AcceptanceReport with U/I/P/E evidence and unresolved gates`.

- [ ] Escribir primero el caso `full_native_journey_no_hidden_mock_or_quality_drop`. Debe fallar cuando falte el comportamiento indicado; no limitarse a comprobar que existe un método.
- [ ] Ejecutarlo antes del cambio y guardar salida/exit code en `evidence/T26/red.log`.
- [ ] Implementar: Matriz física30min/2h, apps/monitores/voz/encoder, regresión visual y reporte sin mocks ocultos.
- [ ] Ejecutar test dirigido y suite completa del ámbito. Para TS usar scripts reales del package; para Rust `cargo test --manifest-path src-tauri/Cargo.toml`; el test físico utiliza el runbook de Windows y no se reemplaza por fixture.
- [ ] Registrar `green.log`, diff, hash/commit, entorno y toda prueba sustituida. No declarar física una prueba controlada.
- [ ] Revisar coherencia del contrato y no regresión de preferencias/acciones. Crear commit específico una vez comprobado.

**Puerta de aceptación:** Release declara exactamente capacidades aprobadas; todo P0 pendiente bloquea anuncio de completado.

## Evidencia por tarea

Crear `evidence/Txx/result.json` a partir de la plantilla. La tarea se considera implementada cuando el código/contratos están presentes; se considera validada cuando pasa su clase de evidencia exigida. `implemented` y `physicallyVerified` son campos distintos.

## Handoff final

No fusionar o publicar automáticamente. Entregar build y evidencia al propietario, con pendientes P0/P1, cambios de permisos, coste de servicios y pasos que requieren su autorización. Las instrucciones de ejecución se conservan en AGENTS y PROMPT-EJECUCION.