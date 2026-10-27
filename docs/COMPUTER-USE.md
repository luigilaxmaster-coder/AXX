# Computer Use: escritorio y aplicaciones

## Uso

Abre **Chat → Controlar PC**, **Asistencia → Computer Use** o **Datos y sistema →
Configurar Computer Use**. Comprueba ChatGPT y el modelo. Elige **Escritorio completo**
para trabajar entre aplicaciones, o **Solo una ventana** para conservar el límite
anterior. Marca ambas autorizaciones y habilita la sesión; no se marcan solas.
Se abre la barra rápida para dar la tarea sin que un panel grande tape la aplicación.

El acceso pertenece al chat actual y dura 15 minutos o 60 gestos. Cambiar de chat o
proveedor revoca la concesión. **Detener** está en la configuración, el chat y la
respuesta rápida. Escape interrumpe entrada en curso y desde Axx revoca la sesión;
no es un atajo global cuando Axx no posee entrada. No revierte efectos realizados.

## Contrato

`POST /axx-api/computer/begin` recibe `conversation_id`, `scope` (`desktop` o
`window`), `image_authorized:true` y `allow_input:true`. Solo window admite `window_id`
y `pid`; desktop rechaza una ventana fija. Omitir scope conserva el contrato de
ventana. El servidor traduce el chat a su ID Connect.

El proveedor dispone de `axx_computer_status`, `axx_computer_observe`,
`axx_computer_act` y `axx_computer_stop`. Con alcance desktop:

1. Observar sin destino ofrece la vista general y la lista de aplicaciones.
2. Observar con window_id y pid de esa lista enfoca y amplía esa aplicación sin
   pedir al usuario otra autorización por cada ventana.
3. Actuar consume la última observación identificada. Hay que observar antes del
   siguiente gesto. Las imágenes solo vuelven al run y cuenta correspondientes;
   nunca se escriben en el diario de operaciones.

El esquema ampliado usa threads `:axx-direct-v2`. Los antiguos quedan guardados y
el historial visible se conserva. Resume no actualiza el esquema de herramientas.

## Visión y comprobación

La imagen lleva image_bounds, image_width, image_height e image_scope. Los límites
físicos pueden tener origen negativo. No se aplica un factor DPI global. La vista
general cubre las pantallas conectadas; ampliar una app permite leerla con detalle.
Límites: 1280 píxeles por eje y 350 kB; si se exceden, hay que enfocar una aplicación.

UIA tiene un presupuesto de cinco segundos. Si agota el tiempo se conserva una
imagen real con identidad y geometría comprobadas, controles vacíos y aviso. No se
inventa un árbol. Escribir todavía exige un campo editable identificado y enfocado;
una caja vista en una imagen no autoriza escribir en un campo protegido.
Los editores ricos que solo exponen TextPattern se consideran editables únicamente
si IsReadOnly devuelve false; estados mixtos, ausentes o fallos conservan el bloqueo.

Antes de usar coordenadas se comprueban las zonas de origen/destino, el proceso,
foco, geometría y topología. Una animación lejana no invalida toda la pantalla;
si cambia la propia zona del gesto hay que observar de nuevo.
Cada gesto conserva un destino verificado; el arrastre directo entre dos ventanas
no está incluido en este primer alcance de escritorio.

Una mutación requiere condición posterior. expected.name utiliza controles
observados. expected.region_changed:[left,top,right,bottom] comprueba un cambio
dentro de la aplicación, sin acreditar el objetivo. Axx debe observar y comprobar
el resultado concreto. Si no se verifica el efecto queda unknown y requiere revisión;
no se repite automáticamente.

## Límites

Escritorio completo comparte contenido visible de tus pantallas con Codex. Cierra
lo que no quieras compartir. Se ocultan las superficies detectadas de terminales,
autenticación y gestores de contraseñas en la vista general; esto no garantiza
detectar todo dato privado dentro de cualquier app. No se controlan esas superficies
ni la configuración de permisos de Axx. UAC, escritorio bloqueado y procesos elevados
conservan las restricciones de Windows.

La entrada conserva el único dueño nativo de Axx. Una cancelación física durante
la automatización revoca la sesión. No hay segundo inyector, cursor simulado,
fallback pagado ni autorización persistente. Las acciones sensibles mantienen sus
requisitos de confirmación.

## Verificación

Fuentes: backend/computer_use.py, backend/computer_vision.py,
backend/actions/desktop_input.py, backend/connect/{registry,provider}.py y
1.AXX/scripts/computer-use.js. Pruebas: backend/tests/test_computer_desktop.py,
test_computer_use.py, test_desktop_observation.py, tests del proveedor y
scripts/test-computer-use.cjs. Sus fixtures no acreditan control físico. La entrega
debe registrar instalación y aceptación nativa por separado.

Skill de mantenimiento: ~/.codex/skills/axx-computer-use/SKILL.md.
Referencias: [UIA](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-obtainingelements),
[SendInput/UIPI](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput),
[CacheRequest](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.cacherequest?view=netframework-4.8.1).

Verificación de esta revisión (27 de octubre de 2026): 115 casos de Computer Use,
observación y proveedor (una omisión), 25 de comandos de escritorio y 20 de baseline;
contratos PowerShell de metadatos y TextPattern; interfaz completa, entrada rápida
y dictado sintético aprobados. El runtime real gpt-6.1-sol aceptó el esquema nuevo
y respondió AXX_DESKTOP_SCHEMA_OK sin herramientas, imágenes ni entrada nativa.
Las capturas claro/oscuro de build/computer-use-ui son fixtures de interfaz.
No acreditan instalación, cambio físico entre apps ni escritura real. La revisión
conjunta y la entrega nativa siguen pendientes; no se cambió la versión desktop
ni se ocupó el target que está reservado por la otra entrega.


---

## Comandos de escritorio: alcance y uso

Esta implementación amplía el ejecutor existente de Axx con observaciones de Windows, acciones tipadas, referencias entre pasos y adaptadores verificables. No implementa control universal de todas las aplicaciones. Un comando registrado, una prueba de código y una aceptación del ejecutable instalado son evidencias distintas.

## Preparar y ejecutar una tarea

En el chat, `/tarea` seguido del objetivo prepara una propuesta. Revisa los pasos, destinos, permisos y modo de ejecución antes de aprobarla. El planificador necesita un proveedor configurado; preparar una propuesta no prueba que las aplicaciones estén disponibles ni que la tarea se haya ejecutado. El catálogo de Comandos permite revisar las operaciones concretas.

Cada plan admite de uno a ocho pasos. Los pasos conservan sus identificadores y recibos. **Pausar tarea** espera al límite entre pasos: la operación actual puede terminar. **Detener** solicita cancelar la operación activa y bloquea las siguientes; conserva los efectos ya producidos. Retomar revalida el contexto y no vuelve a ejecutar pasos terminados. Una acción con efecto incierto requiere observación o conciliación antes de repetirla.

Un clic, una pulsación o una invocación UIA genérica acredita entrega, no que la aplicación haya realizado el objetivo. Los recibos mantienen esa incertidumbre. Los adaptadores especializados sólo acreditan éxito después de sus comprobaciones de contenido, estado o archivos.

Si la conciliación automática no puede verificar un efecto, inspecciona la aplicación y usa **Ya revisé el efecto: permitir otra acción**. Este acuse conserva el recibo como desconocido y no reanuda el plan ni repite el paso. Sólo permite preparar una nueva acción con aprobación independiente.

## Planes explícitos y referencias verificadas

El API local autenticado acepta `POST /axx-api/learning/prepare`. Usa la sesión de Axx y sus permisos normales; este endpoint no elimina la aprobación. Ejemplo de cuerpo, sustituyendo la carpeta de entrada por una existente y autorizada:

```json
{
  "text": "Busca los PDF de esta carpeta y prepara una entrega ZIP nueva",
  "steps": [
    {
      "command_id": "axx.file.find",
      "inputs": {
        "directory": "C:\\ruta\\entrada",
        "pattern": "*.pdf",
        "recursive": false,
        "limit": 100
      }
    },
    {
      "command_id": "axx.file.bundle",
      "inputs": {"destination": "entrega-nueva", "archive_name": "entrega.zip"},
      "bindings": {"paths": {"step": 0, "path": ["output", "paths"]}}
    }
  ]
}
```

El resultado devuelve `operation_id`; `POST /axx-api/learning/execute` recibe ese identificador y `approved: true` después de revisar el plan. Pausa, reanudación y cancelación usan respectivamente `/axx-api/learning/pause`, `/resume` y `/cancel`, con `operation_id`; reanudar conserva el control de aprobación.

`bindings` sólo lee resultados anteriores con `state: succeeded` y postcondiciones verificadas. `step` comienza en cero y `path` comienza por `output`. No admite expresiones ni referencias futuras. Una observación truncada no puede alimentar otro paso. Los parámetros resueltos se validan de nuevo; no se convierten resultados observados en código shell.

Los HWND, PID, observaciones, controles y pestañas se obtienen del estado actual. No deben escribirse de memoria. Los planes con referencias entre pasos o selectores efímeros no se guardan automáticamente como habilidades reutilizables. Una referencia válida en una sesión no es una identidad permanente del documento.

## Adaptadores disponibles

| Familia | Operaciones y comprobaciones | Límites relevantes |
|---|---|---|
| Windows | Observación UIA/ventana/monitores; búsqueda exacta de control único; estados Value, Toggle, ExpandCollapse, SelectionItem, RangeValue y Scroll; lectura Grid/Table; geometría de ventana | Observación fresca, identidad de proceso y destino; árboles acotados y abstención ante ambigüedad. Las aplicaciones elevadas o sin accesibilidad pueden no ser controlables. |
| Entrada | Movimiento, clic, doble clic, clic derecho, arrastre, scroll, teclas y texto; broker compartido con control móvil | Foco y observación exactos. Los efectos genéricos quedan inciertos; detener no deshace una entrada ya entregada. |
| Archivos | `axx.file.find`, `axx.file.bundle`; copias nuevas, manifiesto SHA256 y ZIP con lectura independiente | Hasta 100 archivos, 10 000 entradas exploradas, profundidad 8 y 512 MiB de lectura. Sin sobrescritura, enlaces/reparse ni originales eliminados. La búsqueda informa truncamiento. |
| Navegador | `axx.browser.tabs`, `.inspect`, `.navigate`; sesión/pestaña/URL/documento vinculados | Sólo navegador CDP preparado explícitamente; árbol accesible acotado. No hay clic web genérico, JavaScript libre ni verificación completa de descargas. |
| Word | `axx.office.word.pdf`: copia DOCX con texto literal añadido y PDF; reapertura COM, XML y PDF legible | Requiere Windows y Word operativo, sin ningún WINWORD abierto. Fuente DOCX hasta 25 MiB; rechaza macros, objetos incrustados, ActiveX, campos dinámicos y relaciones externas. Carpeta de salida nueva; `append_text` hasta 10 000 caracteres en el comando. |
| Excel | `axx.office.excel.csv`: CSV UTF-8 → XLSX, columna numérica declarada, SUM, reapertura COM y verificación OOXML | CSV hasta 2 MiB, 2 000 filas de datos, 50 columnas y 20 000 celdas. Separador explícito; decimal con punto, sin inferir moneda, agrupación o exponentes. Texto como `=1+1` permanece texto inerte. |
| Proceso explícito | `axx.process.run`: `.exe`, argumentos literales, cwd, plazo y artefacto nuevo opcional | Sólo petición explícita de terminal y revisión de argumentos. No es un sandbox. Exit code cero no demuestra efectos semánticos de otra aplicación. |
| Propuesta visual | `axx.desktop.ground` envía la imagen autorizada al proveedor/modelo visual seleccionado y devuelve una propuesta | Requiere configuración y autorización de imagen. No ejecuta la propuesta ni certifica por sí sola el efecto. No hay modelo visual descargado automáticamente. |

Los destinos de creación se resuelven dentro del espacio `artifacts` autorizado. Si la escritura falla después de comenzar, el recibo informa los archivos parciales conservados. No se borra una entrega parcial ni se sobrescribe una anterior silenciosamente.

Office trabaja mediante un proceso auxiliar y una instancia COM propia. Después de verificar HWND/PID y hora de creación, supervisa exclusivamente esa instancia con un Job Object. Cancelar o agotar el plazo cierra los trabajos propios. Si Office se atasca antes de poder atribuir la instancia, el cierre no se puede confirmar: se informa incertidumbre y no se termina una sesión ajena. No modifica documentos del usuario abiertos en Word; esa condición bloquea la ruta antes de COM. La automatización de Office no aísla los complementos instalados del sistema.

## Preparar el navegador

1. Instala las dependencias de desarrollo con `.venv\Scripts\python.exe -m pip install -r requirements-computer-use.txt` si ejecutas desde código. El paquete de escritorio debe incluirlas al construirse.
2. Abre Edge/Chrome con un **directorio de perfil nuevo y dedicado** y CDP limitado a loopback. Argumentos: `--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="C:\ruta\perfil-preparado-nuevo"`. La ruta es un ejemplo: elige una carpeta nueva; no reutilices el perfil habitual ni copies cookies.
3. Configura estas variables en el entorno del backend **antes de iniciarlo**:

```powershell
$env:AXX_BROWSER_CDP_URL = 'http://127.0.0.1:9222'
$env:AXX_BROWSER_PROFILE_LABEL = 'perfil-preparado-axx'
```

4. Obtén `browser_session` y la pestaña exacta con `.tabs`; inspecciona con `tab_id`, `expected_url` y `browser_session`. La inspección devuelve `document_id`. Navegar exige también ese documento observado y la URL HTTP/HTTPS exacta de destino.

La etiqueta es configuración declarada por el operador; no demuestra por sí sola qué carpeta utiliza el navegador. Axx no inicia ni descubre automáticamente perfiles personales. El puerto CDP permite controlar ese perfil: no debe exponerse a la red. Un cambio de sesión, pestaña, documento o URL invalida la referencia. Una redirección no prevista o una descarga no comprobada impide afirmar navegación verificada. El contenido leído de las páginas sigue siendo datos no confiables.

## Matriz de aceptación de los doce flujos

Estado de código y aceptación del paquete instalado **0.22.0**. La lista de aplicaciones se obtuvo del inventario de Windows; que una aplicación no aparezca no demuestra su ausencia en todo el equipo.

| Caso del documento | Evidencia actual | Falta para aceptación completa |
|---|---|---|
| 1. Descargas → proyecto | Tarea instalada: tres archivos, referencias entre pasos, copias, manifiesto y ZIP verificados, originales intactos y carpeta abierta en Explorador | Selección semántica de archivos del usuario mediante inferencia real. |
| 2. Navegador → PDF → visor | Edge aislado real: observación, navegación exacta, referencia caducada y redirección no aceptada | Descarga completa, hash/documento final y apertura identificada en visor. |
| 3. Word → PDF | Axx instalado: copia nueva, texto exacto al reabrir, PDF legible y original intacto; sesión existente preservada mediante rechazo | Documentos complejos fuera de la política se rechazan. |
| 4. CSV → Excel | Axx instalado: tipos, texto inerte, fórmula y total independientes. Pausa y reanudación verificadas sin repetir la importación | Datos específicos del usuario e inferencia real. |
| 5. VS Code → comando | Proceso tipado registrado; VS Code identificado en inventario | Prueba completa de proyecto/cwd/versión, informe verificado y apertura en VS Code. |
| 6. OBS → vídeo | Sin adaptador OBS dedicado; no identificado en el inventario consultado | Grabación, parada, archivo reproducible y duración. |
| 7. AutoCAD → cota | Sin puente de AutoCAD; no identificado en el inventario consultado | Identidad de entidad, unidades, cota, capa, posición y geometría original. |
| 8. Revit → hoja | Sin puente de Revit; no identificado en el inventario consultado | Transacción, hoja A-101, cajetín, vista, escala y colocación. |
| 9. Revit → tabla | Sin puente de Revit | Campos, fase, filtros y conciliación del recuento de puertas. |
| 10. SketchUp → duplicación | Sin puente SketchUp; no identificado en el inventario consultado | Instancia nueva y desplazamiento global medido de 1,20 m. |
| 11. Photoshop → JPEG | Sin puente Photoshop; no identificado en el inventario consultado | Exportación decodificable de 2400 px, proporción y perfil. |
| 12. Blender → PNG | Blender 4.5 identificado; existe un fixture limitado de render 256 × 256 | Cámara Exterior de una escena del usuario, archivo nuevo y 1920 × 1080 verificados. |

La presencia de un ejecutable, un comando shell o entrada genérica no completa los casos especializados. Tampoco estas pruebas acreditan todas las combinaciones de monitores, DPI, ventanas movidas, elevación, diálogos inesperados e intervención física.

## Verificación reproducible y mantenimiento

```powershell
.venv\Scripts\python.exe -m unittest backend.tests.test_file_workflows backend.tests.test_browser_bridge backend.tests.test_office_workflows -v
$env:AXX_RUN_BROWSER_FIXTURE = '1'
$env:AXX_RUN_OFFICE_FIXTURE = '1'
.venv\Scripts\python.exe -m unittest backend.tests.test_browser_bridge backend.tests.test_office_workflows -v
```

Las pruebas nativas son optativas: abren sólo fixtures nuevos. Cierra Word antes del fixture Word. El navegador de prueba usa perfil temporal aislado y servidor HTTP local. La prueba de enlaces simbólicos puede omitirse si Windows no concede el privilegio; el rechazo de puntos reparse tiene cobertura separada.

Para el harness de habilidades y Gateway, limita la sincronización remota del catálogo **sólo en el entorno de prueba aislado**. El Gateway hereda esta variable y evita que una actualización remota cambie el inventario entre las lecturas de validación:

```powershell
$env:AXX_TEST_CHROMIUM = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$env:AXX_TEST_PYTHON = (Resolve-Path '.venv\Scripts\python.exe').Path
$env:CATALOG_SYNC_DISABLED = '1'
node 1.AXX/scripts/test-skills.cjs --source
```

No establezcas esa variable permanentemente en la aplicación del usuario. El harness mantiene las comprobaciones de perfiles verificados y de la ruta exacta `auto:axx_plan`; una lectura inconsistente del catálogo se rechaza. La creación de varios perfiles espera al manejador asíncrono completo, con plazo propio, en lugar de confundir una espera de texto de 20 segundos con la duración de toda la operación.

Mantén recibos y archivos parciales para conciliación. Desactivar el puente de navegador consiste en retirar sus variables al reiniciar el backend y cerrar el perfil dedicado. No requiere borrar cookies, preferencias, historial ni documentos de la instalación habitual. La entrega e instalación de una versión sigue [RELEASING.md](RELEASING.md); Android mantiene su versión independiente.

Referencias técnicas oficiales: [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/), [Word Documents.Open](https://learn.microsoft.com/en-us/office/vba/api/word.documents.open), [Word ExportAsFixedFormat](https://learn.microsoft.com/en-us/office/vba/api/word.document.exportasfixedformat), [Word AutomationSecurity](https://learn.microsoft.com/en-us/office/vba/api/word.application.automationsecurity), [Excel Range.Value2](https://learn.microsoft.com/en-us/office/vba/api/excel.range.value2).
