# Informe de Investigación Técnica — Hito 3: Biblioteca de Comandos, Action Desk y Flujo de Automatización del Sistema

**Investigador**: Explorer M3-2 (Especialista en Biblioteca de Comandos, Action Desk y Automatización del Sistema)  
**Hito**: Milestone 3 — Motor de Conversación y Comandos (Feature 9: Command Execution)  
**Fecha**: 2026-10-21  
**Directorio de Trabajo**: `c:\Users\luigi\Desktop\Axx assistant\.agents\teamwork\explorer_m3_2\`  
**Archivos Auditados**:
- `1.AXX/scripts/command-library.js` (336 líneas)
- `1.AXX/scripts/test-command-library.cjs` (220 líneas)
- `1.AXX/Axx.html` (18.937 líneas, enfocado en secciones `#view-actions`, `#desktop-runtime`, `#command-palette`, `#flow-fan`, `#a11-action`, `ActionDesk`, `DesktopRuntime`, `App.execute`)
- `backend/commands.py` (352 líneas)
- `backend/server.py` (735 líneas, rutas `/axx-api/commands/*`, `/axx-api/actions/*`, `/axx-api/recipes/*`)
- `backend/actions/tools.py` y `backend/actions/executor.py`
- `backend/tests/test_command_library.py` y `backend/tests/test_commands_http.py`
- `resources/command-library.json` (7,2 MB, 7.562 entradas)
- `reference/Axx_reference_v20.html` (referencia visual aprobada)

---

## 1. Resumen Ejecutivo

El subsistema de ejecución de comandos y automatización del sistema de Axx Assistant presenta una **paradoja arquitectónica**:
- Por un lado, el backend en Python (`backend/commands.py`, `backend/actions/executor.py`) y el módulo puente `1.AXX/scripts/command-library.js` poseen un motor de catálogo documental y ejecución tipada, transaccional y validada criptográficamente (19/19 tests unitarios en Python y 19/19 tests de contrato Playwright pasando al 100%).
- Por otro lado, **en la interfaz de usuario real (`1.AXX/Axx.html`), este motor está prácticamente aislado, desconectado y desubicado**:
  1. La sección visual `#command-library` fue insertada forzosamente dentro de `#view-files` ("Archivos"), mientras que la vista `#view-actions` ("Acciones") permanece con un formulario obsoleto (`#command-form`) que falla con el mensaje *"No hay un modelo de IA conectado"* ante cualquier comando de sistema.
  2. La paleta de comandos (`#command-palette`, accesible con `Ctrl+K`) solo busca notas, tareas y vistas de paneles, ignorando por completo los comandos del sistema.
  3. El abanico radial (`#flow-fan` / `OrbitExperience`) carece de un acceso directo a los comandos de automatización o a la biblioteca.
  4. La vista de escritorio de Windows (`#desktop-runtime` en `#view-settings`) invoca directamente `/axx-api/actions/execute`, que bloquea de forma estricta cualquier acción no telemétrica con `HTTP 403 USE_COMMAND_POLICY`. Aunque `command-library.js` parchea este método dinámicamente en tiempo de ejecución, cualquier acción con confirmación (como escribir archivos) expulsa bruscamente al usuario de la configuración y lo traslada a la vista de archivos.
  5. La retroalimentación es dispersa y cruda: en el chat solo se emite una línea de texto plano sin tarjeta expandible, y en la biblioteca los resultados se vierten en bloques `<pre>` de JSON crudo sin indicadores visuales de estado (ejecutando, verificado, fallido).

A continuación se detalla la investigación paso a paso, el trazado de la tubería de ejecución y la estrategia de corrección línea por línea.

---

## 2. Catálogo y Biblioteca de Comandos

### 2.1 Comandos Registrados en Backend (`backend/commands.py:25-39, 86-140`)

El backend define dos clases de comandos:

#### A. Adaptadores Ejecutables Validados (`ADAPTERS`)
Existen exactamente **3 adaptadores reales con ejecución habilitada**:
1. `axx.system.telemetry`:
   - **Herramienta**: `system_telemetry` (`backend/actions/tools.py:16`).
   - **Nivel de riesgo**: `read` (no destructivo, no muta estado).
   - **Requiere aprobación previa**: No (`requires_approval = False`).
   - **Parámetros**: Ninguno (`{}`).
   - **Alias reconocidos**: `"estado del sistema"`, `"información del sistema"`, `"informacion del sistema"`.
   - **Comportamiento real**: Obtiene plataforma del SO, uso porcentual de CPU, memoria RAM total y libre, y espacio disponible en disco (`C:\`). Verifica postcondiciones matemáticas (RAM > 0, disco > 0).
2. `axx.process.inspect`:
   - **Herramienta**: `process_state_inspector` (`backend/actions/tools.py:28`).
   - **Nivel de riesgo**: `read`.
   - **Requiere aprobación previa**: No.
   - **Parámetros**: `pid` (entero opcional entre 1 y 4.294.967.295; por defecto el PID del proceso de Axx).
   - **Alias reconocidos**: `"estado de axx"`.
   - **Comportamiento real**: Inspecciona el proceso de Windows indicado vía `psutil`, comprobando existencia, nombre, estado y uso de recursos.
3. `axx.artifact.write`:
   - **Herramienta**: `file_artifact_writer` (`backend/actions/tools.py:46`).
   - **Nivel de riesgo**: `workspace_write` (muta el sistema de archivos local).
   - **Requiere aprobación previa**: **Sí** (`requires_approval = True`).
   - **Parámetros**:
     - `path`: obligatorio, ruta relativa (máximo 240 caracteres). Estrictamente confinada dentro de `%LOCALAPPDATA%\Axx\artifacts\`. Rechaza rutas absolutas, dispositivos reservados (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`), secuencias `..` o archivos ya existentes.
     - `content`: obligatorio, texto (máximo 65.536 bytes UTF-8).
   - **Comportamiento real**: Escribe el archivo en disco, calcula su hash SHA-256 y verifica como postcondición que el archivo exista en disco, coincida en tamaño y coincida en el hash SHA-256.

#### B. Adaptador de Fixture / Prueba Bloqueado
- `axx.blender.fixture`:
  - Registrado en `commands.py:93`.
  - Herramienta: `blender_render_fixture`.
  - Estado: `execution_enabled: False`, `blocked_reason: 'Pendiente de validación física del adaptador'`.

#### C. Catálogo Documental Heredado (`resources/command-library.json`)
- Archivo de 7,2 MB cargado en el arranque.
- Contiene **7.562 comandos documentales** (ej. `AXX-01-0001` *"Abrir Inicio sin ratón"*).
- **Son comandos decorativos / informativos únicamente**: todos se importan forzosamente con `execution_enabled: False`, `source_status: 'DOCUMENTED_NOT_EXECUTED'`, `risk: 'unreviewed'`, `blocked_reason: 'Sin adaptador ejecutable validado'`.
- El backend (`commands.py:266`) bloquea cualquier intento de preparar estos comandos con parámetros ejecutables arrojando `ValueError('El comando documental no admite parámetros ejecutables')`.

### 2.2 Desconexión en el Frontend (`1.AXX/Axx.html` y `1.AXX/scripts/command-library.js`)

Al contrastar el catálogo del backend con la interfaz de usuario en `1.AXX/Axx.html`, se identifican 4 puntos críticos:

| Componente en UI | Líneas en `Axx.html` | Estado Actual | Problema Observado |
|---|---|---|---|
| `#view-actions` | 1498–1501, 6655, 7024–7075 | **Desconectado** | Posee `<form id="command-form">` con `<input id="command">`. Está cableado al método local `App.prototype.execute(command)` que solo evalúa 8 expresiones regulares locales (temporizador, notas, calculadora). Si se escribe `estado del sistema` o `/comando axx.system.telemetry`, responde: *"No hay un modelo de IA conectado"*. |
| `ActionDesk` (`#a11-action`) | 12868–13200 | **Desconectado** | Controlador exclusivo de widgets multimedia (`music`, `screen`, `dictation`, `reader`, `timer`, `stopwatch`). No gestiona comandos de sistema ni automatizaciones. |
| `#command-palette` | 1689, 9917–9949, 10131–10157 | **Desconectado** | Diálogo accesible con `Ctrl + K` o botón "Buscar en Axx". Solo busca vistas de paneles en `Axx.FEATURES`, notas de usuario y tareas pendientes. No incluye los comandos del backend. |
| `#view-files` | 1534, `command-library.js:42` | **Mal ubicado** | `command-library.js` inyecta `<section id="command-library">` al inicio de la vista de archivos. Un usuario buscando automatizaciones nunca pensaría que los comandos del sistema están dentro de "Archivos". |
| `#desktop-runtime` | 18742–18774, 18815–18821 | **Ruta insegura parcheada** | Botones "Consultar este PC" y "Crear un archivo verificado" dentro de Ajustes (`#view-settings`). Invoca por defecto `/axx-api/actions/execute`. |

---

## 3. Trazado de la Tubería de Ejecución de Comandos

### 3.1 Flujo A: Comando desde la Entrada de Chat (`#chat-input`)

Este es el único flujo que actualmente utiliza la biblioteca de comandos preparada:
```
1. Usuario escribe "estado del sistema" en #chat-input y pulsa Enviar (o tecla Intro).
   ↓
2. command-library.js:158 intercepta `Axx.companion.send(text)`.
   ↓
3. Descarta si es comando local (hasLocalIntent) o atajo "/cancelar-comando".
   ↓
4. POST /axx-api/commands/resolve  { "text": "estado del sistema", "source": "text" }
   Backend (commands.py:170) normaliza texto y busca en ADAPTERS['axx.system.telemetry']['aliases'].
   Devuelve: { "match": "exact", "command_id": "axx.system.telemetry", "inputs": {} }
   ↓
5. Interceptor agrega mensaje de usuario en el chat:
   Axx.companion.message('user', "estado del sistema", 'local')
   ↓
6. POST /axx-api/commands/prepare  { "command_id": "axx.system.telemetry", "inputs": {}, "source": "text", "operation_id": "fixture-uuid" }
   Backend valida inputs con esquema, asigna expiración (300 s), inserta en SQLite 'command_runs'.
   Como risk == 'read', state = 'prepared' (requires_approval = False).
   Devuelve objeto operation JSON.
   ↓
7. command-library.js:241 ejecuta adopt(operation).
   Como state === 'prepared', invoca de inmediato this.execute(false).
   ↓
8. POST /axx-api/commands/execute  { "operation_id": "fixture-uuid" }
   Backend adquiere execution_gate, cambia state a 'running', despacha a ActionExecutor.execute_action('system_telemetry', ...).
   ActionExecutor obtiene métricas del SO, verifica postcondiciones.
   Backend actualiza SQLite con state = 'succeeded', postconditions_passed = True, evidence = {...}.
   Devuelve resultado.
   ↓
9. command-library.js:265 actualiza UI:
   - Formatea texto resumen: "Comando completado y verificado: axx.system.telemetry (CPU 14%, RAM 8.1 de 16 GB)."
   - Llama Axx.companion.localNotice(message) → publica mensaje del asistente en el chat y sintetiza voz si está activa.
   - Llama Axx.companion.action('success').
   - Vuelca JSON en #command-library-result (dentro de #view-files).
```

### 3.2 Flujo B: Comando con Aprobación Requerida (Escritura de Archivos)

```
1. Usuario envía "crear archivo" o ejecuta desde la biblioteca un comando de riesgo 'workspace_write'.
   ↓
2. POST /axx-api/commands/prepare devuelve state: 'awaiting_approval', requires_approval: true.
   ↓
3. command-library.js:248 ejecuta adopt(operation):
   - Invoca this.open() → LLAMA A `Axx.companion.openFeature('files')` (¡Cambia forzosamente la vista a Archivos!).
   - Despliega tarjeta #command-library-approval con el botón "Aprobar y ejecutar este comando".
   - Vuelca parámetros en #command-library-preview.
   - Publica aviso en el chat: "Comando preparado. Revisa sus parámetros en Biblioteca y pulsa «Aprobar y ejecutar este comando»."
   ↓
4. El usuario DEBE hacer clic en el botón #command-library-approve.
   ↓
5. POST /axx-api/commands/execute  { "operation_id": "...", "approved": true }
   Backend verifica que approved === True, ejecuta file_artifact_writer, genera archivo en disk, valida SHA-256.
   ↓
6. Se notifica éxito en el chat y se actualiza el estado.
```

### 3.3 Flujo C: La Trampa del 403 `USE_COMMAND_POLICY` en `/axx-api/actions/execute`

En `backend/server.py` (líneas 472–477):
```python
elif path == '/axx-api/actions/execute':
    # The legacy transport cannot confer permission to write or run blocked adapters.
    if body.get('tool_name') not in ('system_telemetry', 'process_state_inspector'):
        self._send_json(403, {'error': {'code': 'USE_COMMAND_POLICY',
            'message': 'Prepara y aprueba este comando en la biblioteca; la ruta antigua no autoriza efectos.'}})
        return
    with self.server.action_lock:
        self._send_json(200, self.executor.execute_action(body.get('tool_name'), body.get('inputs', {}), body.get('operation_id')))
```

**Diagnóstico del Conflicto**:
1. En `1.AXX/Axx.html` (línea 18817), el objeto nativo `DesktopRuntime` implementa su método de ejecución invocando directamente la ruta antigua:
   ```javascript
   const result = await Axx.backendRequest('POST', '/axx-api/actions/execute', { tool_name: toolName, inputs, operation_id: Axx.newId() });
   ```
2. En `1.AXX/scripts/command-library.js` (línea 58), se intenta corregir esto sobreescribiendo el método mediante monkey-patching:
   ```javascript
   Axx.desktop.execute = async (toolName, inputs) => {
       if (!ids[toolName]) throw new Error('Este adaptador está pendiente de validación. Consulta la biblioteca.');
       await this.prepare(ids[toolName], inputs, 'text');
   };
   ```
3. **Puntos de Falla Comprobados**:
   - **Desfase de carga de scripts**: `command-library.js` se carga al final del DOM (`Axx.html:18936`). Si cualquier evento interactivo invoca `Axx.desktop.execute` antes de que este script termine de registrarse, o si ocurre un fallo en la inicialización de `CommandLibrary`, la llamada cae en `/axx-api/actions/execute`. Si `tool_name === 'file_artifact_writer'`, el backend devuelve **403 `USE_COMMAND_POLICY`**.
   - **Adaptadores inexistentes o pendientes**: En `Axx.html:18764`, el botón `#desktop-blender` invoca `this.execute('blender_render_fixture', ...)`. `ids['blender_render_fixture']` no existe en `command-library.js`, por lo que lanza excepción. Si se ejecutara contra `/axx-api/actions/execute`, devolvería **403 `USE_COMMAND_POLICY`**.
   - **Ruptura de contexto por aprobación**: Cuando el usuario está en Ajustes (`#view-settings`) y pulsa *"Guardar y comprobar SHA-256"*, la llamada redirigida a `this.prepare('axx.artifact.write', ...)` detecta `awaiting_approval` y dispara `this.open()`, el cual ejecuta `Axx.companion.openFeature('files')`. **El panel de Ajustes se cierra bruscamente y se abre el panel de Archivos**. El usuario no entiende por qué la pantalla cambió ni dónde quedó la acción que estaba configurando.

---

## 4. Retroalimentación Observable y Visualización de Resultados

### 4.1 Estado Actual de la Visualización

Al ejecutar un comando, los resultados y estados se dispersan de manera inconsistente en 4 ubicaciones distintas:

| Ubicación | Elemento DOM | Formato del Resultado | Visibilidad para el Usuario |
|---|---|---|---|
| **Chat** (`#view-chat`) | Mensaje `.chat-message.notice` en `#chat-log` | Texto resumen de 1 línea: *"Comando completado y verificado: axx.system.telemetry (CPU 14%, RAM 8.1 de 16 GB)."* | Visible solo si el panel de Chat está abierto. No muestra métricas completas ni estructura JSON. |
| **Biblioteca en Archivos** (`#view-files`) | `<p id="command-library-status">`<br>`<pre id="command-library-result">` | Párrafo de estado + bloque `<pre>` de JSON crudo sin coloreado sintáctico ni diseño accesible. | Oculto salvo que el usuario esté deliberadamente en `#view-files`. |
| **Escritorio en Ajustes** (`#view-settings`) | `<p id="desktop-runtime-status">`<br>`<pre id="desktop-action-result">` | Párrafo de estado + bloque `<pre>` de JSON crudo. | Oculto salvo que el usuario esté en `#view-settings`. |
| **Panel de Acciones** (`#view-actions`) | `<div id="response">` | Mensaje de texto plano estático: *"No hay un modelo de IA conectado"*. | Visible si se abre el panel de acciones, pero muestra información errónea / falsa. |
| **ActionDesk** (`#a11-action`) | Ninguno | Ninguno | Completamente ajeno a los comandos del sistema. |

### 4.2 Estados de Ejecución: ¿Son Visibles al Usuario?

El backend implementa una máquina de estados robusta:
`prepared` → `awaiting_approval` → `running` → `succeeded` / `failed` / `blocked` / `cancelled` / `expired` / `unknown`.

Sin embargo, en el frontend:
1. **Estado `running` (En ejecución)**:
   - Solo cambia el texto de `<p id="command-library-status">` a *"Ejecutando y comprobando el resultado."*.
   - **No hay spinner, ni barra de progreso, ni bloqueo visual de controles**.
   - En el chat, no aparece ningún indicador de pensamiento o progreso durante la ejecución del comando.
2. **Estado `awaiting_approval` (Esperando confirmación)**:
   - Muestra el bloque `<section id="command-library-approval">` únicamente dentro de `#view-files`.
   - Si el comando se inició desde el chat o desde un atajo, el chat solo dice: *"Revisa sus parámetros en Biblioteca y pulsa..."*. El usuario debe adivinar cómo llegar a la Biblioteca si no vio el cambio de panel.
3. **Estado `succeeded` con postcondiciones verificadas**:
   - Se muestra un volcado JSON crudo. No hay tarjetas visuales estructuradas (ej. tarjeta de telemetría con barras de uso de CPU/RAM, o tarjeta de archivo con nombre, tamaño y chip de hash SHA-256 verificado).
4. **Estado `failed` o `blocked`**:
   - Se reporta con texto plano en rojo tenue. No hay botones de acción para reintentar o corregir parámetros.

---

## 5. Estrategia de Corrección y Recomendaciones Línea por Línea

Para resolver la desconexión total, garantizar resultados observables reales, eliminar errores 403 y alinear la experiencia con la identidad visual aprobada (`reference/Axx_reference_v20.html`), se formulan las siguientes modificaciones concretas:

### 5.1 Correcciones en `1.AXX/Axx.html`

#### 1. Reconstrucción y Conexión de `#view-actions` (Líneas 1498–1501)
- **Problema**: `#view-actions` tiene un formulario desconectado con el texto engañoso *"Acciones locales. No hay un modelo de IA conectado."*.
- **Corrección**: Transformar `#view-actions` en el **Centro de Comandos y Automatización del Sistema**. Debe alojar:
  1. Barra de entrada de comandos directa con soporte para comandos naturales (`estado del sistema`, `crear archivo`), comandos explícitos (`/comando <id> {params}`), y búsqueda en el catálogo.
  2. Selector de comandos ejecutables destacados (Telemetría del sistema, Inspección de procesos, Creación de archivos verificados).
  3. Contenedor de resultados estructurados `#actions-result-card` con insignias de estado visuales (`Listo`, `Ejecutando`, `Verificado`, `Requiere aprobación`, `Error`).
  4. Tarjeta modal de aprobación integrada en la misma vista, evitando saltos inesperados entre paneles.

#### 2. Delegación en `App.prototype.execute` (Líneas 6655 y 7024–7075)
- **Problema**: `App.prototype.execute(command)` rechaza cualquier comando que no sea temporizador o notas locales con el texto hardcodeado en la línea 7074.
- **Corrección**:
  ```javascript
  // En Axx.html línea 7074:
  // Reemplazar el fallback estático por delegación hacia la biblioteca de comandos:
  if (window.Axx?.commandLibrary) {
      void window.Axx.commandLibrary.dispatchFromInput(raw);
      return;
  }
  this.respond('Comando no reconocido. Prueba «estado del sistema», «temporizador 10 s» o «mis notas».');
  ```

#### 3. Integración de Comandos en `#command-palette` (Líneas 10134–10157)
- **Problema**: `CommandPalette.prototype.search()` solo busca en `Axx.FEATURES`, `notes` y `todos`.
- **Corrección**: En `search()`, agregar las operaciones del catálogo de comandos:
  ```javascript
  // En Axx.html línea 10141:
  if (Axx.commandLibrary?.commands) {
      for (const cmd of Axx.commandLibrary.commands.filter(c => c.execution_enabled)) {
          items.push({
              title: cmd.title || cmd.id,
              detail: cmd.description || 'Comando del sistema verificado',
              kind: 'Comando',
              open: () => {
                  Axx.companion.openFeature('actions');
                  void Axx.commandLibrary.prepare(cmd.id, {}, 'text');
              }
          });
      }
  }
  ```

#### 4. Sustitución Nativa de `DesktopRuntime.prototype.execute` (Líneas 18815–18821)
- **Problema**: Invoca directamente `/axx-api/actions/execute`, detonando el 403 `USE_COMMAND_POLICY`.
- **Corrección**: Redefinir `DesktopRuntime.prototype.execute` de forma nativa para que invoque `Axx.commandLibrary.prepareAndExecute(commandId, inputs)` directamente, sin depender de monkey-patching posterior. Eliminar el botón inservible `#desktop-blender` o marcarlo explícitamente como desactivado por política de seguridad.

---

### 5.2 Correcciones en `1.AXX/scripts/command-library.js`

#### 1. Reubicación del Montaje DOM (Línea 42)
- **Problema**: `node('view-files').prepend(section);` monta la biblioteca dentro del explorador de archivos.
- **Corrección**:
  Cambiar el montaje para que se inserte en `node('view-actions')` o en su propio contenedor de comandos:
  ```javascript
  const targetView = node('view-actions') || node('view-files');
  targetView.replaceChildren(section);
  ```

#### 2. Aprobación en el Mismo Contexto (Líneas 54 y 248)
- **Problema**: `this.open()` en la línea 54 fuerza `Axx.companion.openFeature('files')`, rompiendo el flujo de trabajo del usuario cuando este se encuentra en Ajustes o en el Chat.
- **Corrección**:
  Hacer que `open()` abra la vista activa de comandos (`Axx.companion.openFeature('actions')`). Si el comando se inició desde el Chat, renderizar una tarjeta interactiva de confirmación directamente dentro del hilo del chat, permitiendo pulsar *"Aprobar"* o *"Cancelar"* sin salir de la conversación.

#### 3. Filtro entre Comandos Ejecutables y Catálogo Documental (Líneas 88–96)
- **Problema**: El selector `#command-library-select` mezcla los 3 comandos reales con miles de comandos documentales bloqueados, generando frustración.
- **Corrección**:
  Crear dos `<optgroup>` en el desplegable:
  - `<optgroup label="Comandos verificados en este equipo (Ejecución real)">`: contiene `axx.system.telemetry`, `axx.process.inspect`, `axx.artifact.write`.
  - `<optgroup label="Catálogo de referencia documental (Sin adaptador)">`: contiene los comandos documentales buscados, claramente diferenciados con badge atenuado.

#### 4. Presentación Visual de Resultados Observables (Líneas 202–216, 266–278)
- **Problema**: Vuelca JSON crudo en un elemento `<pre>`.
- **Corrección**:
  Crear una función `renderResultCard(operation)` que genere un componente visual limpio:
  - **Encabezado**: Nombre del comando + Chip de estado con color semántico (Verde para `succeeded` con postcondiciones, Azul para `running`, Ámbar para `awaiting_approval`, Rojo para `failed`).
  - **Métricas para `axx.system.telemetry`**: Barra de progreso de CPU (`XX%`), indicador de memoria RAM (`X.X GB de XX GB`), espacio libre en disco.
  - **Evidencia para `axx.artifact.write`**: Ruta del archivo, tamaño en bytes, resumen del contenido y hash SHA-256 verificado con botón para copiar.
  - **Métricas de proceso para `axx.process.inspect`**: Nombre del ejecutable, PID, estado en Windows, memoria residente.
  - Botón colapsable *"Ver JSON técnico"* para diagnósticos avanzados sin ensuciar la interfaz.

---

## 6. Matriz de Verificación y Criterios de Aceptación (Milestone 3)

| Escenario de Prueba | Entrada / Acción | Resultado Esperado en Frontend | Endpoint Backend | Verificación de Éxito |
|---|---|---|---|---|
| **Telemetría desde Chat** | Escribir `"estado del sistema"` en chat | Chat muestra respuesta con CPU y RAM real. El avatar pasa a estado de éxito. | `POST /axx-api/commands/resolve`<br>`POST /axx-api/commands/prepare`<br>`POST /axx-api/commands/execute` | `state === 'succeeded'`, `postconditions_passed === true`. Evidencia registrada en SQLite. |
| **Escritura con Aprobación** | Escribir `"/comando axx.artifact.write {\"path\":\"test.txt\",\"content\":\"ok\"}"` | Se muestra tarjeta de aprobación con preview de ruta y contenido. La ejecución no inicia hasta pulsar "Aprobar". | `POST /axx-api/commands/prepare` (retorna `awaiting_approval`)<br>`POST /axx-api/commands/execute` (con `approved: true`) | Archivo `%LOCALAPPDATA%\Axx\artifacts\test.txt` existe en disco, su SHA-256 coincide exactamente. |
| **Comando desde `#view-actions`** | Introducir `"estado del sistema"` en el campo de `#view-actions` | La vista `#view-actions` muestra la tarjeta de telemetría sin errores de "sin IA". | Idem Flujo Telemetría | Interfaz muestra métricas en tiempo real. |
| **Búsqueda en Command Palette** | Presionar `Ctrl + K`, escribir `"telemetria"` | Aparece la opción "Estado del sistema · Comando". Al pulsar Intro, se ejecuta el comando. | `POST /axx-api/commands/prepare` | Panel de acciones se abre y muestra el resultado verificado. |
| **Comando Documental Bloqueado** | Seleccionar `AXX-01-0001` en el catálogo | El botón "Preparar" permanece deshabilitado. Mensaje claro: *"Sin adaptador ejecutable validado"*. No se emite ninguna petición `/execute`. | Ninguna llamada a `/execute` | Cero ejecuciones espurias; política de seguridad intacta. |
| **Parada de Emergencia / Cancelar** | Presionar tecla `Escape` durante la preparación | La operación pasa a estado `cancelled`. Las respuestas tardías se descartan. | `POST /axx-api/commands/cancel` | `state === 'cancelled'`, ninguna escritura en disco. |

---

## 7. Conclusión

El motor de comandos de Axx posee un núcleo backend de alta seguridad y rigor técnico, pero sufre de una integración superficial y fracturada en la interfaz de usuario. Al reubicar la biblioteca en `#view-actions`, conectar `#command-form` y `#command-palette`, reemplazar el vuelco de JSON crudo por tarjetas de resultados enriquecidas con métricas del sistema, y eliminar las llamadas residuales a `/axx-api/actions/execute`, se transformará la experiencia en un sistema de automatización fluido, observable, transparente y 100% funcional de extremo a extremo para el Hito 3.
