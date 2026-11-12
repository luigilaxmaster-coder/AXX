# Rendimiento medido

Smoke ASR base real, 3 audios sintéticos SAPI ingleses, CPU int8, 2 hilos:
primera respuesta 9375.16 ms; warm p50 3038.02 ms; warm p95 3045.04 ms sobre SOLO
2 observaciones calientes. Pico RSS del árbol worker 328978432 bytes; CPU del
árbol 22.859375 s. Muestreo psutil cada 50 ms: puede omitir picos entre muestras.
Carga paralela de compilación/pruebas presente. No es una mejora contra baseline
ni representa latencia física micrófono→campo ni rendimiento sostenido.

Comparación posterior, pesos autorizados y ABI corregida, mismo corpus de 3
clips, 2 hilos CPU; primera llamada incluye arranque/carga, no frío de caché OS:

| Motor | Primera ms | Warm p50 ms | Warm p95 ms | Pico árbol MiB | CPU árbol s |
| --- | ---: | ---: | ---: | ---: | ---: |
| faster-whisper base int8 | 2398.31 | 756.03 | 756.05 | 306.14 | 5.95 |
| Parakeet V3 Q8_0 | 3888.50 | 806.75 | 884.79 | 1190.11 | 6.98 |
| Whisper Small Q8_0 | 6974.59 | 6626.25 | 6796.73 | 466.89 | 36.55 |

SOLO 2 observaciones warm por motor, sin aislamiento de carga. No extrapolar
percentiles ni declarar superioridad lingüística. Informe agregado privado:
build/phase8/asr-approved-models-comparison.json. Backend empaquetado también
preparó, transcribió y liberó ambos modelos con una muestra sintética real.

Nuevo dictado: segmentos de ~10 s máximo (hasta un bloque extra), PCM mono,
WASAPI entrega 16 kHz/16 bits; 2 segmentos en cola y 1 activo.
Máximo ~2 MiB de Float32 PCM segmentado más buffers de WAV/base64/pipe; no es un límite de
RSS del proceso. Backpressure pausa con error visible y libera audio pendiente.
Pendientes: 10 textos de hasta 8000 caracteres; no se persisten. ASR máximo
60 s/1.4 MiB por petición; el archivo debe elegirse explícitamente.

Worker C++ aislado y de carga diferida. Un solo modelo residente por worker;
cambiar entre C++ y Whisper libera el anterior, cancelación mata el árbol.
Liberación manual del modelo disponible. GPU/Vulkan no se habilitaron.

Pendiente: corpus físico 50+, p95 suficiente, primer arranque en frío controlado,
10 min / 100+ segmentos / 10+ cambios de campo, cambio de micrófono, carga RAM
junto a LLM, recuperación de suspensión/bloqueo y pérdidas de WASAPI/IPC bajo carga.
El dictado global ya no usa ScriptProcessor ni depende de autoplay/AudioContext.
El hilo nativo limita paquetes a 16000 muestras, emite bloques de 2048 y vence a
los 3 s sin latido. Una discontinuidad tras el primer paquete detiene la sesión;
no se ofrece captura sin pérdidas. No se midió aún ese camino con hardware real.

Host detectado: Intel Core i7-1255U de 12.ª generación, 12 procesadores lógicos, 16870006784 bytes de RAM física (~15.71 GiB). No es el i7 de 11.ª generación de la propuesta; no extrapolar sus mediciones ni certificar aquel equipo.

El límite de IDs explícitos del supervisor existente es 4096 por vida del servicio; al agotarlo falla de forma visible y requiere reinicio del servicio. No se ofrece escucha de duración ilimitada.
