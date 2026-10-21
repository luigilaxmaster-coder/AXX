# Informe de Implementación Técnica — Hito 1: Hit-Testing y Menú Radial

**Integrador**: Worker M1 (Hit-Testing & Radial Interaction Integrator)  
**Fecha**: 2026-10-21  
**Directorio**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\worker_m1\`  
**Archivos Modificados**:  
- `1.AXX/Axx.html`  
- `src-tauri/src/lib.rs`  

---

## 1. Resumen de Objetivos y Resultados del Hito 1

En respuesta a la asignación del Hito 1 (Hit-Testing & Radial Interaction), se completaron con éxito y verificación rigurosa las 8 tareas requeridas:

| # | Tarea del Hito 1 | Estado | Resultado / Verificación |
|---|---|---|---|
| 1 | Limpieza de procesos zombi huérfanos | **COMPLETADO** | 22 procesos huérfanos de `python.exe -m backend.connect.mcp_server` terminados de forma segura vía PowerShell. 0 procesos residuales. |
| 2 | Eliminación de cancelación destructiva de clics DOM | **COMPLETADO** | Eliminada la comprobación `event.detail > 0` en `Axx.html:18378`. Implementado umbral genuino de arrastre de 4 px (`Math.hypot > 4`). Solo se suprimen clics si hubo desplazamiento efectivo. |
| 3 | Ajuste de corte alfa en Hit-Testing | **COMPLETADO** | Reducido el umbral alfa en `SoftwareRenderer.hitTest`, `hitMask` y `LiquidRenderer.hitTest` de `> 96` / `> 100` a `> 16`, permitiendo interacción fluida en bordes translúcidos. |
| 4 | Máquina de estados del Menú Radial | **COMPLETADO** | Modificado `FlowDock.tap()` para conmutar directamente `this.step = this.step ? 0 : 2` (abriendo `#flow-fan`), y `ResidentDesktop.tap()` para alternar la clase `resident-invoked`. |
| 5 | Corrección de bloqueo CSS en `#flow-fan` | **COMPLETADO** | Eliminado `pointer-events: none !important` de `#flow-fan` en CSS línea 1346. Añadido `pointer-events: auto !important` a los botones y sus hijos SVG/span. |
| 6 | Fondo de `#flow-sheet` y registro en Hit Map | **COMPLETADO** | Asignado `pointer-events: none` al telón de fondo de `#flow-sheet` en `layout()`, y añadido explícitamente el bounding box de `#stage` / `#avatar` a `interactiveRegions()`. |
| 7 | Optimización de sondeo en Rust Tauri y sincronización DPI | **COMPLETADO** | Sondeo acelerado a 10 ms (100 Hz), factor de escala sincronizado con `current_monitor().scale_factor()`, e `ignore` fijado incondicionalmente en `false` cuando el cursor está dentro de una región activa. Tolerancia de borde de 2 px añadida a `PixelMask`. |
| 8 | Verificación y Validación de Compilación | **COMPLETADO** | `cargo check` finalizado en 4.75s con 0 errores y 0 advertencias. Node AST validation de bloques `<script>` en `Axx.html` con 0 errores. Suite de 6 aserciones automatizadas ejecutada al 100% PASS. |

---

## 2. Detalle de Modificaciones en Código Fuente

### 2.1 Limpieza de Procesos Zombi (`python.exe -m backend.connect.mcp_server`)
- Se identificaron los 22 PIDs huérfanos generados por sesiones MCP anteriores.
- Se ejecutó el comando PowerShell seguro filtrado por nombre y línea de comando específica:
  ```powershell
  Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*backend.connect.mcp_server*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  ```
- Se realizó una consulta de verificación posterior confirmando que no queda ningún proceso Python ejecutando dicho módulo.

### 2.2 Eliminación de Cancelación de Clics DOM (`1.AXX/Axx.html`)
- **Problema**: `ResidentDesktop.bindDrag()` contenía:
  ```javascript
  document.addEventListener('click', event => {
      if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) {
          event.preventDefault();
          event.stopImmediatePropagation();
      }
  }, true);
  ```
  En el estándar W3C UI Events, cualquier clic de ratón genera `event.detail >= 1`. Por tanto, el 100% de los clics en el avatar eran interceptados y cancelados.
- **Corrección**:
  - Se eliminó `event.detail > 0`.
  - Se ajustó el umbral de movimiento a 4 píxeles (`Math.hypot(event.clientX - drag.x, event.clientY - drag.y) <= 4`).
  - En `pointerup`: se evalúa `wasDrag = drag.moved || (distance > 4)`. Si no hubo arrastre (`!wasDrag`), se ejecuta `this.tap()`. Si hubo arrastre real, se activa `this.suppressClickUntil = performance.now() + 800`.
  - El listener de `click` ahora solo cancela si `performance.now() < this.suppressClickUntil`.

### 2.3 Ajuste de Umbral Alfa de Hit-Testing (`1.AXX/Axx.html`)
- **Problema**: En `SoftwareRenderer.hitTest` y `hitMask`, el corte alfa exigía `alpha > 96`. En `LiquidRenderer.hitTest`, exigía `alpha > 100`. Las pulsaciones en el borde del muñeco no activaban `pointerdown`.
- **Corrección**:
  - En `SoftwareRenderer.hitTest`: `raster.pixels[...] > 16`.
  - En `SoftwareRenderer.hitMask`: `raster.pixels[...] > 16 ? 1 : 0`.
  - En `LiquidRenderer.hitTest`: `v[3] > 16`.

### 2.4 Máquina de Estados del Menú Radial (`1.AXX/Axx.html`)
- **Problema**: `FlowDock.tap()` conmutaba `this.step = this.step ? 0 : 1`. El paso 1 solo mostraba una píldora colapsada `Herramientas +` sin abrir el abanico radial orbital (`step === 2`).
- **Corrección**:
  - En `FlowDock.tap()`:
    ```javascript
    tap() { this.step = this.step ? 0 : 2; this.tool = ''; }
    ```
  - En `FlowExperience.tap()`:
    ```javascript
    tap() {
        this.cancelReview();
        this.organic.fold();
        this.nav.tap();
        this.render();
        if (this.nav.step === 2)
            fx('flow-fan')?.querySelector('button')?.focus({ preventScroll: true });
        else if (this.nav.step === 1)
            fx('flow-pill')?.focus({ preventScroll: true });
    }
    ```
  - En `ResidentDesktop.tap()`:
    ```javascript
    tap() {
        Axx.flow.tap();
        const isOpen = (Axx.flow.nav.step !== 0);
        this.invoked = isOpen;
        document.body.classList.toggle('resident-invoked', isOpen);
        this.schedule();
    }
    ```

### 2.5 Desbloqueo de Pointer-Events en CSS (`1.AXX/Axx.html`)
- **Problema**: La regla CSS:
  ```css
  body.native.axx-resident #flow-quick,body.native.axx-resident #flow-fan... { pointer-events: none !important; }
  ```
  impedía que los botones orbitales de herramientas respondieran al cursor de Windows.
- **Corrección**:
  - Se separó `#flow-fan` de la regla con `!important`.
  - Se definió `#flow-fan` con `pointer-events: none` normal (permitiendo que los hijos reciban eventos).
  - Se configuró `pointer-events: auto !important` explícito sobre `#flow-fan>button`, `#flow-fan [data-quick]`, `#flow-all` y todos los elementos internos (`#flow-fan [data-quick] *`).

### 2.6 Fondo de `#flow-sheet` y Registro del Avatar en Hit Map (`1.AXX/Axx.html`)
- **Problema**: Cuando el menú radial se abría (`step === 2`), `#flow-sheet` se expandía a toda la pantalla y cubría al avatar en `z-index: 45`. Además, `#stage` / `#avatar` no estaba incluido en `interactiveRegions()`.
- **Corrección**:
  - En `ResidentDesktop.layout()` (`step === 2`), `#flow-sheet` recibe `pointer-events: none !important`.
  - En `ResidentDesktop.interactiveRegions()`:
    ```javascript
    const stage = document.getElementById('stage') || document.getElementById('avatar');
    if (stage && !stage.hidden) {
        const sr = stage.getBoundingClientRect();
        if (sr.width > 0 && sr.height > 0 && sr.right > 0 && sr.bottom > 0 && sr.x < innerWidth && sr.y < innerHeight) {
            regions.push({ x: sr.x, y: sr.y, width: sr.width, height: sr.height });
        }
    }
    ```
  - Los contenedores de pantalla completa (`#flow-sheet`, `#flow-fan`) se excluyeron del selector de regiones interactivas, evitando que una capa transparente vacía bloquee el click-through al escritorio.

### 2.7 Optimización del Bucle de Sondeo de Cursor y DPI en Rust (`src-tauri/src/lib.rs`)
- **Problema**: El sondeo de cursor cada 30 ms (`std::thread::sleep(Duration::from_millis(30))`) causaba que al mover el cursor rápidamente sobre el avatar y hacer clic, `set_ignore_cursor_events(true)` continuara activo, traspasando el clic a ventanas del sistema. Además, `scale_factor` no consideraba monitores secundarios.
- **Corrección**:
  - Intervalo reducido a **10 ms** (100 Hz, instantáneo para eventos de ratón).
  - Escala sincronizada consultando `window.current_monitor().ok().flatten().map(|m| m.scale_factor())` con fallback a `window.scale_factor()`.
  - Lógica de `ignore`:
    ```rust
    let ignore = if inside {
        false
    } else if lbutton_down && !*current {
        false
    } else {
        (!regions_empty || mask_present) && !inside
    };
    ```
    Si el cursor está dentro de una región interactiva o de la máscara del avatar, `ignore` es **incondicionalmente `false`**.
  - En `PixelMask.contains`: añadido margen de tolerancia de borde de 2 px (`padded.contains(x, y)`) para que clics en la periferia no se pierdan durante desplazamientos rápidos.

---

## 3. Pruebas y Verificación

1. **Compilación en Rust (`src-tauri`)**:
   - Comando: `cargo check --manifest-path src-tauri/Cargo.toml`
   - Resultado: `Finished dev profile [unoptimized + debuginfo] target(s) in 4.75s`.
   - Estado: **0 errores, 0 advertencias**.

2. **Validación Sintáctica de JavaScript (`1.AXX/Axx.html`)**:
   - Comando: Script de Node.js extrayendo y compilando bloques `<script>` mediante `vm.Script`.
   - Resultado: `Successfully validated 2 script blocks in 1.AXX/Axx.html with ZERO errors!`.
   - Estado: **0 errores de sintaxis**.

3. **Suite de Aserciones Unitarias Automatizadas**:
   - Aserción 1: Supresión de clics con `event.detail > 0` eliminada y umbral de 4 px activo -> **PASS**.
   - Aserción 2: Umbrales alfa `> 16` en `SoftwareRenderer.hitTest`, `hitMask` y `LiquidRenderer` -> **PASS**.
   - Aserción 3: `FlowDock.tap()` conmuta entre 0 y 2 -> **PASS**.
   - Aserción 4: `#flow-fan` libre de `pointer-events: none !important`, botones con `pointer-events: auto !important` -> **PASS**.
   - Aserción 5: `#flow-sheet` backdrop en `pointer-events: none`, `#stage` / `#avatar` registrado en `interactiveRegions()` -> **PASS**.
   - Aserción 6: Bucle Rust a 10 ms, sincronización DPI con monitor, `ignore = false` garantizado en `inside` -> **PASS**.

---

## 4. Guía de Reversión (Reversion Instructions)

Si se requiriera revertir los cambios de este hito:
1. **Archivo `1.AXX/Axx.html`**:
   - Revertir líneas 1345–1347 al selector unificado con `pointer-events: none !important`.
   - En línea 2713, restaurar `this.step = this.step ? 0 : 1`.
   - En línea 4093, restaurar `return v[3] > 100`.
   - En líneas 5258 y 5267, restaurar `> 96`.
   - En líneas 12261–12263, restaurar el chequeo de foco exclusivo de `step === 1`.
   - En línea 18294, restaurar `this.invoked = true; document.body.classList.add('resident-invoked');`.
   - En líneas 18358–18382, restaurar el umbral `<= 7` y el chequeo `event.detail > 0`.
   - En líneas 18465 y 18481, restaurar los selectores originales sin la inclusión manual de `#stage`.
2. **Archivo `src-tauri/src/lib.rs`**:
   - En líneas 54–74, restaurar `PixelMask.contains` original sin `padded`.
   - En líneas 810–865, restaurar el tiempo de espera a `Duration::from_millis(30)` y el cálculo directo de `scale_factor`.
