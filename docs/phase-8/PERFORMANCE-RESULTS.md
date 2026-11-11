# Rendimiento medido

Smoke ASR base real, 3 audios sintéticos SAPI ingleses, CPU int8, 2 hilos:
primera respuesta 9375.16 ms; warm p50 3038.02 ms; warm p95 3045.04 ms sobre SOLO
2 observaciones calientes. Pico RSS del árbol worker 328978432 bytes; CPU del
árbol 22.859375 s. Muestreo psutil cada 50 ms: puede omitir picos entre muestras.
Carga paralela de compilación/pruebas presente. No es una mejora contra baseline
ni representa latencia física micrófono→campo ni rendimiento sostenido.

Nuevo dictado: segmentos de ~10 s máximo (hasta un bloque extra), PCM mono,
contexto solicitado 16 kHz, máximo admitido 48 kHz; 2 segmentos en cola y 1 activo.
Máximo ~6 MiB de PCM a 48 kHz más buffers de WAV/base64/pipe; no es un límite de
RSS del proceso. Backpressure pausa con error visible y libera audio pendiente.
Pendientes: 10 textos de hasta 8000 caracteres; no se persisten. ASR máximo
60 s/1.4 MiB por petición; el archivo debe elegirse explícitamente.

Worker C++ aislado y de carga diferida. Un solo modelo residente por worker;
cambiar entre C++ y Whisper libera el anterior, cancelación mata el árbol.
Liberación manual del modelo disponible. GPU/Vulkan no se habilitaron.

Pendiente: corpus físico 50+, p95 suficiente, primer arranque en frío controlado,
10 min / 100+ segmentos / 10+ cambios de campo, cambio de micrófono, carga RAM
junto a LLM, recuperación de suspensión/bloqueo y impacto de ScriptProcessor
bajo trabajo de UI. Pasar a AudioWorklet si se miden pérdidas de frames.

Host detectado: Intel Core i7-1255U de 12.ª generación, 12 procesadores lógicos, 16870006784 bytes de RAM física (~15.71 GiB). No es el i7 de 11.ª generación de la propuesta; no extrapolar sus mediciones ni certificar aquel equipo.

El límite de IDs explícitos del supervisor existente es 4096 por vida del servicio; al agotarlo falla de forma visible y requiere reinicio del servicio. No se ofrece escucha de duración ilimitada.
