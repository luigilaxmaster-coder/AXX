# Catálogo de instrucciones por aplicación

El catálogo contiene 48 perfiles y 160 operaciones descritas. La presencia de
un perfil no demuestra que la aplicación esté instalada, conectada o validada.
El inventario procede de Get-StartApps y conserva sus nombres y AppID observados.

## Qué puede ejecutarse

- Abrir una app instalada usa su AppID exacto. Enfocar, listar ventanas,
  inspeccionar controles y cerrar son operaciones universales existentes.
- `navigate` admite una URL http/https explícita y una barra de direcciones
  única recién observada. Una lectura explícita del control comprueba la dirección
  visible antes y después de Enter; la inspección general conserva sólo metadatos.
  Se admite exclusivamente que el navegador oculte el prefijo `http://` o
  `https://`; autoridad, puerto, ruta, consulta y fragmento deben coincidir.
  Cuando el esquema está oculto, `scheme_verified` es `false`. El resultado siempre
  conserva `content_verified:false`: la barra no prueba TLS ni que la página haya
  cargado. Una petición recibida por un servidor de prueba u otra evidencia de
  contenido debe comprobarse de forma independiente.
- `invoke` usa un nombre UIA exacto visible y único. Una pulsación entregada
  exige comprobar el efecto en la aplicación; no certifica recepción de mensajes.
- `shortcut` se limita aquí a Ctrl+T en Chrome, Edge y Firefox, contrastado con
  sus documentos oficiales. La entrega del atajo no prueba que apareció una pestaña.
- `guide` sólo muestra requisitos y pasos de revisión. No genera permisos,
  no ejecuta un flujo y no se convierte en una acción por estar descrita.

En esta revisión hay 5 operaciones de navegación, 11 de control observado,
3 atajos documentados y 141 guías. Son estados documentales y de preparación;
las pruebas nativas de cada aplicación se acreditan con recibos separados.

## Selección y límites

La selección admite un ID de perfil, título, alias o nombre de proceso
documentado exactos, normalizando mayúsculas, espacios y tildes. Para abrir
también admite cualquier nombre completo o AppID exacto del inventario, aunque
no tenga perfil. No se hace selección aproximada ni se inventan rutas de ejecutables.
Si hay varias instalaciones candidatas se debe elegir el AppID observado.

Los nombres de procesos y selectores son metadatos condicionales. La entrada
requiere una ventana identificada, foco y controles frescos; una app elevada,
un escritorio seguro, una versión distinta o una UI inaccesible pueden impedirla.

Telegram, WhatsApp, Slack, Signal, Teams y el correo requieren autorización
concreta del destinatario y contenido antes de enviar. Las sesiones remotas,
credenciales y transferencias de TeamViewer permanecen como guías. El perfil
no habilita acceso desatendido ni permite copiar claves a comandos o registros.

## Perfiles

| Aplicación | Operaciones descritas | Requisitos y límites |
|---|---|---|
| **Google Chrome** (`chrome`) | Navegar a una URL indicada [navigate]; Abrir una pestaña nueva [shortcut]; Descargar y comprobar PDF [guide]; Revisar una página [guide] | Requiere una instalación observada o una ventana identificada de este navegador. La navegación no concede acceso a contraseñas, perfiles personales ni sesiones de otros usuarios. Una barra no expuesta a UIA debe causar abstención; descargas verificadas usan el adaptador CDP. Ctrl+T confirmado por documentación oficial: https://support.google.com/chrome/answer/157179 |
| **Microsoft Edge** (`edge`) | Navegar a una URL indicada [navigate]; Abrir una pestaña nueva [shortcut]; Descargar y comprobar PDF [guide]; Revisar una página [guide] | Requiere una instalación observada o una ventana identificada de este navegador. La navegación no concede acceso a contraseñas, perfiles personales ni sesiones de otros usuarios. Una barra no expuesta a UIA debe causar abstención; descargas verificadas usan el adaptador CDP. Ctrl+T confirmado por documentación oficial: https://support.microsoft.com/en-us/edge/keyboard-shortcuts-in-microsoft-edge |
| **Mozilla Firefox** (`firefox`) | Navegar a una URL indicada [navigate]; Abrir una pestaña nueva [shortcut]; Descargar y comprobar PDF [guide]; Revisar una página [guide] | Requiere una instalación observada o una ventana identificada de este navegador. La navegación no concede acceso a contraseñas, perfiles personales ni sesiones de otros usuarios. Una barra no expuesta a UIA debe causar abstención; descargas verificadas usan el adaptador CDP. Ctrl+T confirmado por documentación oficial: https://support.mozilla.org/en-US/kb/tabs-organize-websites-single-window |
| **Brave** (`brave`) | Navegar a una URL indicada [navigate]; Descargar y comprobar PDF [guide]; Revisar una página [guide] | Requiere una instalación observada o una ventana identificada de este navegador. La navegación no concede acceso a contraseñas, perfiles personales ni sesiones de otros usuarios. Una barra no expuesta a UIA debe causar abstención; descargas verificadas usan el adaptador CDP. Los atajos específicos permanecen como guía hasta contrastarlos con documentación oficial. |
| **Opera** (`opera`) | Navegar a una URL indicada [navigate]; Descargar y comprobar PDF [guide]; Revisar una página [guide] | Requiere una instalación observada o una ventana identificada de este navegador. La navegación no concede acceso a contraseñas, perfiles personales ni sesiones de otros usuarios. Una barra no expuesta a UIA debe causar abstención; descargas verificadas usan el adaptador CDP. Los atajos específicos permanecen como guía hasta contrastarlos con documentación oficial. |
| **Telegram Desktop** (`telegram`) | Abrir ajustes locales [invoke]; Buscar un chat [guide]; Enviar un mensaje revisado [guide]; Compartir un archivo revisado [guide] | La instalación no acredita sesión iniciada ni acceso a conversaciones. Buscar, preparar texto y enviarlo son operaciones distintas. No extraer códigos, sesiones, contactos ni archivos de chats por estar el perfil descrito. |
| **TeamViewer** (`teamviewer`) | Preparar conexión remota [guide]; Iniciar una sesión autorizada [guide]; Transferir archivos con consentimiento [guide]; Gestionar portapapeles remoto [guide] | El perfil no habilita acceso desatendido ni acepta sesiones automáticamente. No leer, introducir, copiar ni enviar credenciales de TeamViewer como efecto de un comando genérico. La conexión y transferencia remotas permanecen documentales hasta disponer de un flujo aprobado y verificable. |
| **WhatsApp** (`whatsapp`) | Abrir configuración [invoke]; Buscar conversación [guide]; Enviar mensaje revisado [guide]; Iniciar llamada autorizada [guide] | Requiere cuenta vinculada por el propietario. No vincular teléfonos, exportar contactos ni enviar adjuntos automáticamente. La entrega de una pulsación no demuestra que el mensaje fue recibido. |
| **Discord** (`discord`) | Abrir ajustes de usuario [invoke]; Seleccionar canal [guide]; Publicar mensaje revisado [guide]; Entrar en voz con autorización [guide] | La presencia de Discord no acredita sesión ni membresía en servidores. No aceptar invitaciones, modificar roles ni compartir pantalla por una guía. Revisar el destino visible antes de cualquier envío. |
| **Slack** (`slack`) | Buscar en un espacio de trabajo [guide]; Abrir un canal [guide]; Enviar mensaje revisado [guide]; Preparar conversación de audio [guide] | Los espacios de trabajo y scopes deben autorizarse individualmente. No instalar apps, ampliar permisos o enviar mensajes a canales por estar documentados. La UIA puede omitir parte del historial; no presentar una lectura parcial como conversación completa. |
| **Microsoft Teams** (`teams`) | Abrir chat identificado [guide]; Enviar mensaje revisado [guide]; Preparar reunión [guide]; Compartir una ventana autorizada [guide] | Requiere sesión y políticas del tenant compatibles. No compartir escritorio completo ni aceptar permisos de dispositivo automáticamente. Teams clásico y nuevo pueden exponer controles distintos. |
| **Zoom Workplace** (`zoom`) | Preparar acceso a reunión [guide]; Revisar audio y video [guide]; Compartir una ventana [guide]; Preparar grabación autorizada [guide] | Instalación y enlace no acreditan acceso a una reunión. No iniciar llamadas, grabaciones ni captura audiovisual sólo por una guía. Las políticas de reuniones pueden exigir intervención del anfitrión. |
| **Microsoft Outlook** (`outlook`) | Buscar correo [guide]; Preparar borrador [guide]; Enviar correo autorizado [guide]; Preparar un evento [guide] | Las versiones clásica y nueva tienen interfaces y conexiones distintas. No enviar, reenviar ni borrar correo por inferir intención desde el catálogo. Usar conectores oficiales cuando proporcionen una operación verificable. |
| **Mozilla Thunderbird** (`thunderbird`) | Buscar mensajes [guide]; Preparar borrador [guide]; Enviar correo revisado [guide] | La configuración de una cuenta no demuestra que el servidor esté accesible. No modificar certificados, contraseñas o políticas de correo automáticamente. Conservar borradores y originales hasta comprobar el resultado. |
| **Signal** (`signal`) | Buscar conversación [guide]; Preparar envío revisado [guide]; Revisar adjuntos [guide] | Requiere vinculación autorizada por el propietario. No exportar mensajes, claves o contactos por estar la app instalada. Verificar destinatario y estado de envío de manera independiente. |
| **Spotify** (`spotify`) | Reproducir [invoke]; Pausar [invoke]; Pista siguiente [invoke]; Pista anterior [invoke]; Buscar música [guide] | La reproducción exige una sesión y dispositivo de salida utilizables. Los comandos multimedia sólo se consideran efectivos tras comprobar estado o metadatos. No cambiar cuenta, dispositivo de reproducción, suscripción ni compras. |
| **VLC media player** (`vlc`) | Reproducir medio abierto [invoke]; Pausar medio abierto [invoke]; Abrir un medio local [guide]; Preparar conversión [guide] | Debe existir una ventana y un medio identificado. La salida de audio y decodificación completa requieren verificación propia. No asumir permisos para acceder a redes, cámaras o discos por abrir VLC. |
| **OBS Studio** (`obs`) | Consultar estado OBS [guide]; Seleccionar escena exacta [guide]; Preparar grabación [guide]; Detener y comprobar grabación [guide] | Requiere OBS instalado y WebSocket autenticado configurado por el usuario. Este perfil no habilita el servidor OBS ni valida una grabación nativa. Una cancelación de Axx no detiene por sí sola una grabación ya iniciada. |
| **Windows Media Player clásico** (`windows_media_player`) | Reproducir [invoke]; Pausar [invoke]; Revisar biblioteca [guide] | Se refiere al reproductor clásico wmplayer, no certifica la nueva aplicación multimedia. Confirmar archivo y dispositivo de salida antes de declarar reproducción. No copiar discos ni realizar compras automáticamente. |
| **Audacity** (`audacity`) | Importar audio local [guide]; Editar selección [guide]; Exportar copia [guide] | No activar grabación de micrófono o loopback sin autorización. Las pruebas de ffprobe no certifican calidad auditiva ni edición semántica. Conservar fuente y proyecto antes de exportar. |
| **Microsoft Word** (`word`) | Editar una copia de DOCX [guide]; Exportar y comprobar PDF [guide]; Revisar documento [guide] | Requiere Word instalado; el flujo de copia privada exige Word cerrado. No habilitar macros ni vínculos externos de documentos. La presencia de texto en PDF no demuestra composición visual correcta. |
| **Microsoft Excel** (`excel`) | Importar CSV a una copia XLSX [guide]; Leer rango identificado [guide]; Preparar fórmula [guide] | Instalación no acredita acceso a un libro ni permisos de archivo. No ejecutar macros, consultas externas o cambios masivos implícitos. Distinguir fórmula escrita, recálculo y resultado comprobado. |
| **Microsoft PowerPoint** (`powerpoint`) | Cambiar texto exacto en copia [guide]; Exportar copia y PDF [guide]; Revisar diapositivas [guide] | El flujo privado requiere PowerPoint cerrado. No admitir macros, objetos incrustados peligrosos ni relaciones externas. La verificación textual no certifica calidad gráfica de todas las diapositivas. |
| **Microsoft OneNote** (`onenote`) | Elegir bloc y sección [guide]; Preparar una nota [guide]; Preparar exportación [guide] | Requiere cuenta y bloc accesibles. No compartir blocs ni cambiar permisos por una guía. Distinguir guardado local, sincronización y disponibilidad en otros dispositivos. |
| **Adobe Acrobat / Reader** (`acrobat`) | Revisar PDF [guide]; Preparar anotación [guide]; Preparar exportación [guide] | Reader y Acrobat pueden tener capacidades distintas según licencia. No firmar, enviar formularios ni aceptar acuerdos automáticamente. No eliminar seguridad de un documento ni ignorar avisos de certificados. |
| **LibreOffice** (`libreoffice`) | Trabajar sobre copia [guide]; Preparar exportación PDF [guide]; Revisar hoja de cálculo [guide] | Writer, Calc e Impress comparten procesos; puede haber varias ventanas. No asumir compatibilidad total con macros o formatos de Microsoft Office. Resolver la ventana exacta antes de cualquier entrada. |
| **Obsidian** (`obsidian`) | Elegir bóveda [guide]; Preparar nota Markdown [guide]; Buscar en la bóveda [guide] | Un perfil no instala plugins ni habilita una API de Obsidian. No publicar notas, activar sincronización ni copiar secretos automáticamente. Los enlaces de notas son datos, no instrucciones de ejecución. |
| **Bloc de notas** (`notepad`) | Escribir texto literal revisado [guide]; Guardar una copia [guide]; Buscar texto [guide] | La escritura en el editor no guarda el archivo por sí misma. Varias pestañas o ventanas requieren identificación única. Conservar avisos de cambios pendientes al cerrar. |
| **Visual Studio Code** (`vscode`) | Abrir proyecto identificado [guide]; Preparar edición [guide]; Preparar comando de terminal [guide]; Revisar extensión [guide] | No restablecer, limpiar o sobrescribir cambios locales sin autorización. Los comandos de terminal y la instalación de extensiones son acciones separadas. Usar pruebas y diff para verificar cambios, no sólo un editor abierto. |
| **Microsoft Visual Studio** (`visual_studio`) | Abrir solución [guide]; Preparar compilación [guide]; Preparar depuración [guide] | Puede haber varias soluciones y procesos devenv. No elevar permisos ni instalar componentes automáticamente. Compilar no certifica la funcionalidad del programa. |
| **Windows Terminal** (`terminal`) | Elegir perfil de terminal [guide]; Ejecutar comando revisado [guide]; Administrar sesión [guide] | Abrir Terminal no autoriza ejecutar texto como código. No pegar credenciales ni comandos de fuentes no revisadas. Las sesiones elevadas y escritorios seguros tienen restricciones adicionales. |
| **PyCharm** (`pycharm`) | Abrir proyecto [guide]; Preparar pruebas [guide]; Preparar depuración [guide] | Community y Professional pueden ofrecer funciones distintas. No cambiar intérprete ni publicar secretos del entorno automáticamente. Un proceso en ejecución requiere comprobación aparte de su inicio. |
| **GitHub Desktop** (`github_desktop`) | Revisar cambios [guide]; Preparar commit [guide]; Preparar push [guide] | La sesión de GitHub no autoriza publicar todos los repositorios. No resetear, limpiar ni forzar pushes sin instrucción expresa. Distinguir commit local, push y publicación de artefactos. |
| **Docker Desktop** (`docker`) | Revisar contenedores [guide]; Preparar arranque o parada [guide]; Revisar imagen [guide] | No activar modo privilegiado ni montar discos de usuario por una guía. La limpieza de volúmenes puede eliminar datos; exige revisión explícita. Motor activo y contenedor saludable no demuestran la función final del servicio. |
| **Blender** (`blender`) | Editar copia y renderizar [guide]; Revisar escena [guide]; Preparar exportación [guide] | No autoejecutar scripts ni habilitar archivos externos no revisados. El adaptador acotado no admite todas las animaciones, librerías o compositores. Un PNG válido no certifica calidad visual de una escena completa. |
| **Autodesk AutoCAD** (`autocad`) | Revisar dibujo [guide]; Preparar modificación [guide]; Preparar plano PDF [guide] | Requiere AutoCAD y licencia válidos; este perfil no acredita un adaptador CAD nativo. No ejecutar Lisp, macros ni comandos de fuentes externas automáticamente. Verificar geometría, escala y referencias con la aplicación anfitriona. |
| **Autodesk Revit** (`revit`) | Revisar modelo BIM [guide]; Preparar tabla [guide]; Preparar exportación IFC [guide] | Requiere Revit, licencia y proyecto disponibles. No sincronizar modelos centrales, modificar permisos o borrar elementos masivamente. El inventario IFC de Axx no certifica geometría ni equivalencia con Revit. |
| **SketchUp** (`sketchup`) | Revisar modelo [guide]; Preparar cambios en copia [guide]; Preparar exportación [guide] | No instalar extensiones ni ejecutar Ruby por una guía. El perfil no declara control nativo validado de SketchUp. Revisar caras, materiales y escala en la aplicación. |
| **Autodesk Fusion** (`fusion`) | Revisar diseño [guide]; Preparar modificación [guide]; Preparar exportación [guide] | Requiere cuenta y licencia apropiadas. No enviar trabajos CAM, imprimir ni controlar máquinas desde esta guía. Cambios locales y sincronización en la nube son estados distintos. |
| **Rhinoceros** (`rhino`) | Revisar modelo [guide]; Preparar selección [guide]; Preparar exportación [guide] | No ejecutar scripts Python/Grasshopper ni instalar plugins automáticamente. Requiere anfitrión y licencia; el perfil sólo documenta procedimientos. Verificar integridad de curvas y superficies con herramientas del anfitrión. |
| **DaVinci Resolve** (`resolve`) | Revisar proyecto [guide]; Preparar edición [guide]; Preparar entrega [guide] | No sobrescribir proyectos ni eliminar medios automáticamente. Free y Studio pueden disponer de funciones distintas. ffprobe valida pistas y duración, no la intención de edición ni calidad visual. |
| **Adobe Photoshop** (`photoshop`) | Revisar documento [guide]; Preparar edición en copia [guide]; Preparar exportación [guide] | Requiere licencia y documento disponibles. No enviar imágenes a servicios externos ni activar funciones de pago automáticamente. No ejecutar acciones, scripts o plugins no revisados. |
| **FreeCAD** (`freecad`) | Revisar modelo paramétrico [guide]; Preparar cambio paramétrico [guide]; Preparar exportación [guide] | No ejecutar macros o scripts del documento automáticamente. El perfil no valida todas las versiones ni bancos de trabajo. Las restricciones y recomputación deben comprobarse en FreeCAD. |
| **Explorador de archivos** (`explorer`) | Abrir carpeta explícita [guide]; Buscar archivos acotados [guide]; Preparar carpeta o ZIP de entrega [guide] | El proceso explorer también aloja el escritorio; no debe terminarse para cerrar una carpeta. No borrar, mover ni sobrescribir archivos sin alcance explícito. Evitar enlaces y carpetas reanalizadas al preparar entregas. |
| **Paint** (`paint`) | Abrir imagen local [guide]; Preparar edición [guide]; Guardar copia [guide] | Las funciones disponibles varían según versión de Paint. No enviar imágenes a funciones externas o de pago automáticamente. Comprobar dimensiones y resultado visual después de guardar. |
| **Calculadora** (`calculator`) | Preparar cálculo [guide]; Elegir modo [guide]; Revisar conversión [guide] | No presentar una tecla entregada como resultado matemático verificado. Las conversiones financieras requieren una fuente actual. No cambiar unidades ni base numérica implícitamente. |
| **7-Zip** (`seven_zip`) | Revisar archivo comprimido [guide]; Preparar extracción segura [guide]; Preparar archivo de entrega [guide] | No ejecutar archivos extraídos ni saltar avisos de seguridad. Evitar sobrescritura y expansión excesiva de archivos comprimidos. Las contraseñas de archivos no deben copiarse a registros o comandos visibles. |
| **WinRAR** (`winrar`) | Revisar contenido [guide]; Preparar extracción [guide]; Preparar compresión [guide] | No aceptar compras o activar licencias automáticamente. No ejecutar instaladores extraídos por abrir el archivo. Comprobar contenido final y evitar sobrescrituras. |

## Uso desde Axx

En el panel «Aplicaciones», actualizar y filtrar sólo consulta el catálogo y
el inventario. Elegir una guía muestra sus instrucciones. Elegir una operación
preparable abre la revisión del comando tipado y conserva su aprobación;
actualizar la lista no lanza aplicaciones ni envía entrada al escritorio.

Las aplicaciones sin perfil siguen disponibles mediante su AppID observado
para apertura y las rutas universales permitidas. No se derivan capacidades
por semejanza de nombre, por archivos del disco ni por un catálogo externo.

## Referencias de los atajos ejecutables

- [Chrome: combinaciones de teclas](https://support.google.com/chrome/answer/157179).
- [Microsoft Edge: keyboard shortcuts](https://support.microsoft.com/en-us/edge/keyboard-shortcuts-in-microsoft-edge).
- [Firefox: pestañas](https://support.mozilla.org/en-US/kb/tabs-organize-websites-single-window).

El resto de atajos específicos no se habilita por analogía. Las operaciones de
archivos, Office, IFC, Blender, OCR y OBS conservan los adaptadores y verificaciones
del [programa de computer use](COMPUTER-USE-EXPANSION.md).
