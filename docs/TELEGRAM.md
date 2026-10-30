# Usar Axx desde Telegram

Esta guía describe la integración en el código actual. Tener la cuenta guardada
no demuestra que el canal o las llamadas funcionen: cada capacidad debe comprobarse
por separado en la versión instalada. Axx debe estar abierto en la PC, que también
debe permanecer encendida y conectada a Internet.

## Conectar y usar

1. En Axx en la PC, abre **Herramientas → Asistencia → Telegram**. Si tu cuenta
   ya está guardada en esta PC, no necesitas repetir el primer QR.
2. Si aún no está guardada, pulsa **Conectar con QR**. En la cuenta de Telegram
   dedicada a Axx, abre **Ajustes → Dispositivos → Vincular dispositivo de
   escritorio** y escanea el **QR 1**. Si Telegram pide tu contraseña de
   verificación en dos pasos, introdúcela en la ventana de Axx de la PC.
3. Elige lo que permites, activa Telegram y pulsa **Guardar permisos**.
   Cambiar permisos después de vincular el teléfono requiere escanear otra vez el QR 2.
4. Para abrir la Mini App en tu teléfono, pulsa **Mostrar QR para teléfono**.
   Escanea el **QR 2** con la cámara, toca **Iniciar** en el bot y después
   **Abrir Axx**. Si el QR vence, genera otro. Esta etapa requiere tener el bot
   y la dirección HTTPS de la Mini App configurados.
5. Usa **Comprobar conexión** para consultar si el proceso está activo.
   Eso no sustituye una prueba real enviando un mensaje.
6. En la Mini App puedes consultar el estado y la actividad disponible. Los
   comandos y acciones mantienen los permisos y las aprobaciones de la PC.
   Si un envío queda pendiente, consulta su estado antes de reintentarlo.

En **Inicio**, el resumen corresponde a las últimas 30 solicitudes recibidas.
**Revisar pendientes** abre las órdenes que tienen una revisión disponible.
En **Actividad**, puedes filtrar por pendientes, en curso o finalizadas; abre el
resultado para comprobar si se verificó. Filtrar no ejecuta ninguna acción.
Los ejemplos de **Chat** solo rellenan el borrador: tú decides cuándo enviarlo.
En **Comandos**, busca por nombre o filtra por categoría. **Escribir** lleva la
frase al borrador sin enviarla. También puedes escribir `/comandos` o `ver comandos`
en el bot para consultar la lista y después pedir, por ejemplo, `abre calculadora`,
`mis ventanas` o `cierra Spotify`. No necesitas copiar identificadores ni JSON.
La lista se obtiene del catálogo ejecutable de tu PC; un ejemplo no demuestra que
su acción ya se haya ejecutado. Las tarjetas indican si falta un permiso y el
cierre necesita que la ventana esté abierta.
Si se pierde la conexión, la app marca los datos anteriores como desactualizados
y conserva el borrador y el identificador de cualquier envío pendiente.
Si se retira el acceso, limpia los datos privados visibles y descarta las
respuestas anteriores que lleguen tarde. Una respuesta atrasada tampoco borra
un borrador ni vuelve a abrir una revisión cerrada. Los envíos pendientes se
consultan antes de reintentarlos; no se repiten automáticamente.

Si es la primera configuración y faltan datos de aplicación o del bot, abre
**Opciones avanzadas** en ese mismo panel. Los datos se introducen solo en la PC:
`api_id`, `api_hash`, ID numérico de tu cuenta personal, token del bot y dirección
HTTPS de la Mini App. La cuenta personal autorizada debe ser distinta de la
cuenta dedicada a Axx. Dejar vacío el token al editar conserva el token guardado.
No pegues códigos, contraseñas ni tokens en el chat.

Para detener el acceso, pulsa **Pausar**. Puedes reanudarlo después. Para retirar
el acceso de un teléfono, usa **Desvincular** junto a él; **Desvincular todos**
revoca las vinculaciones de la Mini App. Estas acciones conservan la cuenta y
los datos guardados en la PC y no deshacen una acción ya realizada. Revocar una
sesión de Telegram desde sus ajustes de dispositivos es una acción independiente.

## Confirmar una orden desde Telegram

Esta ampliación requiere una versión que la incluya. En la PC, activa **Acciones
en esta PC** y guarda los permisos. Después marca **Confirmar comandos desde
Telegram** y pulsa **Guardar confirmación remota**. Es un permiso nuevo que
empieza desactivado; los permisos anteriores no se amplían automáticamente.

1. Envía una orden compatible, por ejemplo `abre calculadora` o
   `información del sistema`.
2. Revisa la tarjeta: muestra la acción, los parámetros completos, el riesgo y
   la hora de vencimiento. Abrir la tarjeta todavía no ejecuta la orden.
3. Pulsa **Aprobar una vez** para esa orden o **Denegar**. En la Mini App, también
   puedes encontrarla en **Actividad → Revisar orden**.
4. Consulta el resultado. Solo se muestra como comprobado cuando el ejecutor
   devuelve un recibo con su verificación.

La confirmación dura como máximo dos minutos y se vincula a una operación,
propietario y revisión exactos. Una nueva revisión invalida el botón anterior;
reiniciar Axx, cambiar permisos o retirar la autorización también lo invalida.
Si se pierde una respuesta, consulta Actividad: la orden no se vuelve a ejecutar
automáticamente. **Revisar de nuevo** sirve para leer la orden y obtener otro
botón, siempre que todavía esté pendiente y permitida.

El alcance incluye consultas, apertura de aplicaciones o páginas y el cierre de
una ventana observada. Por ejemplo, `cierra Spotify` muestra el título, la ventana
y su proceso antes de decidir. El cierre verifica de nuevo el título, el proceso
y su momento de inicio para detectar si la aplicación se reinició;
si cambiaron, envía una nueva orden. No fuerza el cierre ni responde a avisos de
cambios sin guardar. Una orden antigua sin título o instancia del proceso sigue
requiriendo revisión en la PC.
Shell, escrituras, controles
sensibles, comandos generados y pasos reservados de planes mantienen la aprobación
en la PC. No se cambia el proveedor de conversación para aprobar una orden.
Con el permiso nuevo activo, las órdenes compatibles también funcionan con la
conversación desactivada. Escribir solamente «sí» no confirma ninguna operación.

La política se guarda aparte en `telegram/confirmations.dpapi`, sin reescribir
credenciales. El registro de confirmaciones conserva solo el hash del desafío;
el núcleo vuelve a verificar el plan y el permiso justo antes del despacho.

## Lo que está pendiente

- **Llamadas privadas:** todavía no están operativas. Las pruebas recibieron audio,
  pero no confirmaron que el teléfono escuchara el audio saliente; una prueba de
  archivo terminó con un tiempo de espera en la limpieza. No se ha comprobado una
  conversación de voz bidireccional ni su interrupción. El canal de mensajes puede
  rechazar una llamada y avisar al propietario de que está en reparación.
- **Notas de voz y archivos:** pendientes de implementación y aceptación. El
  canal responde que los adjuntos aún no están habilitados.
- **Chat con IA:** se conserva el proveedor seleccionado en el escritorio. Si
  su acceso remoto no está disponible o no ha pasado las comprobaciones de
  aislamiento, la conversación queda bloqueada; Axx no cambia de proveedor ni
  activa uno de pago por su cuenta.
- **Acciones en la PC:** utilizan los comandos, permisos y aprobaciones existentes.
  Una función configurada o un permiso concedido no prueban que el resultado de
  una acción haya sido verificado.

## Referencia técnica

### Órdenes compuestas y enlaces

Estas mejoras están en la fuente posterior a Windows 0.22.32; el instalador de
esa versión no las contiene. Requieren la siguiente entrega instalada y su
aceptación nativa, además de las pruebas de fuente.

Puedes escribir `abre calculadora y abre bloc de notas` o `abre youtube y pon faint de linkin park`.
El bot y la Mini App preparan el primer paso; cada paso requiere su propia tarjeta de
aprobación. El siguiente solo se prepara tras un recibo comprobado del anterior.
Denegar, un resultado incierto, un cambio de permisos o un reinicio detienen la
continuación. Consulta Actividad antes de repetir una petición tras desconectarte.
No se reanudan secuencias automáticamente.

Denegar detiene la secuencia incluso si el paso anterior ya terminó. Detener o
reiniciar elimina los parámetros pendientes de la secuencia. El olvido coordinado
depura su payload, las respuestas operativas y las confirmaciones de los contextos
afectados; conserva los IDs de conciliación y las otras sesiones. Si el almacén de
Telegram falla, el olvido permanece incompleto y se reintenta al iniciar. Una
preparación tardía no puede restaurar una secuencia olvidada. El historial manual
de conversaciones mantiene el contrato de memoria existente; esto no borra copias
externas de Telegram.

Un enlace seguido de `ponme este video` prepara la apertura de esa URL exacta.
Abrir una URL no demuestra reproducción. La reproducción por búsqueda usa el adaptador
existente de YouTube para Chrome, que debe observar el título y el avance del reproductor;
si no puede comprobarlos, el resultado permanece sin confirmar. No se habilitan scripts
ni controles arbitrarios del navegador con esta aprobación.

Si la Mini App no abre, comprueba primero que Tailscale esté conectado y que Funnel
publique exclusivamente la fachada local en `127.0.0.1:6451`. Una respuesta local correcta
no demuestra que la dirección HTTPS sea accesible. El chat con IA conserva por separado
el control de aislamiento del proveedor seleccionado.

La cuenta de usuario de Telegram y el bot auxiliar son canales distintos. La
sesión de usuario se protege con DPAPI en `%LOCALAPPDATA%\Axx\telegram` y el
trabajador admite únicamente mensajes privados del propietario autorizado. La
bandeja conserva identificadores de operación; no reejecuta automáticamente un
despacho o una entrega de resultado inciertos. Las acciones sensibles continúan
requiriendo aprobación en la PC.

La Mini App requiere una dirección HTTPS configurada para el bot. La fachada se
mantiene separada del backend nativo y verifica la identidad firmada por Telegram;
el QR de vinculación es de un solo uso y caduca. No expongas el backend nativo
completo a Internet. La conexión del teléfono o del bot no demuestra por sí sola
que la conversación, los archivos o las llamadas funcionen.

Las pruebas automatizadas y las pruebas reales tienen alcances diferentes. La
entrega de una versión de escritorio requiere además seguir `docs/RELEASING.md`
y el protocolo de compatibilidad móvil del proyecto. No publiques evidencias
que contengan credenciales, códigos, muestras de voz o estado privado.
