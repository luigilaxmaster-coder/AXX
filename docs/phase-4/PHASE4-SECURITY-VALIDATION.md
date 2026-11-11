# Validación de seguridad · fase 4

Código evaluado en 7eb0f792b5db127b843f3e4b18c047daea8a3481.

## Autoridad del canal

| Tramo | Identidad y control |
|---|---|
| Daemon, bot y worker Telegram | Descriptor DPAPI independiente. Bearer de alcance Telegram generado en cada arranque. HTTP de loopback con rutas acotadas por método. Se comprueba el vínculo entre cuenta activa, propietario, conversación y operación del inbox durable. |
| Android a PC | TLS y credencial individual de /v1. El gateway mantiene el bearer móvil dentro del proceso y la asociación de Work en la base local. El botón de aprobación en la PC usa la ruta de escritorio después de comprobar operación, parámetros y concesión. |
| Chat con herramientas | El backend vincula el contexto opaco del chat con la memoria vigente. El modelo aporta únicamente nombre y argumentos estructurados. Connect deriva el canal model y CommandService aplica el modo y la categoría de acción. |
| ActionExecutor | Revisión antes de efectos, comprobación de parámetros y permiso vigente en el despacho. Una denegación confirmada queda blocked y postconditions_passed=false. Las operaciones interrumpidas sin evidencia conservan estado incierto. |

## Evidencia

- La prueba HTTP Telegram pasa por CoreClient, TelegramService, el servidor real de loopback y CommandService. Usa identidad sintética y descriptor de prueba. Comprueba que una cabecera desktop y un campo channel carecen de autoridad, el bearer anterior recibe 401, la nueva cuenta no puede consultar ni cancelar el recibo previo y revocar el permiso impide llamar al ejecutor.
- El test Android levanta el gateway TLS, prepara y verifica telemetría, conserva el mismo recibo en reintento y solicita revisión en PC para escritura. La suite móvil prueba un segundo dispositivo contra el recibo terminal del primero.
- La suite del callback repitió diez veces el rechazo de tokens y orígenes inválidos y conservó la autorización válida. El adaptador de chat rechaza shell, campos de autorización, un archivo privado fuera del catálogo, argumentos JSON duplicados y rutas de escape. La cancelación de la escritura pendiente conserva el archivo ausente.
- La mutación de revocación comprueba que sustituir commands_authorized por una función que siempre concede provoca la llegada al límite del ejecutor y falla la expectativa blocked. Se interceptó el ejecutor para evitar ejecutar el comando durante la mutación.

Computer Use conserva su autorización explícita independiente. El modelo puede ejecutar una admisión efímera válida de esa sesión y el ejecutor vuelve a verificar conversación, proceso, cuenta, vencimiento, revocación y consumo único del ticket. Los tickets inventados y revocados fallan sin capturar ni introducir datos. La excepción se limita al canal de modelo y a los dos adaptadores internos de Computer Use.

## Archivos y revisión

La confirmación de Unrestricted habilita escritura de texto de hasta 65536 bytes en un destino relativo nuevo dentro de artifacts. Se rechazan rutas absolutas, escapes, flujos alternos, nombres reservados y colisiones. El ejecutor de Windows vuelve a comprobar el destino y verifica el hash del archivo. La lectura de archivos sensibles sigue su validación de ruta y autorización.

La descarga PDF sigue ligada al navegador y documento observados, nombre y URL del enlace y ruta nueva en el workspace. El adaptador rechaza redirecciones, acota recursos, inspecciona estructura y páginas y verifica hash. Crear una copia PDF mediante Office sigue la ruta tipada y revisada con selección de origen. La descarga y la exportación de PDF, shell, ejecución de procesos y acciones de escritura propuestas por el chat de herramientas requieren revisión individual. Computer Use mantiene su sesión separada con permiso explícito y límites propios. Ampliar esa autonomía exige autorización del propietario. Los valores Unrestricted de esquemas antiguos siguen requiriendo la confirmación del propietario al incorporarse a esta política.

Estado MANUAL_REQUIRED para recepción y confirmación de una acción desde una cuenta Telegram real y desde un Android físico. Las credenciales de prueba de loopback solo prueban el contrato local.
