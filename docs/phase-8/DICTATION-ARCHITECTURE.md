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

Captura global: WASAPI compartido en hilo nativo STA, PCM mono 16 kHz/16 bits;
sin nueva dependencia. El renderer recibe bloques de 2048 muestras, hace VAD y
consume la misma API ASR. El host conserva dispositivo, autorización, foco y atajo.
Comprueba cancelación, escritorio y latido cada ~10 ms; 3 s sin latido detienen la
captura aunque el renderer no ejecute JS. UIA refresca el destino cada ~100 ms;
un epoch distinto descarta audio hasta revalidar, un campo protegido cierra audio.
Las colas dejan de crecer al vencer el latido. No se guardan PCM ni transcripciones.

La voz existente conserva sus adaptadores browser, coordinados por el mismo lease.
Sus tres callers (grabador, medidor y micrófono visual) esperan confirmación nativa
de liberación antes de abrir otro stream. Un fallo/timeout de cierre bloquea ese
handoff. Escape y salida cancelan desde el host; errores/pérdidas de audio requieren
reanudación explícita. El diseño ya no depende del renderer para liberar WASAPI;
la aceptación con hardware, bloqueo y suspensión reales sigue pendiente.

APIs verificadas contra windows 0.61.3 y documentación primaria de Microsoft:
[Initialize](https://learn.microsoft.com/windows/win32/api/audioclient/nf-audioclient-iaudioclient-initialize),
[GetBuffer](https://learn.microsoft.com/windows/win32/api/audioclient/nf-audioclient-iaudiocaptureclient-getbuffer).
