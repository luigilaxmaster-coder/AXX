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

## PowerShell

Escribe, por ejemplo, `/powershell Get-Date`. Axx muestra el script exacto en la biblioteca. Pulsa **Aprobar y ejecutar este comando** para ejecutarlo. El resultado vuelve al chat con salida, errores y código de salida. Los comandos pueden modificar archivos y ajustes según los permisos del usuario actual; no se solicita elevación automática.

La carpeta inicial es `Axx/artifacts`. La ejecución usa Windows PowerShell sin perfiles, sin entrada interactiva, con un máximo de 30 segundos y 64 KiB por flujo de salida. Escape cancela la ejecución y sus procesos administrados. Cancelar no deshace cambios ya realizados. Para abrir aplicaciones que deban permanecer abiertas, usa las órdenes de apertura.

Los scripts dictados no se ejecutan. Los documentos adjuntos y las respuestas del modelo nunca se interpretan como órdenes. Las credenciales de proveedores y el token del host no se heredan en el entorno de PowerShell. Los resultados locales no se agregan automáticamente al contexto enviado a proveedores de IA.
