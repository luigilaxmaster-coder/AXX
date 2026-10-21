# Capacidades conectadas y límites

La fuente de verdad en ejecución es `axx_list_capabilities`. Incluye descripción, esquema, handler, permisos, disponibilidad y motivo, tiempo máximo, cancelación, efecto, verificación, política de reintento y versión. Esta página resume familias y no sustituye ese registro.

| Familia | Disponibilidad |
|---|---|
| Telemetría, PID, archivo de texto verificado | Ejecutores backend existentes; archivo exige aprobación existente y destino nuevo dentro de artifacts. |
| Notas, tareas, temporizador, concentración, cálculo, conversión, análisis y presencia | Adaptador `axx.ui.local` llama `runLocal` original. Requiere UI nativa con heartbeat y handler anunciado. |
| Forma, paleta, material, movimiento y tamaño | `axx.ui.identity`, autoridad visual actual y readback; la tarea no reemplaza la identidad guardada. |
| Apertura de paneles | `axx.ui.panel` abre herramientas y paneles existentes. Conserva la órbita. |
| Transformaciones de texto | `axx.ui.text_transform` usa función determinista existente y devuelve resultado; no envía mensajes. |
| Música local | `axx.ui.music` controla la biblioteca ya seleccionada. No descarga ni conecta Spotify. |
| Lector | `axx.ui.reader` usa lector actual. Estado software no prueba sonido físicamente audible. |
| Cronómetro | `axx.ui.stopwatch` consulta/inicia/pausa/marca vueltas. Reset destructivo no se introdujo sin su autorización original. |
| Dictado | `axx.ui.dictation` consulta/abre/detiene; captura e inserción con permisos del módulo existente. Abrir no acredita transcripción. |
| Grabación | `axx.ui.screen` consulta/abre/detiene; iniciar/guardar sigue el selector autorizado. Un Blob no acredita archivo guardado en disco. |
| Traducción, imágenes, subtítulos, selección de archivos, espacios de trabajo | Módulos originales conservados. Se abren desde el panel; operaciones que requieren selección/permiso/inferencia adicional no se anuncian como automatización física ya verificada. |
| Blender fijo | Adaptador presente pero bloqueado por validación física pendiente. |
| 7562 comandos documentales importados | Conservados y no ejecutables: sin adaptador validado. No se convierten a herramientas shell ni se muestran habilitados por existir el catálogo. |
| Spotify, otras pestañas, automatización de todas las apps | Dependencias/autorización específica no acreditadas. No las habilita el login del modelo. |

Aliases y handlers previos están en [inventario de línea base](../../evidence/axx-connect/inventory-baseline.md). Las pruebas reales del host/ejecutor y las controladas del contrato se reportan por separado. Una familia que requiera UI queda no disponible si falta heartbeat; no se conserva un falso conectado al cerrar Axx.
