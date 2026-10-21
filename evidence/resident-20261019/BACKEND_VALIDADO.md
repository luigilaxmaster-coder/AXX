# Axx — backend, voz y memoria validados

Fecha: 2026-10-19. Alcance: fuentes congeladas y ejecución del **sidecar Windows empaquetado**. Este documento no certifica por sí solo la instalación NSIS, la interacción visual ni el hardware de audio; esos recorridos corresponden al informe final de entrega.

Se contrastó el resultado con la [corrección obligatoria](<C:/Users/luigi/.codex/attachments/86b7b00a-9cb1-492d-a488-f554ae527062/Texto pegado.txt>) y la [orden maestra](<C:/Users/luigi/.codex/attachments/12a699fe-5aab-4ed9-8121-b23afc7d4cd7/Texto pegado.txt>). No se modificaron fuentes durante la aceptación del binario ni al redactar este informe.

## Resultado verificable

- **45/45 pruebas** aprobadas en 13,533 s: [registro completo](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/backend-tests.log>).
- **8/8 comprobaciones del sidecar empaquetado** aprobadas: [resultado JSON](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/packaged-runtime.json>) y [registro](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/packaged-runtime.log>).
- Binario comprobado: [axx-backend.exe](<C:/Users/luigi/Desktop/Axx assistant/src-tauri/resources/axx-backend.exe>), 169.976.093 bytes. SHA-256: `8312ce40f16db6b024cf2a8bac1268b0ae15f867e089002138e1f16884d909ac`. El hash se volvió a comprobar al redactar este documento.
- Ejecución desde un directorio temporal independiente del checkout, mediante el ejecutable y sus recursos distribuidos. El proceso de aceptación no importa módulos Python del proyecto.

Comandos ejecutados:

```powershell
python -m unittest discover -s backend -p 'test_*.py' -v
python backend/tests/verify_resident_packaged.py 'C:/Users/luigi/Desktop/Axx assistant/src-tauri/resources/axx-backend.exe' --output 'evidence/resident-20261019/packaged-runtime.json'
```

El segundo comando terminó con código 0. El [verificador utilizado](<C:/Users/luigi/Desktop/Axx assistant/backend/tests/verify_resident_packaged.py>) conserva las aserciones y el alcance de cada comprobación.

## Capacidades comprobadas

| Capacidad | Resultado observado y alcance |
| --- | --- |
| Servicio privado | Arranque con puerto efímero, identidad de instancia y disponibilidad auténtica. Las API requieren bearer del host; rechazan solicitudes sin autenticación y con origen de navegador. El token no aparece en la respuesta de estado. |
| Inferencia | Trabajador del propio ejecutable, entradas/salidas acotadas y errores tipados. La aceptación empaquetada terminó con `NO_PROVIDER_AVAILABLE` al faltar credenciales; **no se ejecutó una conversación remota**. |
| Archivo real | Creación en el directorio autorizado de artefactos; verificación de existencia, contenido, tamaño y SHA-256. `operation_id` permite recuperar el resultado sin repetir el efecto y rechaza argumentos diferentes. |
| Telemetría/procesos | Herramientas registradas de telemetría real y consulta de PID, comprobadas en la suite. El registro no equivale a control universal de aplicaciones. |
| CLI-Anything | Adaptador Blender fijado a `34f519533bc175d2fe287ab8316b0dd99bb9cc43`; Blender instalado 4.5.5 LTS produjo un PNG real de 256×256 y 37.697 bytes. Se comprobaron formato, dimensiones y hash. El adaptador admite una escena fija y un nombre de salida seguro; no acepta scripts ni escenas arbitrarias. |
| ai-memory | Servicio propio 3.1.1, loopback y autenticación privada; escritura de receta, búsqueda y lectura reales por MCP. La página volvió a leerse después de cerrar y arrancar de nuevo backend y servicio. Embeddings desactivados; no se adoptan servicios ajenos. |
| Memoria procedural | Una acción aprobada por sus poscondiciones originó una receta. Tras reiniciar, se reutilizó con ruta/contenido diferentes y se verificó el segundo archivo. SQLite conserva la autoridad de ejecución; una página recuperada no autoriza herramientas. |
| Voz sintetizada | Windows SAPI generó WAV PCM mono de 16 kHz y 16 bits. Se comprobaron muestras, tamaño y SHA-256. El resultado declara `playback_verified:false`: generar audio no demuestra haberlo oído por el altavoz. |
| Transcripción local | El tiny CTranslate2 distribuido transcribió exactamente una frase sintetizada de 6,49 s. CPU/int8, sin descargas ni llamadas de proveedor. La aceptación empaquetada tardó 1,969 s para ese caso concreto; no es una garantía de latencia general. |

Artefacto Blender generado: [resident-cli.png](<C:/Users/luigi/AppData/Local/Temp/axx-resident-packaged-l_zy11k9/artifacts/resident-cli.png>), SHA-256 `b4a6cc75c9180f6b8ec31a5598e75e7bda0999589b808c0f13c70a1a2cdd29e5`.

Segundo archivo procedural: [memory-second.txt](<C:/Users/luigi/AppData/Local/Temp/axx-resident-packaged-l_zy11k9/artifacts/memory-second.txt>). Estos archivos son evidencia de ensayo temporal, no datos de la instalación definitiva.

## Contratos y límites de voz

| Operación | Contrato y límites efectivos |
| --- | --- |
| `GET /axx-api/speech/voices` | Lista voces realmente instaladas y habilitadas; motor `windows-sapi`. La consulta del ensayo devolvió Zira Desktop `en-US` y Elsa Desktop `it-IT`. No se verificó una voz española instalada. |
| `POST /axx-api/speech/synthesize` | `text`, `voice` opcional, `rate` entero −5…5 y `volume` entero 0…100. Máximo 1.200 caracteres, proceso de 20 s, WAV de 90 s y 3 MiB. Devuelve audio base64 y evidencia; reproducción, pausa y detención del audio recibido corresponden al cliente. |
| `POST /axx-api/speech/transcribe` | `audio_base64`, `mime`, `language` opcional y `task`. Máximo 1.433.600 bytes de audio y 60 s; trabajador de 90 s. Admite firmas WAV, WebM, Ogg y MP4; la aceptación real utilizó WAV. |
| Traducción local | `task:translate` de Whisper produce **inglés**. No implementa traducción a un idioma destino arbitrario. `task:transcribe` conserva el idioma reconocido. Ninguno envía mensajes ni ejecuta acciones automáticamente. |
| `POST /axx-api/actions/cancel` | Señala y termina los procesos activos propios de Blender, síntesis y transcripción; se atiende fuera del bloqueo que mantiene la acción. No controla procesos ajenos. |

El modelo se carga únicamente en el trabajador de transcripción. El backend inactivo no carga sus pesos. Se usan recursos locales con `local_files_only=True`; los frameworks opcionales de conversión Torch/Transformers/TensorFlow/Fairseq/ONNX se excluyen de esta ruta. La [prueba sintética de voz](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/offline-tts-asr.json>) identifica expresamente que **no verifica micrófono físico**.

Referencia de los componentes utilizados: [Microsoft SpeechSynthesizer](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer), [faster-whisper oficial](https://github.com/SYSTRAN/faster-whisper/blob/master/README.md).

## Memoria, persistencia y recuperación

Los endpoints autenticados `POST /axx-api/memory/query {query}` y `POST /axx-api/memory/read {recipe_id}` devuelven resultados reales del adaptador y su estado `ai-memory`/`sqlite`. La consulta está limitada a 4.000 caracteres; los identificadores no permiten rutas arbitrarias. Las respuestas indican `execution_allowed:false`. El fallback SQLite se comprueba por separado en la suite y no se presenta como conexión MCP.

Las recetas registradas desde la API requieren una operación persistida `succeeded` con poscondiciones aprobadas. Las recetas de escritura parametrizan `path` y `content`; el ejecutor mantiene el confinamiento al directorio autorizado. Se conservan versiones, huella de entorno, intentos, tiempos, hashes de entradas y evidencia. Repetir un identificador con entradas distintas se rechaza. Las operaciones que quedaron `prepared`/`running` al caer el proceso pasan a `unknown` y no se repiten automáticamente.

Datos canónicos: [directorio Axx del usuario](<C:/Users/luigi/AppData/Local/Axx>), [providers.json](<C:/Users/luigi/AppData/Local/Axx/providers.json>) y [state.db](<C:/Users/luigi/AppData/Local/Axx/state.db>). Los artefactos se confinan a `artifacts/`; ai-memory utiliza `ai-memory/`. La migración conserva los archivos existentes y crea una copia SQLite consistente previa a la migración en `backups/state-before-desktop-v1.db` cuando corresponde. Los temporales de audio se eliminan después de responder.

## Pendientes exactos frente a la orden maestra

Estos puntos permanecen incompletos o carecen de la evidencia exigida; no alteran el PASS de los ocho casos concretos anteriores.

1. **Conversación y redundancia reales — §7 y §12.** OpenRouter está preparado con `openrouter/free` y variable `OPENROUTER_API_KEY`, pero no hay credencial disponible. No hay modelo efectivo, conversación real, latencia remota ni failover entre dos cuentas verificados. `OLLAMA_API_KEY`, `GEMINI_API_KEY` y `GROQ_API_KEY` tampoco están presentes en el entorno comprobado. Gemini 2.0 Flash permanece deshabilitado. Véase [validación de proveedores](<C:/Users/luigi/Desktop/Axx assistant/evidence/delivery-20261019/provider-validation.json>). Las credenciales deben configurarse localmente; no deben enviarse por el chat.
2. **Progreso de inferencia — §6.** El router entrega el resultado y los intentos finales. No hay transmisión incremental de tokens ni eventos completos por intento/failover. El SSE de compatibilidad entrega una respuesta ya terminada. Faltan los escenarios dirigidos de respuesta upstream lenta y failover cerca del presupuesto, y la prueba concurrente del último cupo compartido; las pruebas de límites/cancelación existentes no sustituyen esos escenarios.
3. **Dictado físico y edición — §11.** Falta evidencia de micrófono real → MediaRecorder de la aplicación instalada → transcripción → inserción en el campo seleccionado, manteniendo foco y sin autoenvío. También falta validación de WebM/Ogg/MP4 reales del WebView, español hablado y precisión en condiciones de uso. La aceptación disponible demuestra WAV sintético inglés.
4. **Traducción comprometida — §11.** El motor local solo ofrece traducción de Whisper hacia inglés. Falta demostrar original más traducción desde la aplicación y resolver los demás idiomas destino mediante un componente autorizado; una API de chat sin credenciales no completa esta función.
5. **Lectura y cancelación de voz — §11–§12.** Falta comprobar audio audible por la salida física y controles de iniciar/pausar/detener en la aplicación instalada. El backend no implementa pausa de un WAV ya entregado: la realiza el reproductor cliente. Falta la prueba de Esc durante TTS/ASR activos en la aplicación distribuida, con estado final correcto y sin resultado tardío. La cancelación real del proceso Blender y de trabajadores de inferencia dispone de pruebas dirigidas; no certifica por extensión los otros recorridos.
6. **Memoria completa del asistente — §10.** El ciclo comprobado recibe intención e inputs estructurados. Falta demostrar desde la interfaz instalada una tarea expresada en lenguaje natural, su interpretación, guardado y reutilización posterior. `model_calls_used:0` identifica la ruta determinista sin invocación al modelo; **no constituye un contador global instrumentado de llamadas**, ni mide una futura interpretación por modelo. Falta esa instrumentación. Las pre/postcondiciones descriptivas de las recetas registradas pueden estar vacías y los pasos no fijan todavía versiones de herramienta; falta cerrar la vigencia/versionado exigidos para procedimientos más amplios.
7. **Reconciliación de interrupciones — §9.** `unknown` bloquea correctamente la repetición automática, pero aún no hay un flujo implementado que observe el efecto externo y reconcilie ese estado antes de decidir una recuperación. No debe presentarse como una transacción atómica sobre la aplicación externa.
8. **Dependencias y generalidad — §9 y §13.** El render requiere Blender instalado en este PC. La capacidad demostrada es la escena fija; no equivale a soporte universal de aplicaciones, edición libre de Blender ni automatización arbitraria desde lenguaje natural. La prueba del sidecar se ejecutó en el PC de compilación; no demuestra un Windows limpio sin dependencias del usuario.
9. **Aceptación del producto instalado — corrección §3–§5 y maestro §8, §11–§13.** Este informe de backend no aporta por sí mismo evidencia del instalador/acceso directo, interfaz nativa y hotkeys con otra app enfocada, máscara de clics, posición/DPI/pantallas, identidad tras reapertura, música real, grabación reproducible ni últimos nueve segundos del temporizador. El informe final debe vincular las pruebas específicas de esos recorridos; un PASS del sidecar no los certifica.

Hey Axx, IAI, BitNet, invisible_dots y extensiones móviles permanecen **FUTURO · NO ACTIVO**, conforme al maestro. No se activaron escucha permanente, facturación ni compras.
