# Micrófono remoto — contrato de integración

Estado: implementación inicial; aceptación física completa todavía pendiente. La compilación no acredita la función.

## Recorrido

`Ctrl+Alt+Shift+V` usa `RegisterHotKey` en Windows, sin interceptar el ratón ni adquirir un lease de entrada. El evento `axx-remote-voice-toggle` llega al coordinador del escritorio. Primera pulsación: sesión nueva con UUID. Segunda: solicitud de parada de esa sesión.

Android consulta por el transporte HTTPS autenticado las órdenes de la sesión. Solo inicia MediaRecorder si Axx Mobile está visible, la pantalla está desbloqueada y RECORD_AUDIO ya fue concedido mediante el diálogo de Android. El indicador muestra captura y nivel real. No hay servicio de grabación en segundo plano.

El audio AAC/MP4 se guarda temporalmente en el almacenamiento privado del teléfono. Se envía por el mismo transporte con pin del certificado y permiso `voice`. Se conserva hasta que el PC confirme una transcripción persistida o la cancelación. Hay una sola captura retenida. El límite configurable es de 5–55 segundos y 1.4 MiB; se detiene tras 8 segundos sin contacto autenticado, al salir de la app, bloquearse o perder permiso.

El gateway llama a `/axx-api/speech/transcribe`: la instancia existente de `OfflineTranscriptionService`, Whisper tiny local, CPU. Este servicio **no ofrece parciales en directo**. El texto provisional no tiene ruta de ejecución. La salida final queda en `mobile_voice_sessions` antes de que pueda ser confirmada.

En modo revisión, se corrige y confirma desde la PC. Manos libres requiere el alcance `tools.control`, otorgado expresamente desde los ajustes de Axx. Las comprobaciones se repiten al admitir la orden, incluyendo revocación y conversación activa.

El escritorio reclama la sesión una sola vez antes de llamar a `Axx.companion.send`. Esa función y sus extensiones siguen siendo los propietarios de interpretación, conversación, herramientas, acciones locales y confirmaciones sensibles. El móvil nunca ejecuta una transcripción directamente.

## Estados y recuperación

`requested → recording → stopping → awaiting_audio → transcribing → review/ready → dispatching → completed`

Estados alternativos: `empty`, `failed`, `cancelled`, `interrupted`, `outcome_unknown`.

- El acuse `recording` procede de MediaRecorder, no del envío del atajo.
- El mismo audio y sesión conservan hash y resultado; un audio distinto bajo el mismo ID es rechazado.
- Perder contacto durante captura fuerza revisión en recuperación.
- Reiniciar durante despacho marca `outcome_unknown` y no vuelve a llamar al motor.
- Un recibo de resultado guardado por el escritorio puede recuperarse sin repetir el comando.
- Cancelar una captura no cancela otras sesiones de Whisper/voz del PC. Una operación ya admitida se detiene mediante sus controles existentes.

## Rutas

| Dueño | Ruta | Función |
|---|---|---|
| Escritorio autenticado | GET `/axx-api/mobile/voice/status` | Clientes y sesión actual |
| Escritorio autenticado | POST `/axx-api/mobile/voice/toggle` | Crear sesión o pedir parada |
| Escritorio autenticado | POST `/axx-api/mobile/voice/confirm` | Confirmar texto corregido |
| Escritorio autenticado | POST `/axx-api/mobile/voice/claim` | Admitir despacho una sola vez |
| Escritorio autenticado | POST `/axx-api/mobile/voice/finish` | Persistir resultado real |
| Escritorio autenticado | POST `/axx-api/mobile/voice/cancel` | Cancelar sesión anterior al despacho |
| Escritorio autenticado | POST `/axx-api/mobile/tools-permission` | Conceder/revocar `tools.control` |
| Teléfono, alcance voice | POST `/v1/voice/poll` | Presencia, permiso, acuse de captura y orden vigente |
| Teléfono, alcance voice | POST `/v1/voice/audio` | Audio final vinculado a sesión/dispositivo |
| Teléfono, alcance voice | POST `/v1/voice/cancel` | Cancelar su propia sesión |

## Aceptación que debe registrarse

1. Atajo global → acuse nativo de micrófono, con app visible y permiso concedido, sin tocar el teléfono.
2. Voz física reconocida por Whisper y resultado real del motor de Axx en ambos equipos.
3. Segunda pulsación finaliza captura y transcripción.
4. Denegación/revocación, app en segundo plano, timeout y desconexión detienen o impiden captura.
5. Reconexión, doble envío y reinicio no duplican órdenes.
6. Confirmación de texto y permisos de manos libres.
7. Independencia de voz y trackpad: la arquitectura está separada; la prueba conjunta requiere el trackpad de MO-4, todavía pendiente.

Tests con backend de prueba no acreditan reconocimiento físico. El atajo inicial es fijo; el tiempo y modo se configuran desde los ajustes de Axx.
