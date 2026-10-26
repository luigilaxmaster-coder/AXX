# Conexiones MCP y gateway local

En Axx, Ajustes → Conexiones MCP permite registrar un servidor stdio o HTTP,
comprobar su catálogo y activar herramientas individualmente. El acceso radial
«MCP» abre el mismo panel. Las herramientas nuevas empiezan desactivadas.
Nombre y contexto identifican la cuenta/instancia; las anotaciones del servidor
no conceden permisos. Revisa cada herramienta antes de marcarla como sólo lectura.

Las conexiones se guardan cifradas con DPAPI para el usuario Windows actual,
fuera del repositorio. El token no se guarda en localStorage ni se devuelve al
frontend. HTTP sin TLS se admite sólo para direcciones loopback literales.
Los esquemas incompatibles se muestran como rechazados; no desactivan otras
herramientas compatibles del mismo servidor. Una reconexión requiere comprobar
el catálogo. Si cambia un esquema, su autorización anterior no se reutiliza.

## AnythingMCP en esta máquina

Motor Docker de la distribución existente `Ubuntu-24.04`, PostgreSQL privado y
dos puertos enlazados a loopback: interfaz 3000 y API/MCP 4000. Las imágenes se
fijan por SHA-256 en `scripts/anythingmcp-local.py`. La carpeta privada es
`%LOCALAPPDATA%\Axx\anythingmcp`; no copies su `.env` al repositorio.

```powershell
.venv\Scripts\python.exe scripts/anythingmcp-local.py status --wsl-distribution Ubuntu-24.04
.venv\Scripts\python.exe scripts/anythingmcp-local.py start --wsl-distribution Ubuntu-24.04
.venv\Scripts\python.exe scripts/anythingmcp-local.py stop --wsl-distribution Ubuntu-24.04
```

`stop` conserva la base de datos. El proceso auxiliar mantiene WSL activo mientras
se utiliza el gateway; no hay una tarea de arranque al iniciar Windows. Después
de reiniciar Windows se debe ejecutar `start`.

1. Abre `http://localhost:3000` y completa el primer administrador.
2. Configura en AnythingMCP el conector de la aplicación/API y su credencial MCP.
3. En Axx registra `http://127.0.0.1:4000/mcp` con esa credencial, comprueba el
   catálogo y activa exclusivamente las herramientas revisadas.
4. Ejecuta una lectura y comprueba su resultado. Una respuesta HTTP de salud no
   acredita autenticación ni ejecución de herramientas.

Estado comprobado el 26 de octubre: administrador local creado e inicio de
sesión verificado. La contraseña generada se conserva fuera del repositorio,
en `%LOCALAPPDATA%\Axx\anythingmcp\administrator-credentials.json`, con ACL
limitada al usuario Windows y SYSTEM. Ese archivo contiene la contraseña en
texto: no debe copiarse a Git, adjuntos ni registros. Correo aún sin verificar.

El servidor «Axx verificación de lectura» expone un conector REST con un GET
fijo a los metadatos públicos de `HelpCode-ai/anythingmcp` en la API de GitHub.
Su clave MCP está acotada a ese servidor y guardada con DPAPI. Axx comprobó el
catálogo autenticado y activó exclusivamente `axx_gateway_public_repo`; la
herramienta auxiliar de conocimiento sigue desactivada. La primera lectura
(`anythingmcp-public-read-20261026`) espera aprobación en Axx: conexión y catálogo
no acreditan todavía ejecución. La instancia mantiene rechazado el MCP anónimo.

## Ejecución y verificación

Los comandos MCP pasan por CommandService y ActionExecutor, con aprobación,
cancelación, identidad de operación y diario existentes. Una mutación remota
queda en estado desconocido si sólo existe una confirmación del servidor y no
una postcondición independiente. No se repite automáticamente.

El adaptador nativo de Windows usa MCP HTTP local con bearer efímero y tickets
de un solo uso para acciones ya admitidas. Comparte el broker de entrada y el
diario de Axx. Actualmente esa conexión nativa es directa: no se ha probado su
recorrido a través de AnythingMCP.

## Capacidades nuevas y requisitos

| Comando | Uso y requisito |
|---|---|
| `axx.browser.download_pdf` / `axx.browser.open_pdf` | Perfil CDP autorizado; documento/enlace exactos, descarga y apertura verificadas por ruta y hash. |
| `axx.desktop.ocr` / `axx.artifact.ocr` | Recorte observado o PNG/JPEG local, modelos latinos privados. Ejecuta `python scripts/prepare-ocr.py` para instalarlos con hash verificado. |
| `axx.ifc.inventory.csv` | IFC local → CSV con GUID, clase, nombre, cantidad y unidad; no calcula geometría. |
| `axx.office.powerpoint.pdf` | PowerPoint cerrado; modifica texto exacto de una forma en una copia, reabre y exporta PDF. |
| `axx.blender.scene.render` | Blender instalado; escena/cámara/objeto estático exactos, posición XYZ y tamaño PNG. Empaqueta texturas en el blend; no admite librerías externas. |
| `axx.artifact.pdf` / `axx.artifact.media` | Inspección acotada con pypdf o ffprobe; no certifica calidad visual ni decodificación completa de vídeo. |

OBS usa su WebSocket 5 autenticado y verifica el archivo con ffprobe. El host OBS
no está instalado en esta máquina, por lo que su funcionamiento nativo queda
pendiente. No se habilitan conectores de aplicaciones/cuentas ausentes.

Instalación de dependencias de desarrollo:
`python -m pip install -r requirements-computer-use.txt`.
Los pesos OCR se conservan fuera del repositorio y del instalador.

## Pruebas

La suite normal no envía entrada al escritorio. Las siguientes pruebas nativas
son optativas y crean fixtures propios: `AXX_TEST_BROWSER_NATIVE`,
`AXX_TEST_OCR_NATIVE`, `AXX_TEST_DESKTOP_OCR_NATIVE`, `AXX_TEST_BLENDER_NATIVE` y
`AXX_RUN_OFFICE_FIXTURE`, todas con valor `1`. No equivalen a aceptación del
ejecutable instalado. Consulta `COMPUTER-USE-EXPANSION.md` y los recibos.

Fuentes: [AnythingMCP](https://github.com/HelpCode-ai/anythingmcp),
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[RapidOCR](https://github.com/RapidAI/RapidOCR),
[IfcOpenShell](https://docs.ifcopenshell.org/),
[PowerPoint PDF](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.presentation.exportasfixedformat).
