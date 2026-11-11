# Arquitectura de dictado · Fase 8

Base aislada: a750362 (incluye 4f4e18b). Rama codex/axx-handy-dictation.
No cambia versión, instalación, Android, credenciales ni diseño protegido.

Alcance: native-voice.js (lease común y lenguas), dictation-engine.js (PCM, VAD,
segmentos y API de UI), host Rust (UIA, foco, recibos, atajo), offline_asr.py
(selección por solicitud), catálogo local, pruebas y contrato UI.
Callers conservados: chat draft, voz, quick reply, anticipation, Android y Telegram.
No usar permisos Computer Use para dictado ni convertir transcripción en comando.

La captura existente conserva prioridad; global solo toma un lease libre. El usuario
arma deliberadamente, estado inicial OFF; Escape, bloqueo y cierre cancelan.
Un stream PCM, máximo 10 s por segmento, cola acotada. Solo frases finales;
idempotencia por sesión/secuencia y epoch nativo. Texto pendiente solo en RAM.
Dictado escribe sin enviar; comandos pasan por su ejecutor autorizado; conversación
usa el proveedor elegido y su ruta actual. Comparten captura, no permisos.

Selección de motor por tarea/solicitud. El motor anterior sigue siendo el defecto.
No recomendar Parakeet frente a Whisper sin mismo corpus y medidas locales.
No descargar pesos automáticamente. No prometer compatibilidad UIA universal.

Implementación propia inspirada en Handy; catálogo con licencia y procedencia.
Cualquier port literal debe conservar MIT. No incorporar auto-submit.

Implementación concreta: captura PCM/lease en el único renderer existente; Rust conserva autorización, epoch/foco, inyección y atajo, no el dispositivo físico. Esto reduce cambios sobre la voz actual, pero no satisface todavía el cierre independiente del micrófono si se congela la UI. Ese punto bloquea producción y la aceptación de bloqueo de Windows.
