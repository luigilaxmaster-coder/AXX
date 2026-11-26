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

## Instrumentación incorporada

- **Servidor (`backend/mobile/control.py`):** cada respuesta de `POST /v1/control/events` añade el campo opcional `metrics` con duraciones monotónicas puras del host (`lock_wait_ms`, `send_input_ms`, `server_total_ms`), sin mezclar relojes entre equipos.
- **Cliente (`mobile/js/remote-control.js`):** mide `queue_ms` (captura táctil a despacho) y `rtt_ms` (despacho a ACK), muestra percentiles `p50 / p95 / p99` y jitter (`p95 - p50`) en Ajustes de control, y expone `window.axxControlTelemetry()` para volcado reproducible.
- **Pendiente de hardware:** medición física dedo-a-cursor con cámara de alta velocidad en LAN y Tailscale directo/relay.
