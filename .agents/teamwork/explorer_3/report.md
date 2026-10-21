# Reporte Técnico de Investigación — Requisito R1: IPC Bridges, Servicios Backend y Entorno de Ejecución

**Investigador**: Explorer 3 (Especialista en IPC Bridges, Servicios Backend, Procesos en Segundo Plano y Entorno de Ejecución)  
**Fecha**: 2026-10-21  
**Hito**: Fase 0 — Investigación Técnica e Inventario R1  
**Directorio de Trabajo**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_3\`

---

## 1. Resumen Ejecutivo de la Investigación

Se ha llevado a cabo una investigación profunda y de solo lectura sobre la arquitectura nativa de **Axx Assistant**, abarcando:
1. Los puentes de comunicación IPC entre la interfaz web (`1.AXX/Axx.html` y módulos complementarios) y el host nativo Tauri v2 en Rust (`src-tauri/src/lib.rs` y `src-tauri/src/resident.rs`).
2. La arquitectura del backend en Python (`backend/server.py`), sus módulos satélite (ASR, TTS, memoria procedimental, herramientas del ejecutor de acciones, proveedores de inferencia y conectores).
3. El estado de los procesos del sistema, detectando la presencia de **22 procesos zombi** huérfanos (`python.exe -m backend.connect.mcp_server`), puertos loopback y la persistencia en `%LOCALAPPDATA%\Axx`.
4. El entorno de ejecución portátil y en desarrollo (`INICIAR-AXX.cmd`, `package.json`, `Cargo.toml`, directivas de compilación condicional).
5. Las garantías de seguridad y no destructividad sobre directorios de usuario (Escritorio, Documentos, etc.).

---

## 2. Diagnóstico Detallado del Entorno y Procesos Activos

### 2.1 Procesos Zombi Detectados
- **Observación Directa**: La inspección de procesos mediante PowerShell reveló 22 instancias activas e inactivas de `python.exe -m backend.connect.mcp_server`.
- **Causa Raíz**:
  El servidor MCP stdio (`backend/connect/mcp_server.py`) entra en un bucle asíncrono esperando tramas JSON-RPC sobre `sys.stdin`. En Windows, las lecturas bloqueantes de stdio no se cancelan automáticamente al terminar un proceso cliente externo si el descriptor de tubería (pipe) no se cierra de forma explícita o si el proceso no está asociado a un Windows Job Object con la bandera `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
  Ejecuciones previas de tests (`backend/connect/tests/test_mcp.py`) o herramientas MCP que cerraron abruptamente dejaron estos 22 procesos en ejecución continua consumiendo recursos en segundo plano.
- **Acción Correctiva Recomendada**:
  Implementar terminación limpia basada en detección de EOF en stdin y verificación periódica del PID padre en Windows (`kernel32.OpenProcess`).

### 2.2 Estado del Proceso Principal y Puertos
- No hay ninguna instancia activa de `Axx.exe` en este momento.
- Se verificó la existencia del servidor local **Ollama** en el puerto `11434`, ejecutando el modelo `llama3.1:8b`, lo que permite inferencia local sin conexión a Internet.
- El directorio de datos del usuario (`%LOCALAPPDATA%\Axx`) contiene `state.db` (SQLite en modo WAL), `providers.json`, `native-window.json` y registros en `logs/backend-stderr.log`.

---

## 3. Mapeo y Diagnóstico del Puente IPC Tauri v2

### 3.1 Mapeo de Handlers Registrados en Rust vs Invocaciones en Frontend

En `src-tauri/src/lib.rs` (línea 1017), la macro `generate_handler![]` registra exactamente los siguientes comandos:
```rust
tauri::generate_handler![
    native_status,
    backend_request,
    window_action,
    set_timer,
    hit_map,
    set_topmost,
    set_shortcut,
    resident::desktop_layout,   // exportado como 'desktop_layout'
    resident::desktop_activity, // exportado como 'desktop_activity'
]
```

Comparación exhaustiva con las llamadas en el frontend (`1.AXX/Axx.html` y scripts asociados):

| Comando Invocado en Frontend | Registrado en Rust | Estado | Impacto en Ejecución |
|---|---|---|---|
| `desktop_layout` | Sí (`resident::desktop_layout`) | Operativo | Redimensiona y reposiciona la ventana nativa mediante `SetWindowPos`. |
| `desktop_activity` | Sí (`resident::desktop_activity`) | Operativo | Actualiza estado de actividad para gestión de presencia. |
| `native_status` | Sí (`native_status`) | Operativo | Devuelve versión, PID, estado del backend y monitor virtual. |
| `backend_request` | Sí (`backend_request`) | Operativo | Puente HTTP autenticado hacia `127.0.0.1:<port>` con Bearer token. |
| `window_action` | Sí (`window_action`) | Operativo | Soporta acciones: `close`, `minimize`, `drag`, `recenter`, `restore`, `close_panel`. |
| `set_timer` | Sí (`set_timer`) | **Parcial / Stub** | Guarda el JSON en memoria (`state.timer_task`), pero no programa alarma en SO. |
| `hit_map` | Sí (`hit_map`) | Operativo | Recibe máscara de píxeles y regiones interactivas para el hit-test nativo. |
| `set_topmost` | Sí (`set_topmost`) | Operativo | Conmuta `HWND_TOPMOST` / `HWND_NOTOPMOST`. |
| `set_shortcut` | Sí (`set_shortcut`) | Operativo | Registra el atajo de teclado global vía hook nativo de bajo nivel. |
| `request_notifications` | **NO** | **FALTANTE (Mismatch)** | `Axx.html:7187` invoca `bridge.command('request_notifications')`. Falla con `command not found`. |
| `set_autostart` | **NO** | **FALTANTE (Mismatch)** | `Axx.html:7221` invoca `bridge.command('set_autostart', ...)`. Falla con `command not found`. |

### 3.2 Causa Raíz Comprobada del Fallo de Clics y Clic-Through

Uno de los problemas más críticos reportados en la experiencia de usuario es que **al hacer clic sobre el personaje o elementos de la UI, los clics no se registran o se traspasan a las ventanas del escritorio**. Nuestra investigación ha aislado cuatro factores determinantes combinados:

1. **Omisión del Canvas de Avatar en `interactiveRegions()`**:
   En `1.AXX/Axx.html` (líneas 18478–18485), la función `interactiveRegions()` recopila los rectángulos de:
   `#panel, #dock-shell, #flow-pill, #flow-sheet, #flow-fan, #reach-tray, ... button, input, textarea`
   **El elemento `#avatar` (canvas WebGL) NO está incluido en esta lista.**
   El personaje depende de forma exclusiva de `avatar_mask`, una máscara de 64×64 generada mediante `gl.readPixels()` que se envía a Rust cada 220 ms.
2. **Ciclo de Hit-Testing en Rust con Desfase y Clic-Through (`WS_EX_TRANSPARENT`)**:
   En `src-tauri/src/lib.rs` (líneas 800–858), un hilo secundario en bucle cada 30 ms comprueba la posición del cursor (`GetCursorPos` y `ScreenToClient`).
   Si el punto no cae dentro de `interactive_regions` ni de `avatar_mask`, ejecuta:
   `window.set_ignore_cursor_events(true)`
   Esto añade la bandera de Windows `WS_EX_TRANSPARENT` al HWND. Cuando el usuario intenta hacer clic, si la máscara de píxeles está desactualizada por el retardo de 220 ms, o si hay un desajuste de DPI entre monitores (como se evidenció en `native-runtime.json` donde el monitor 1 tiene escala 1.25 y el monitor 2 escala 1.0), el cursor se evalúa como `inside == false` y el clic lo absorbe la aplicación que esté detrás de Axx.
3. **Bloqueo Absoluto de Clics en la Fase de Captura de JavaScript**:
   En `1.AXX/Axx.html` (línea 18378):
   ```javascript
   document.addEventListener('click', event => {
       if (isBody(event.target) && (event.detail > 0 || performance.now() < this.suppressClickUntil)) {
           event.preventDefault();
           event.stopImmediatePropagation();
       }
   }, true);
   ```
   En el modelo de eventos DOM, `event.detail` en un evento `click` representa el contador de clics (1 para clic simple, 2 para doble clic). **`event.detail > 0` es SIEMPRE VERDADERO en cualquier clic del ratón.**
   Como `isBody(event.target)` identifica al `#avatar` o `#a11-main-button`, esta regla suprime de manera incondicional cualquier evento `click` sobre el avatar, impidiendo que el frontend reaccione.
4. **Desconexión en el Flujo de Expansión del Menú (`Axx.flow.tap`)**:
   En `1.AXX/Axx.html` (líneas 2711 y 18290), `ResidentDesktop.tap()` ejecuta `Axx.flow.tap()`, cuyo código es:
   `tap() { this.step = this.step ? 0 : 1; this.tool = ''; }`
   El paso 1 solo visualiza el micro-botón `flow-pill` (+). No despliega el menú radial/orbital (`step = 2`, `flow-sheet`). En la versión de referencia aprobada (`reference/Axx_reference_v20.html`), hacer clic en el avatar abre de inmediato las herramientas y opciones, lo que causa la percepción de que la interfaz está "muerta" o no responde.
5. **Bucle de Recálculo de Layout y Redimensión OS**:
   Al cambiar de paso, `ResidentDesktop.layout()` invoca `desktop_layout` en Rust, ejecutando `SetWindowPos`. Esto genera un evento `window.resize` en WebView2, el cual vuelve a llamar a `this.schedule()`, reiniciando transiciones y anulando coordenadas activas.

---

## 4. Diagnóstico de Servicios Backend y Sidecars

El backend de Axx está estructurado como un servicio loopback local autenticado mediante token Bearer (`backend/server.py`). A continuación se detalla el análisis de cada subsistema:

### 4.1 Inferencia y Comandos
- **ChatGPT OAuth legacy**: Desactivado formalmente (línea 279 de `server.py`). Responde 409 indicando el uso de Axx Connect con Codex.
- **Inferencia Local y Remota**: Totalmente funcional vía `InferenceAdapter` con soporte para Ollama local (`llama3.1:8b` detectado activo en puerto 11434) y proveedores en `providers.json`.
- **Biblioteca de Comandos**: En `backend/commands.py`, la resolución y preparación de comandos opera con flujo de aprobación segura.
- **Bloqueo en Ejecución de Acciones**: En `server.py` línea 474, `/axx-api/actions/execute` bloquea cualquier herramienta que no sea `system_telemetry` o `process_state_inspector` con `403 USE_COMMAND_POLICY`. Para ejecutar acciones con efectos, la interfaz debe invocar el flujo `prepare` -> `execute` en `/axx-api/commands/execute`.

### 4.2 Servicio de Voz y Audio (TTS / ASR)
- **TTS (Texto a Voz)**: Implementado en `backend/speech/windows_tts.py` mediante Windows SAPI sobre PowerShell. Funcional en Windows sin dependencias externas.
- **ASR (Reconocimiento de Voz Offline)**:
  `backend/speech/offline_asr.py` utiliza `faster-whisper-tiny`. Busca el modelo en `%LOCALAPPDATA%\Axx\models\faster-whisper-tiny` o `src-tauri\resources\models\faster-whisper-tiny`.
  En el repositorio clonado, la carpeta de modelos se encuentra en la raíz (`resources/models/faster-whisper-tiny`), no dentro de `src-tauri/resources/models/`. En modo desarrollo, si no se copia a `%LOCALAPPDATA%\Axx\models`, el servicio falla con `MODEL_NOT_FOUND` o intenta descargar de HuggingFace.
- **Permisos de Micrófono en WebView2**:
  `src-tauri/src/lib.rs` no define un `permission_request_handler` para WebView2. Cuando el frontend invoca `navigator.mediaDevices.getUserMedia`, WebView2 bloquea la captura de audio salvo que los permisos globales de Windows y el host nativo lo concedan explícitamente.

### 4.3 Servicio de Música
- En `backend/server.py` (líneas 219–220 y 593–594), las rutas `/axx-api/spotify/*` devuelven explícitamente HTTP 501 `NOT_CONFIGURED` ("Spotify requires a separately configured account integration").
- No existe ningún servicio backend de reproducción local de audio (MP3/WAV) ni puente hacia APIs de streaming de música local.

### 4.4 Grabación de Pantalla (Screen Recorder)
- En el frontend (`1.AXX/Axx.html`), la acción de grabar pantalla intenta llamar a `navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })`.
- En el entorno WebView2 de Windows, `getDisplayMedia` no está habilitado por defecto y lanza `NotSupportedError: Screen capture is not supported`. La interfaz muestra "Captura no disponible aquí". No existe implementación nativa en Rust o Python para captura de escritorio.

### 4.5 Temporizador y Notificaciones
- `src-tauri/src/lib.rs` solo implementa `set_timer` almacenando el objeto JSON en `HostState.timer_task`. No interactúa con la API de temporizadores de Windows ni emite alarmas nativas.
- El frontend depende de `setInterval` en JavaScript. Si la ventana se suspende o se minimiza, el temporizador se desfasa.
- El comando `request_notifications` falla por no estar registrado en Rust.

### 4.6 Manejo de Archivos y Seguridad de Solo Lectura
- `backend/actions/tools.py` contiene `FileArtifactTool` (`file_artifact_writer`).
- Esta herramienta restringe de manera estricta cualquier escritura al directorio `workspace_root` (por defecto `%LOCALAPPDATA%\Axx\artifacts`).
- Cualquier intento de escribir fuera de `artifacts` o en carpetas del sistema es rechazado con error de preconducción.
- Las carpetas del usuario (Escritorio, Documentos, Descargas) permanecen completamente protegidas y en modo solo lectura.

### 4.7 Configuración y Persistencia
- La configuración de proveedores reside en `%LOCALAPPDATA%\Axx\providers.json`.
- La persistencia relacional reside en `%LOCALAPPDATA%\Axx\state.db` (SQLite).
- En `server.py` (línea 372), el endpoint `/axx-api/auth/save-key` contiene una inconsistencia: si `self.config_path` no está explícitamente enlazado, escribe en `root_dir / 'providers.json'` en lugar de `%LOCALAPPDATA%\Axx\providers.json`, produciendo una divergencia de configuración.

---

## 5. Entorno de Ejecución y Modo Portátil (`INICIAR-AXX.cmd`)

- **Script `INICIAR-AXX.cmd`**:
  Verifica si existe `%LOCALAPPDATA%\Programs\Axx\Axx.exe` (instalación de producción) o `src-tauri\target\release\Axx.exe`. Si no existen, muestra un mensaje solicitando ejecutar el instalador.
  No inicia el servidor de desarrollo (`npm run tauri:dev` ni `cargo tauri dev`).
- **Modo Desarrollo (`debug_assertions`)**:
  En `src-tauri/src/lib.rs` (línea 587), cuando está en modo depuración, si no encuentra `resources/axx-backend.exe`, ejecuta `python ../backend/server.py`.
  Requiere que `python` esté en el PATH del sistema con todas las dependencias instaladas.
- **Modo Release (`not(debug_assertions)`)**:
  Exige estrictamente la presencia de `resources/axx-backend.exe`.

---

## 6. Inventario R1: 9 Subsistemas de Backend e IPC

A continuación se presentan las 9 fichas obligatorias del inventario R1 con los 5 campos requeridos:

---

### Entrada R1-1: IPC / Tauri Bridge
1. **Problema observado**:
   Comandos no registrados en Rust (`request_notifications` y `set_autostart`) que lanzan errores no controlados al invocarse desde `Axx.html`. Adicionalmente, clics en el avatar y controles son bloqueados o ignorados debido a supresión en captura DOM (`event.detail > 0`) y activación errónea de `WS_EX_TRANSPARENT` por desfase de la máscara WebGL (220 ms) y desajustes de DPI multimonitor.
2. **Causa comprobada o hipótesis**:
   - Falta de registro en `generate_handler![]` en `src-tauri/src/lib.rs`.
   - `interactiveRegions()` en `Axx.html` omite `#avatar`.
   - `document.addEventListener('click', ..., true)` en `Axx.html:18378` intercepta y cancela todos los clics donde `event.detail > 0`.
   - Bucle de 30 ms en `lib.rs:854` aplica `set_ignore_cursor_events(true)` basándose en coordenadas escaladas por `window.scale_factor()` que discrepan en configuraciones de monitores mixtos (1.25 vs 1.0).
3. **Archivos implicados**:
   - `src-tauri/src/lib.rs` (líneas 490–535, 800–858, 1017–1030)
   - `1.AXX/Axx.html` (líneas 7187, 7221, 18378, 18476–18485)
4. **Corrección propuesta**:
   - Registrar stubs seguros para `request_notifications` y `set_autostart` en `lib.rs` o conectar con APIs nativas de notificación/autostart de Windows.
   - Incluir `#avatar` con un cuadro delimitador de tolerancia en `interactiveRegions()` para evitar que la ventana se vuelva transparente al pasar el ratón.
   - Eliminar la condición `event.detail > 0` en `Axx.html:18378`, permitiendo que el clic simple del usuario llegue a los handlers de interacción.
   - Corregir el cálculo de coordenadas del cursor en `lib.rs` utilizando las funciones de conversión de DPI por monitor de Windows (`GetDpiForMonitor` o `PhysicalPosition`).
5. **Prueba de aceptación**:
   - Al pulsar sobre el avatar, no se traspasa el clic al escritorio y se despliega inmediatamente el menú orbital de herramientas.
   - La consola de WebView2 no registra rechazos por `command request_notifications not found` ni `command set_autostart not found`.

---

### Entrada R1-2: Backend Conversación / Comandos
1. **Problema observado**:
   Intentos directos de ejecutar acciones de sistema desde la interfaz en `/axx-api/actions/execute` resultan en HTTP 403 `USE_COMMAND_POLICY`.
2. **Causa comprobada o hipótesis**:
   En `backend/server.py` (líneas 474–477), las rutas heredadas de ejecución directa fueron restringidas intencionalmente por política de seguridad, pero ciertos paneles del frontend no completan el flujo de dos pasos: `prepare` -> `execute` con aprobación explícita.
3. **Archivos implicados**:
   - `backend/server.py` (líneas 472–479)
   - `1.AXX/Axx.html` (sección `DesktopRuntime`, líneas 18520–18650)
   - `backend/commands.py` (líneas 120–210)
4. **Corrección propuesta**:
   Unificar las llamadas de ejecución de herramientas en el frontend para que pasen siempre por la API de comandos (`/axx-api/commands/prepare` y `/axx-api/commands/execute`), garantizando que las acciones con efectos secundarios (escritura de archivos, telemetría) cuenten con el token de aprobación correspondiente.
5. **Prueba de aceptación**:
   - Ejecutar "Consultar este PC" desde el panel de acciones y verificar respuesta 200 con telemetría del sistema en el elemento `<pre id="desktop-action-result">`.

---

### Entrada R1-3: Backend Voz / Dictado
1. **Problema observado**:
   El reconocimiento de voz offline (ASR) falla al inicializarse en modo desarrollo con error de modelo no encontrado, y el dictado en el navegador no accede al micrófono de forma fiable.
2. **Causa comprobada o hipótesis**:
   - `backend/speech/offline_asr.py` busca `faster-whisper-tiny` en `src-tauri/resources/models/` o en `%LOCALAPPDATA%\Axx\models\`, mientras que el repositorio lo tiene alojado en `resources/models/faster-whisper-tiny`.
   - `src-tauri/src/lib.rs` carece de gestor de permisos de WebView2 para conceder captura de audio (`navigator.mediaDevices.getUserMedia`).
3. **Archivos implicados**:
   - `backend/speech/offline_asr.py` (líneas 40–75)
   - `src-tauri/src/lib.rs` (configuración del builder de WebView)
4. **Corrección propuesta**:
   - Añadir la ruta `root_dir / 'resources' / 'models' / 'faster-whisper-tiny'` a las rutas de búsqueda predeterminadas en `offline_asr.py`.
   - Configurar en `lib.rs` el manejador de permisos de WebView2 para autorizar automáticamente las peticiones de micrófono de la URL local segura de la aplicación.
5. **Prueba de aceptación**:
   - Activar el botón de dictado en la barra de chat de Axx, dictar una frase y verificar que el texto transcrito se inserte en el campo de texto sin errores en la consola.

---

### Entrada R1-4: Backend Traducción
1. **Problema observado**:
   La funcionalidad `VoiceTranslation18` falla en WebView2 mostrando mensajes de API de traducción no soportada.
2. **Causa comprobada o hipótesis**:
   `1.AXX/Axx.html` intenta invocar `window.Translator` (API experimental exclusiva de Google Chrome Canary). En Microsoft Edge WebView2 dicha API no existe. El backend de Python carece de una ruta dedicada `/axx-api/translate`.
3. **Archivos implicados**:
   - `1.AXX/Axx.html` (líneas 14200–14350, clase `VoiceTranslation18`)
   - `backend/server.py`
4. **Corrección propuesta**:
   Enrutar las peticiones de traducción hacia el router de inferencia de Axx (`/axx-api/chat`) con una plantilla de sistema específica para traducción directa, o integrar un endpoint dedicado `/axx-api/translate` en `backend/server.py` que use el modelo local Ollama (`llama3.1:8b`).
5. **Prueba de aceptación**:
   - Seleccionar un texto y pulsar traducir a inglés/español; la interfaz debe mostrar la traducción obtenida a través del backend sin consultar `window.Translator`.

---

### Entrada R1-5: Backend Música
1. **Problema observado**:
   Cualquier comando de música o interacción con Spotify falla de inmediato con error 501 `NOT_CONFIGURED`.
2. **Causa comprobada o hipótesis**:
   En `backend/server.py` (líneas 219–221 y 593–595), todos los endpoints `/axx-api/spotify/*` están explícitamente programados para rechazar peticiones con `_unsupported('Spotify requires a separately configured account integration')`. No hay reproductor local de audio en Python ni integración con transporte de Windows (SMTC).
3. **Archivos implicados**:
   - `backend/server.py` (líneas 219–221, 593–595)
   - `1.AXX/Axx.html` (manejadores de medios y música)
4. **Corrección propuesta**:
   - Documentar que la integración Spotify requiere credenciales OAuth de usuario o servicio externo.
   - Para reproducción de música local o sonidos ambientales, implementar un servicio local ligero basado en audio web o reproductor de archivos locales en segundo plano (`backend/audio_player.py`).
5. **Prueba de aceptación**:
   - Al solicitar música o sonido ambiente, el sistema informa con claridad el estado de la integración o reproduce una pista local de muestra sin error 500/501 no controlado.

---

### Entrada R1-6: Backend Grabación (Screen Recorder)
1. **Problema observado**:
   Al activar la grabación de pantalla desde la interfaz, aparece el mensaje "Captura no disponible aquí" y no se genera ningún archivo de vídeo.
2. **Causa comprobada o hipótesis**:
   El frontend en `1.AXX/Axx.html` depende de `navigator.mediaDevices.getDisplayMedia`. En el contexto de WebView2 sobre Windows, la captura de pantalla por API web está restringida y lanza `NotSupportedError`. No hay comando IPC en Rust para captura de pantalla.
3. **Archivos implicados**:
   - `1.AXX/Axx.html` (líneas 15800–15950, módulo de pantalla)
   - `src-tauri/src/lib.rs`
4. **Corrección propuesta**:
   - Implementar un comando Tauri en Rust (`capture_screen` o `record_screen`) utilizando las APIs nativas de Windows (`Windows.Graphics.Capture` o GDI `BitBlt` para capturas de fotogramas), o alternativamente capturar mediante el backend Python con la librería estándar de telemetría/gráficos.
   - En el frontend, conmutar a la llamada del comando nativo si se detecta entorno de escritorio (`Axx.isNative()`).
5. **Prueba de aceptación**:
   - Iniciar grabación de pantalla, detenerla tras 3 segundos y comprobar que se almacena el archivo MP4 o PNG de evidencia en la carpeta de artefactos de Axx.

---

### Entrada R1-7: Backend Temporizador
1. **Problema observado**:
   El temporizador configurado en Axx no emite alertas audibles ni notificaciones del sistema si la ventana pierde el foco, se minimiza o se bloquea el equipo.
2. **Causa comprobada o hipótesis**:
   El comando `set_timer` en Rust (`src-tauri/src/lib.rs:486`) solo almacena el payload en una variable en memoria (`*state.timer_task.lock().unwrap() = Some(task)`). No programa ningún hilo de cuenta regresiva nativo, ni temporizador del sistema (`CreateWaitableTimer`), ni invoca notificaciones de Windows. El temporizador depende completamente de `setInterval` en JavaScript.
3. **Archivos implicados**:
   - `src-tauri/src/lib.rs` (líneas 470–488)
   - `1.AXX/Axx.html` (gestor de temporizador)
4. **Corrección propuesta**:
   Implementar en Rust un temporizador en hilo de fondo que, al cumplirse el tiempo fijado, emita una notificación nativa de Windows (o invoque el sonido de alarma del sistema) y envíe un evento `axx-timer-expired` a WebView2 mediante `window.emit()`.
5. **Prueba de aceptación**:
   - Configurar un temporizador de 10 segundos, minimizar o desenfocar Axx; a los 10 segundos debe sonar la alarma y mostrarse la notificación del sistema en Windows.

---

### Entrada R1-8: Backend Archivos (Seguridad y Solo Lectura)
1. **Problema observado**:
   Verificar que las operaciones con archivos respeten rigurosamente el principio de solo lectura sobre carpetas de usuario personales (Escritorio, Documentos, Descargas) y que no existan rutas de escape.
2. **Causa comprobada o hipótesis**:
   En `backend/actions/tools.py`, `FileArtifactTool` valida las rutas contra nombres reservados de Windows y enlaces simbólicos, y escribe exclusivamente dentro de `workspace_root` (`%LOCALAPPDATA%\Axx\artifacts`). No existen herramientas de borrado o sobreescritura arbitraria de archivos en el sistema.
3. **Archivos implicados**:
   - `backend/actions/tools.py` (líneas 22–48, 83–167)
   - `backend/actions/executor.py`
4. **Corrección propuesta**:
   Mantener esta disciplina de sandboxing estricto. Asegurar que cualquier herramienta futura de lectura de documentos de usuario se limite a operaciones de apertura en modo `'r'` / `'rb'` sin privilegios de modificación, manteniendo el Escritorio y Documentos protegidos contra escrituras accidentales.
5. **Prueba de aceptación**:
   - Intentar guardar un artefacto con ruta `../../Escritorio/prueba.txt`; el sistema debe rechazar la operación antes de la ejecución indicando error de preconducción de ruta.
   - Guardar un artefacto legítimo en `mi-nota.txt` y verificar que se crea únicamente dentro de `%LOCALAPPDATA%\Axx\artifacts\mi-nota.txt` con validación de hash SHA-256.

---

### Entrada R1-9: Backend Configuración / Persistencia
1. **Problema observado**:
   Guardar una clave de API mediante `/axx-api/auth/save-key` puede escribir en la raíz del repositorio (`providers.json`) en lugar del directorio de datos del usuario (`%LOCALAPPDATA%\Axx\providers.json`), produciendo desincronización entre la configuración cargada por el servidor y la editada por el usuario.
2. **Causa comprobada o hipótesis**:
   En `backend/server.py` (línea 370), la propiedad `self.config_path` se consulta con `getattr(self, 'config_path', None)`. Si no está asignada en la instancia del handler, recurre a `root_dir / 'providers.json'`. Mientras tanto, `run_server()` inicializa `resolve_app_paths()` apuntando a `%LOCALAPPDATA%\Axx\providers.json`.
3. **Archivos implicados**:
   - `backend/server.py` (líneas 370–375, 609–632, 679–685)
4. **Corrección propuesta**:
   Asegurar que `self.server.config_path` o `self.config_path` apunte invariablemente a la ruta resuelta devuelta por `resolve_app_paths()` (`%LOCALAPPDATA%\Axx\providers.json`), evitando modificar archivos en el directorio del código fuente.
5. **Prueba de aceptación**:
   - Configurar una clave mediante la API y verificar que el archivo actualizado sea exclusivamente `%LOCALAPPDATA%\Axx\providers.json` sin alterar ningún archivo dentro del repositorio de trabajo.

---

## 7. Conclusiones y Próximos Pasos

1. **Prioridad Inmediata (IPC y Clics)**:
   La solución al problema de que el personaje "no responde a los clics" requiere resolver los 3 factores simultáneos:
   - Eliminar el bloqueo `event.detail > 0` en `Axx.html:18378`.
   - Incluir `#avatar` en `interactiveRegions()` para evitar la activación indebida de `WS_EX_TRANSPARENT`.
   - Modificar `tap()` para que abra directamente el menú orbital (`expand()`, paso 2) en vez de requerir tocar el diminuto `flow-pill`.
2. **Prioridad Backend (Procesos Zombi y Rutas)**:
   - Limpiar los 22 procesos zombi `python.exe -m backend.connect.mcp_server`.
   - Corregir la ruta de modelos de Whisper para asegurar el funcionamiento de ASR sin conexión.
   - Sincronizar la ruta de persistencia de `providers.json`.
3. **Garantía de Seguridad**:
   - El sistema de archivos cumple con la restricción de solo lectura en carpetas de usuario.

---
*Fin del Reporte Técnico de Explorer 3.*
