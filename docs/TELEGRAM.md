# Telegram: cuenta única de Axx

Estado: implementación inicial en fuente. La autorización de cuenta se comprueba
por separado de mensajes y llamadas; no instalado ni publicado como integración
completa.

La cuenta de usuario dedicada conserva mensajes y pruebas de llamadas privadas.
Por autorización posterior del propietario, un bot auxiliar añade el menú y la
Mini App oficial. Ambos canales comparten la autoridad de Axx. El PC debe
permanecer encendido, conectado y con Axx abierto.

## Bot y Mini App

```powershell
& "$env:LOCALAPPDATA\Axx\telegram-runtime\Scripts\pythonw.exe" -m backend.telegram.bot_setup
```

Crear el bot con BotFather, abrirlo desde la cuenta personal y enviar `/start`.
Pegar el token solo en la ventana local. El token validado se guarda con DPAPI
antes de configurar el menú; un fallo de menú no pierde ese guardado. La ventana
muestra códigos públicos acotados, nunca la respuesta cruda con el token.

La Mini App necesita una URL HTTPS real. La fachada escucha solo en loopback,
puerto 6451, y requiere `initData` firmado por Telegram para el propietario,
caducidad, sesión revocable y CSRF. Tailscale Funnel debe habilitarse explícitamente
en la cuenta Tailscale antes de hacer accesible esa fachada. Nunca reenviar todo
el backend nativo hacia Internet.

El conector provisional puede utilizar el backend instalado sin otro ejecutor:

```powershell
& "$env:LOCALAPPDATA\Axx\telegram-runtime\Scripts\pythonw.exe" -m backend.telegram.daemon --account-channel
```

Su endpoint DPAPI es independiente del endpoint nativo. Los comandos se admiten,
aprueban y ejecutan mediante las rutas autenticadas de Axx instalado. Se detiene
si cambia la instancia nativa. No registra inicio automático de Windows y no
sustituye una entrega del instalador. El propietario eligió conservar el proveedor
del escritorio aunque la conversación remota permanezca bloqueada: el conector
provisional no hace inferencia ni selecciona otro proveedor.

## Alta local y primera prueba

Desde la raíz del repositorio en Windows x64, Python 3.12:

```powershell
python -m venv "$env:LOCALAPPDATA\Axx\telegram-runtime"
& "$env:LOCALAPPDATA\Axx\telegram-runtime\Scripts\python.exe" -m pip install -r requirements-telegram.txt
& "$env:LOCALAPPDATA\Axx\telegram-runtime\Scripts\pythonw.exe" -m backend.telegram.setup
```

Obtén `api_id` y `api_hash` mediante https://my.telegram.org. Introduce los
datos únicamente en la ventana local: teléfono de la cuenta dedicada, ID
numérico de tu cuenta personal, código y 2FA cuando corresponda. El propietario
debe ser otra cuenta; la primera persona que escriba no obtiene acceso.

Activa el canal y el permiso de llamadas para la prueba. Antes de iniciar el
trabajador de mensajes, ejecuta:

```powershell
& "$env:LOCALAPPDATA\Axx\telegram-runtime\Scripts\python.exe" -m backend.telegram.call_probe --output build/telegram-call-probe.json --timeout 180 --confirm-audible
```

Durante esos tres minutos llama al contacto de Axx desde la cuenta autorizada.
Escucha el tono de prueba, habla y cuelga desde Telegram. La confirmación auditiva
se introduce en esa consola después de la llamada. El recibo contiene contadores
y estados, sin grabación ni credenciales. Energía entrante puede ser ruido: el
corte de un tono no acredita una interrupción de conversación con IA.

`PASS` exige audio entrante no silencioso, frames salientes, colgado remoto,
limpieza, salida comprobada del proceso aislado y confirmación auditiva local.
Sin esos datos queda `BLOCKED`. Importar una DLL no acredita una llamada.

## Lo implementado y sus límites

- Configuración y StringSession protegidas por DPAPI del usuario de Windows en
  `%LOCALAPPDATA%\Axx\telegram\account.dpapi`; no hay sesión en texto plano.
- Trabajador de mensajes aislado con la misma cuenta, solo chat privado del
  propietario. Descarta grupos, bots, ediciones, reenvíos y respuestas citadas.
- Bandeja de transporte persistente con payload protegido, deduplicación e IDs
  de operación estables. Un envío o despacho incierto no se repite automáticamente.
- Conversación separada y visible en ChatStore. Se reutiliza la selección API
  que el escritorio comparte con el backend; requiere UI abierta/sincronizada.
  La selección Connect no se conecta remotamente hasta verificar su aislamiento.
- Acciones exactas del catálogo mediante CommandService, modo guardado, permisos,
  aprobación en la PC y recibos. No hay ejecución directa de shell ni aprobación
  concedida por un mensaje. `/estado` y `/cancelar <id>` conservan prioridad.
- Los mensajes anteriores a 120 segundos se rechazan; los nuevos con el mismo
  texto son solicitudes diferentes. Las operaciones inciertas se revisan en la PC.

El backend de esta fuente inicia el trabajador si hay configuración habilitada,
al arrancar. El trabajador de texto y la prueba telefónica comparten una exclusión
de sesión; hay que detener uno antes de iniciar el otro. El instalador anterior
no incluye estos cambios. Los permisos pueden retirarse en la ventana local sin
detenerla; el trabajador desconecta y el backend comprueba autoridad otra vez.
Revocar no deshace un efecto ya ejecutado.

Rutas nuevas, solo bajo autenticación nativa existente:
`GET /axx-api/telegram/status`, `POST /axx-api/telegram/input`.
No se exponen puertos públicos ni se modifica `/v1` móvil.

**Pendiente:** notas de voz, recepción/procesamiento y devolución de archivos,
conversación ASR/TTS dentro de la llamada, perfil sonoro, interrupción real de
respuesta, aceptación instalada y publicación. Los adjuntos reciben una respuesta
explícita de función todavía no habilitada.

Las pruebas reales del transporte privado recibieron audio, pero no obtuvieron
confirmación de reproducción saliente y una prueba con archivo terminó en timeout
de limpieza nativa. Los contadores de envío no acreditan sonido en el teléfono.
No hay aceptación completa de llamadas ni receptor permanente con conversación.

## Comprobaciones y entrega

```powershell
python -m unittest backend.tests.test_telegram_config backend.tests.test_telegram_service backend.tests.test_telegram_worker backend.tests.test_telegram_http backend.tests.test_telegram_call_probe
python scripts/validate_companion.py --output build/telegram-companion-validation.json
```

Las pruebas automáticas usan dobles de Telegram. El recibo de llamada real y las
pruebas instaladas se evalúan por separado. No se cambia la versión ni se publica
un instalador completo antes de resolver la prueba prioritaria y la aceptación
de las capacidades solicitadas. Para una entrega posterior sigue RELEASING.md.

Para detener acceso, desactiva el canal en la ventana local. Los datos y las
operaciones se conservan. Para revocar la autorización en Telegram usa su gestión
de dispositivos/sesiones; desconectar localmente no equivale a esa revocación.
