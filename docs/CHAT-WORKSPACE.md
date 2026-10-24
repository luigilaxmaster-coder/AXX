# Conversaciones de Axx

El panel **Chats y grupos** permite crear, buscar por título, abrir, renombrar,
archivar, exportar y eliminar conversaciones. **Reiniciar contexto** conserva el
hilo anterior y abre uno nuevo dentro del mismo grupo. Cada chat tiene un borrador,
adjunto y sus propias identidades de Connect y sincronización móvil.

## Modos de comandos

El modo inicial es **Preguntar**. **Auto seguro** permite ejecutar acciones del
catálogo que no requieren aprobación según su política. Escribir archivos, enviar,
borrar o ejecutar comandos sensibles sigue requiriendo aprobación. El servidor
consulta el modo guardado del chat y no acepta que la petición lo rebaje.

La tarjeta de operación muestra parámetros y permite revisar, aprobar, cancelar y
consultar el resultado. Una segunda acción espera a que termine o se cancele la
pendiente. Las preguntas normales pueden continuar. Un resultado incierto no se
repite automáticamente.

## Contexto y datos

Los grupos comparten únicamente las notas guardadas explícitamente mediante
**Contexto común** o **Guardar en contexto del grupo**. Los mensajes privados de
otros chats no se incluyen. Cambiar o quitar contexto renueva la identidad de
Connect para no reutilizar instrucciones retiradas de un hilo del proveedor.

**Contexto de este chat** permite además conectar hasta tres hilos anteriores.
Cada conexión copia un extracto de hasta 4.000 caracteres de mensajes terminados,
con una vista previa del contenido. No copia borradores, notas del grupo del
origen ni conexiones indirectas. **Actualizar extracto** incorpora cambios
posteriores solo cuando el usuario lo decide; **Desconectar** deja de enviarlo.
**Nuevo chat con contexto de este hilo** combina crear y vincular. Los mensajes
copiados conservan su fecha original de vencimiento; vincular no prolonga 90 días.
Eliminar el origen retira sus vínculos en la siguiente consulta.

El perfil global del agente es una preferencia persistente independiente del
historial. Se administra en **Personalizar agente**, y se aplica a las respuestas
nuevas. Cambiarlo también renueva los IDs de Connect. Véase
[Personalización y comandos](COMMAND-EXTENSIONS.md).

El almacenamiento de Axx es SQLite, en el directorio de datos existente de la
aplicación. Los mensajes, adjuntos y notas comunes vencen a los 90 días. Las
exportaciones externas y los datos que ya recibió un proveedor externo están
sujetos a sus propios controles; Axx no declara borrarlos remotamente.

La migración importa el hilo anterior por lotes idempotentes. El historial de
`localStorage` solo se retira después de confirmar su guardado en el backend.
Las preferencias y otros datos de Companion conservan su propietario existente.

## Contratos locales

Todas las rutas requieren autenticación del host nativo:

- `GET /axx-api/chat/conversations`: índice de chats, grupos y modo predeterminado.
- `GET /axx-api/chat/conversations?id=...`: conversación, mensajes y contexto vigente.
- `POST /axx-api/chat/{migrate,create,save,update,delete}`: ciclo de vida del chat.
- `POST /axx-api/chat/{group,group_update,group_delete,context}`: grupos y notas.
- `POST /axx-api/chat/{default,forget}`: modo inicial y eliminación del historial guardado.
- `POST /axx-api/chat/{link,unlink}`: vincular extracto o retirarlo.
- `GET/POST /axx-api/chat/profile`: leer/guardar configuración del agente.
- `GET /axx-api/chat/operations`: recuperar operaciones registradas en ambos ejecutores.

## Apariencia y voz

El tema claro u oscuro y los colores de fondo, texto e iconos se ajustan desde
**Sistema y datos**. Cada tema conserva su combinación. Hay tipografía y tamaño
de texto; el indicador de contraste avisa cuando una combinación dificulta la
lectura. Restablecer devuelve la combinación de fábrica. El aspecto 3D conserva
sus controles y almacenamiento propios. Cada herramienta guarda su propio tamaño.

La lectura conserva puntuación para respetar las frases. Las voces MOSS preparan
cada frase antes de reproducirla, evitando vaciar el búfer entre pequeños paquetes
PCM. La siguiente frase se prepara durante la reproducción cuando hay capacidad.
La latencia inicial depende del modelo y del equipo; este cambio no garantiza
inferencia más rápida que tiempo real. Pausa, cancelación y selección de voz se
mantienen. Las muestras personales se quedan en el equipo.

### Conversación continua

Junto al cuadro de mensaje, un clic en **Voz en vivo** activa turnos de voz. Whisper
transcribe localmente; el texto utiliza el modelo, perfil y contexto de ese chat.
La pausa de cierre puede ser de 0,7, 0,9 o 1,5 segundos. **Responder ahora** termina
la captura; **Interrumpir y hablar** cancela la respuesta y vuelve a escuchar;
**Terminar** libera el micrófono y la salida. Cambiar de chat, cerrar el panel o
ocultar la ventana termina la sesión. Nunca arranca sola al abrir Axx.

El panel distingue preparación, escucha, transcripción y respuesta. Espere a
**Te escucho** antes de hablar: el detector mide primero el nivel de fondo. La
barra de entrada muestra si llega sonido y si se ha detectado una frase. En
**Voz, ritmo y privacidad → Micrófono** puede elegir la entrada de Windows o un
dispositivo concreto; si ese dispositivo falta, se informa sin cambiarlo por otro.
Cambiar el foco a otra aplicación conserva una sesión visible; cerrar u ocultar
el chat continúa deteniéndola. **Responder ahora** permite cerrar la frase sin
esperar al detector de pausa.

El micrófono se pausa durante la respuesta para evitar realimentación. El modelo
puede empezar a producir frases antes de terminar el texto; cada frase de voz se
reproduce completa, una sola vez. No es audio simultáneo de doble dirección.
El selector permite elegir Windows para menor espera o las voces naturales MOSS.
No se sustituye el proveedor ni el modelo seleccionado. La interfaz muestra el
tiempo medido de transcripción y de texto reconocido hasta la primera voz.

**Modelo para voz** conserva por defecto el del chat. Permite elegir otro modelo
detectado en esa misma conexión; la preferencia se guarda sin cambiar el modelo
principal. Si deja de estar disponible, seleccione **Mismo del chat** o un modelo
de la lista. La aparición en el catálogo no garantiza su velocidad ni una
inferencia exitosa; la solicitud conserva la validación del backend.

`commands/prepare` admite `conversation_id` y `command_mode`; el modo persistido
tiene precedencia. Los registros conservan la conversación de origen y los IDs
de operación para recuperar resultados sin repetir efectos.

## Comprobaciones

```powershell
python -m unittest backend.tests.test_chat_store backend.tests.test_commands_http backend.tests.test_command_library backend.connect.tests.test_service -q
node scripts/test-chat-workspace.cjs
node scripts/test-installed-chat.cjs
node scripts/test-installed-chat-focus.cjs
node scripts/test-installed-chat-layout.cjs
node scripts/test-installed-surfaces.cjs
node scripts/test-installed-appearance.cjs
node scripts/test-installed-speech.cjs
node scripts/test-installed-live.cjs
```

La prueba de navegador usa SQLite y HTTP reales con un Companion mínimo. Las
pruebas `test-installed-*` necesitan el ejecutable instalado con CDP temporal
en loopback 9224; usan datos de aceptación y restauran las preferencias previas.
Ejecutarlas de una en una y volver al arranque normal sin CDP al finalizar.

La prueba de voz continua usa una pregunta sintetizada localmente a volumen bajo
mediante un MediaStream, MediaRecorder real, detección de pausa y Whisper, seguida
del modelo seleccionado y la salida de voz instalada. La disponibilidad
del micrófono se comprueba por separado; no equivale a probar una frase hablada
por una persona en ese ambiente acústico.
