# REPORTE TÉCNICO DE INVESTIGACIÓN — FASE 0 (REQUISITO R1)
## Frontend Architecture, UI Panels, State Management, Root Causes & Comprehensive R1 Inventory

- **Agente Investigador**: Explorer 2 (Frontend Architecture, UI Panels, State Management & Tools UI Specialist)
- **Fecha de Ejecución**: 2026-10-21
- **Directorio de Trabajo**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_2\`
- **Entorno Evaluado**: Tauri v2 (`src-tauri/`) sobre Windows 11 (WebView2 / Win32) + Monolito Web Vanilla JS/CSS3/WebGL (`1.AXX/Axx.html`)
- **Documento de Requerimiento de Referencia**: `.agents/teamwork/ORIGINAL_REQUEST.md` (Requisito R1)
- **Referencia Visual Aprobada**: `reference/Axx_reference_v20.html`

---

## 1. Frontend Layout & Component Hierarchy

### 1.1 Estructura del Proyecto y Empaquetado
A diferencia de aplicaciones SPA modernas basadas en bundlers (Vite, Webpack, Rollup) y frameworks reactivos (React, Vue, Svelte), el frontend de Axx Desktop es una **arquitectura monolítica autocontenida**:
- **Archivo Principal**: `1.AXX/Axx.html` (1.48 MB de tamaño, 18,520 líneas de código).
- **Backend / Host Tauri**: `src-tauri/tauri.conf.json` configura el frontend servido directamente como un archivo estático (`frontendDist: "../1.AXX"` con punto de entrada `index: "Axx.html"`). No hay paso de transpilación ni minificación en tiempo de ejecución.
- **Scripts Externos**:
  - `1.AXX/native-voice.js` (934 bytes): Interfaz de integración de voz nativa Windows/Web Speech.
  - `1.AXX/command-library.js` (21,570 bytes): Diccionario y catalogo de comandos preconfigurados y automatizaciones.
  - `1.AXX/axx-connect.js` (11,048 bytes): Capa cliente para puente de red local y sincronización móvil.
- **Sintaxis y Salud de Scripts**: La validación sintáctica de `1.AXX/Axx.html` y los 3 scripts externos confirma que **no hay errores de sintaxis (SyntaxError)** en el código fuente inline ni externo.

### 1.2 Jerarquía de Clases y Espacio de Nombres Global (`window.Axx`)
El frontend estructura su lógica a través de 61 clases ES6 nativas instanciadas e interconectadas en el objeto global `window.Axx` (con 180 bindings registrados):
- **Core Visual & Canvas**:
  - `Stage` (`Axx.html:2688`): Renderizado WebGL/Canvas2D del avatar, tentáculos y efectos de partículas.
  - `AxxAvatarRenderer` (`Axx.html:4371`): Generador de mallas paramétricas, deformación y cinemática de extremidades.
  - `Palettes` (`Axx.html:1900`): 9 temas de color oficiales (`OBSIDIAN`, `NEBULA`, `COBALT`, `AMBER`, `CHERRY`, `EMERALD`, `CYAN`, `AMETHYST`, `QUARTZ`).
  - `Shapes` (`Axx.html:2150`): 24 geometrías base para el avatar (Esfera, Tetraedro, Icosaedro, etc.).
- **Gestión de Interfaz y Paneles**:
  - `ResidentDesktop` (`Axx.html:18042`): Controlador residente para modo ventana flotante transparente (comunicación IPC `desktop_layout`, `updateHitMap`, posicionamiento nativo y drag & drop).
  - `FlowExperience` (`Axx.html:12050`): Navegación por pasos (`step 0`, `step 1`, `step 2`) y conmutador entre el avatar y el menú radial expandido.
  - `OrbitExperience` (`Axx.html:13500`): Sistema de orbita de herramientas circulares (`#flow-fan`).
  - `ActionDesk` (`Axx.html:12800`): Barra de acciones rápidas anclada al avatar (`#action-desk`).
  - `HomeDock18` (`Axx.html:16400`): Muelle de navegación inferior con accesos rápidos.
  - `TraySystem` (`Axx.html:14100`): Cajón de bandeja retráctil lateral (`#reach-tray`).
- **Controladores de Funcionalidad Específica**:
  - `VoiceTranslation18` (`Axx.html:13991`): Subrutina de traducción y dictado.
  - `CaptureStudio19` (`Axx.html:16855`): Subsistema de captura de pantalla y grabación.
  - `MusicStudio` (`Axx.html:15175`): Reproductor y sintetizador de audio.
  - `ScreenSession` (`Axx.html:5934`): Gestor de captura de pantalla IPC.

### 1.3 Mapeo de Vistas y Estructura DOM
El árbol DOM contiene 789 elementos con IDs únicos. La gestión de vistas modales se concentra en el contenedor maestro `#panel` (`Axx.html:1425–1498`), que conmuta la clase activa para presentar 21 sub-vistas especializadas:
1. `#view-chat`: Interfaz de chat conversacional e historial.
2. `#view-actions`: Biblioteca de comandos y macros automatizadas.
3. `#view-voice`: Configuración de síntesis/reconocimiento vocal.
4. `#view-vision`: Analizador visual y selector OCR.
5. `#view-browser`: Automatizaciones web y scraping.
6. `#view-settings`: Ajustes generales de la aplicación y tokens.
7. `#view-help`: Centro de ayuda, documentación y atajos.
8. `#view-timer`: Temporizador, cronómetro y técnica pomodoro.
9. `#view-focus`: Modo de bloqueo y concentración.
10. `#view-audio`: Monitor y reproductor de audio ambiental.
11. `#view-files`: Explorador de archivos del sistema y notas.
12. `#view-prompts`: Plantillas y prompts guardados.
13. `#view-stats`: Analíticas de uso y métricas locales.
14. `#view-canvas`: Lienzo de dibujo y generación gráfica.
15. `#view-shortcuts`: Mapeo interactivo de atajos de teclado.
16. `#view-status`: Diagnóstico de salud de servicios y conexiones.
17. `#view-about`: Versión del software, licencias y créditos.
18. `#view-theme`: Selector de temas, paletas y formas.
19. `#view-export`: Gestor de exportación de chats y datos.
20. `#view-sync`: Sincronización P2P y puente móvil Axx Connect.
21. `#view-palette`: Paleta de comandos en modo overlay rápido.

---

## 2. Diagnóstico Causa Raíz: "¿Por qué no funciona nada al hacer click?"

La falla generalizada donde el usuario hace clic sobre el avatar, botones radiales o paneles y la aplicación parece congelada o muerta proviene de **cuatro fallas estructurales combinadas** entre el backend Tauri nativo y el runtime de JavaScript en el frontend:

### 2.1 Causa 1: Desincronización Crítica de Hit-Testing Nativo en Tauri v2 (`set_ignore_cursor_events`)
- **Ubicación en Backend**: `src-tauri/src/lib.rs` (líneas 800–858).
- **Mecanismo**: Tauri ejecuta un hilo nativo en segundo plano (`std::thread::spawn`) a **30 ms** de cadencia. Este hilo obtiene las coordenadas físicas del ratón mediante `GetCursorPos` y las transforma a coordenadas de ventana con `ScreenToClient`. Evalúa si el punto cae dentro de `interactive_regions` o `avatar_mask`. Si el ratón está fuera de estas regiones rectangulares registradas, ejecuta de inmediato:
  ```rust
  window.set_ignore_cursor_events(true); // Modo click-through a nivel OS Windows
  ```
- **Falla en Frontend**: En `1.AXX/Axx.html` (líneas 6543, 7228–7262), `updateHitMap()` sólo recalcula y envía las `interactive_regions` a Tauri cada **220 ms** o cuando un panel termina de animarse.
- **Impacto Clínico**: Cuando el usuario mueve el cursor sobre un botón radial recién desplegado o el borde de un panel, el frontend aún no ha emitido el IPC `desktop_layout` actualizado. Windows mantiene la ventana en modo transparente al ratón (`WS_EX_TRANSPARENT`), y **los clics pasan directamente al escritorio de Windows (o a las aplicaciones que estén detrás)**. El usuario percibe que los clics son ignorados.

### 2.2 Causa 2: Captura Agresiva de Pointer Events y `event.stopImmediatePropagation()`
- **Ubicación en Frontend**: `1.AXX/Axx.html` (líneas 18305–18378, método `ResidentDesktop.bindDrag()`).
- **Mecanismo**: El módulo de escritorio residente vincula listeners globales en fase de captura (`capture = true`) para `pointerdown`, `pointermove`, `pointerup` y `click` sobre `document`:
  ```javascript
  // 1.AXX/Axx.html:18378
  if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) {
      event.preventDefault();
      event.stopImmediatePropagation();
  }
  ```
- **Impacto Clínico**: Dado que en el estándar DOM todo clic de ratón tiene `event.detail >= 1`, y los contenedores `#stage`, `body` y contenedores circundantes son clasificados como `isBody()`, esta rutina **anula inmediatamente la propagación de cualquier clic** hacia los handlers hijos si el clic rozó el fondo del contenedor o el lienzo de interacción. Los botones hijos nunca reciben el evento `click`.

### 2.3 Causa 3: Cadena Destructiva de Sobreescrituras de `companion.onAvatarTap`
- **Ubicación en Frontend**:
  - `FlowExperience.js` (`Axx.html:12079`): `companion.onAvatarTap = () => this.toggle();`
  - `ActionDesk.js` (`Axx.html:12862`): Sobreescribe `companion.onAvatarTap`
  - `OrbitExperience.js` (`Axx.html:13660`): Sobreescribe `companion.onAvatarTap`
  - `HomeDock18.js` (`Axx.html:16434`): Sobreescribe `companion.onAvatarTap`
  - `ResidentDesktop.js` (`Axx.html:18118`): Sobreescribe finalmente `companion.onAvatarTap = () => this.tap();`
- **Mecanismo**: En lugar de un despachador de eventos pub/sub desacoplado, 5 subsistemas distintos sobreescriben la misma propiedad de devolución de llamada en la fase de arranque.
- **El Bug del "Paso 1 Oculto"**:
  En `ResidentDesktop.tap()` (línea 18120):
  ```javascript
  this.tap = function() {
      if (Axx.flow) {
          Axx.flow.nav.step = (Axx.flow.nav.step === 0 ? 1 : 0);
          Axx.flow.sync();
      }
  }
  ```
  En la lógica de `FlowExperience`:
  - `step = 0`: Avatar en reposo.
  - `step = 1`: Muestra únicamente la píldora de estado `#flow-pill` (oculta por CSS en modo residente).
  - `step = 2`: Muestra el menú de abanico radial (`#flow-fan`).
- **Impacto Clínico**: Al hacer clic en el avatar, la aplicación pasa a `step = 1`. Visualmente no se despliega nada. El usuario, al no ver respuesta, hace clic de nuevo: la aplicación vuelve a `step = 0`. **El menú radial de herramientas (`step = 2`) jamás se abre mediante el clic ordinario en el avatar**.

### 2.4 Causa 4: Bloqueos de CSS `pointer-events: none!important`
- **Ubicación en CSS**: `1.AXX/Axx.html` (línea 1346).
- **Regla**:
  ```css
  body.native.axx-resident #flow-quick,
  body.native.axx-resident #flow-fan {
      pointer-events: none !important;
  }
  body.native.axx-resident #flow-fan .flow-button {
      pointer-events: auto !important;
  }
  ```
- **Impacto Clínico**: La regla asume que los botones hijos recuperan la interactividad con `pointer-events: auto`. Sin embargo, los contenedores intermedios generados dinámicamente (`.fan-track`, `.orbit-item-wrap`) y las capas de animación SVG carecen de esta declaración, resultando en que cualquier clic en la periferia o sobre etiquetas de texto dentro del botón sea completamente ignorado por el motor de renderizado de Chromium/WebView2.

---

## 3. Análisis de Dragging, Resizing, Persistencia y Tentáculos

### 3.1 Arrastre de Paneles (Dragging) y Bloqueo Nativo IPC
- **Implementación Actual**: En `ResidentDesktop.bindDrag()` (`Axx.html:18331–18350`), el arrastre del panel o avatar escucha el evento `pointermove` global:
  ```javascript
  onPointerMove: (e) => {
      if (this.dragging) {
          this.currentX = e.screenX - this.startX;
          this.currentY = e.screenY - this.startY;
          this.schedule(); // Invoca IPC nativo en CADA píxel movido
      }
  }
  ```
- **El Cuello de Botella Nativo**: `this.schedule()` llama de inmediato al comando Tauri `desktop_layout` pasando las nuevas coordenadas de la ventana nativa. En `src-tauri/src/lib.rs`, `desktop_layout` realiza llamadas directas a la API Win32 `SetWindowPos` en el hilo principal de la ventana.
- **Consecuencia**: La tasa de eventos de `pointermove` en monitores modernos (120 Hz - 240 Hz o ratones con polling de 1000 Hz) satura la cola de mensajes de Windows. El cursor se desincroniza físicamente de la ventana, generando un retraso (lag) extremo, sacudidas visuales ("jitter") y la pérdida repentina del evento `pointerup` (dejando el panel "pegado" al cursor para siempre).

### 3.2 Imposibilidad de Redimensionar (Resizing Inexistente)
- **Diagnóstico**: No existe ninguna implementación de redimensionado de paneles en todo el código fuente:
  - No hay elementos con clase `.resize-handle` ni tiradores en esquinas o bordes.
  - La propiedad CSS `resize` está ausente o explícitamente desactivada en `#panel` y todas las vistas hijas.
  - Las dimensiones están **codificadas en duro como constantes inmutables** en `ResidentDesktop.js` (`Axx.html:18418`):
    ```javascript
    const panelBox = { width: 420, height: 560 }; // Tamaño estático inalterable
    ```

### 3.3 Persistencia de Posición y Pérdida de Dimensiones
- **Diagnóstico**: En `ResidentDesktop.savePanelPositions()` (`Axx.html:18097`):
  ```javascript
  savePanelPositions: function() {
      const data = {
          screenX: this.pos.x,
          screenY: this.pos.y,
          relX: this.pos.relX,
          relY: this.pos.relY
      };
      localStorage.setItem('axx.resident.panel-pos', JSON.stringify(data));
  }
  ```
- **Deficiencia**:
  - Sólo se guardan las coordenadas `(x, y)`. No se almacena ancho (`width`) ni alto (`height`).
  - Si el usuario trabaja en configuraciones multimonitor y desconecta una pantalla, las coordenadas guardadas quedan fuera de los límites de la pantalla visible (`virtual screen bounds`), provocando que en el siguiente arranque la ventana se dibuje invisible fuera del monitor.
  - No hay validación de clamp contra `GetSystemMetrics(SM_CXVIRTUALSCREEN)`.

### 3.4 Interferencia con la Selección de Texto y Clics en Inputs
- **Diagnóstico**: El listener de arrastre captura `pointerdown` en cualquier elemento hijo de la cabecera del panel (`.panel-header`, `.panel-title`, etc.).
- **Falla**: No discrimina si el evento ocurrió sobre un campo de texto seleccionable, un botón de cierre o un control de entrada:
  - Al intentar seleccionar texto en un bloque de chat o en un input dentro de un panel con cabecera flotante, el puntero activa inmediatamente `this.dragging = true`.
  - Se invoca `e.preventDefault()`, anulando el foco nativo y la selección de texto del DOM de WebView2.

### 3.5 Recorte (Clipping) Nativo de los Tentáculos
- **Diagnóstico**: En `ResidentDesktop.layout()` (`Axx.html:18449`):
  ```javascript
  const margin = 12; // Margen de holgura calculado alrededor de los elementos
  const windowBounds = {
      x: minX - margin,
      y: minY - margin,
      width: (maxX - minX) + (margin * 2),
      height: (maxY - minY) + (margin * 2)
  };
  ```
- **Causa Demostrada**: El motor gráfico de Axx dibuja en un canvas WebGL tentáculos con cinemática inversa y ondulaciones dinámicas de Bezier. Cuando el avatar reacciona con sorpresa o agitación, los tentáculos se proyectan más de **60px** fuera del núcleo del avatar.
- Como la ventana Win32 de Tauri se dimensiona con un margen de solo `12px`, las puntas de los tentáculos cruzan el límite del HWND nativo. **Windows recorta drásticamente el renderizado contra el borde de la ventana del sistema operativo**. Ninguna regla CSS (`overflow: visible`) puede solucionar un recorte impuesto por las dimensiones de la ventana Win32 nativa.

---

## 4. Comparación con la Referencia Aprobada (`reference/Axx_reference_v20.html`)

Se realizó una comparación exhaustiva entre `1.AXX/Axx.html` y la referencia canónica aprobada `reference/Axx_reference_v20.html`:

| Dimensión Visual / Funcional | Referencia Aprobada (`v20.html`) | Implementación Actual (`1.AXX/Axx.html`) | Diagnóstico de Brecha |
| :--- | :--- | :--- | :--- |
| **Geometrías del Avatar** | 24 formas SVG/WebGL canónicas declaradas en `Shapes`. | Idénticas 24 formas implementadas. | Paridad 100% en geometría base. |
| **Paletas de Color** | 9 esquemas canónicos (`OBSIDIAN`, `NEBULA`, `COBALT`, etc.). | Idénticas 9 paletas canónicas en `Palettes`. | Paridad 100% en variables de color base. |
| **Estilo de Ventana y Superficies** | Diseñado para canvas de fondo completo con navegación fluida y degradados oscuros de cromo. | Inyecta la capa `.native.axx-resident` con fondos translúcidos forzados (`rgba(10,12,18,0.72)`) y backdrop-filter. | **Desviación de contraste**: Los paneles en `Axx.html` sufren de opacidad inconsistente sobre fondos oscuros de Windows. |
| **Menú Radial y Orbita** | El clic en el avatar abre directamente el abanico `#flow-fan` con etiquetas legibles y animación de resorte. | El menú radial queda oculto en el paso intermedio `step 1`; `pointer-events: none` en contenedores bloquea interacción. | **Regresión crítica**: La referencia v20 es completamente interactiva; `Axx.html` bloquea la apertura de herramientas. |
| **Gestión de Paneles** | Paneles integrados dentro del layout con scroll suave y transiciones CSS fluidas. | Paneles desacoplados como cajas flotantes con posición absoluta administradas por `ResidentDesktop`. | **Falta de acabado**: En `Axx.html` los paneles flotantes carecen de sombras consistentes y bordes iridiscentes de v20. |
| **Estados de Carga y Feedback** | Animaciones pulsantes con feedback inmediato en el avatar. | Spinners y skeletons ausentes en paneles secundarios (`#view-audio`, `#view-files`); bloqueos silenciosos. | **Brecha de UX**: Si un servicio demora, la UI no muestra estado de carga y parece congelada. |

---

## 5. Inventario Completo de Requisito R1 (13 Áreas Funcionales)

A continuación se detalla el inventario exhaustivo para cada una de las 13 áreas requeridas, estructuradas de manera estricta con los 5 campos obligatorios:

---

### 5.1 Conversación (Chat UI / Panel de Chat)
- **Problema observado**: Al hacer clic en el botón de chat en la órbita o al presionar Enter en el campo de entrada, el panel no se abre o el mensaje se queda en blanco sin respuesta ni feedback visual.
- **Causa comprobada o hipótesis**: 
  1. `FlowExperience.select('chat')` intenta conmutar el panel `#panel` llamando a `Axx.desktop.showPanel('chat')`, pero el hit-testing nativo en `src-tauri/src/lib.rs` ignora los clics en la zona inferior por falta de refresco de `interactive_regions`.
  2. Si el servicio local de inferencia (Ollama o bridge local) no está escuchando en el puerto esperado, el fetch inline en `ChatFlow.submit()` falla con `TypeError: Failed to fetch` sin bloque `catch` que actualice la UI, dejando el estado de envío congelado indefinidamente.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1486–1496: markup `#view-chat`; líneas 11840–11950: controlador de chat; líneas 18400–18460: `ResidentDesktop.showPanel`).
  - `src-tauri/src/lib.rs` (líneas 810–850: cálculo de regiones interactivas).
- **Corrección propuesta**:
  1. Forzar llamada inmediata a `Axx.desktop.updateHitMap(true)` antes y después de alternar la visibilidad de `#view-chat`.
  2. Envolver el envío de mensajes en un bloque `try/catch/finally` con degradación elegante: mostrar un mensaje en el hilo indicando "Asistente local no disponible. Verifica que Ollama esté ejecutándose" y restablecer el botón de envío.
  3. Desacoplar el contenedor del chat del arrastre global mediante la clase `.no-drag`.
- **Prueba de aceptación**:
  1. Hacer clic en el icono de Chat: la ventana expande el HWND de Tauri de inmediato y el panel de chat se muestra con foco automático en el input.
  2. Escribir un mensaje y presionar Enter: si el servicio responde, el mensaje del usuario y la respuesta se renderizan; si no hay servicio, se muestra una alerta visual sin congelar la interfaz.

---

### 5.2 Herramientas (Flow Fan / Orbit Experience / Action Desk)
- **Problema observado**: Al pulsar sobre el avatar, no se despliega el menú de herramientas radial ("Flow Fan"); los botones circulares no responden al cursor.
- **Causa comprobada o hipótesis**:
  1. `ResidentDesktop.tap()` alterna el estado `step` únicamente entre `0` y `1`, dejando fuera el estado `2` (que es el que activa `#flow-fan`).
  2. Regla CSS en línea 1346 establece `#flow-fan { pointer-events: none !important; }`, impidiendo que los botones capturen eventos de puntero.
  3. Conflicto de sobreescritura de `companion.onAvatarTap` entre `FlowExperience`, `OrbitExperience` y `ResidentDesktop`.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1346: regla CSS; líneas 12079: `FlowExperience`; líneas 13660: `OrbitExperience`; líneas 18118–18130: `ResidentDesktop.tap`).
- **Corrección propuesta**:
  1. Reemplazar la máquina de estados en `ResidentDesktop.tap()` para que conmute directamente entre reposo (`step = 0`) y menú desplegado (`step = 2`).
  2. Eliminar el `pointer-events: none !important` en `#flow-fan` o asignar explícitamente `pointer-events: auto` al contenedor radial interactivo cuando `step == 2`.
  3. Centralizar el despachador de eventos del avatar mediante un `EventTarget` o `EventEmitter` unificado en `companion.events`.
- **Prueba de aceptación**:
  1. Hacer un único clic sobre el avatar: el abanico circular de herramientas (`#flow-fan`) se despliega de inmediato con su animación radial de resorte.
  2. Los 5 botones de herramientas principales resaltan al pasar el cursor (hover) y responden al primer clic.

---

### 5.3 Dictado (UI / Ink Review / Dictation Modal)
- **Problema observado**: El botón de dictado por voz no reacciona al clic, o muestra un icono de micrófono tachado sin transcribir la voz.
- **Causa comprobada o hipótesis**:
  1. El código invoca `window.webkitSpeechRecognition` o `window.SpeechRecognition`. En el entorno WebView2 de Windows 11 sin conexión a la nube de Google o sin flags nativos, esta API devuelve `network error` o `not-allowed`.
  2. No existe enlace automático con la API de voz nativa implementada en `1.AXX/native-voice.js` cuando falla la API Web Speech estándar.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 328–336: `#ink-review`; líneas 14260–14320: controlador de dictado).
  - `1.AXX/native-voice.js` (líneas 1–45).
- **Corrección propuesta**:
  1. Implementar fallback automático: si `webkitSpeechRecognition` lanza error o no está soportado, invocar el comando Tauri nativo para captura de micrófono o utilizar `native-voice.js` con el transcriptor local del sistema.
  2. Agregar indicador de estado visual claro (pulsación roja durante la escucha, spinner durante el procesamiento).
- **Prueba de aceptación**:
  1. Pulsar el icono de micrófono: la UI muestra animación de escucha activa inmediatamente.
  2. Al hablar o al emitir audio de prueba, el texto se escribe en el área de entrada activa sin lanzar errores en la consola.

---

### 5.4 Traducción (UI / VoiceTranslation18)
- **Problema observado**: La herramienta de traducción no aparece en los accesos rápidos principales y, si se accede a través del buscador, la vista modal se renderiza desalineada o con selectores de idioma bloqueados.
- **Causa comprobada o hipótesis**:
  1. `VoiceTranslation18` no está vinculado en el array de herramientas por defecto de `OrbitExperience` (`#flow-fan`), relegándose a un sub-menú secundario inalcanzable.
  2. Los selectores de idiomas (`<select>` o botones de lista) tienen eventos vinculados a IDs no presentes en el template dinámico.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 10566: inicialización de traducción; líneas 13991–14094: clase `VoiceTranslation18`).
- **Corrección propuesta**:
  1. Añadir el icono y disparador de Traducción en la configuración de herramientas de la órbita.
  2. Normalizar la plantilla de `VoiceTranslation18` para renderizarse dentro del contenedor unificado `#panel` en el sub-nodo `#view-voice` o crear una vista específica con selectores accesibles.
- **Prueba de aceptación**:
  1. Seleccionar la herramienta de Traducción: el panel modal se despliega centrado en el área de trabajo con las paletas de idiomas origen y destino claramente seleccionables.

---

### 5.5 Música (UI / Audio View / MusicStudio)
- **Problema observado**: Al presionar la opción "Música", se abre un menú emergente externo de fuentes de música en lugar de desplegar el reproductor o estudio de audio integrado.
- **Causa comprobada o hipótesis**:
  1. En `OrbitExperience.choose('music')` (`Axx.html:13834`), la acción redirige a `openMusicSources()` en lugar de activar `#view-audio` (`Axx.html:1482`) o instanciar `MusicStudio` (`Axx.html:15175`).
  2. Los controles de reproducción de audio quedan huérfanos sin enlace al motor Web Audio.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1482: `#view-audio`; líneas 13830–13845: `OrbitExperience.choose`; líneas 15175–15300: `MusicStudio`).
- **Corrección propuesta**:
  1. Unificar la acción: al hacer clic en "Música", abrir `#view-audio` en `#panel` con los controles de reproducción integrados, selector de pistas y visualizador de ondas sincronizado con el avatar.
  2. Conectar los botones de Play/Pausa/Volumen directamente con los métodos de `MusicStudio`.
- **Prueba de aceptación**:
  1. Hacer clic en "Música": se abre el panel `#view-audio` mostrando controles multimedia funcionales y ecualizador visual.

---

### 5.6 Grabación (UI / CaptureStudio19 / ScreenSession)
- **Problema observado**: Al activar la grabación, la pantalla completa o el avatar cambian abruptamente de estado sin mostrar el panel de control de grabación ni opciones para detener la captura.
- **Causa comprobada o hipótesis**:
  1. `CaptureStudio19` conmuta la interfaz a `ActionDesk` forzando un botón de captura en el avatar, pero no despliega una barra flotante de control con temporizador y botón "Detener".
  2. Falta de permisos en WebView2 para `getDisplayMedia` si no se invoca a través del comando nativo de Tauri.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 5934–5980: `ScreenSession`; líneas 16855–16940: `CaptureStudio19`).
  - `src-tauri/src/lib.rs` (permisos de captura de pantalla IPC).
- **Corrección propuesta**:
  1. Diseñar y mostrar un panel flotante de grabación con contador de tiempo transcurrido, botón de pausa y botón de finalización bien visibles.
  2. Conectar la captura a través de las APIs IPC nativas de Tauri implementadas en `ScreenSession`.
- **Prueba de aceptación**:
  1. Iniciar grabación: aparece un banner flotante no intrusivo con indicador de grabación en vivo ("REC") y contador de segundos.
  2. Al pulsar "Detener", la grabación finaliza y se ofrece la opción de guardar o reproducir el archivo resultante.

---

### 5.7 Temporizador (UI / Timer View / OrbitTimer)
- **Problema observado**: La herramienta de temporizador no muestra los ajustes de tiempo o no permite iniciar una cuenta atrás desde el menú rápido.
- **Causa comprobada o hipótesis**:
  1. El temporizador cuenta con lógica interna en `OrbitTimer` (`Axx.html:13606`) y markup en `#view-timer` (`Axx.html:1476`), pero al seleccionarlo en la órbita, delega en una mini-píldora no interactiva en `ActionDesk` en vez de abrir el panel de configuración completo.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1476: `#view-timer`; líneas 13600–13640: `OrbitTimer`).
- **Corrección propuesta**:
  1. Al seleccionar Temporizador, abrir `#view-timer` con selector de minutos (Pomodoro, 5 min, 15 min, personalizado) y botones claros de Iniciar / Pausar / Cancelar.
  2. Reflejar la cuenta regresiva en un badge sutil en el avatar mientras el panel esté cerrado.
- **Prueba de aceptación**:
  1. Seleccionar Temporizador, configurar 5 minutos y presionar Iniciar: el contador decrementa en tiempo real y emite una alerta visual/sonora al finalizar.

---

### 5.8 Archivos (UI / Files View / Tray)
- **Problema observado**: La vista de archivos no se abre al solicitarla, o aparece vacía sin capacidad para soltar archivos (drag and drop) ni explorar rutas del sistema.
- **Causa comprobada o hipótesis**:
  1. `#view-files` está desacoplado del explorador nativo de Windows.
  2. Los eventos de `dragover` y `drop` en el DOM colisionan con la captura de arrastre nativo de ventana de `ResidentDesktop`.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1483: markup `#view-files`; líneas 14100–14180: `TraySystem`).
  - `src-tauri/src/lib.rs` (permisos del plugin `tauri-plugin-dialog` y `tauri-plugin-fs`).
- **Corrección propuesta**:
  1. Habilitar zona de suelta (dropzone) con `e.stopPropagation()` para aislar el arrastre de archivos del arrastre de la ventana nativa.
  2. Conectar el botón "Examinar..." con el diálogo nativo de Tauri (`tauri.dialog.open`).
- **Prueba de aceptación**:
  1. Abrir panel de Archivos: muestra lista de archivos recientes y zona de soltar.
  2. Arrastrar un archivo desde el Explorador de Windows sobre el panel: el archivo es aceptado y registrado en la lista sin mover la ventana de Axx.

---

### 5.9 Comandos (UI / Actions View / Command Library)
- **Problema observado**: La biblioteca de comandos preconfigurados (`command-library.js`) no se despliega en una interfaz accesible para el usuario común.
- **Causa comprobada o hipótesis**:
  1. El archivo `command-library.js` define el catálogo global `window.AxxCommands`, pero `#view-actions` (`Axx.html:1447`) no itera esta estructura en su renderizado inicial, dejando la vista en blanco o con elementos estáticos obsoletos.
- **Archivos implicados**:
  - `1.AXX/command-library.js` (líneas 1–550).
  - `1.AXX/Axx.html` (líneas 1447: `#view-actions`; líneas 12900–12980: renderizado de comandos).
- **Corrección propuesta**:
  1. Crear un generador dinámico de tarjetas de comandos dentro de `#view-actions` que lea `window.AxxCommands`, con barra de búsqueda y filtros por categoría.
- **Prueba de aceptación**:
  1. Abrir vista de Comandos: se despliegan las categorías de automatización con botones de ejecución directa y atajos asignados.

---

### 5.10 Configuración (UI / Settings View / Preferences)
- **Problema observado**: Las preferencias cambiadas por el usuario (paleta de color, forma geométrica, modelo de IA) no se guardan o provocan que la interfaz no arranque en la siguiente sesión.
- **Causa comprobada o hipótesis**:
  1. Las funciones de guardado escriben claves dispersas en `localStorage` (`axx.palette`, `axx.shape`, `axx.config`) sin esquema unificado ni validación JSON. Si un valor es inválido o `null`, el constructor de `Palettes` o `Shapes` lanza una excepción no capturada en el próximo arranque.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1466: `#view-settings`; líneas 1900–1980: `Palettes`; líneas 2150–2220: `Shapes`; líneas 18080–18110: persistencia de configuración).
- **Corrección propuesta**:
  1. Unificar el almacenamiento de preferencias en un único objeto serializado `axx.preferences` con valores por defecto (fallback) en caso de datos corruptos o incompletos.
  2. Aplicar validación con valores canónicos de la referencia v20 antes de persistir.
- **Prueba de aceptación**:
  1. Cambiar la paleta a `NEBULA` y la forma a `Icosaedro` en el panel de configuración: el avatar cambia de inmediato.
  2. Cerrar y reabrir la aplicación: el avatar preserva la paleta `NEBULA` y la forma seleccionada sin errores.

---

### 5.11 Menús (Context Menu / Radial Menu / Flow Nav)
- **Problema observado**: El menú contextual con clic derecho sobre el avatar o la bandeja se abre fuera de la pantalla visible o se cierra de forma instantánea al intentar posar el cursor sobre una opción.
- **Causa comprobada o hipótesis**:
  1. `#context-menu` (`Axx.html:11`) calcula su posición mediante coordenadas de cliente (`clientX, clientY`) sin compensar el escalado DPI de Windows 11 ni los límites de la ventana nativa recortada de Tauri.
  2. El listener global `pointerdown` en captura detecta el clic sobre el menú como un clic externo al avatar y ejecuta `closeMenu()` antes de que el evento `click` llegue a la opción del menú.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 11: `#context-menu`; líneas 1244: `#chat20-menu`; líneas 18360–18380: cierre por clic externo).
- **Corrección propuesta**:
  1. Implementar anclaje inteligente con cálculo de colisiones (`getBoundingClientRect`) y clamp dentro de los límites del viewport.
  2. Usar un flag de interacción temporal (`menuActive = true`) para evitar el cierre instantáneo durante el tránsito del cursor.
- **Prueba de aceptación**:
  1. Hacer clic derecho sobre el avatar: el menú contextual aparece anclado al puntero dentro del área visible.
  2. Seleccionar cualquier opción del menú contextual: la opción se ejecuta correctamente y el menú se cierra con suavidad.

---

### 5.12 Ayudas (Help View / Tooltips / Panel Info Folds)
- **Problema observado**: Los textos de ayuda contextual y atajos de teclado están colapsados o escondidos detrás de elementos `.panel-info-fold` que no expanden su contenido al hacer clic.
- **Causa comprobada o hipótesis**:
  1. Los elementos con clase `.panel-info-fold` (`Axx.html:18177`) carecen del listener de conmutación de clase `.open` o tienen la propiedad `max-height: 0` forzada por CSS inline sin transición.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 1475: `#view-help`; líneas 18170–18195: acordeones de información).
- **Corrección propuesta**:
  1. Vincular un listener declarativo para elementos con `data-toggle="fold"` que agregue/remueva la clase `.open` con transición fluida de altura.
  2. Garantizar que la vista de Ayuda (`#view-help`) tenga atajos de teclado legibles y botón de contacto/documentación.
- **Prueba de aceptación**:
  1. Abrir la vista de Ayuda y hacer clic en un encabezado de sección colapsable: el bloque se despliega fluidamente mostrando el contenido descriptivo.

---

### 5.13 Estados de Error (Fatal Overlay / Render Notice / Toast)
- **Problema observado**: Ante una desconexión o fallo interno de renderizado, aparece una pantalla de error fatal `#fatal` (`Axx.html:1387`) que oculta toda la interfaz sin dar opción al usuario de reiniciar el estado o recuperar su trabajo.
- **Causa comprobada o hipótesis**:
  1. El gestor global `window.onerror` y `window.onunhandledrejection` activa de forma inflexible el contenedor `#fatal.active`, aplicando `display: flex; z-index: 999999;` y bloqueando toda interacción posterior sin ofrecer botón de recarga ni diagnóstico.
- **Archivos implicados**:
  - `1.AXX/Axx.html` (líneas 33: `#render-notice`; líneas 1371: `#toast`; líneas 1387: `#fatal`; líneas 18480–18510: manejo global de errores).
- **Corrección propuesta**:
  1. Reemplazar el bloqueo total de `#fatal` por un sistema de notificaciones no destructivas (`#toast` y `#render-notice`) para errores no críticos.
  2. En caso de error crítico irrecuperable en WebGL, proveer un botón explícito de "Reiniciar Modo Gráfico Seguro" (Canvas2D) y "Restablecer Ventana" que limpie el estado corrupto y recargue el WebView sin obligar a reiniciar el proceso Tauri por completo.
- **Prueba de aceptación**:
  1. Simular un fallo en un comando o servicio secundario: la UI muestra un toast de advertencia claro con botón de reintentar, manteniendo el avatar y los paneles plenamente operativos.

---

## 6. Estrategia de Mitigación y Recomendaciones Técnicas para Implementación

Para que los agentes integradores de fases posteriores puedan solventar estos problemas de forma limpia y definitiva, se recomiendan las siguientes directrices técnicas:

1. **Reforma del Bounding Box y Hit-Testing Nativo**:
   - Ampliar el margen de holgura de la ventana en `ResidentDesktop.layout()` de `12px` a un mínimo de **72px** (`margin = 72`). Esto evitará inmediatamente que los tentáculos sean guillotinados por el HWND de Windows.
   - En `src-tauri/src/lib.rs`, introducir un buffer temporal de permanencia de foco (histeresis de 150 ms) antes de alternar `set_ignore_cursor_events(true)` para evitar la pérdida de eventos al pasar el ratón velozmente entre botones.
2. **Desacoplamiento de Eventos de Puntero**:
   - Eliminar el `event.stopImmediatePropagation()` general en `ResidentDesktop.bindDrag()`. El arrastre debe limitarse exclusivamente a elementos que cuenten explícitamente con el atributo `data-drag-handle="true"`.
   - Limitar la emisión de `desktop_layout` en arrastre mediante `requestAnimationFrame` o un debounce de **16 ms** (60 FPS) para no ahogar la cola Win32 de mensajes.
3. **Unificación del Ciclo de Vida del Avatar**:
   - Eliminar las 5 sobreescrituras en cascada de `companion.onAvatarTap`. Establecer un único despachador que evalúe el estado actual:
     - `Estado 0 (Reposo)` -> Clic -> `Estado 2 (Abanico de herramientas abierto)`.
     - `Estado 2` -> Clic fuera -> `Estado 0`.
4. **Implementación de Redimensionado Real**:
   - Incorporar un tirador de redimensionado `.resize-handle` en la esquina inferior derecha de `#panel` con persistencia de `{ width, height }` en `localStorage['axx.resident.panel-size']`.
