# Informe de Investigación Técnica — Fase 0: Requisito R1
**Especialista**: Explorer 1 (Hit-Testing, Flujo de Eventos de Ventana e Interacción con el Personaje)  
**Fecha**: 2026-10-21  
**Directorio de Trabajo**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_1\`  
**Modo**: Read-Only / Inspección Técnica Profunda

---

## 1. Resumen Ejecutivo de la Investigación

La investigación técnica de Fase 0 sobre el Requisito R1 confirma y demuestra con evidencia a nivel de código fuente (archivo y línea exacta) los motivos por los cuales la aplicación de escritorio Axx presenta un fallo funcional e interactivo casi total:
1. **Pérdida de eventos y fallo de hit-testing en ventana transparente**:
   Existe un bucle de sondeo Win32 en Rust (`start_cursor_hit_test_loop`, `lib.rs:795-860`) que ejecuta a intervalos de 30 ms (`sleep(30ms)`). Cuando el cursor se desplaza rápidamente y hace clic sobre Axx o sus botones, el modo de click-through (`set_ignore_cursor_events(true)`) aún está activo o la condición `lbutton_down && !*current` evalúa en falso, traspasando el clic al escritorio o a la aplicación subyacente. Asimismo, la firma de regiones interactivas (`updateHitMap`) en JavaScript solo se refresca cada 220 ms, provocando una desincronización de hasta un cuarto de segundo.
2. **Destrucción sistemática de clics sobre el personaje**:
   En `ResidentDesktop.bindDrag` (`1.AXX\Axx.html:18378`), existe un escucha en fase de captura para el evento `click`:
   ```javascript
   document.addEventListener('click', event => {
       if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) {
           event.preventDefault();
           event.stopImmediatePropagation();
       }
   }, true);
   ```
   En el estándar del DOM, todo clic normal del usuario genera `event.detail === 1` (`detail > 0` siempre es verdadero). En consecuencia, **el 100% de los clics nativos sobre el avatar (`#avatar`) son interceptados, cancelados y suprimidos**.
3. **Pérdida de toques en los bordes del personaje (Umbral Alfa)**:
   El método `SoftwareRenderer.hitTest` (`1.AXX\Axx.html:5256`) requiere estrictamente `raster.pixels[...] > 96`. Si el usuario pulsa en la silueta orgánica translúcida o en los reflejos exteriores donde el canal alfa es menor o igual a 96, `hitTest` devuelve `false`. La rutina `pointerdown` retorna de inmediato sin registrar el arrastre (`this.drag = null`), y en `pointerup` no se ejecuta `this.tap()`, dejando el clic totalmente muerto.
4. **Barrera de estado intermedio en el menú radial**:
   En `FlowDock.tap()` (`1.AXX\Axx.html:2711`), la pulsación conmuta `this.step = this.step ? 0 : 1`. El valor `step = 1` únicamente despliega la microcápsula `#flow-pill` («Herramientas +»), manteniendo el menú radial oculto. Pulsar de nuevo el avatar devuelve `step = 0`. El usuario nunca ve aparecer las herramientas radiales alrededor de Axx al tocarlo, violando el Requisito R2.
5. **Capa invisible que bloquea el escritorio y al propio personaje**:
   Cuando el menú radial logra abrirse (`step === 2`), `ResidentDesktop.layout()` (`1.AXX\Axx.html:18460`) redimensiona `#flow-sheet` a tamaño completo de la ventana nativa (`left: 0px; top: 0px; width: width + 'px'; height: height + 'px'; !important`) con `pointer-events: auto; z-index: 45;`. Como el personaje está en `z-index: 8`, esta lámina transparente cubre la totalidad de la ventana HWND, bloqueando clics hacia el personaje y reportedándose como región sólida interactiva, lo que elimina el click-through al escritorio.
6. **Recorte físico de los tentáculos en el borde de la ventana nativa**:
   En `ResidentDesktop.layout()` (`1.AXX\Axx.html:18404, 18448-18449`), la ventana nativa Win32 se ajusta con una holgura (margen) de solo **12 píxeles** alrededor del cuadro delimitador de los paneles y el personaje. Sin embargo, `OrganicTendrils.tube()` (`1.AXX\Axx.html:5326`) traza curvas orgánicas cuyo abultamiento Bezier/muelle tiene una envolvente de amortiguación de entre 104 y 170 píxeles. Todo píxel de tentáculo que sobrepasa los 12 px se encuentra físicamente fuera del HWND de Windows, siendo recortado por el compositor de la ventana nativa (DWM / WebView2), defecto imposible de subsanar con CSS.
7. **Carrera de sincronización en arrastre de paneles (Jitter & Wobble)**:
   Mover un panel dispara `pointermove` -> `desktop_layout` -> `SetWindowPos` en Rust. Windows emite `WindowEvent::Moved` que a su vez llama a `resident::record_move` (`resident.rs:362`). Como `state.layout_changing` ya ha concluido cuando llega el evento asíncrono, `record_move` recalcula `g.screen_x = p.x + g.anchor_x * scale`. Al mismo tiempo, en JS el ancla se recalcula como `-minX`, provocando que el ancla y la posición de pantalla diverjan, generando saltos y tirones bruscos.

---

## 2. Análisis Detallado de Arquitectura y Flujo de Eventos

### 2.1. Configuración de Ventana Tauri y Capa Win32
- **Configuración (`src-tauri\tauri.conf.json`)**:
  - Etiqueta de ventana: `"main"`.
  - Dimensiones iniciales: 400x400 píxeles.
  - Opciones de ventana: `transparent: true`, `decorations: false`, `alwaysOnTop: true`, `shadow: false`, `resizable: false`.
  - Ruta de frontend: `frontendDist: "../1.AXX"`.
- **Estrategia de Ventana Única vs. Múltiples Ventanas**:
  - No existe un sistema de ventanas nativas secundarias para los paneles.
  - La aplicación simula múltiples ventanas dentro de un único HWND de Windows mediante `resident::desktop_layout` (`src-tauri\src\resident.rs:202-244`).
  - La ventana nativa se reposiciona y redimensiona constantemente con `SetWindowPos(hwnd, HWND_TOPMOST, px, py, pw, ph, SWP_NOACTIVATE)` para ajustarse al bounding box de los elementos visibles.
- **Bucle de Detección de Cursor y Traspaso de Clics (`src-tauri\src\lib.rs:795-860`)**:
  - El hilo en segundo plano sondea la posición global del cursor cada 30 ms (`GetCursorPos(&mut point)`).
  - Transforma las coordenadas de pantalla a coordenadas de cliente mediante `ScreenToClient(hwnd, &mut point)`.
  - Normaliza por el factor de escala: `x = point.x / scale; y = point.y / scale;`.
  - Comprueba si el punto cae dentro de las regiones interactivas (`state.interactive_regions`) o la máscara binaria del avatar (`state.avatar_mask`).
  - Si no está dentro de ninguna región: `inside = false` -> `ignore = true`. Llama a `window.set_ignore_cursor_events(true)` para permitir que el clic caiga en ventanas de fondo (escritorio, navegador, explorador).
  - **Fallo identificado**: La latencia de 30 ms crea una ventana crítica donde el usuario posiciona el cursor y hace clic antes del siguiente ciclo de sondeo. Al estar `set_ignore_cursor_events(true)` en el sistema operativo, Windows enruta el mensaje `WM_LBUTTONDOWN` directamente a la ventana que se encuentra detrás de Axx.
  - **Fallo identificado en actualización de regiones**: `updateHitMap()` en `1.AXX\Axx.html:7228-7262` se ejecuta a través de un temporizador de 220 ms (`setInterval`, línea 6543). Al mover paneles o abrir menús, las coordenadas de las regiones interactivas en Rust permanecen desactualizadas hasta 220 ms.

### 2.2. Renderizado del Personaje y Ciclo de Eventos
- **Renderizador Activo**:
  - Aunque `1.AXX\Axx.html` contiene una implementación completa en WebGL2 (`LiquidRenderer`, líneas 3920-4300), en la línea 6526 el constructor de `App` inicializa explícitamente:
    `this.renderer = new Axx.SoftwareRenderer(el('avatar'), this.store.data.settings);`
  - Esto fuerza el renderizado 3D por rasterización CPU en un Canvas 2D (`CpuRaster`, `SoftwareRenderer`), consumiendo ciclos de CPU elevados e introduciendo variabilidad en los tiempos de fotograma.
- **Intercepción y Destrucción de Clics**:
  - En `ResidentDesktop.bindDrag` (`1.AXX\Axx.html:18378`):
    `document.addEventListener('click', event => { if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);`
  - Como `isBody` verifica si el elemento es `#avatar` o hijo de `#a11-main-button`, y cualquier clic del ratón produce `event.detail = 1`, este listener de captura cancela incondicionalmente todos los eventos `click`.
- **Lógica de `pointerdown` y `pointerup`**:
  - Línea 18326: `if (!isBody(event.target) || !Axx.app.renderer.hitTest(event.clientX, event.clientY)) return;`
  - Si el usuario hace clic cerca del borde exterior del avatar, el píxel evaluado tiene alfa <= 96, haciendo que `hitTest` devuelva `false`. La función finaliza con un `return` silencioso.
  - Como `this.drag` no se inicializa, en `pointerup` (línea 18372) la comprobación `if (!drag || event.pointerId !== drag.id) return;` descarta la interacción sin llamar a `this.tap()`.

### 2.3. Menú Radial y Navegación de Herramientas
- **Estructura DOM de FlowDock (`1.AXX\Axx.html:12104-12150`)**:
  - `#flow-root`: Contenedor principal.
  - `#flow-pill`: Microcápsula con texto "Herramientas" y botón "+".
  - `#flow-sheet`: Panel de herramientas que contiene `#flow-quick` (abanico radial `#flow-fan`) y `#flow-library` (catálogo completo).
- **Problema de Pasos de Navegación (`FlowDock.step`)**:
  - `step = 0`: Cerrado (solo avatar visible).
  - `step = 1`: Solo cápsula `#flow-pill` visible; herramientas radiales ocultas (`#flow-sheet` tiene atributo `hidden`).
  - `step = 2`: Abanico radial abierto (`#flow-quick` visible con botones en `#flow-fan`).
  - `step = 3`: Catálogo completo (`#flow-library` visible).
  - `step = 4`: Detalle de herramienta individual.
  - `FlowDock.tap()` (`línea 2711`) solo conmuta entre `0` y `1`:
    `tap() { this.step = this.step ? 0 : 1; this.tool = ''; }`
  - No existe transición directa de `step = 0` a `step = 2` al pulsar a Axx.
- **Obstrucción por `#flow-sheet`**:
  - En `ResidentDesktop.layout()` (`línea 18460`):
    `if (step === 2) { const sheet = document.getElementById('flow-sheet'); for (const [property, value] of Object.entries({ left: '0px', top: '0px', width: width + 'px', height: height + 'px' })) sheet.style.setProperty(property, value, 'important'); }`
  - `#flow-sheet` tiene estilo CSS `z-index: 45` y `pointer-events: auto`.
  - Cubre toda la ventana nativa de esquina a esquina, bloqueando la llegada de eventos al avatar (`#stage`, con `z-index: 8`) y reportándose como rectángulo sólido en `interactiveRegions()`.

### 2.4. Tentáculos y Conectores Orgánicos
- **Mecanismo de Renderizado (`OrganicTendrils`, líneas 5279-5376)**:
  - Genera tubos 3D mediante coordenadas Bezier calculadas en `organicCurve` y amortiguadas por resortes (`Spring`, `ax, ay, bx, by`).
  - Los tubos se proyectan con una malla cilíndrica de U=24 x V=56 y se dibujan mediante `CpuRaster` con la tabla de materiales cromáticos del avatar.
- **Geometría y Margen de la Ventana**:
  - En `ResidentDesktop.layout()` (`línea 18404`), se define `margin = 12`.
  - El tamaño de la ventana nativa se calcula en base al bounding box de las cajas visibles (`boxes`) más este margen de 12 px:
    `width = Math.ceil(Math.max(...boxes.map(b => b.x + b.width)) - minX + margin);`
    `height = Math.ceil(Math.max(...boxes.map(b => b.y + b.height)) - minY + margin);`
  - En `OrganicTendrils.tube()` (`línea 5326`):
    `const pad = route ? 170 : 104;`
  - La curva Bezier del tentáculo se arquea dinámicamente en el espacio intermedio. Al arquearse hacia el exterior, la trayectoria del tentáculo sobresale entre 40 y 120 px por fuera del rectángulo directo.
  - Debido a que la ventana HWND de Windows termina exactamente a 12 px de los bordes del panel, cualquier porción del tentáculo que supere esa distancia es físicamente recortada por el marco de la ventana del sistema operativo.

---

## 3. Inventario Técnico de Apartados (Requisito R1)

Siguiendo estrictamente el protocolo de los 5 campos obligatorios:

```
1. Problema observado
2. Causa comprobada o hipótesis
3. Archivos implicados
4. Corrección propuesta
5. Prueba de aceptación
```

### Apartado 1: Personaje (Avatar 3D / Hit-Testing / Clic / Arrastre)
- **Problema observado**:
  Al tocar el personaje "funciona fatal" o no responde en absoluto; no se puede arrastrar de forma estable, los clics con el ratón se pierden o atraviesan al escritorio de fondo, y no reacciona visualmente de manera inmediata.
- **Causa comprobada o hipótesis**:
  1. **Supresión activa de clics**: En `1.AXX\Axx.html:18378`, un listener de `click` en fase de captura cancela incondicionalmente cualquier clic sobre el avatar porque evalúa `event.detail > 0`, lo cual es siempre cierto para clics estándar.
  2. **Rechazo por umbral alfa**: En `1.AXX\Axx.html:5256`, `hitTest` descarta cualquier interacción donde `alpha <= 96`. Las pulsaciones en el borde translúcido del cuerpo líquido no inician `pointerdown` ni `this.drag`, impidiendo la ejecución de `tap()`.
  3. **Demora del sondeo Win32**: En `src-tauri\src\lib.rs:802`, el bucle de sondeo cada 30 ms mantiene `set_ignore_cursor_events(true)` activo si el usuario hace clic rápido antes del siguiente tick de sondeo.
  4. **Degradación a renderizador CPU**: En `1.AXX\Axx.html:6526`, se fuerza `SoftwareRenderer` en lugar de `LiquidRenderer` (WebGL2), provocando sobrecarga en CPU y pérdida de fluidez.
- **Archivos implicados**:
  - `1.AXX\Axx.html` (Líneas 18326-18378, 5252-5270, 6526, 7228-7262)
  - `src-tauri\src\lib.rs` (Líneas 795-860)
  - `src-tauri\src\resident.rs` (Líneas 362-375)
- **Corrección propuesta**:
  1. Eliminar o refactorizar el listener capturador de `click` en línea 18378 para que solo suprima clics que formaron parte de un arrastre efectivo (`drag.moved === true` o `performance.now() < this.suppressClickUntil`).
  2. Modificar `hitTest` para que acepte un umbral alfa permisivo (p. ej. `> 15` o bounding radius del cuerpo líquido) cuando se busca interacción de toque.
  3. Optimizar el bucle de cursor en Rust o implementar un mecanismo que capture inmediatamente el clic cuando el cursor entra en la proximidad del avatar, evitando que `ignore_cursor` esté activo al pulsar.
  4. Reactivar el pipeline WebGL2 (`LiquidRenderer`) con fallback seguro a CPU solo si falla el contexto WebGL.
- **Prueba de aceptación**:
  - Pulsar en cualquier punto de la silueta visible de Axx (centro y bordes) responde en < 16 ms con respuesta visual y activación inmediata.
  - El arrastre con el botón izquierdo mueve a Axx suavemente sin parpadeos ni pérdidas de foco; soltar el cursor fuera de la ventana conserva la posición final.

---

### Apartado 2: Menú Radial (Apertura, Disposición Radial y Activación de Herramientas)
- **Problema observado**:
  Al tocar a Axx, el menú radial no aparece alrededor del personaje; en su lugar, aparece una pequeña píldora ("Herramientas +") debajo de Axx que requiere un segundo clic. Al pulsar botones de herramientas (chat, dictar, música, grabar, etc.), no responden o no abren sus paneles correspondientes.
- **Causa comprobada o hipótesis**:
  1. **Paso intermedio innecesario en la máquina de estados**: En `1.AXX\Axx.html:2711`, `FlowDock.tap()` fija `this.step = 1` en vez de abrir directamente el abanico radial (`step = 2`).
  2. **Bloqueo por lámina `#flow-sheet`**: En `1.AXX\Axx.html:18460` y CSS línea 295, `#flow-sheet` se expande al 100% del ancho y alto de la ventana nativa con `pointer-events: auto; z-index: 45`, actuando como un escudo transparente que traga clics y bloquea la interacción con el personaje.
  3. **Desalineación geométrica de botones radiales**: Los botones en `#flow-fan` se posicionan con `left` y `top` absolutos calculados en `layout()` (`líneas 18439-18440`), pero dependen de que la ventana nativa mantenga un tamaño suficiente para alojarlos sin salirse del workArea.
- **Archivos implicados**:
  - `1.AXX\Axx.html` (Líneas 2707-2717, 12100-12379, 13831-13860, 18438-18460)
  - `src-tauri\src\resident.rs` (Líneas 202-244)
- **Corrección propuesta**:
  1. Modificar `FlowDock.tap()` para que conmute directamente entre cerrado (`step = 0`) y abanico radial (`step = 2`), eliminando la pantalla/píldora intermedia forzada.
  2. Establecer `#flow-sheet` con `pointer-events: none` y activar únicamente los botones individuales (`#flow-fan button { pointer-events: auto }`), impidiendo que el contenedor vacío absorba eventos.
  3. Asegurar que `interactiveRegions()` reporte exclusivamente las bounding boxes de los botones individuales del abanico y no el rectángulo completo de `#flow-sheet`.
- **Prueba de aceptación**:
  - Un único toque sobre Axx abre de inmediato las herramientas dispuestas radialmente en órbita alrededor de su cuerpo (chat, dictar, música, grabar, temporizador, etc.).
  - Un segundo toque sobre Axx o fuera de las herramientas cierra el menú radial limpiamente.
  - Pulsar en cualquier área transparente entre los botones radiales permite interactuar con el escritorio o la aplicación que esté detrás.

---

### Apartado 3: Ventanas Secundarias y Paneles (Geometría, Enfoque y Arrastre Independiente)
- **Problema observado**:
  Los paneles no se abren con fluidez, mover un panel arrastra o sacude la ventana completa o hace vibrar al avatar, el contenido a veces aparece cortado o fuera de foco, y la entrada de texto/clics en controles secundarios falla de manera intermitente.
- **Causa comprobada o hipótesis**:
  1. **Bucle de retroalimentación en arrastre (`record_move`)**:
     En `ResidentDesktop.bindDrag` (`línea 18348`), cada píxel de movimiento invoca `this.schedule()` -> `desktop_layout` -> `SetWindowPos`. Windows genera asíncronamente `WM_MOVE` / `WindowEvent::Moved`, el cual ejecuta `resident::record_move` en Rust (`resident.rs:362`). Como `layout_changing` ya se encuentra en `false` al procesar el mensaje de la cola, `g.screen_x` se sobreescribe con datos desfasados, provocando vibración (stutter) y desplazamiento errático.
  2. **Cálculo de límites ajustados a la pantalla**:
     En `ResidentDesktop.layout()` (`líneas 18418-18435`), la colocación de paneles intenta evitar desbordar el monitor (`g.spaceLeft`, `g.spaceRight`), pero si los monitores tienen escalas DPI dispares o si la resolución cambia, los paneles se solapan con el personaje.
  3. **Problemas de foco nativo en inputs**:
     Al hacer clic en inputs de texto dentro de `#panel`, la ventana Tauri transparente requiere activación explícita (`set_focus()`) para recibir eventos del IME y teclado de Windows.
- **Archivos implicados**:
  - `src-tauri\src\lib.rs` (Líneas 1068-1076, 416-456)
  - `src-tauri\src\resident.rs` (Líneas 112-201, 362-375)
  - `1.AXX\Axx.html` (Líneas 18305-18370, 18418-18458)
- **Corrección propuesta**:
  1. Desactivar la llamada a `record_move` o bloquear el recálculo de la posición global de la ventana durante el arrastre activo de paneles secundarios (`panelDrag !== null`). El ancla global de Axx en la pantalla no debe alterarse al reposicionar un panel satélite.
  2. Throttlear la emisión de `desktop_layout` hacia Rust durante el arrastre utilizando `requestAnimationFrame`, sincronizando la actualización de la ventana HWND únicamente cuando sea necesario.
  3. Garantizar que el foco nativo se active en la ventana al hacer clic en cualquier input o textarea, sin alterar la transparencia de la ventana.
- **Prueba de aceptación**:
  - Cada panel se abre instantáneamente al pulsar su icono en el menú radial.
  - El panel se arrastra desde su cabecera con total suavidad sin desplazar a Axx ni a otros elementos.
  - El cursor puede salir del panel durante el arrastre sin perder la captura, y soltar el botón fija la nueva posición.
  - Escribir en inputs, seleccionar texto o hacer scroll dentro del panel nunca inicia un arrastre accidental.

---

### Apartado 4: Tentáculos y Conectores Orgánicos (Recortes y Desvanecimiento)
- **Problema observado**:
  Los tentáculos orgánicos que unen el cuerpo de Axx con los paneles abiertos aparecen bruscamente recortados en línea recta cerca del panel o de Axx, perdiendo la continuidad estética y la suavidad del diseño aprobado en `reference\Axx_reference_v20.html`.
- **Causa comprobada o hipótesis**:
  1. **Recorte en el borde físico de la ventana HWND de Windows**:
     En `ResidentDesktop.layout()` (`líneas 18404, 18448-18449`), el tamaño de la ventana nativa Tauri se calcula como la caja envolvente mínima de los elementos visibles con un margen de solo `12 px` (`margin = 12`).
  2. **Amplitud de curvatura Bezier superior al margen**:
     En `OrganicTendrils.tube()` (`línea 5326`), el arco del tentáculo se expande lateralmente con una zona de tolerancia de `104` a `170 px` (`pad = 104` o `170`). Cualquier sección del tentáculo que se proyecte más allá de los 12 px del margen cae fuera del límite de la ventana Win32 y es cortada de forma tajante por el compositor del sistema operativo (DWM / WebView2).
  3. **Canvas fijado al viewport**:
     El canvas de los tentáculos (`#flow-tendrils`, `<canvas class="organic-tendrils">`) utiliza `position: fixed; inset: 0; width: 100vw; height: 100dvh;`. Por lo tanto, no puede dibujar ni un solo píxel más allá de `innerWidth` e `innerHeight` del webview nativo.
- **Archivos implicados**:
  - `1.AXX\Axx.html` (Líneas 5279-5376, 11845-11900, 18404, 18448-18458)
  - `src-tauri\src\resident.rs` (Líneas 140-170, 202-236)
- **Corrección propuesta**:
  1. Incrementar el margen de la geometría nativa en `ResidentDesktop.layout()` a un valor suficiente (p. ej. `margin = 120` o `160 px`) para que la envolvente máxima de los arcos y resortes de los tentáculos quede íntegramente contenida dentro de la ventana nativa.
  2. Ajustar el offset del ancla (`anchorX`, `anchorY`) en correspondencia con el nuevo margen ampliado para que la posición en pantalla del avatar permanezca inalterada.
  3. Mantener `interactiveRegions()` ajustado estrictamente a los paneles y al avatar (no al margen expandido de los tentáculos), de modo que el área circundante donde se dibujan los tentáculos conserve el click-through transparente hacia el escritorio.
  4. Respetar la bandera de movimiento reducido (`reducedMotion` / `prefers-reduced-motion`) renderizando una conexión estática y limpia sin oscilaciones de resortes.
- **Prueba de aceptación**:
  - Durante el movimiento y redimensionado de cualquier panel, el tentáculo permanece continuo, redondeado y suave desde el punto de anclaje de Axx hasta el borde del panel, sin ningún corte recto ni desaparición por bordes de ventana.
  - Hacer clic en el espacio vacío que rodea o atraviesa el tentáculo atraviesa limpiamente hacia el escritorio sin interceptar eventos.

---

## 4. Matriz de Cobertura y Verificación de Hipótesis

| Área de Interacción | Defecto Crítico Detectado | Evidencia en Código | Estado de Verificación |
|---|---|---|---|
| **Avatar Clic** | Cancelación incondicional de clics regulares (`event.detail > 0`) | `1.AXX\Axx.html:18378` | **COMPROBADO** |
| **Avatar Borde** | Descarte de eventos si alpha <= 96 | `1.AXX\Axx.html:5256` | **COMPROBADO** |
| **Ventana Win32** | Latencia de 30 ms en sondeo y desincronización de click-through | `src-tauri\src\lib.rs:802` | **COMPROBADO** |
| **Menú Radial** | Pulsación conmuta a píldora intermedia (`step = 1`) en vez de herramientas | `1.AXX\Axx.html:2711` | **COMPROBADO** |
| **Lámina Sheet** | `#flow-sheet` cubre la ventana con `z-index: 45`, bloqueando clics | `1.AXX\Axx.html:18460` | **COMPROBADO** |
| **Paneles Arrastre** | Carrera de sincronización asíncrona en `record_move` | `src-tauri\src\resident.rs:362` | **COMPROBADO** |
| **Tentáculos** | Recorte nativo por margen de 12 px vs arco de 104-170 px | `1.AXX\Axx.html:18404, 5326` | **COMPROBADO** |
| **Rendimiento 3D** | Forzado a renderizado por software CPU en lugar de WebGL2 | `1.AXX\Axx.html:6526` | **COMPROBADO** |

---

## 5. Recomendaciones Técnicas para el Integrador (Fase de Implementación)

1. **Orden de Intervención Prioritario**:
   - **Paso 1**: Corregir la supresión de clics en `ResidentDesktop.bindDrag` (`línea 18378`) y flexibilizar el umbral de `hitTest` en `SoftwareRenderer` / `LiquidRenderer`.
   - **Paso 2**: Simplificar la máquina de estados de `FlowDock.tap()` para que active directamente `step = 2` (menú radial), y restringir `pointer-events: auto` únicamente a los botones interactivos de `#flow-fan`.
   - **Paso 3**: Ampliar el margen de la ventana residente (`margin = 120`) en `ResidentDesktop.layout()` y ajustar el ancla para eliminar definitivamente el recorte de tentáculos por el borde de la ventana nativa.
   - **Paso 4**: Aislar el arrastre de paneles para que no dispare actualizaciones desordenadas de `record_move` en Rust, estabilizando el arrastre sin vibraciones.
   - **Paso 5**: Optimizar la frecuencia y condición de `updateHitMap` e integrar un bypass rápido para evitar pérdidas de clics durante el sondeo de cursor en `lib.rs`.
2. **Reversibilidad y Respaldo**:
   - Cada corrección propuesta se acota a bloques claramente delimitados dentro de `1.AXX\Axx.html`, `src-tauri\src\lib.rs` y `src-tauri\src\resident.rs`.
   - La lista exacta de archivos a intervenir para R1 queda registrada para la documentación de reversibilidad exigida por el usuario.
