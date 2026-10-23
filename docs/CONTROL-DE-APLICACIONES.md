# Control extensible de aplicaciones Windows

## Estado y alcance

El control amplía el `CommandService` y el `ActionExecutor` existentes. La presencia de un programa en `Get-StartApps` prueba que Windows lo registra; no prueba que Axx pueda automatizarlo. El inventario informa por separado detección instalada, rutas genéricas UIA registradas y disponibilidad desconocida de sus controles. Cada aplicación necesita una prueba por acción antes de declarar esa acción validada.

La apertura diferencia `launch_requested`, `window_observed`, `foreground_verified` y `ready_for_action`. `os.startfile` solo acredita el traspaso a Windows. Axx no debe continuar con escritura si no puede asociar y leer de vuelta una ventana en foreground cuyo título concuerde con el nombre/alias solicitado.

## Acciones registradas

| ID | Entrada | Efecto y verificación | Permiso |
|---|---|---|---|
| `axx.desktop.list_apps` | Ninguna | Inventario de aplicaciones registradas; identifica la detección, no capacidades por app. | Lectura |
| `axx.desktop.list_windows` | Ninguna | Ventanas superiores visibles, HWND, PID, título y foco. | Lectura |
| `axx.desktop.window.inspect` | `window_id` hexadecimal observado y `pid` | Árbol UIA limitado, sin valores de campos de texto. | Lectura |
| `axx.desktop.window.focus` | `window_id` y `pid` | Comprueba que la identidad sigue vigente y verifica el HWND foreground después de pedir foco. | Local reversible |
| `axx.desktop.window.set_value` | `window_id`, `pid`, `control_id` efímero emitido por inspección UIA, texto literal | Re-resuelve el RuntimeId dentro de la ventana observada; requiere un único control visible/habilitado con `ValuePattern`; verifica lectura posterior por longitud y SHA-256. | Aprobación por operación |

Las referencias HWND/PID y el `control_id` son efímeros: deben venir de la observación actual y se vuelven a resolver antes de actuar. El texto no se transforma en código ni se envía a través de PowerShell como fuente. La acción `set_value` no envía formularios ni pulsa botones; una aprobación de escritura no autoriza un envío.

## Ejecución UI Automation

`backend/actions/uia_worker.ps1` es un worker estático empaquetado con el backend. `windows_automation.py` lo ejecuta en un proceso PowerShell separado con `-MTA`, límites de tiempo/salida y JSON por stdin. La fuente del worker se envía como payload codificado fijo; los parámetros del usuario permanecen datos JSON. No cambia la política de ejecución de PowerShell.

Una respuesta de timeout se considera incierta. Se inspecciona la ventana antes de repetir; la interfaz no reenvía el mismo efecto automáticamente. UIA sin `ValuePattern`, controles ambiguos, proceso cambiado, pérdida de foco o control fuera de pantalla hacen fallar cerrado. No se usa un fallback a coordenadas antiguas ni al shell.

El cursor remoto continúa siendo propiedad de `WindowsInput`/`RemoteControl`. Estas acciones UIA semánticas no inyectan un segundo flujo de `SendInput`; la automatización por coordenadas, controles externos y superficies sin UIA siguen pendientes de adaptadores y puertas propios.

## Procedimientos reutilizables

Los procedimientos solo se guardan después de completar y verificar todos sus pasos. La huella de compatibilidad combina Windows/Python con IDs, parámetros y versiones de adaptador; un cambio invalida la reutilización automática. Los procedimientos aprendidos no guardan controladores HWND/UIA ni texto de escritura. La acción concreta puede prepararse manualmente con aprobación ligada a la ventana y parámetros actuales.

## Verificación

- Unitarios: `python -m unittest backend.actions.tests.test_windows_automation backend.tests.test_desktop_commands backend.tests.test_action_learning -v`
- Frontend sin Chromium: `node --check 1.AXX/scripts/command-library.js` y `node 1.AXX/scripts/test-command-library.cjs`.
- Aceptación Windows: abrir Notepad y Explorador; confirmar estado de ventana/foco; observar controles; escribir en un documento de prueba nuevo de Notepad con aprobación y comparar el valor leído; confirmar que un PID/HWND obsoleto, foco perdido, control ambiguo o falta de `ValuePattern` bloquean la escritura.

Los controles de botones genéricos quedan sin ejecución porque `InvokePattern` solo demuestra despacho, no el efecto final. Cada acción posterior requiere un adaptador con una postcondición real y pruebas para esa aplicación.
