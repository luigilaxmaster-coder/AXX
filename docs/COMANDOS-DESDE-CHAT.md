# Comandos desde el chat de Axx

Las acciones directas funcionan en Axx para Windows aunque no haya un modelo conectado. El chat identifica la orden, valida los parámetros y muestra el resultado local. El texto generado por un modelo no se ejecuta.

Ejemplos:

- `abre YouTube`
- `¿Puedes abrir YouTube por favor?`
- `abre https://example.com`
- `busca música tranquila en YouTube`
- `busca en Google clima La Paz`
- `abre la calculadora`
- `abre el bloc de notas`
- `abre Paint`
- `abre explorador`
- `estado del sistema`
- `/comandos` para consultar otras acciones y sus parámetros.

Los atajos a sitios incluyen YouTube, Google, Gmail, GitHub, ChatGPT y Spotify. Las búsquedas abren resultados en el navegador; no entregan el contenido de la página al modelo. El recibo de apertura confirma que Windows aceptó la solicitud, no que una página haya terminado de cargar.

## Chrome, elementos y continuidad musical

La corrección local separa estas operaciones:

- `abre Chrome y busca YouTube`: abre Chrome si hace falta y verifica la dirección en una ventana única. No confirma que haya cargado todo el contenido.
- `pon el mouse sobre Geist en Chrome`: busca una etiqueta accesible exacta y única; mueve el cursor mediante el broker y comprueba su posición. Si la etiqueta falta, se repite o la observación está truncada, se abstiene.
- `busca en yotune una cncion la cancion Faint de Linkin Park`: reconoce el destino y quita el prefijo de solicitud. La búsqueda conserva el título y artista.
- `reprodúcela` o `reproduce la canción`: recupera la consulta de YouTube del mismo chat durante diez minutos, vuelve a observar resultados y solicita reproducción. Sin ese contexto pide la canción.
- `reproduce Faint de Linkin Park en YouTube`: selecciona un resultado observado que coincida con los términos; prefiere una grabación oficial única. Una coincidencia múltiple requiere concretar la versión.

La reproducción sólo entrega un recibo de éxito al observar el título seleccionado, el estado Pausa del reproductor y dos posiciones crecientes. Un anuncio visible, un árbol incompleto, un reproductor detenido o un bloqueo no acreditan reproducción. Escape y la intervención física conservan prioridad mediante el dueño de entrada existente. No se envía contenido leído a un modelo ni se añaden dependencias.

Estado de esta corrección: implementación y pruebas de contrato locales. La aceptación del ejecutable instalado y de YouTube real está pendiente: el control visual se detuvo al no poder identificar con confianza la URL del navegador. La versión instalada y el enlace publicado no se modificaron. Los catálogos de tareas adjuntos siguen siendo casos especificados, salvo los recorridos expresamente probados.

## PowerShell

Escribe, por ejemplo, `/powershell Get-Date`. Axx muestra el script exacto en la biblioteca. Pulsa **Aprobar y ejecutar este comando** para ejecutarlo. El resultado vuelve al chat con salida, errores y código de salida. Los comandos pueden modificar archivos y ajustes según los permisos del usuario actual; no se solicita elevación automática.

La carpeta inicial es `Axx/artifacts`. La ejecución usa Windows PowerShell sin perfiles, sin entrada interactiva, con un máximo de 30 segundos y 64 KiB por flujo de salida. Escape cancela la ejecución y sus procesos administrados. Cancelar no deshace cambios ya realizados. Para abrir aplicaciones que deban permanecer abiertas, usa las órdenes de apertura.

Los scripts dictados no se ejecutan. Los documentos adjuntos y las respuestas del modelo nunca se interpretan como órdenes. Las credenciales de proveedores y el token del host no se heredan en el entorno de PowerShell. Los resultados locales no se agregan automáticamente al contexto enviado a proveedores de IA.
