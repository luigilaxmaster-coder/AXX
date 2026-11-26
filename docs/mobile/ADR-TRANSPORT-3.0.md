# ADR: Transporte móvil de baja latencia y sincronización incremental (AXX Mobile 3.0)

Fecha: 2026-11-25  
Estado: **Aceptado (etapa 1 implementada; etapa 2 WSS/WebRTC condicionada a benchmark físico)**

## Contexto

Antes de AXX Mobile 3.0:
- El cliente móvil sondeaba cada 2 s en serie `/v1/status`, `/v1/snapshot` y `/v1/tasks` con `Connection: close`, provocando 3 handshakes TLS cada 2 s.
- `POST /v1/control/renew` también cerraba la conexión cada 500 ms.
- El servidor delimitaba 8 conexiones totales y cerraba silenciosamente el exceso (percibido como `PC_UNREACHABLE`).
- El envío de ratón/teclado mezclaba movimientos continuos con clics/teclas en una única cola y cancelaba la sesión ante cualquier fallo transitorio de red.

## Opciones evaluadas

1. **HTTPS/1.1 keep-alive ampliado + `GET /v1/events?after=<cursor>` (long-poll) sobre `AxxTransportPlugin` existente** *(Elegida para etapa 1)*
   - Reutiliza el modelo exacto de TLS pinning SHA-256 del QR y Android Keystore sin abrir otro puerto ni introducir WebSocket JS no autenticado.
   - Usa un pool dedicado (`eventsNetwork`) en Android para no bloquear `network` ni `inputNetwork`.
   - Mantiene 100 % compatibilidad retroactiva con `/v1` (`axx-companion-v1`).
   - Elimina los handshakes TLS repetitivos en `/v1/control/renew`, `/v1/status`, `/v1/snapshot`, `/v1/tasks` y `/v1/events`.
   - Separa colas lógicas en el cliente: `motion` coalesced por frame (`requestAnimationFrame`) y `critical` ordenada (down/up, teclas, texto, STOP), conservando el desplazamiento acumulado antes de cada evento crítico.
2. **WebSocket seguro (WSS) con TLS pinning en el plugin nativo** *(Etapa 2, solo tras benchmark físico)*
   - Requiere gestión de frames, reconexión explícita y mantenimiento de dependencia/socket nativo adicional.
   - **Criterio de adopción:** solo se implementará si las mediciones físicas en LAN con cámara 120/240 FPS + `window.axxControlTelemetry()` superan los presupuestos objetivo (`p50 >= 35 ms`, `p95 >= 65 ms`, `p99 >= 100 ms`) después de la optimización keep-alive + colas separadas.
3. **WebRTC DataChannel** *(Descartado en etapa 1)*
   - Introduce señalización ICE/SDP/DTLS y complejidad de relay/TURN injustificada sin evidencia de que HTTPS keep-alive/WSS no cumplan los presupuestos medidos.

## Instrumentación y optimizaciones de rendimiento incorporadas

- **Servidor (`backend/mobile/gateway.py`, `shared_state.py`, `trust_store.py`, `windows_input.py`):**
  - SQLite en modo `WAL` (`PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=10000`) para eliminar bloqueos `database is locked` entre escritorio y móvil.
  - Keep-alive ampliado a `/v1/control/events`, `/v1/control/status`, `/v1/control/renew`, `/v1/status`, `/v1/snapshot`, `/v1/tasks`, `/v1/events`, `/v1/voice/poll` y `/v1/files/status`, evitando handshakes TLS repetitivos.
  - Filtrado estructural de apariencia (`_structural_appearance`): los ticks de rotación de cámara (`autoRotate`) se mantienen en RAM sin disparar escrituras SQLite ni despertar `/v1/events` cada segundo.
  - Desconexiones/timeouts de sockets SSL manejados sin intentar respuestas 502 sobre sockets cerrados.
  - Hilo nativo de entrada (`windows_input.py`): premultiplicación BGRA en C vía `image.convert('RGBa').tobytes('raw', 'BGRa')` (~200× más rápido que el bucle Python por píxel), drenaje por lotes de hasta 8 comandos antes de redibujar el overlay, caché de DPI de monitores (sin `CreateWindowExW`/`DestroyWindow` cada segundo) y espera inactiva de 250 ms con despertar inmediato por `PostThreadMessageW`.
  - Cada respuesta de `POST /v1/control/events` añade el campo opcional `metrics` con duraciones monotónicas del host (`lock_wait_ms`, `send_input_ms`, `server_total_ms`).
- **Cliente Android (`AxxTransportPlugin.java`, `live-client.js`, `remote-voice.js`, `remote-control.js`, `avatar-customization.js`):**
  - Pools nativos dedicados: `network` (3 hilos), `inputNetwork` (3 hilos) y `eventsNetwork` (1 hilo) con reutilización keep-alive en las rutas de control, estado, eventos, voz y archivos.
  - Sondeo adaptativo de voz remota (`2500 ms` en reposo, `750 ms` en sesión activa, pausado completamente durante `axxInputActive`, caché de `paired` y deduplicación de mutaciones DOM); temporizador bajo demanda en `avatar-customization.js`.
  - Pacing de fotogramas del avatar en GPUs móviles de gama de entrada (~30 FPS cuando la media móvil de `drawMs > 11 ms`, volviendo a 60 FPS en GPUs rápidas o durante arrastre táctil), diferimiento de `syncHomeIcon` y eliminación de escrituras `localStorage` por rotación de cámara.
  - Telemetría de control remoto (`queue_ms`, `rtt_ms`, `p50/p95/p99`, jitter) visible en Ajustes de control (`⚙`) y exportable con `window.axxControlTelemetry()`.
- **Pendiente de hardware avanzado:** medición física dedo-a-cursor con cámara 120/240 FPS en LAN y Tailscale directo/relay para decidir si alguna vez se requiere WSS en etapa 2.
