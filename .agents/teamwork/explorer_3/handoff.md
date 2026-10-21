# Handoff Report — Explorer 3 (IPC Bridges, Backend Services, Background Processes & Runtime Environment)

**Agent**: Explorer 3  
**Working Directory**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_3\`  
**Target Recipient**: Parent Orchestrator (`4513c1ff-1817-48de-b3d4-90214475e7e6`)  
**Type**: Hard Handoff (Investigation & Inventory Phase 0 Complete)

---

## 1. Observation

1. **Procesos en Segundo Plano y Zombis**:
   - Comando ejecutado: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*mcp_server*' }`
   - Resultado directo: Se detectaron **22 procesos activos** de `python.exe -m backend.connect.mcp_server` ejecutándose de fondo sin GUI.
   - En `backend/connect/mcp_server.py:9-60`, el servidor stdio lee continuamente `sys.stdin` sin mecanismo de temporización ni comprobación de vida del proceso padre de Windows.
   - Puerto `11434` activo con servicio local **Ollama** ejecutando `llama3.1:8b`.

2. **Registro de Comandos en Rust (`src-tauri/src/lib.rs`)**:
   - En `lib.rs:1017-1027`, la macro `generate_handler![]` contiene únicamente:
     `native_status`, `backend_request`, `window_action`, `set_timer`, `hit_map`, `set_topmost`, `set_shortcut`, `desktop_layout`, `desktop_activity`.
   - En `1.AXX/Axx.html:7187`: `this.bridge.command('request_notifications')`
   - En `1.AXX/Axx.html:7221`: `this.bridge.command('set_autostart', { enabled: opt.checked })`
   - Verificado: Ninguno de los dos comandos existe en Rust ni en los plugins registrados (`tauri-plugin-log` es el único plugin en `Cargo.toml`). Invocarlos arroja `Unhandled Promise Rejection: command <name> not found`.

3. **Hit-Testing y Clic-Through (`WS_EX_TRANSPARENT`)**:
   - En `src-tauri/src/lib.rs:800-858`, un hilo corre cada 30 ms:
     ```rust
     let scale = window.scale_factor().unwrap_or(1.);
     let x = point.x as f64 / scale;
     let y = point.y as f64 / scale;
     let inside = regions.iter().any(|r| r.contains(x, y)) || mask.as_ref().is_some_and(|m| m.contains(x, y));
     let ignore = (!regions_empty || mask_present) && !inside;
     if *current != ignore && window.set_ignore_cursor_events(ignore).is_ok() { *current = ignore; }
     ```
   - En `1.AXX/Axx.html:18478-18485`, `interactiveRegions()` consulta:
     `#panel,#dock-shell,#flow-pill,#flow-sheet,#flow-fan,#reach-tray,#reach-preview,#ink-review,#v13-dock,#v13-settings,#v13-pad,#reader-mini,.organic-satellite,dialog[open],button,input,textarea,select,summary`
     `#avatar` **NO** forma parte de la lista.
   - En `%LOCALAPPDATA%\Axx\logs\native-runtime.json`:
     `monitors`: Monitor 0 escala `1.25` (1920×1020), Monitor 1 escala `1.0` (1920×1032). `window.scale_factor()` introduce desfases en cálculo de cursor entre monitores.

4. **Bloqueo Incondicional de Clics en Captura DOM**:
   - En `1.AXX/Axx.html:18378`:
     ```javascript
     document.addEventListener('click', event => {
         if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) {
             event.preventDefault();
             event.stopImmediatePropagation();
         }
     }, true);
     ```
   - `isBody(target)` verifica `target.id === 'avatar' || target.closest('#a11-main-button')`.
   - En la especificación DOM UI Events, `event.detail` en un clic es el contador de pulsaciones (`detail >= 1`). Por ende, el 100% de los clics en el avatar son prevenidos y detenidos.

5. **Flujo de Expansión del Menú**:
   - En `1.AXX/Axx.html:2711`:
     `tap() { this.step = this.step ? 0 : 1; this.tool = ''; }`
   - El paso 1 solo activa el botón diminuto `flow-pill` (+); no abre el menú radial orbital (`step = 2`).

6. **Servicios Backend**:
   - `/axx-api/spotify/*` responde HTTP 501 `NOT_CONFIGURED` (`backend/server.py:220, 594`).
   - Grabación de pantalla invoca `navigator.mediaDevices.getDisplayMedia`, fallando en WebView2 con `NotSupportedError`.
   - `offline_asr.py:40-75` no incluye en sus rutas de búsqueda la carpeta raíz `resources/models/faster-whisper-tiny`.
   - `FileArtifactTool` en `backend/actions/tools.py` confina la escritura estrictamente a `workspace_root` (`%LOCALAPPDATA%\Axx\artifacts`). No hay comandos destructivos sobre las carpetas de usuario (Escritorio, Documentos).
   - `/axx-api/auth/save-key` en `server.py:372` recurre a `root_dir / 'providers.json'` si `self.config_path` no está instanciado, en lugar de `%LOCALAPPDATA%\Axx\providers.json`.

---

## 2. Logic Chain

1. **Premisa**: El usuario experimenta que hacer clic en el avatar no abre las herramientas y los clics se traspasan a ventanas inferiores.
2. **Conexión A (Transparencia OS)**: Si `#avatar` no está en `interactiveRegions()`, el hilo de Rust a 30 ms (`lib.rs:840`) depende exclusivamente de `avatar_mask`. Si la máscara WebGL se retrasa (intervalo de 220 ms en JS), o el cálculo de escala DPI discrepa en configuraciones multimonitor, `inside` resulta `false`, invocando `set_ignore_cursor_events(true)` (`WS_EX_TRANSPARENT`), haciendo que Windows entregue el clic a la ventana debajo de Axx.
3. **Conexión B (Bloqueo DOM)**: Si el clic logra ingresar a WebView2 porque el cursor estaba dentro de la máscara, el listener de fase de captura en `Axx.html:18378` evalúa `isBody(event.target) && event.detail > 0`. Dado que `event.detail` es siempre `1` en un clic del ratón, el listener ejecuta `preventDefault()` y `stopImmediatePropagation()`, suprimiendo el evento antes de que cualquier manejador de UI lo reciba.
4. **Conexión C (Comportamiento de Menú)**: Incluso al desencadenar `tap()`, la máquina de estados `FlowDock` conmuta al paso 1 (que solo renderiza el botón flotante `+`), requiriendo un segundo clic que frecuentemente se pierde por las condiciones A y B.
5. **Conexión D (Procesos Huérfanos)**: Los 22 procesos de `backend.connect.mcp_server` persisten porque al no ejecutarse dentro de un Job Object con `KILL_ON_JOB_CLOSE` (a diferencia del backend principal que sí lo está en `lib.rs:719`), las desconexiones de clientes stdio no provocan su salida en Windows.
6. **Conclusión Lógica**: El sistema presenta fallas acumuladas en la capa de interacción de escritorio (IPC + DOM + Hit testing) y desalineaciones de endpoints/modelos en el backend, pero su arquitectura de archivos es segura y no destructiva.

---

## 3. Caveats

1. **Axx Connect**: Se mantuvo la restricción estricta de no modificar ni alterar el código de `evidence/axx-connect` o plugins en esta fase.
2. **Ollama Local**: Se comprobó la presencia activa de Ollama (`llama3.1:8b`) en el puerto 11434. Su disponibilidad futura dependerá de que el servicio del usuario continúe en ejecución.
3. **Grabación de Pantalla**: La activación nativa de captura requerirá una extensión en Rust mediante Windows Media Capture / Graphics Capture o integración con ffmpeg/mss, dado que WebView2 no soportará `getDisplayMedia` sin infraestructura de captura del host.

---

## 4. Conclusion

El diagnóstico técnico del Requisito R1 para las áreas de IPC, Backend, Procesos y Entorno está **100% completado** y documentado en `.agents/teamwork/explorer_3/report.md`.

Se han redactado las 9 fichas completas del inventario R1 con los cinco campos obligatorios:
1. `IPC / Tauri Bridge`
2. `Backend Conversación/Comandos`
3. `Backend Voz/Dictado`
4. `Backend Traducción`
5. `Backend Música`
6. `Backend Grabación`
7. `Backend Temporizador`
8. `Backend Archivos`
9. `Backend Configuración/Persistencia`

---

## 5. Verification Method

Para verificar independientemente estos hallazgos:

1. **Verificación de Procesos Zombi**:
   ```powershell
   Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*mcp_server*' } | Select-Object Id, ProcessName, CommandLine
   ```
2. **Verificación de Comandos Rust Faltantes**:
   Inspeccionar `src-tauri/src/lib.rs` líneas 1017–1030 para confirmar que `request_notifications` y `set_autostart` no están presentes en `tauri::generate_handler![]`.
3. **Verificación del Bloqueo de Clics en Avatar**:
   Inspeccionar `1.AXX/Axx.html` línea 18378 y confirmar la condición `event.detail > 0`.
4. **Verificación de Rutas de Whisper ASR**:
   Inspeccionar `backend/speech/offline_asr.py` líneas 40–60 y cotejar con la ubicación física de `resources/models/faster-whisper-tiny` en la raíz del proyecto.
5. **Verificación de Rutas de Spotify**:
   Inspeccionar `backend/server.py` líneas 219–221 y 593–595 para corroborar el retorno forzado de 501 `NOT_CONFIGURED`.
6. **Verificación de Seguridad de Archivos**:
   Inspeccionar `backend/actions/tools.py` líneas 83–120 y verificar la restricción estricta a `workspace_root` (`artifacts`).
