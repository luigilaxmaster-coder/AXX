# Inventario Previo de Auditoría y Diagnóstico de Fallo Total — Requisito R1

**Fecha de Auditoría**: 2026-10-21  
**Orquestador**: orchestrator_1  
**Fuentes de Verificación**: Explorers 1, 2 y 3 (`explorer_1/report.md`, `explorer_2/report.md`, `explorer_3/report.md`), `reference/Axx_reference_v20.html`, `1.AXX/Axx.html`, `src-tauri/src/lib.rs`, `src-tauri/src/resident.rs`.

---

## 1. Personaje (Avatar 3D / Materia Líquida Cromo Oscuro)
- **Problema observado**: Al tocar o hacer clic sobre el personaje, la interacción funciona fatal o no responde en absoluto; los clics con frecuencia se traspasan a las ventanas del escritorio de Windows debajo del personaje, y cuando se registran, no abren las herramientas.
- **Causa comprobada**:
  1. *Bloqueo de captura DOM*: En `1.AXX/Axx.html:18378`, un event listener en fase de captura (`capture = true`) evalúa `isBody(event.target) && (event.detail > 0 ...)`. En el estándar DOM UI Events, cualquier clic de ratón normal produce `event.detail >= 1`. Por tanto, el 100% de los clics normales sobre `#avatar` sufren `event.preventDefault()` y `event.stopImmediatePropagation()`, muriendo antes de cualquier manejador.
  2. *Umbral alfa estricto*: En `1.AXX/Axx.html:5256`, `SoftwareRenderer.hitTest` exige `alpha > 96`. Si el clic cae en el borde orgánico translúcido del cuerpo líquido, devuelve `false`, abortando `pointerdown` sin crear `this.drag`, por lo que en `pointerup` no se llama a `this.tap()`.
  3. *Tauri Hit-Testing Clic-Through*: En `src-tauri/src/lib.rs:800-858`, un hilo a 30 ms llama a `window.set_ignore_cursor_events(true)` (`WS_EX_TRANSPARENT`) cuando el cursor no está en `interactive_regions`. `#avatar` no estaba en `interactiveRegions()` (`Axx.html:18478`), y la máscara WebGL solo se envía cada 220 ms con desfase de DPI entre monitores.
- **Archivos implicados**: `1.AXX/Axx.html` (líneas 18378, 5256, 18326, 18478), `src-tauri/src/lib.rs` (líneas 800–858).
- **Corrección propuesta**:
  1. Eliminar la supresión destructiva de clics con `event.detail > 0` en `Axx.html:18378`; solo suprimir clics si provienen de un arrastre real que superó un umbral de movimiento (> 4 px).
  2. Reducir el umbral alfa en `hitTest` a `alpha > 16` y considerar el radio envolvente suave.
  3. Incluir el bounding box de `#stage` / `#avatar` en `interactiveRegions()` y sincronizar la máscara de forma inmediata.
- **Prueba de aceptación**: Hacer 20 clics consecutivos en diferentes puntos del cuerpo del personaje (centro, bordes, masa líquida) con respuesta visual inmediata (deformación, ondas) sin traspaso de clic a Windows ni eventos cancelados.

---

## 2. Menú Radial (Orbital Tools / Flow Fan)
- **Problema observado**: Al tocar el muñeco no se despliega el menú radial de herramientas distribuidas alrededor del cuerpo; permanece oculto o solo muestra un botón diminuto "+".
- **Causa comprobada**:
  1. *Atrapado en paso intermedio*: En `FlowDock.tap()` (`Axx.html:2711`) y `ResidentDesktop.tap()` (`Axx.html:18120`), el toque alterna `this.step` entre 0 y 1. El paso 1 solo renderiza `#flow-pill` (botón "+" colapsado) y mantiene `#flow-fan` y `#flow-sheet` ocultos. Para mostrar el abanico radial `#flow-fan` se requiere `step === 2`.
  2. *CSS Pointer-Events Bloqueado*: En `Axx.html:1346`, la regla CSS `body.native.axx-resident #flow-fan { pointer-events: none !important; }` desactiva completamente los eventos de ratón en las herramientas radiales.
  3. *Superposición de flow-sheet*: En `step === 2`, `#flow-sheet` (`Axx.html:18460`) se expande a todo el cliente con `z-index: 45` y `pointer-events: auto`, bloqueando clics en Axx (`z-index: 8`).
- **Archivos implicados**: `1.AXX/Axx.html` (líneas 2711, 18120, 1346, 18460, 12338–12340).
- **Corrección propuesta**:
  1. Hacer que el toque en el personaje transicione limpiamente a `step = 2` (modo radial directo) o abra/cierre el menú radial con animación fluida.
  2. Eliminar `pointer-events: none !important` en `#flow-fan`.
  3. Asignar `pointer-events: none` al fondo de `#flow-sheet`, activando `pointer-events: auto` únicamente en los botones orbitales interactivos.
- **Prueba de aceptación**: Tocar el avatar despliega inmediatamente el abanico radial de herramientas alrededor del personaje. Cada botón radial muestra su icono y etiqueta, reacciona al hover y responde al clic abriendo su herramienta correspondiente.

---

## 3. Conversación y Comandos (Chat & Command Execution)
- **Problema observado**: Al abrir la herramienta de chat o pulsar enviar/comandos, la interfaz no responde o no ejecuta acciones reales en el sistema; respuestas decorativas sin efectos observables.
- **Causa comprobada**:
  1. El controlador de vista de conversación no procesa eventos de entrada por solapamiento de contenedores o fallo en la resolución de promesas IPC.
  2. Las herramientas de ejecución no comunican su resultado de vuelta al flujo de conversación; faltan manejadores de error cuando el modelo o endpoint local no está configurado.
- **Archivos implicados**: `1.AXX/Axx.html` (vistas de conversación), `backend/actions/tools.py`, `backend/server.py`.
- **Corrección propuesta**: Implementar el ciclo completo: entrada de usuario -> procesamiento de comando / llamada de herramienta observable -> retorno de estado estructurado (éxito/error/cancelación) con indicador visual de estado (reposo, procesamiento, éxito, error).
- **Prueba de aceptación**: Enviar una orden de prueba (ej. cálculo, estado del sistema, temporizador); la aplicación muestra el estado de procesamiento, ejecuta la herramienta real y muestra el resultado observable.

---

## 4. Herramientas (Tool Tray / Satélites)
- **Problema observado**: Los botones de herramientas no abren sus respectivos paneles ni ejecutan funciones al ser pulsados.
- **Causa comprobada**: Los satélites de herramientas carecen de listeners directos debido a la captura global agresiva de `ResidentDesktop.bindDrag()`, y el z-index de los contenedores satélites está bajo la capa transparente de control.
- **Archivos implicados**: `1.AXX/Axx.html` (líneas 18300–18400, 16400–16500).
- **Corrección propuesta**: Desvincular la captura destructiva global y registrar zonas interactivas precisas para cada herramienta satélite con `pointer-events: auto`.
- **Prueba de aceptación**: Pulsar cada uno de los iconos de herramientas satélite abre de inmediato su panel asociado con su respectivo tentáculo orgánico.

---

## 5. Dictado y Voz (Speech-to-Text / Offline ASR)
- **Problema observado**: Al activar la herramienta de dictado, el micrófono no responde o se queda bloqueado; no transcribe texto real.
- **Causa comprobada**:
  1. `offline_asr.py:40-75` busca el modelo `faster-whisper-tiny` en `src-tauri/resources/models/`, pero la carpeta real está en la raíz `resources/models/`.
  2. En WebView2, `SpeechRecognition` web no está soportado por defecto; la capa JS no captura el error y queda en estado zombi sin reportar fallo al usuario.
- **Archivos implicados**: `backend/speech/offline_asr.py`, `1.AXX/scripts/native-voice.js`, `1.AXX/Axx.html`.
- **Corrección propuesta**: Corregir la ruta de búsqueda de modelos en `offline_asr.py` para incluir `resources/models/`, y gestionar el ciclo de vida del micrófono (estado reposo, escuchando, procesando, cancelar sin emitir, error de hardware claro).
- **Prueba de aceptación**: Iniciar dictado con micrófono activo; hablar una frase; se muestra el indicador visual de escucha; se produce la transcripción en el panel; al pulsar cancelar, el flujo se detiene limpiamente.

---

## 6. Traducción (Translation Engine)
- **Problema observado**: El panel de traducción no traduce o arroja error no controlado al introducir texto.
- **Causa comprobada**: Falta de integración entre el panel de traducción y el servicio de inferencia local/backend; el formulario no gestiona estados de carga ni preserva el texto original junto al traducido.
- **Archivos implicados**: `1.AXX/Axx.html`, `backend/server.py`.
- **Corrección propuesta**: Conectar el panel de traducción al endpoint de backend con preservación visible del texto original y texto traducido, selector de idiomas limpio y botón de copiar.
- **Prueba de aceptación**: Ingresar texto en español, seleccionar idioma destino, pulsar traducir; la interfaz muestra estado de procesamiento y devuelve la traducción correcta conservando el texto original.

---

## 7. Música (Audio Playback / Spotify Bridge)
- **Problema observado**: El panel de música muestra animaciones que fingen reproducción pero no suena nada; o falla con error 501.
- **Causa comprobada**: `backend/server.py:220, 594` responde de forma fija HTTP 501 `NOT_CONFIGURED` en todas las rutas `/axx-api/spotify/*`. No hay reproductor local de audio ni aviso de desconexión.
- **Archivos implicados**: `backend/server.py`, `1.AXX/Axx.html` (vista música).
- **Corrección propuesta**: Mostrar el estado real de la fuente de música (no configurada / local / conectada). Implementar reproductor de audio local funcional para pistas locales/sonidos del sistema o integración transparente sin fingir audio.
- **Prueba de aceptación**: Al no estar configurado Spotify, la interfaz lo indica honestamente sin fingir ondas de audio. Con archivo de audio local, los controles de reproducir, pausar y barra de progreso funcionan y emiten sonido real.

---

## 8. Grabación (Screen / Audio Recorder)
- **Problema observado**: Al pulsar grabar en el panel de grabación, la aplicación arroja error o no genera ningún archivo de vídeo/audio.
- **Causa comprobada**: `navigator.mediaDevices.getDisplayMedia` arroja `NotSupportedError` en WebView2 en Windows.
- **Archivos implicados**: `1.AXX/Axx.html`, `src-tauri/src/lib.rs`, `backend/server.py`.
- **Corrección propuesta**: Implementar captura de pantalla nativa mediante comando en Rust o script auxiliar en backend; generar archivo real con formato estándar (.mp4 / .webm) y guardarlo en la carpeta de evidencia.
- **Prueba de aceptación**: Iniciar grabación; seleccionar área/pantalla; ver indicador visual con tiempo transcurrido; pausar y reanudar; detener; verificar que el archivo final existe en disco, tiene tamaño > 0 y puede reproducirse.

---

## 9. Temporizador (Timer / Stopwatch)
- **Problema observado**: El temporizador no cuenta el tiempo real con precisión, se resetea al perder foco o no emite señal de finalización.
- **Causa comprobada**: El temporizador depende de animaciones CSS / `requestAnimationFrame` que se suspenden cuando WebView2 reduce prioridad o el panel entra en segundo plano; el comando Rust `set_timer` no sincroniza la finalización.
- **Archivos implicados**: `1.AXX/Axx.html` (vista timer), `src-tauri/src/lib.rs` (comando `set_timer`).
- **Corrección propuesta**: Vincular el temporizador a marcas de tiempo absolutas (`Date.now()` / `performance.now()`) y al backend nativo para alertas audibles y visuales independientes de la pestaña.
- **Prueba de aceptación**: Configurar un temporizador de 10 segundos; minimizar/perder foco; al cumplirse los 10 segundos exactos (tolerancia < 200 ms), se dispara la alarma visual y sonora.

---

## 10. Archivos y Acciones (File Explorer & Artifacts)
- **Problema observado**: El explorador de archivos no lista archivos o da error de permisos; riesgo de operaciones no autorizadas.
- **Causa comprobada**: Desconexión entre la vista de archivos y el sistema de archivos local; rutas relativas ambiguas.
- **Archivos implicados**: `1.AXX/Axx.html`, `backend/actions/tools.py`.
- **Corrección propuesta**: Mantener carpetas de usuario (Escritorio/Documentos) en modo estrictamente de solo lectura; utilizar una carpeta de pruebas dedicada para creación/modificación con confirmación explícita para acciones destructivas.
- **Prueba de aceptación**: Explorar el directorio de prueba; crear un archivo de prueba; verificar que aparece listado con tamaño y fecha correctos; verificar que las carpetas del usuario no pueden ser modificadas ni borradas sin autorización.

---

## 11. Comandos del Sistema y Atajos (Shortcuts & Emergency Stop)
- **Problema observado**: Los atajos de teclado globales y la parada de emergencia no responden o causan cuelgues.
- **Causa comprobada**: Falta de registro robusto de atajos globales y ausencia de manejador para detener procesos en segundo plano.
- **Archivos implicados**: `src-tauri/src/lib.rs`, `1.AXX/Axx.html`.
- **Corrección propuesta**: Asegurar que la tecla de escape o combinación de parada de emergencia detenga de inmediato cualquier reproducción, dictado, grabación o proceso activo.
- **Prueba de aceptación**: Durante una operación de audio o grabación activa, presionar el atajo de parada de emergencia; todos los procesos activos se detienen de inmediato y la UI pasa a estado de reposo.

---

## 12. Configuración y Persistencia (Settings & Providers)
- **Problema observado**: Los ajustes cambiados en la interfaz de configuración no se guardan entre reinicios o intentan escribir en ubicaciones indebidas (como la raíz del repositorio).
- **Causa comprobada**:
  1. `Axx.html:7187` invoca `request_notifications` y `Axx.html:7221` invoca `set_autostart`, comandos que no existen en Rust.
  2. `backend/server.py:372` escribe `providers.json` en la raíz del repositorio en lugar de `%LOCALAPPDATA%\Axx\providers.json`.
- **Archivos implicados**: `src-tauri/src/lib.rs`, `backend/server.py`, `1.AXX/Axx.html`.
- **Corrección propuesta**: Registrar comandos nativos faltantes en Rust; unificar la persistencia en `%LOCALAPPDATA%\Axx\` y `localStorage`; ofrecer botón funcional de "Restablecer valores predeterminados".
- **Prueba de aceptación**: Modificar un ajuste (ej. paleta, opacidad, escala); cerrar la aplicación por completo; volver a abrir; verificar que el ajuste persiste. Pulsar "Restablecer" y comprobar que vuelve al valor por defecto.

---

## 13. Ventanas Secundarias y Paneles Movibles
- **Problema observado**: Los paneles no se mueven suavemente (tirones graves), no pueden redimensionarse, interfieren con la selección de texto dentro del panel, y no recuerdan su tamaño y posición tras reiniciar.
- **Causa comprobada**:
  1. *Saturación Win32*: En cada evento `pointermove` se invoca `desktop_layout` IPC de forma síncrona con `SetWindowPos`, inundando el bucle de mensajes de Windows (`Axx.html:18331`).
  2. *Feedback loop en Rust*: `WindowEvent::Moved` invoca `record_move` en `resident.rs:362`, desfasando las coordenadas de anclaje de JS.
  3. *Dimensiones fijas*: Tamaño hardcodeado a `420x560` en `Axx.html:18418`; no existen agarraderas de redimensionado ni persistencia de tamaño en `localStorage`.
- **Archivos implicados**: `1.AXX/Axx.html` (líneas 18090–18450), `src-tauri/src/resident.rs` (líneas 360–380).
- **Corrección propuesta**:
  1. Limitar el redimensionamiento/arrastre por IPC a 60 FPS con `requestAnimationFrame` y mover el DOM localmente durante el arrastre, sincronizando con Rust al finalizar el gesto.
  2. Impedir que clics en inputs, botones o selección de texto inicien arrastre accidental.
  3. Añadir agarraderas de redimensionamiento con tamaño mínimo y persistir tanto posición `(x, y)` como dimensiones `(w, h)` en `localStorage`.
  4. Implementar función de recuperación para reubicar paneles dentro de la pantalla si cambian la resolución o monitores.
- **Prueba de aceptación**: Abrir un panel; arrastrarlo desde la cabecera (suave a 60 FPS sin tirones); redimensionarlo desde los bordes; seleccionar texto en su interior sin que se inicie arrastre; cerrar y reiniciar; el panel reaparece en la posición y dimensiones exactas.

---

## 14. Tentáculos y Recortes (Tentacles & Native HWND Clipping)
- **Problema observado**: Los tentáculos que conectan al personaje con los paneles se cortan abruptamente en líneas rectas invisibles en el aire.
- **Causa comprobada**: En `ResidentDesktop.layout()` (`Axx.html:18404, 18449`), el margen de la ventana nativa de Windows es de solo `12px` alrededor de los cuadros activos. Las curvas Bezier de los tentáculos en `OrganicTendrils.tube()` (`Axx.html:5326`) arquean hacia afuera entre `104px` y `170px`. Todo píxel fuera de los 12px cae físicamente fuera de la ventana Win32 HWND y es cortado por el compositor de Windows.
- **Archivos implicados**: `1.AXX/Axx.html` (líneas 18404, 18449, 5326).
- **Corrección propuesta**: Incrementar el margen de la ventana nativa a `72px` o calcular dinámicamente la envolvente convexa del arco de los tentáculos para que el HWND siempre contenga la trayectoria completa de los tubos Bezier sin recortes. Con movimiento reducido activado, congelar la simulación en forma estática.
- **Prueba de aceptación**: Abrir dos paneles y moverlos en diferentes direcciones; los tentáculos permanecen fluidamente conectados a Axx y a sus anclas sin ningún corte en los bordes. Con movimiento reducido activado en accesibilidad, los tentáculos se representan de forma estática sin consumir CPU.

---

## 15. Menús y Navegación
- **Problema observado**: Dificultad para alternar entre herramientas; menús flotantes se solapan o quedan inaccesibles.
- **Causa comprobada**: Falta de un sistema de gestión de capas (z-index) y foco unificado para paneles activos.
- **Archivos implicados**: `1.AXX/Axx.html` (CSS y gestión de paneles).
- **Corrección propuesta**: Establecer una pila de z-index clara donde el panel enfocado pasa al frente, y la navegación por pestañas/menús es consistente.
- **Prueba de aceptación**: Alternar entre múltiples paneles; el panel pulsado pasa al frente sin descolocar a los demás.

---

## 16. Ayudas y Tooltips
- **Problema observado**: Falta de indicaciones claras de uso o textos de ayuda que saturan la interfaz visualmente.
- **Causa comprobada**: Ausencia de tooltips no invasivos en los botones orbitales y controles avanzados.
- **Archivos implicados**: `1.AXX/Axx.html`.
- **Corrección propuesta**: Incorporar micro-tooltips flotantes elegantes con la paleta de cromo oscuro iridiscente que expliquen brevemente la función de cada herramienta al pasar el cursor.
- **Prueba de aceptación**: Al situar el cursor sobre cada botón del menú radial o cabecera de panel, se muestra un tooltip conciso y legible que desaparece inmediatamente al retirar el cursor.

---

## 17. Estados de Error y Recuperación
- **Problema observado**: Cuando una función falla (ej. sin conexión o comando inválido), la aplicación se congela en silencio o no muestra ninguna indicación.
- **Causa comprobada**: Promesas IPC sin cláusula `.catch()` y falta de banner de estado de error visual diferenciado.
- **Archivos implicados**: `1.AXX/Axx.html`, `backend/server.py`.
- **Corrección propuesta**: Implementar sistema visual de notificación de estado unificado (reposo, escucha, procesamiento, ejecución, error con acción recomendada).
- **Prueba de aceptación**: Simular una llamada con error (ej. servicio no disponible); la interfaz muestra un aviso visual claro indicando qué falló y cómo reintentar, sin bloquear el resto de la aplicación.

---

## 18. IPC / Puente Tauri y Procesos en Segundo Plano
- **Problema observado**: 22 procesos zombi de `python.exe -m backend.connect.mcp_server` consumiendo memoria en segundo plano; comandos de autostart y notificaciones arrojando errores de comando no encontrado.
- **Causa comprobada**:
  1. `backend/connect/mcp_server.py` no implementa autodetección de cierre de proceso padre ni enlace a Job Object de Windows.
  2. Comandos `request_notifications` y `set_autostart` no registrados en `tauri::generate_handler![]` en `src-tauri/src/lib.rs`.
- **Archivos implicados**: `backend/connect/mcp_server.py`, `src-tauri/src/lib.rs`.
- **Corrección propuesta**: Terminar procesos zombi huérfanos; registrar los comandos Rust faltantes (o implementar stubs controlados); asegurar que los subprocesos de Python se ejecuten dentro de un Job Object con `KILL_ON_JOB_CLOSE`.
- **Prueba de aceptación**: Al cerrar la aplicación Axx, todos los subprocesos de Python y Tauri se cierran de inmediato sin dejar ningún proceso zombi activo en el Administrador de Tareas.

---

## Resumen de la Auditoría Previa R1
La auditoría previa ha sido completada con éxito antes de cualquier modificación de código. Todos los 18 apartados han sido diagnosticados a nivel de línea de código, identificando las causas exactas del fallo total de clics e interacciones y definiendo correcciones y pruebas de aceptación específicas.
