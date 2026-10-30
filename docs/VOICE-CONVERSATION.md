# Conversación hablada y capacidades de modelos

## Alcance de 0.22.2

El flujo actual es micrófono → Whisper local → modelo de texto seleccionado →
síntesis local. ChatGPT se conecta mediante el runtime oficial de Codex; las
herramientas Axx conservan admisión, permisos, aprobación y recibos de ejecución.

Desde 0.22.29 el instalador público no incluye pesos de modelos. El dictado
reutiliza los modelos locales compatibles en
`%LOCALAPPDATA%\Axx\models\faster-whisper-base` y, después,
`%LOCALAPPDATA%\Axx\models\faster-whisper-tiny`. El modelo necesita
`model.bin`, `tokenizer.json`, `config.json` y `vocabulary.txt` compatibles con
faster-whisper/CTranslate2; no basta renombrar archivos de otro formato.
Sin un modelo completo, Axx informa que la transcripción no está disponible;
no lo descarga automáticamente. Añadir un modelo requiere reiniciar Axx.
La actualización conserva los modelos locales existentes.

- Espera silenciosa. Se retiraron los osciladores de carga y las frases de relleno.
  Las preferencias antiguas `loadingSound` y `voiceFillers` ya no se restauran.
- Las instrucciones de voz priorizan una primera respuesta útil, frases completas,
  contexto y correcciones. Se retiró la obligación absoluta de dos frases y el
  techo de 80 tokens; las rutas de texto que admiten límite reciben 384 en voz.
  Codex recibe `purpose=voice`, manteniendo sus herramientas tipadas.
- Las frases se envían al lector cuando están completas, con bloques de hasta
  180 caracteres cortados por palabras o cláusulas. No se corta un decimal ni un
  tratamiento como «Dr.». Un identificador sin espacios se conserva completo al
  finalizar, aunque supere ese tamaño. El remanente se entrega al terminar el modelo.
- SAPI y MOSS esperan si se agota temporalmente el texto generado. Esa espera no
  cierra el turno ni rearma el micrófono. Cancelar invalida el audio pendiente.
- Las órdenes sin coincidencia determinista usan las herramientas de Connect
  cuando ChatGPT está seleccionado. Las coincidencias ambiguas, errores de
  autorización y restricciones explícitas siguen siendo visibles.
- Las herramientas se publican en el namespace `axx`, con exposición directa y
  sin carga diferida. Codex 0.160 permite `direct_only_tool_namespaces`; se usa
  únicamente para `axx` y se mantiene `code_mode_host=false`. Así los modelos
  cuyo catálogo requiere Code Mode pueden llamar las herramientas de Axx sin
  activar el host de código. Las conversaciones antiguas conservan su asociación
  original; la ruta nueva crea una asociación separada y Axx reenvía su contexto
  local. No se borra el historial.
- Las solicitudes de aprobación de ChatGPT se muestran en el chat de origen con
  el controlador de comandos existente. Se presentan una sola vez por operación
  y no sustituyen una tarea ajena; los paquetes repetidos no restauran una tarjeta
  descartada. La aprobación sigue ligada a los parámetros preparados.
- Las tarjetas de modelos separan catálogo, modalidades declaradas, inferencia
  comprobada, herramientas de Axx y motores de voz. Una conexión detectada no se
  etiqueta como inferencia comprobada. Los metadatos se insertan como texto.

## Lo que la conexión ChatGPT permite demostrar

El catálogo de Codex aporta nombre, modalidades de entrada y opciones de
razonamiento. No demuestra derecho de acceso, calidad, velocidad ni que todas las
modalidades estén conectadas a Axx. La conexión actual de Axx envía texto; aunque
el modelo declare imágenes, se debe utilizar una ruta visual configurada para
adjuntarlas. Las acciones son capacidades del ejecutor, no permisos universales
concedidos por el nombre del modelo.

La documentación oficial consultada distingue el flujo de uso del plan ChatGPT
de los servicios de audio. No se reutilizan credenciales gestionadas por Codex
para llamar a Realtime, transcripción ni síntesis de OpenAI. Tampoco se activan
créditos adicionales ni una API de pago como alternativa automática.

Fuentes consultadas el 26 de octubre de 2026:

- [Codex app-server: catálogo, turnos, herramientas y cancelación](https://learn.chatgpt.com/docs/app-server)
- [Limitaciones del acceso con ChatGPT](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
- [Conversaciones Realtime e interrupciones](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [Detección de turnos de voz](https://developers.openai.com/api/docs/guides/realtime-vad)
- [Configuración oficial de Codex 0.160](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/core/config.schema.json)

## Validación y límites

Los contratos verifican separación entre selección y prueba del modelo, propósito
de voz, conservación de herramientas y aprobaciones, texto de metadatos no
ejecutable, silenciamiento de opciones antiguas y reproducción continua cuando
el modelo tarda en producir la siguiente frase. El audio PCM de los contratos es
controlado: no demuestra pronunciación ni reconocimiento de una persona real.

La interrupción disponible requiere pulsar «Interrumpir y hablar». El micrófono
se pausa durante la respuesta para evitar realimentación. No se afirma detección
automática del habla simultánea ni equivalencia con ChatGPT Voice. Para certificar
esa equivalencia faltan pruebas físicas de micrófono/altavoces, eco, prosodia,
corrección por tarea y latencia de extremo a extremo.

Medir por separado: final del habla → transcripción, primer texto útil, primer
audio útil, pausas entre frases y recuperación tras interrupción. Reportar p50 y
p95 sobre el mismo conjunto de frases y condiciones. Una animación o un sonido
de espera no cuenta como respuesta útil. Los dos segundos siguen siendo una
meta pendiente de aceptación física.

El transcriptor informa `timings_ms` de importación, decodificación, carga del
modelo, inferencia, total del worker y `service_total` (incluye espera y transporte
local). El silencio y el audio inválido se descartan antes de cargar un modelo
frío; se conserva el modelo local instalado, CPU int8 y búsqueda de cinco haces.
La interfaz conserva una copia de la medición al enviar cada turno: una grabación
posterior no debe modificar la latencia mostrada del turno anterior. Son mediciones
de software; no certifican el instante de sonido audible en el altavoz.

## Comprobaciones reproducibles

```powershell
node scripts/validate_js.js
node 1.AXX/scripts/test-conversational-filler.cjs
node 1.AXX/scripts/test-custom-speech.cjs
node 1.AXX/scripts/test-providers.cjs
node 1.AXX/scripts/test-axx-connect.cjs
node 1.AXX/scripts/test-command-library.cjs
node 1.AXX/scripts/test-desktop-frontend.cjs
python -m unittest backend.connect.tests.test_provider -q
```

Los contratos de navegador utilizan Playwright ya instalado en el runtime de
Codex y `AXX_TEST_CHROMIUM` para seleccionar el ejecutable existente. No instalan
modelos, no cambian cuentas y no ejecutan comandos generados durante los tests.

La reversión se realiza con una versión posterior que revierta estos cambios y
el procedimiento de entrega de Windows. No requiere borrar conversaciones,
voces, credenciales ni la configuración visual del usuario.
