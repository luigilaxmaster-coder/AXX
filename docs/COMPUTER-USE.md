# Computer Use en Axx

En el chat, abra **Computer Use**, seleccione una ventana y autorice compartir su
imagen y texto con Codex y controlar su entrada. Seleccione ChatGPT como proveedor
y describa la tarea en ese mismo chat. La interfaz conserva el avatar 3D y el
indicador nativo del dueño de entrada existente.

El modelo recibe imágenes reales y controles de accesibilidad, decide un gesto y
consulta su recibo. Las operaciones pasan por Connect, CommandService,
ActionExecutor, la fachada MCP nativa y el broker de Windows. No existe un segundo
ejecutor de shell. Las herramientas de planificación y generación siguen aisladas.

La autorización dura 15 minutos o 60 gestos y se limita al proceso y ventana
seleccionados. Cambiar de chat o proveedor revoca la sesión. Use **Detener** o
Escape desde Axx. La entrada física puede interrumpir al broker. El botón de
parada mantiene visible cualquier fallo de confirmación.

Una imagen no ejecuta instrucciones que aparezcan en la aplicación. Los tickets
son de un solo uso, pertenecen al chat, cuenta y ejecución admitidos; no pueden
crearse desde el modelo ni recuperarse después de reiniciar. Las imágenes viven
en RAM y viajan al runtime Codex como `inputImage`; el journal guarda metadatos y
texto autorizado, sin imágenes ni base64. No seleccione ventanas con información
que no quiera compartir.

La captura usa PrintWindow sobre el HWND autorizado dentro del worker acotado de
Windows. Se comprueban proceso, geometría física, topología y límites antes de
enviarla. Los puntos visuales se transforman desde la imagen a coordenadas físicas
y requieren una imagen vigente sin cambios. Los controles semánticos se vuelven
a resolver. No se controla el escritorio seguro, ventanas elevadas ni terminales
desde este modo. Una captura negra o no compatible produce un error visible.

Salvo mover el cursor, cada gesto declara una condición de accesibilidad y Axx la
comprueba después. Un efecto no verificable queda `unknown` y bloquea nuevos
gestos hasta revisión manual en Comandos. Una condición ya cumplida no dispara
el gesto. Esto limita las tareas sobre lienzos sin controles accesibles: aún no
hay aceptación universal de CAD, juegos, vídeo o todas las aplicaciones. No se
afirma paridad completa con ChatGPT.

Comprobaciones:

```powershell
.venv/Scripts/python.exe -m unittest backend.tests.test_computer_use -v
node scripts/test-computer-use.cjs
.venv/Scripts/python.exe scripts/verify-computer-use.py
.venv/Scripts/python.exe scripts/verify-computer-use.py --installed
```

La prueba nativa crea su propia ventana Win32, la autoriza por HTTP autenticado,
envía imágenes al modelo real, exige un clic verificado y lee el resultado de
Windows independientemente. Usa el acceso oficial Codex con `allow_paid=false`.
Los recibos privados quedan en `build/computer-use`; no se publican.
