# Axx API Router — conmutación de proveedores

Módulo independiente para conectar al Axx existente. Python 3.11 o superior, sin dependencias externas. No instala otro asistente ni ejecuta modelos locales. No está integrado en tu equipo ni probado con cuentas reales.

## Qué puedes hacer

Con modelos de texto: conversación, traducción, resumen, extracción, clasificación, redacción y código. Con un modelo que soporte visión: análisis de capturas enviadas explícitamente. Con tool calling: propuestas estructuradas de acciones que Axx debe validar y ejecutar con sus herramientas. Un modelo por sí mismo no controla Windows, no recibe la pantalla y no adquiere memoria persistente. Este módulo transporta chat compatible con OpenAI; no implementa STT, TTS, imágenes generativas ni ejecución de herramientas.

## Instalación Windows

1. Instala Python 3.11+ y descomprime esta carpeta. No requiere GPU ni Docker.
2. Abre PowerShell dentro de la carpeta.
3. Copia la configuración:

```powershell
Copy-Item providers.example.json providers.json
```

4. En cada proveedor que utilices, sustituye `model` por un identificador real disponible en tu cuenta. Comprueba precio, cuota, condiciones y capacidades en la documentación y consola del proveedor. Después activa `enabled` y `free_confirmed` con `true`. Los valores iniciales están desactivados intencionadamente: son una plantilla de conexión, no credenciales ni modelos inventados.
5. Define tus claves en la sesión local; no las compartas en el chat:

```powershell
$env:GROQ_API_KEY = Read-Host 'Clave Groq' -MaskInput
$env:OPENROUTER_API_KEY = Read-Host 'Clave OpenRouter' -MaskInput
python router.py --request request.example.json
```

`-MaskInput` requiere PowerShell 7. En Windows PowerShell 5, define las variables mediante tu gestor de secretos o interfaz de variables de entorno; evita guardar claves en scripts/historial. Las variables de sesión deben definirse antes de iniciar Axx para que el proceso hijo las herede. `providers.json` solo contiene nombres de variables.

## Funcionamiento

El orden del array es la prioridad. Para cada solicitud:

1. Filtra proveedores activados, confirmados como gratuitos, con credenciales y capacidades suficientes.
2. Comprueba en SQLite la pausa y el límite diario local; reserva un intento antes de enviar.
3. Envía la misma conversación con el modelo configurado del proveedor.
4. Ante 429, pasa al siguiente y pausa el proveedor durante `Retry-After` o al menos 60 segundos. Si la cuota es diaria, los siguientes intentos pueden recibir otro 429: el router no conoce el saldo real ni interpreta mensajes privados del proveedor.
5. Ante 401/402/403, pausa 24 horas. Ante 404/408/5xx o fallo de red, pausa 30 segundos y cambia. Ante otros errores, incluido 400, detiene la solicitud para no multiplicar errores de entrada.
6. Máximo `max_attempts` envíos por solicitud, un intento por proveedor. Si ninguno funciona, devuelve error y salida de proceso 1. No crea cuentas, no rota claves para evadir cuotas y no habilita pagos.

Los límites `daily_attempt_limit` son intentos de este router, reiniciados por fecha UTC; no representan tokens, dinero ni consumo realizado desde otras apps. El proveedor puede contabilizar de otra forma. Los límites y pausas persisten en `state.db`; mantén la misma ruta absoluta para todos los procesos. Cada instancia Router es de un único hilo; para uso concurrente crea una instancia/conexión por hilo. SQLite serializa las reservas entre procesos.

`free_confirmed` es una declaración del operador, no una consulta de precios: configura restricciones de facturación también en el proveedor. No existe una garantía automática de coste cero basada solo en una lista comunitaria.

## Conectar con Axx

Desde Python, ejecutado en esta carpeta:

```python
import json
from router import Router

router = Router(json.load(open('providers.json', encoding='utf-8')), 'state.db')
try:
    result = router.chat({'messages': [{'role': 'user', 'content': 'Hola'}]})
    message = result['choices'][0]['message']
    print(message)
finally:
    router.close()
```

Desde Tauri, Node u otro runtime, invoca `python` con argumentos mediante una API de procesos sin shell, pasando la solicitud JSON por stdin. Lee stdout como JSON; los eventos operativos van a stderr. Usa rutas absolutas para el script, configuración y estado. No interpolar el texto del usuario en comandos de shell.

Entrada: chat compatible con OpenAI (`messages`, `tools`, `tool_choice`, `response_format`, `temperature`, `top_p`, `max_tokens`, `seed`, `stream=false`). El modelo se elige en configuración. Salida: respuesta upstream y `axx_router` con proveedor/modelo/intentos. Los parámetros no son compatibles con todos los modelos: valida cada combinación antes de marcarla apta.

Añade `tools`, `vision` o `json` a `capabilities` solo después de probar esa función en ese modelo concreto. La detección de imágenes contempla partes `image_url`; otros formatos multimedia son rechazados. No envía solicitudes a modelos incompatibles a propósito. Si el proveedor ha cambiado y la configuración quedó obsoleta, una respuesta 400 detiene la solicitud.

## Continuidad y seguridad

- Cambiar de modelo conserva los mensajes enviados; no conserva razonamiento interno, cachés ni calidad idéntica. Axx debe administrar el historial, ajustar contexto y persistir memoria por separado.
- El router no ejecuta tool calls. Axx debe validar herramientas/argumentos y usar identificadores de acción y registro de resultados para evitar ejecutar dos veces una operación.
- Un timeout puede ocurrir después de que el proveedor haya procesado la petición; el respaldo puede consumir cuota adicional.
- Solo respuestas completas, sin streaming. Así no mezcla tokens de dos modelos. Se limita cada respuesta leída a 8 MiB. `timeout_seconds` es timeout de operaciones de socket, no un plazo total estricto; un servidor que entregue bytes lentamente puede tardar más.
- Claves solo en variables de entorno. HTTPS obligatorio, redirecciones rechazadas para impedir reenviar credenciales a otro destino. Los destinos son configuración confiable del propietario; no aceptarlos desde mensajes ni importar automáticamente URLs del catálogo.
- Los logs no contienen prompts ni claves. Los datos se envían al proveedor elegido y, si falla, al de respaldo. Configura únicamente destinos autorizados para esos datos.
- No es un servidor HTTP ni una pasarela multiusuario. No expone puertos. Su integración exacta depende del código real de Axx, que no estaba disponible al crear el paquete.

## Pruebas y verificación

```powershell
python -m unittest discover -s tests -v
python -m compileall -q router.py tests
```

Suite local: 20 pruebas de enrutamiento con transporte simulado; valida éxito, conservación de mensajes, 429 y persistencia, 401, 400, 503, límites locales, filtrado gratuito, herramientas, claves ausentes, streaming y respuesta inválida, además de HTTPS, selección por tarea, filtro de datos sensibles, métricas, estado local, recuperación de pausas y límites de tamaño/salida. No certifica disponibilidad, rendimiento, precios ni capacidades de APIs externas.

Antes de uso real: prueba cada proveedor individualmente; luego prueba el respaldo desactivando el principal y confirma `axx_router.provider`. Para recuperar inmediatamente un proveedor tras corregir credenciales, espera su pausa o elimina solo su fila de `cooldown` con SQLite; no borres la base entera porque perderías los contadores.

## Referencias

- https://github.com/pacocartones/free-llm-api-hub
- https://github.com/pacocartones/free-llm-api-hub/blob/main/packages/mcp/README.md
- https://console.groq.com/docs/openai
- https://openrouter.ai/docs/api-reference/limits

El catálogo sirve como fuente de descubrimiento. Este módulo no depende de su MCP, no actualiza precios automáticamente y no requiere consultar un modelo para seleccionar un proveedor.


## Versión mejorada: control y observabilidad

```powershell
# Demostración offline: no necesita claves ni internet
python demo.py
# Inspección local: no consume llamadas
python router.py --config providers.example.json --status
# Recuperar una API tras corregir credenciales; conserva contadores
python router.py --reset-cooldown groq
```

El estado muestra `disabled`, `free_not_confirmed`, `missing_key`, `cooldown`, `local_quota_exhausted` o `ready`. `ready` significa elegible según datos locales; no certifica salud remota ni saldo. Las métricas persistentes incluyen éxitos, errores, latencia media de los intentos y último HTTP observado. Las métricas son históricas por nombre; si cambias el modelo o destino del mismo nombre, conserva esa historia. Usa nombres nuevos si quieres separar mediciones.

Cada proveedor admite `tasks`: categorías permitidas (`chat`, `code`, `summarize`, `translate` o tus etiquetas). La solicitud puede indicar `axx_task`; por defecto es `chat`. Ausencia de `tasks` permite todas. Esta selección es determinista: no usa un modelo ni consume tokens para clasificar. Axx debe establecer la categoría; no existe clasificación semántica automática.

```json
{"axx_task":"code","axx_sensitive":false,"messages":[{"role":"user","content":"Explica esta función"}],"max_tokens":512}
```

`axx_sensitive=true` solo permite proveedores con `allow_sensitive=true`. Es una etiqueta establecida por Axx/usuario, no un detector automático ni una garantía de confidencialidad del proveedor. El router elimina los campos `axx_*` antes de enviar. Axx debe bloquear datos que no puedan salir del equipo aunque ningún proveedor responda.

`max_output_tokens` ahora limita también los valores explícitos de `max_tokens` (se usa el menor). `max_request_bytes` limita el JSON serializado, por defecto 2 MiB, antes de enviar. No equivale a la ventana de contexto del modelo: no cuenta tokens ni recorta el historial. El historial nunca se elimina silenciosamente.

Los modelos de un mismo proveedor pueden compartir cuota de cuenta: configurar dos entradas no crea dos cuotas independientes. El contador es local por nombre; los errores remotos siguen siendo la autoridad efectiva.
