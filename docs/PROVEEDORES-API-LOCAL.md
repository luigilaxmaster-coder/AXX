# Conectar modelos a Axx

En **Conectar IA → Por API** puedes añadir varias conexiones con nombres distintos:

1. Elige Ollama local, Ollama Cloud, LM Studio, Groq, Claude/Anthropic, OpenRouter, OpenAI, Gemini u otra API compatible.
2. Pon un nombre, la URL base o IP con puerto, y la clave si el servidor la requiere.
3. Pulsa **Consultar modelos**. Elige uno en la lista Modelo disponible. Para servidores que no publican catálogo, elige **Escribir ID manualmente**. La clave de API se introduce únicamente en el campo de clave, nunca como modelo.
4. Habilita la conexión. Para servicios remotos con cuota o saldo, marca su autorización de uso.
5. Pulsa **Guardar y seleccionar** y **Probar respuesta**. La prueba envía una frase sintética al modelo seleccionado, sin el historial, y muestra respuesta y tiempo. Una conexión guardada o un catálogo válido todavía no prueban inferencia.

Ejemplos de direcciones:

| Servicio | URL base |
| --- | --- |
| Ollama en este equipo | `http://127.0.0.1:11434/v1` |
| Ollama Cloud con clave | `https://ollama.com/v1` |
| Ollama en otro equipo de tu red | `http://192.168.1.50:11434/v1` (sustituye la IP) |
| LM Studio | `http://127.0.0.1:1234/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Claude | `https://api.anthropic.com/v1` |
| Otro proveedor | Su URL base compatible con OpenAI o Anthropic Messages |

El servidor de red debe estar iniciado y accesible desde este equipo. Axx no cambia su firewall ni habilita servicios remotos automáticamente. HTTP se admite para direcciones locales/privadas; los servicios de Internet requieren HTTPS.

Una clave de Ollama Cloud no instala modelos en el servidor local. Si Ollama local no tiene modelos, Axx lo indica; selecciona Ollama Cloud para consultar los modelos de la nube. El catálogo cloud no requiere descargarlos al equipo.

Las claves se guardan cifradas mediante DPAPI para el usuario actual de Windows. No se incluyen en las preferencias del navegador. Para actualizar un modelo, selecciona su conexión guardada. Deja la clave vacía para conservarla. Para cambiar el servidor, crea otra conexión con su propia clave. Puedes deshabilitar una conexión sin borrarla.

La selección fija tanto la conexión como el modelo: un fallo no cambia silenciosamente al modelo de otra plataforma. Consultar el catálogo no envía una conversación. La compatibilidad se limita a chat de texto; no implica soporte de todas las herramientas multimedia de cada proveedor.

Desde 0.22.22, la barra intenta reconectar al proveedor guardado antes de responder que no hay IA. Desconectar explícitamente conserva el modo sin proveedor. Las órdenes directas usan los comandos tipados; las peticiones nuevas y los parámetros que faltan se preparan con el modelo elegido, incluido ChatGPT. Las aclaraciones conservan esa selección. El plan requiere revisión y mantiene los límites y comprobaciones del ejecutor; el texto del modelo no concede permisos ni activa comandos documentales sin adaptador.

La conexión de Ollama Cloud utiliza el endpoint y los IDs de su [documentación oficial](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx). La prueba instalada de 0.22.21 con la conexión existente devolvió texto en 2,76 s y preparó dos consultas en 1,62 s; esas mediciones no garantizan disponibilidad de otros servicios o modelos.

## Modelo local para este equipo

Hardware comprobado el 21 de octubre de 2026: Intel Core i7-14700KF, 31,8 GiB de RAM y NVIDIA RTX 3050 con 8 GiB de VRAM. Ollama 0.32.3 ya estaba instalado y su catálogo estaba vacío.

Recomendación inicial: **Qwen3 4B Q4_K_M**, descarga de aproximadamente 2,5 GB. Deja margen para Windows, Axx y otras aplicaciones. Para instalarlo cuando lo decidas:

```powershell
ollama pull qwen3:4b
```

Después consulta los modelos de Ollama en Axx, selecciona `qwen3:4b` y guarda. Empieza con 4096 tokens de contexto. El consumo real también depende del contexto y de las demás aplicaciones; no se ha medido velocidad de generación en este equipo.

Alternativas: Qwen3.5 4B (descarga de 4,0 GB) y Qwen3 8B Q4_K_M (5,2 GB). El de 8B deja menos margen de VRAM y puede requerir descargar parte del cálculo en CPU.

Fuentes: [Qwen3 4B](https://ollama.com/library/qwen3:4b), [Qwen3.5 4B](https://ollama.com/library/qwen3.5:4b), [Qwen3 8B](https://ollama.com/library/qwen3:8b), [contexto de Ollama](https://docs.ollama.com/context-length), [compatibilidad OpenAI de Ollama](https://docs.ollama.com/api/openai-compatibility), [Claude Messages](https://platform.claude.com/docs/en/api/messages/create), [Groq](https://console.groq.com/docs/overview).
