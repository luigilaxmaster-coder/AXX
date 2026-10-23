# Control extensible de aplicaciones Windows

## Estado y alcance

### Integración 0.21.3

- P1: `ActionExecutor.input_control` recibe el mismo `MobileGateway.control` que arbitra el teléfono. Toda escritura, enfoque y apertura integrada toma una concesión exclusiva de `WindowsInput`. El hilo de hooks/SendInput permanece separado del worker COM MTA. Entrada local, Escape, cancelación explícita, pérdida del material visual y vencimiento revocan la concesión. La UI muestra el origen `axx_automation`, remoto o físico. Una concesión revocada no revive cuando otro controlador adquiere la entrada.
- Foco: no se acoplan colas de entrada con `AttachThreadInput`. El dueño restaura ventanas minimizadas, solicita foreground y, si Windows lo rechaza, realiza el gesto ALT etiquetado de activación. Siempre vuelve a comprobar HWND/PID y foreground. No escribe si la activación falla. Notepad y Explorer se asocian también al ejecutable observado; un título de otra aplicación no acredita la apertura.
- P2: `axx.desktop.explorer.folder(path)` abre una carpeta local y contrasta `Shell.Application.Windows().Document.Folder.Self.Path` y foreground. `axx.desktop.notepad.text(window_title,value)` resuelve un único Notepad con el título exacto seleccionado, enfoca, observa un único Document visible con ValuePattern y verifica longitud UTF-16 y SHA256 después de escribir. No guarda el archivo, envía formularios ni cierra pestañas. La selección de ventana y la escritura se ofrecen en el panel existente de lectura de aplicaciones. Los destinos ambiguos quedan bloqueados.
- P3: «Guardar procedimiento verificado» toma exclusivamente un recibo exitoso del ejecutor y crea una habilidad parametrizada en la memoria existente. Se parametrizan `path` o `window_title`/`value`; nunca HWND, RuntimeId o coordenadas. Cada repetición pasa por CommandService y vuelve a resolver el destino, con los permisos y la huella del adaptador actuales. La evidencia de una ejecución concreta no certifica todos los parámetros posibles.
- Recuperación: un worker de escritura interrumpido, con timeout o sin respuesta válida produce `unknown` y conserva destino y etapas parciales. El mismo operation_id no repite el efecto. Otra escritura en el mismo destino queda bloqueada hasta reconciliar. «Revisar efecto sin repetir» hace una lectura de ValuePattern y compara el texto aprobado; solo entonces cambia ambos recibos a éxito. Si el control desapareció o el contenido difiere, mantiene la incertidumbre para revisión manual.

Referencias técnicas: [restricciones de foreground y gesto ALT](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-locksetforegroundwindow) y [hilos de UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading). La prioridad local limita el trabajo pendiente; no revierte efectos ya consumados ni garantiza detener una llamada ya recibida por un proveedor UIA externo.

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

El cursor continúa siendo propiedad de `WindowsInput`/`RemoteControl`. Las acciones semánticas toman su concesión y el foco usa su hilo de entrada. La automatización por coordenadas no se guarda como procedimiento; dispositivos externos y superficies sin UIA necesitan adaptadores y aceptación propios.

## Procedimientos reutilizables

Los procedimientos solo se promueven a verificados después de comprobar sus pasos. La huella combina Windows/Python con IDs, parámetros y versiones de adaptador; un cambio invalida la reutilización automática. Los procedimientos aprendidos no guardan controladores HWND/UIA. Los nuevos flujos guardan plantillas tipadas; el usuario proporciona el texto y el destino para cada ejecución y revisa la aprobación. Los recibos locales conservan los parámetros concretos necesarios para auditoría y recuperación.

## Verificación

- Unitarios: `python -m unittest backend.actions.tests.test_windows_automation backend.tests.test_desktop_commands backend.tests.test_action_learning -v`
- Frontend sin Chromium: `node --check 1.AXX/scripts/command-library.js` y `node 1.AXX/scripts/test-command-library.cjs`.
- Aceptación Windows: abrir Notepad y Explorador; confirmar estado de ventana/foco; observar controles; escribir en un documento de prueba nuevo de Notepad con aprobación y comparar el valor leído; confirmar que un PID/HWND obsoleto, foco perdido, control ambiguo o falta de `ValuePattern` bloquean la escritura.

Los controles de botones genéricos quedan sin ejecución porque `InvokePattern` solo demuestra despacho, no el efecto final. Cada acción posterior requiere un adaptador con una postcondición real y pruebas para esa aplicación.
