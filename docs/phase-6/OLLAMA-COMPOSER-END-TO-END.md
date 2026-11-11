# Ollama real desde el compositor normal — extremo a extremo y arranque en frío

Candidata `4f4e18b` (paralela, WebView2 real, backend empaquetado). Ollama real aislado en `127.0.0.1:11486` (sin nube, sin descargas, pesos ya instalados, detenido al terminar). La aplicación apunta a `127.0.0.1:11485`, donde un **proxy de captura** de la prueba registra cada petición y reenvía a Ollama (excepto marcadores deterministas B3–B6, respondidos por el proxy). Proveedor `ollama-qwen` → `qwen2.5:7b-instruct`, capacidades `text,tools`, modo `auto_safe`, casilla «Herramientas de Axx en el chat local» activada (opt-in conservado), `timeout_seconds=60`, `global_deadline_seconds=70`.

## Prueba B — la petición obligatoria

Entrada en el compositor: **«AXX, muéstrame el estado actual de CPU y memoria RAM.»** (chat nuevo, modelo caliente)

| Eslabón | Observado |
|---|---|
| Compositor → bandeja/planificador | No intercepta (herramientas activas): llega al chat |
| Petición al proveedor | 1 petición; herramientas anunciadas: `axx_system_telemetry`, `axx_architecture_status`, `axx_artifact_write` (ni shell ni procesos); guía de sistema incluida |
| Llamada estructurada del modelo | `axx_system_telemetry` con `{}` |
| Ejecutor | `ConnectService → CommandService → ActionExecutor`, `origin=axx-provider`, `state=succeeded`, `postconditions_passed=true`, **266 ms** |
| Datos reales | `cpu_percent 27.8`, `memory_used_mb 15 588.1` de `16 088.5` (GlobalMemoryStatusEx / GetSystemTimes) |
| Interfaz | Tarjeta de recibo: `CPU: 27.8 % (12 núcleos lógicos) · RAM: 15.2 GB en uso de 15.7 GB (96.9 %) · Disco libre: 118.41 GB de 952.6 GB`; el chat solo dice «Acción verificada en Axx. Consulta sus detalles en Comandos.» |
| Recibo persistido | Diario de comandos (`/axx-api/commands/operations`), `chat-tool-3177cfa2…` |
| Tiempos | Total UI 5.6 s: proveedor 4.4 s (modelo caliente) + ejecución 0.27 s |
| Privacidad | En el turno siguiente, ningún cuerpo enviado al proveedor contiene `memory_used_mb`, `cpu_percent`, «núcleos lógicos», «Disco libre» ni los valores concretos |

Rechazos, errores y cancelación (misma app, proveedor simulado en red para B3–B6; real para B7/B8):

| Caso | Resultado |
|---|---|
| Argumentos inválidos (`axx_artifact_write` sin `content`) | `blocked`, 0 operaciones, sin archivo |
| Herramienta fuera del catálogo (`axx_shell_powershell`) | `blocked`, 0 operaciones |
| Campos de autoridad (`approved`, `channel`) en una herramienta sin parámetros | `blocked` |
| Escritura (`axx_artifact_write`) en `auto_safe` | `awaiting_approval`; sin archivo hasta aprobar |
| Casilla apagada | No se ofrecen herramientas; sin recibo |
| Cancelación con el modelo real trabajando | No se crea operación; ver `BUSY` abajo |
| **Un texto del modelo sin llamada estructurada nunca cuenta como ejecución** | Con llama3.2:1b: esquema/JSON como texto o llamada mal formada → «Resultado de herramienta sin confirmar» |

Cancelación y capacidad: tras cancelar, las **consultas inmediatas** devolvieron `BUSY: Inference capacity is busy (HTTP 409)` en dos intentos separados 8 s; la tercera (≈25 s después de cancelar) completó. El router no puede interrumpir la lectura en curso del proveedor; la UI se libera, el slot de inferencia no, hasta que el modelo termina. No se «arregló» ocultándolo.

## Prueba C — arranque en frío y el timeout de 60 s

Procedimiento: `ollama /api/generate keep_alive=0` → `/api/ps` vacío (modelo descargado) → misma petición del compositor, **sin tocar el timeout** (60 s; el valor por defecto del producto es 20 s por intento, 70 s globales).

Resultado en la UI: **error `UPSTREAM_TEMPORARY: Transport connection error: timed out`**, cliente cerrado a los 60.0 s. El modelo **terminó igualmente en 63.95 s** y la llamada a la herramienta era correcta (`axx_system_telemetry`); simplemente Axx ya se había rendido.

Desglose medido por Ollama para la **misma petición** (3 844 caracteres, 874 tokens de prompt: contrato de conversación 2 222 car. + sistema 321 + herramientas 865 + guía + mensaje):

| Fase | Frío (tras reposo) | Caliente (misma petición) |
|---|---|---|
| Carga del modelo | **10.24 s** | 0.30 s |
| Evaluación del prompt (874 tokens, CPU) | **52.45 s** | 0.21 s (caché de prefijo) |
| Generación (20 tokens) | 3.87 s | 3.83 s |
| **Total Ollama** | **66.59 s** | **4.35 s** |
| Ejecución de la herramienta en Axx | 0.27–0.30 s | 0.27–0.30 s |

**Conclusión:** el timeout lo causa la **evaluación del prompt en CPU (~79 % del tiempo en frío) más la carga del modelo (~15 %)**; la inferencia generativa (6 %) y la ejecución de la herramienta (<0.5 %) son irrelevantes. En caliente el mismo turno cuesta 4–6 s. Un segundo intento tras el primer fallo funciona porque Ollama completó y cacheó el prefijo (observado en la fase anterior: intentos 2 y 3 pasaron).

**Por qué no se subió el timeout:** el techo global es 70 s y el frío total fue ~66.6 s en esta máquina (16 GB, CPU, 12 hilos): subirlo ocultaría que un primer turno de 7B en CPU tarda >1 min y que el límite por intento por defecto (20 s) es inalcanzable para este modelo. Opciones razonadas (no aplicadas): (a) reducir el prompt enviado a modelos locales cuando hay herramientas (~12 % es la guía añadida en esta fase, ~58 % el contrato de conversación), (b) precalentar el modelo al conectar el proveedor, (c) un indicador de «cargando el modelo» en el compositor, (d) recomendar un modelo menor/GPU para uso interactivo. Pendiente de decisión del propietario.

## Datos reales de esta fase (resumen de ejecuciones)

- Candidata empaquetada + qwen2.5:7b-instruct: B1 PASS (modelo caliente).
- En el arnés de navegador con backend real (no empaquetado): qwen2.5:7b PASS en 4 ejecuciones con modelo caliente (1 timeout tras reposo, documentado); llama3.2:1b variable.
- Un turno con un chat de historial largo tardó **58 s** con el modelo caliente (B1 de la primera tanda): la latencia crece con el historial/contexto en CPU; en chat nuevo, 4.4 s.
