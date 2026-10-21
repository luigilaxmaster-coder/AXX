# Axx Connect: inventario previo de implementación

Inspección de fuentes: 20 de octubre de 2026. Este inventario describe la línea base anterior a Axx Connect; no constituye aceptación física. No se ejecutaron operaciones del usuario al levantarlo.

## Proyecto y compilación

- Raíz real: `C:\Users\luigi\Desktop\Axx assistant`; `git status` devuelve `not a git repository`. No hay rama/commit atribuible. Conservar copias por archivo antes de editar.
- Interfaz canónica: `1.AXX/Axx.html`, JavaScript embebido compilado y CSS/HTML, con scripts externos `1.AXX/scripts/native-voice.js` y `command-library.js`.
- Host nativo: Rust 2024, Tauri 2.12.4, `src-tauri/src/lib.rs` y `resident.rs`. CLI npm fijada en 2.12.3; paquete raíz 0.20.3, `package-lock.json`. No framework React detectado en la UI canónica.
- Backend: Python 3.11+ por contrato, biblioteca estándar para servidor/router, procesos aislados; PyInstaller en `axx-backend.spec`. ASR local tiny y ai-memory ya empaquetados por la compilación existente; no se requieren modelos generativos locales para Connect.
- Build: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1`; comprueba hashes e impide deriva de fuente, usa lock `build/.windows-delivery.lock`, construye backend y NSIS.
- Pruebas reales disponibles: `python -m unittest discover -s backend -p test_*.py -v`, `node 1.AXX/scripts/test-desktop-frontend.cjs`, `node 1.AXX/scripts/test-command-library.cjs`, `cargo test --manifest-path src-tauri/Cargo.toml --lib`. Baseline histórico: `python scripts/verify-baseline-windows.py` cierra SQLite sin cambiar asserts originales. Scripts antiguos `scripts/test_runtime_guarantees.py` referencian `ProcessJobManager`, clase ausente en el módulo activo; no usarlos como aceptación actual sin reparar primero.

## Capacidad ejecutable y documentación

La fuente actual de comandos backend es `backend/commands.py:ADAPTERS`, ejecutada por `CommandService.prepare/execute/get/cancel/operations` y el mismo `ActionExecutor`.

| ID existente | Handler real | Entradas | Permisos y evidencia |
|---|---|---|---|
| `axx.system.telemetry` | `system_telemetry`, `SystemTelemetryTool` | `{}` | Lectura local; SO/arquitectura/Python/disco/PID; validación estructural y espacio no cero. No mide CPU/RAM/GPU. |
| `axx.process.inspect` | `process_state_inspector`, `ProcessStateTool` | `pid` entero opcional 1..4294967295 | Windows OpenProcess/SYNCHRONIZE; presencia del PID real, sin afirmar estado de ventana. |
| `axx.artifact.write` | `file_artifact_writer`, `FileArtifactTool` | `path` relativo nuevo, `content` texto hasta 65536 bytes | Aprobación existente por parámetros; dentro de artifacts, sin overwrite/reparse/device paths; existencia, tamaño y SHA256 leídos. |
| `axx.blender.fixture` | `blender_render_fixture`, `BlenderRenderFixtureTool` | `filename` PNG simple | Adaptador presente pero catálogo bloqueado por validación física pendiente. No habilitar por importar metadatos. |

Aliases backend: `estado del sistema`, `información del sistema`, `informacion del sistema`; `estado de axx`; ID exacto; `/comando ID {JSON}`. `source` original permite `text` y `voice`. JSON duplicado, NaN y parámetros desconocidos se rechazan. Operaciones se persisten en `command_runs`; ID repetido no repite efectos; reinicio de `running` produce `unknown`, otros no terminales `expired`.

`resources/command-library.json` contiene **7562 comandos importados documentales**; ninguno tiene adaptador ejecutable. Provenance: total 7562, principal 7351, suplementos 211, recetas completas 4. `CommandService` fuerza `DOCUMENTED_NOT_EXECUTED` y bloquea todos; preservar motivos y aliases documentales.

## Herramientas reales de interfaz

El estado de estos módulos pertenece a sus objetos/UI actuales. Para Connect usar llamadas tipadas al mismo objeto y leer de vuelta el estado; no duplicar notas, temporizadores ni preferencias en otra base. No llamar `Companion.send` desde una herramienta.

| Módulo | Operaciones existentes y firma | Lectura/verificación existente |
|---|---|---|
| Temporizador/concentración | `Axx.companion.runLocal({type:'timer',ms,kind:'timer'\|'focus'})`; `runLocal({type:'pause'\|'resume'\|'cancel'})`; `Axx.time19.adjust(deltaMs)`, `nextPhase()` | `Axx.app.store.data.timer`, `Axx.remaining(timer)`, `time19.routine/history`; `persistTimer()` sincroniza host. Inicio debe comprobar estado resultante. |
| Notas | `runLocal({type:'note',text})`, `runLocal({type:'notes'})`, `runLocal({type:'searchNotes',text})`; `app.newNote/saveNote/deleteNote` dependen de formulario/selección | `app.store.data.notes`; límite 200 notas, texto 100000 caracteres; guardado original `LocalStore.save()` puede fallar. |
| Tareas | `runLocal({type:'todo',text})`, `runLocal({type:'completeTodo',index})`, `runLocal({type:'todos'})` | `companion.data.todos`; `companion.save()` y lectura posterior. |
| Cálculo/unidades/texto | `Axx.safeCalculate(text)`; `Axx.convertUnit(value,from,to)`; `Axx.analyzeText(text)`; `Axx.transformText(text,action)` con clean/dedupe/sort/upper/lower/json/links | Funciones finitas sin eval; resultado concreto. `utilities.changeText(action)` modifica editor y guarda; `utilities.snapshot()`. |
| Cronómetro | `Axx.utilities.toggleWatch()`, `markLap()`; reset original asigna `Axx.emptyStopwatch()` y llama `renderWatch/save` tras confirmación | `utilities.stopwatch`, `Axx.stopwatchElapsed`, `utilities.snapshot()`; reset borra vueltas y no debe ejecutarse como lectura. |
| Paneles/órbita | `Axx.companion.openFeature(id)`, `openFamily(id)`; `Axx.organic.newWorkspace/arrange/fold/openDesk()`; `resident.summon/home/fold` | `Axx.FEATURES`, panel visible, `organic.data.workspaces/surfaces/snapshot`, `resident.geometry`; no clonar nodos. |
| Identidad | `Axx.stability20.updateSettings({form,palette,motionStyle,...})`; `app.persistStudio20/syncSurfaceControls`; `symbiosis.applyFinish20('obsidian'\|'prism'\|'smoke')`; `companion.setSize(px,true)` | `app.store.data.settings`, renderer `getStudio/getFinish/getCamera20`, `resident.size`, `axx-studio-v2` leído. Formas 0..23, paletas 0..8, tamaño 160..640. |
| Música local | `Axx.actions.music.play/pause/next/previous/select(index)/setShuffle(bool)/setRepeat('off'\|'all'\|'one')/seek(deltaSeconds)/remove(index)/move(index,delta)` | Instancia LocalMusic: `audio.paused/currentTime/duration/volume`, tracks/index/order; `Axx.music15` es presentación. Carga de archivos requiere selección autorizada. |
| Lectura | `Axx.symbiosis.reader.setText(text,title)`, `play/pause/stop/jump(index)`; nativo reemplazado por `native-voice.js` con interfaz equivalente | reader state/chunks/index; reproducción física audible requiere evidencia adicional. |
| Dictado/inserción | `Axx.voice13.enter/begin/pause/stop/applyPending/undo`; captura nativa puenteada por `native-voice.js` | status/transcript/pending/target, snapshot; insertar y enviar siguen separados. Micrófono requiere permiso. No guardar transcripciones en logs. |
| Traducción | `Axx.symbiosis.translate/cancelTranslation`, campos translation-source/from/to/engine; `voice13.translateManual18` usa cola de traducción preparada | translation-output/state y disponibilidad de `window.Translator`; vía provider llama `brain.chat` y debe impedir delegación recursiva desde agente. |
| Grabación | `Axx.capture19.start()` inicia ruta de permisos sin esperar grabación; `Axx.actions.screen.toggle/stop`; `capture19.save(as,automatic)` | screen.state/blob/saved; capture19.filename/saveStatus/saving; comenzar no significa guardado. File picker y getDisplayMedia requieren interacción. |
| Imágenes | `Axx.utilities.selectImage(file)` y `exportImage()` tras opciones DOM | `utilities.image`, image-error/target y Blob; descarga solicitada no prueba archivo escrito. |
| Subtítulos | `Axx.parseSubtitles(text)`, `Axx.subtitlesSrt(cues)`, `symbiosis.loadSubtitles(file)`, `loadMedia(file)` | cues y estado DOM; archivos son selección local autorizada. |
| Archivos/alcance | `Axx.reach.importFiles(files)`, `preview(resource)`, `perform(resource,'open'\|'fetch')`, `attach(resource)` | Inventario seleccionado y referencias autorizadas; no lectura arbitraria del disco. `app.hashFile()` depende del archivo de formulario. |
| Apps Windows | backend `/desktop/discover/authorize/revoke-all/launch`; IDs notepad/calc/explorer | Aprobaciones por sesión; launch devuelve `dispatched`, PID, verified=false. No hay confirmación actual de ventana. |
| Datos/preferencias | `companion.backup/importBackup/clearData`, presets, apariencia, layout, sonido | Exportar/importar y limpiar tienen confirmaciones/validaciones propias; conservar. |

Catálogo de paneles se genera en tiempo de ejecución en `Axx.FEATURES`: experience, stopwatch, textstudio, images, reach, chat, timer, notes, todos, calculator, files, focus, focusNow, appearance, studio, lab, audio, tour, sound, ai, settings, inbox, help; además dictation, reader, translation, transcript, morphui, roadmap, organic y extensiones de acciones music/screen/layout11. `focusNow` ejecuta un inicio inmediato aunque use `openFeature`; las muestras lab/tour no son ejecuciones de herramientas.

## Aliases de voz/texto existentes

- `Axx.parseIntent` (HTML 1937): guarda/anota/nota/apunta; añade/agrega/crea/apunta/pon tarea; temporizador/timer/cuenta atrás/concentración/focus/pomodoro; analiza/cuenta; busca en notas; calcula/cuánto es/resuelve; convierte/pasa; completa/marca como hecha/termina tarea; pausa/reanuda/cancela; mis notas/tareas; hora/fecha; ven/acércate; sígueme; quédate; ocúltate; ayuda/saludos.
- `UtilityDesk.bindCommands` (10109): inicia/reanuda/pausa cronómetro, marca vuelta, abre taller/editor de texto, abre preparador de imágenes.
- `Symbiosis.setupCommands` (11079): abre lector/dictado/traductor/transcripción/subtítulos/modos; pausa/reanuda/detén lectura; léeme texto. Lectura automática de otra pestaña permanece pendiente.
- `OrganicDesk.hooks` (11430): crea/abre cuaderno, organiza paneles/superficies, recoge/repliega, mesa de trabajo.
- `Stability20.installAllCommands` (17549): activar/silenciar/cambiar voz, repetir/di texto, forma siguiente/anterior/aleatoria/por número/nombre (24 aliases), paletas (9), acabados, estilos de movimiento (6), tamaño, volumen, base, plegar y abrir paneles. Alias música contiene llamadas a `music15.demo/toggle/playing` ausentes: no tratarlas como capacidad verificada; usar LocalMusic real.
- `ReachHub` usa `parseReachCommand`: abre/trae/busca/muestra recursos seleccionados y comandos de alcance, nunca shell.

## Transporte y persistencia previos

- Frontend `Axx.backendRequest` → Tauri `backend_request` → HTTP loopback privado de `backend/server.py`; el token nunca se entrega al frontend. Host y Origin validados, límite de cuerpo, rutas `/axx-api` acotadas.
- Datos `%LOCALAPPDATA%/Axx`: `providers.json`, `state.db`, artifacts, ai-memory y `native-window.json`; backend migración mediante backup SQLite; ninguna sobrescritura de configuración existente.
- Identidad: `axx-studio-v2` es autoridad original de forma/material/cámara; `IdentityStore` SQLite guarda snapshot sincronizado y elimina claves temporales. Layout y preferencias en claves axx.companion.v4, axx.live.v1, axx.utilities.v6, axx.voice13.prefs, axx.time19, axx.capture19, axx.music15, axx.orbit12/17, axx.organic.v1 y resident.panel-pos.
- Memoria: `ProceduralMemory.register_recipe(id,intent_key,steps,schema,preconditions,postconditions,status,env_fingerprint)`; `find_recipe`, `execute_recipe`; tablas recipes, recipe_versions, recipe_attempts. Endpoint de registro exige operación ActionExecutor persistida y postcondiciones verificadas. ai-memory ya integrado mediante proceso propio y autenticado, opcional; SQLite sigue autoridad.
- Inferencia anterior: `InferenceAdapter.route(envelope)` limita una petición por conversación y dos globales; timeout de pared 70s; router `allow_paid:false`; procesos manejados con Job Object.
- Autenticación anterior: auth ChatGPT propia con DPAPI y PKCE, catálogo hardcoded gpt-4o y petición OAuth a chat/completions, fallback Ollama. Esto no demuestra elegibilidad ni inferencia oficial vigente; sustituir por interfaz oficial admitida y no reutilizar tokens extraídos.

## Atajos y cancelación previos

- Rust `start_global_hotkey_thread`: Alt+Shift+A invoca/sigue; doble pulsación bajo 450ms vuelve base; MOD_NOREPEAT.
- Hook Esc global cuando actividad/follow/operaciones/requests: `cancel_active` emite axx-cancel y llama commands/cancel, actions/cancel y chat/cancel. Cancelación no significa rollback.
- Otros locales existentes: Ctrl+K búsqueda, Alt+Shift+D dictado, Alt+Shift+R pausa grabación y Alt+Shift+S detiene; paneles conservan foco y rutas propias de Escape.

## Límites observados

- Spotify endpoints responden NOT_IMPLEMENTED; tabs multimedia requieren extensión autorizada no demostrada; icono desktop devuelve unavailable; autostart no está implementado por host.
- SSE previo empaqueta una respuesta completa al final; no es streaming del proveedor.
- No MCP Axx ni paquete Axx Connect existente en las rutas de aplicación inspeccionadas antes del cambio; la inspección de instalaciones globales corresponde a la fase de plugin.
- No se presume funcionamiento físico por tener handler: ASR, audio audible, grabación/selección de pantalla, ventana de app y dictado en campos reales requieren pruebas separadas.
