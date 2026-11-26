# AXX Mobile 3.0 — Registro de cambios, compatibilidad y aceptación

Fecha: 2026-11-25  
Rama de integración: `feat/mobile-3`

> **Regla de verificación estricta:** este documento separa explícitamente resultados de **fuente/pruebas automáticas**, **compilación de binarios**, **instalación local Windows** y **aceptación física en Android** (pendiente hasta conectar el teléfono físico).

## 1. Cambios implementados

### P1 — Conexión y chat unificados
- **Persistencia de estado del gateway (`backend/mobile/trust_store.py`, `backend/mobile/gateway.py`, `backend/mobile/http_api.py`):** guarda el último `share_history`, `preferences` (sin secretos) y `appearance` confirmados en SQLite para sobrevivir reinicios de PC.
- **Estados explícitos en `/v1/snapshot` (aditivos):** `server_epoch`, `chat_available`, `chat_blocked_reason`, `model_status`, `always_on` y `capabilities.events_stream`.
- **Resiliencia de red:** `CLAIMED_IDLE_TIMEOUT` ampliado de 30 s a 600 s tras emparejamiento válido; keep-alive habilitado en `/v1/control/renew`, `/v1/status`, `/v1/snapshot`, `/v1/tasks` y `/v1/events`; límite de conexiones ampliado con rechazo HTTP `503 SERVER_BUSY` en lugar de cierre silencioso; pool dedicado `eventsNetwork` en `AxxTransportPlugin.java`.
- **Sincronización incremental (`GET /v1/events?after=<cursor>`):** long-poll sobre `shared_events` con detección de huecos (`resync_required`), filtrado estricto de `share_history`, actualización incremental del DOM sin reconstruir `#messages` y soporte de deltas de streaming.
- **UX de «Guardar historial» (`1.AXX/scripts/mobile-gateway.js`, `mobile/js/live-client.js`):** mantiene el bloqueo explícito cuando «Guardar historial» está desactivado, explica la causa en Android y ofrece botón directo en Ajustes del PC para activarlo.

### P2 — AXX Action Brain
- **Planificador multi-paso y procedimientos aprendidos (`backend/server.py`, `backend/mobile/gateway.py`):** las coincidencias `sequence`, `sequence_request` y `learned` (y comandos con parámetros faltantes o receta) se enrutan a `/axx-api/learning/prepare` y `/axx-api/learning/propose` exigiendo `tools.control`. Todas las aprobaciones permanecen exclusivas del PC.
- **Herramientas estructuradas del modelo (`axx_tools`):** habilitadas en canal `mobile` únicamente cuando concurren `tools.control`, `chat_tools` activo en el escritorio y ámbito de memoria vigente; recibos verificados vs pendientes vs bloqueados sin falsos positivos.
- **Trazabilidad viva:** emisión de `operation.changed` con fases (`planning`, `preparing`, `awaiting_approval`, `executing`, `succeeded`, `failed`).

### P3 — Ratón, trackpad y teclado de baja latencia
- **Colas separadas (`mobile/js/remote-control.js`):** `motion` coalesced por frame con `requestAnimationFrame` y `getCoalescedEvents()`, y `critical` ordenada preservando el desplazamiento previo a cada clic/tecla/arrastre. Fallos críticos siguen cancelando sin reintentar; fallos transitorios de movimiento puro reconcilian `seq` mediante `renew` solo si no hay teclas/botones pulsados.
- **Teclado y gestos (`backend/mobile/control.py`, `backend/mobile/windows_input.py`, `mobile/js/remote-control.js`):** soporte `F1`–`F12`, `Home/End`, `PageUp/PageDown`, `Space`, doble toque, y modo opt-in «En vivo (IME)» con manejo de composición Unicode (`compositionstart`/`compositionend`).
- **Caché de permisos con invalidación inmediata (`backend/mobile/trust_store.py`):** elimina consultas SQLite repetitivas por cada paquete de movimiento, invalidando al instante en revocación o cambio de permisos.
- **Instrumentación (`control.py`, `remote-control.js`):** métricas monotónicas servidor + cliente (`window.axxControlTelemetry()`).

### P4 — Avatar y prioridad de entrada
- **Sin cambios en `mobile/design-baseline.json` ni en `avatar-renderer.js`:** se conservan intactas geometría, materiales, paletas, acabados y cámara canónica.
- **Cooperación con control remoto y paneles (`mobile/js/live-client.js`):** suspende el bucle de renderizado del avatar mientras se usa el trackpad/teclado remoto (`axxInputActive`) o al cambiar fuera de la pestaña Axx; añade telemetría `window.axxAvatarTelemetry()` y calidad adaptativa con histéresis.

## 2. Compatibilidad `/v1` y diseño protegido
- Contrato `axx-companion-v1`: todas las rutas requeridas preservadas; todos los campos nuevos son opcionales/aditivos.
- `mobile/design-baseline.json`: 10/10 superficies protegidas sin modificación.

## 3. Procedimiento de rollback
1. Restaurar binario anterior de Windows desde el respaldo generado por `scripts/backup-mobile-upgrade.py` (o reinstalar `v0.23.4` publicada) sin borrar `%LOCALAPPDATA%\Axx`.
2. En Android, conservar los datos de Keystore/emparejamiento (no desinstalar); reinstalar el APK firmado anterior si hubiera regresión de `versionCode` solo mediante copia ensayada, o publicar versión correctiva con `versionCode` superior.
3. En git, revertir la rama o el commit de fusión en `main`.

## 4. Matriz de aceptación (estado actual)

| Gate / Prueba | Estado | Evidencia / Nota |
|---|---|---|
| `python scripts/validate_companion.py` | **Verificado en esta entrega** | Recibo `build/companion-validation.json` |
| Pruebas unitarias backend móvil + `test_mobile3_upgrades.py` | **Verificado en esta entrega** | Ver salida de ejecución |
| Pruebas Playwright + `test_mobile3_ui.py` | **Verificado en esta entrega** | Ver salida de ejecución |
| Pruebas backend comandos (`test_command_*`, `test_phase6_tools`) | **Verificado en esta entrega** | Ver salida de ejecución |
| Unit tests & APK Android (`gradlew testDebugUnitTest assembleDebug`) | **BLOQUEADO EN ESTE PC (falta Android SDK)** | `npm --prefix mobile run sync` OK (`0.2.15-companion` / `code 36`), pero `C:\Users\luigi\AppData\Local\Android\Sdk` (API 36 / build-tools 35.0.0) no está instalado actualmente en este equipo. El `app-debug.apk` existente en disco es histórico del 2026-10-29 y NO corresponde a `0.2.15-companion`. |
| C01–C05 (Pairing QR físico, LAN↔Tailscale, reconexión) | **PENDIENTE DE TELÉFONO FÍSICO** | Sin dispositivo en `adb devices` |
| A01–A02 (20 prompts reales con modelo configurado + denegaciones) | **PARCIAL (pruebas automatizadas OK; falta sesión real end-to-end PC+Android)** | Requiere teléfono y proveedor IA en vivo |
| I01–I03 (60 s dedo-a-cursor 120/240 FPS, IME físico, lease caída) | **PENDIENTE DE TELÉFONO FÍSICO** | Requiere dispositivo físico |
| V01 (Comparación visual lado a lado PC vs Android real) | **PENDIENTE DE TELÉFONO FÍSICO** | Requiere capturas en dispositivo |
| R01 (`adb install -r` in-place + conservación de datos/firma) | **PENDIENTE DE TELÉFONO FÍSICO** | Requiere dispositivo conectado |
| Publicación de release en GitHub | **BLOQUEADA INTENCIONALMENTE (decisión A4)** | Se publicará tras completar la aceptación física |
