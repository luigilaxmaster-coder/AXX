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

### P4 — Avatar, rendimiento móvil y PC
- **Sin cambios en `mobile/design-baseline.json` ni en `avatar-renderer.js`:** se conservan intactas geometría, materiales, paletas, acabados y cámara canónica.
- **Cooperación con control remoto y paneles (`mobile/js/live-client.js`):** suspende el bucle de renderizado del avatar mientras se usa el trackpad/teclado remoto (`axxInputActive`) o al cambiar fuera de la pestaña Axx; pacing automático a ~30 FPS en GPUs móviles lentas (`avgDrawMs > 11 ms`) manteniendo 60 FPS en GPUs rápidas y arrastre táctil; diferimiento de `syncHomeIcon` y sin reescritura de `localStorage` en ticks de cámara.
- **Eliminación de tormentas de sondeo y carga en PC (`remote-voice.js`, `avatar-customization.js`, `mobile-gateway.js`, `gateway.py`, `windows_input.py`, `AxxTransportPlugin.java`):**
  - Keep-alive también en `/v1/voice/poll` y `/v1/files/status`, pool `inputNetwork` de 3 hilos, sondeo de voz adaptativo (`2500 ms` en reposo, pausado durante `axxInputActive`, deduplicación de DOM).
  - SQLite en modo `WAL` + `busy_timeout=10000`; `update_appearance()` ignora cambios exclusivos de cámara para SQLite y `/v1/events`; manejo limpio de desconexiones SSL sin 502 en sockets muertos.
  - `windows_input.py`: premultiplicación BGRA en C (`RGBa -> BGRa`, ~200× más rápida), caché de DPI de monitores sin crear ventanas de prueba cada segundo, drenaje por lotes de comandos antes de dibujar el overlay y espera inactiva de 250 ms.

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
| Unit tests & APK Android (`gradlew testDebugUnitTest assembleDebug lintDebug`) | **Verificado en esta entrega** | Compilado con JDK 21 + Android SDK 36 (`0.2.15-companion` / `code 36`), firma idéntica a `0.2.11` (`d1ae0589...61a8`). |
| Instalación in-place (`adb install -r`) + reconexión real PC ↔ Samsung A21s (`SM-A217M`, Android 12 API 31) | **Verificado en hardware real** | Actualizado desde `0.2.11-companion` (`code 32`) a `0.2.15-companion` (`code 36`) sin borrar datos/Keystore/tema; reconexión automática a `LAPTOP-9CJBQB83` con `↔ Sincronizado`, avatar intacto y stream `GET /v1/events` activo. |
| C01–C05 (Pairing QR nuevo, LAN↔Tailscale, reconexión cross-network) | **PARCIAL** | Reconexión LAN con credenciales conservadas verificada en `SM-A217M`; falta prueba física LAN ↔ Tailscale. |
| A01–A02 (20 prompts reales con modelo configurado + denegaciones) | **PARCIAL (pruebas automatizadas OK; falta sesión real de 20 prompts)** | A validar interactivamente desde el teléfono. |
| I01–I03 (60 s dedo-a-cursor 120/240 FPS, IME físico, lease caída) | **PENDIENTE DE MEDICIÓN CON CÁMARA** | Instrumentación `window.axxControlTelemetry()` y `metrics` ya activas. |
| V01 (Comparación visual lado a lado PC vs Android real) | **PARCIAL** | Captura real en `SM-A217M` verificada (avatar prismático + gotas + tema oscuro/púrpura intactos). |
| Publicación de release en GitHub | **BLOQUEADA INTENCIONALMENTE (decisión A4)** | Rama `feat/mobile-3` + PR #9 con CI en verde; se publicará tras completar la aceptación física completa. |
