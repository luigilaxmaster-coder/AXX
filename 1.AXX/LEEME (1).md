# Axx 20 · Tu identidad, estable

Revisión del mismo proyecto Axx 19. No sustituye el personaje, los ejecutores de tareas, el chat ni las conexiones anteriores. Cabecera: **IDENTITY / 20**.

## Abrir y conservar tus datos

El HTML compilado se entrega con dos nombres de contenido idéntico: `Axx.html` (nombre estable para seguir actualizando) y `Axx-20.html` (identificador de esta entrega). `ABRIR-AXX.cmd` abre el primero.

Para mantener un origen estable entre versiones, extrae el proyecto y ejecuta **INICIAR-AXX.cmd** con Node.js 22.16 o posterior. Abre siempre:

```text
http://127.0.0.1:4173
```

No hace falta instalar las dependencias ni compilar para ese arranque: `dist/index.html` y el servidor están incluidos. El servidor solo escucha en loopback. No cambia tus cuentas ni conecta un modelo automáticamente.

**Antes de cambiar desde otro archivo o dirección, exporta una copia en Axx anterior e impórtala en Datos y sistema.** El almacenamiento del navegador está asociado al origen. Para archivos `file://` su comportamiento no está garantizado y suele diferir por archivo; renombrar el HTML no puede transportar por sí mismo las preferencias de otra URL. No uses una sesión privada para conservar datos después de cerrarla. No borres los datos del sitio sin exportarlos.

Fuente: https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage

## Lo primero: fijar tu figura

Abre **Herramientas → Todas las herramientas**, busca **Apariencia** o **Formas y superficie** y abre esa función.

1. Elige forma y paleta. La selección se muestra como vista previa.
2. Pulsa **Guardar cambios**, ahora siempre visible al pie. **Descartar prueba** vuelve a lo guardado.
3. Mantén **Conservar mi forma** activado: las tareas, notificaciones y pausas no sustituyen la silueta elegida.

**Botones vivos en las acciones** es una preferencia diferente: permite que Música, Tiempo o Grabación transformen temporalmente el cuerpo en reproducción/pausa/números. Al volver a la base se recupera tu figura. Desactívala para conservar la figura incluso mientras controlas una actividad; tocarla seguirá pausando o continuando la tarea.

El tamaño manual, superficie, exposición, rugosidad, fluidez y cámara se guardan sin que una preferencia antigua de otra capa reemplace la configuración al iniciar. El encaje temporal en un teléfono o una ventana estrecha no sobreescribe tu medida de escritorio.

## 24 formas, movimiento y estilos

Se mantienen las doce formas originales: **Core, Flow, Pearl, Torus, Split, Wave, Bloom, Fold, Spike, Drift, Orbit y Morph**.

Se añaden doce superficies tridimensionales: **Cushion, Trefoil, Nova, Heart, Infinity, Helix, Knot, Petal, Prism, Capsule, Crescent y Ripple**. Las miniaturas del selector proceden del renderizador; el personaje en uso no es una imagen ni una animación de vídeo.

En Apariencia, baja a **Movimiento**: **Orgánico, Seda, Marea, Vórtice, Respiración y Suspendido** cambian velocidad, deformación, torsión, flotación y respiración dentro de límites. No cambian por sí mismos la forma elegida. Ajusta Expresividad para moderar el comportamiento. El movimiento reducido y estático mantienen prioridad.

**Reacciones** permite probar Onda, Asentir, Balanceo, Elasticidad, Giro fluido y Reunir materia. Son muestras visuales breves, no señales de una tarea ejecutada. Una interacción nueva puede interrumpirlas.

**Mis estilos** guarda hasta ocho combinaciones con nombre: forma, paleta, acabado, superficie, movimiento, tamaño y cámara. Guarda primero los cambios de apariencia; después asigna nombre al estilo. Recuperarlo no modifica tus notas, mensajes o tareas. Los estilos se incluyen en la copia de seguridad.

## Volver y tocar

- **Alt + Mayús + A:** llamar y seguir al cursor.
- **Alt + Mayús + A, A:** dos pulsaciones físicas de A dentro de 450 ms para regresar a la base. Mantener A pulsada no cuenta como doble pulsación.
- **Esc:** detener seguimiento; conserva las reglas de regreso entre niveles del menú cuando no hay seguimiento.
- En la base solo queda la figura. **El primer toque muestra únicamente Herramientas**. El segundo, sobre Herramientas, abre los accesos alrededor.

Un ligero movimiento involuntario del ratón no se considera arrastre. Tocar por primera vez después de volver no pausa por accidente la tarea que estuviera seleccionada. Los controles esenciales de una captura activa continúan disponibles independientemente del dock; ocultar Herramientas no oculta que hay una captura.

Los atajos operan dentro de la página enfocada: esta versión no añade un overlay nativo ni atajos globales de Windows. Regresar detiene la entrada de micrófono/traducción pendiente conforme a la regla existente, pero conserva música local, temporizadores y tareas independientes.

## Conversación mínima

La superficie conserva únicamente **cabecera Axx, historial y barra de mensaje**, con adjuntar, micrófono y enviar. Conexión, nueva conversación, exportación, lectura y medidas están en **⋯**. No hay tarjetas de sugerencias permanentes.

El mismo chat sirve para comandos locales y para preguntas a una IA que conectes. Por ejemplo:

```text
Calcula 125 × 2
Pon un temporizador de cinco minutos
Guarda una nota: revisar los planos
```

Sin proveedor conectado, los comandos locales funcionan; el chat no fabrica respuestas de IA. La captura de ejemplo muestra una respuesta local real del temporizador. Los borradores permanecen al cambiar de herramienta. Durante una respuesta pendiente puedes preparar el siguiente borrador, pero no se dispara un envío duplicado. Al desplazarte hacia mensajes anteriores, no se te fuerza continuamente al final.

Los menús ya no se interpretan como arrastre de su panel. En móvil la figura se encaja por encima de la conversación, sin borrar su tamaño guardado. Los avisos de actividad y los botones de llamada disponen de filas separadas.

## Funciones conservadas

Música local y sus controles, fuentes remotas y extensión opcional, dictado con original/traducción, selección de destino y revisión, notas, tareas, texto, imágenes, archivos, lector, cronómetro, cuenta e intervalos, grabación/halo/guardado permanecen en el proyecto. Las reglas de permisos y ausencia de envío automático del dictado no se cambian.

Las instrucciones históricas de las conexiones están en `docs/v16/distribucion-original/` cuando existe esa carpeta, y en la documentación versionada del paquete. Se mantienen los límites: algunas capacidades necesitan el servidor, un navegador compatible, una autorización o una integración externa. Esta actualización no autentica Spotify/YouTube ni conecta tu modelo de IA.

## Hey Axx: actualización futura

Se muestra como **FUTURO · NO ACTIVO** en Próximamente. Se ha documentado el recorrido: palabra de activación → escuchar una orden → ejecutar un comando permitido o pedir aprobación → responder por voz → volver al reposo. Se implementará como capacidad opcional del proyecto ejecutándose. **No hay escucha permanente, detector de activación ni reconocimiento de identidad vocal activos en esta entrega.** Véase POR-IMPLEMENTAR.md.

## Qué se comprobó

Consulta VALIDACION.md: 268 pruebas Node; 252 comprobaciones de navegador y contratos; vídeo/audio locales reales cuando se indica; voz, pantalla seleccionada y directorio con fronteras controladas. Las pruebas no equivalen a validación de tu Windows o de un micrófono físico.

El renderizador conserva malla, antialias y tabla de material. La mejora medida de dibujo aislado no significa 60 FPS garantizados ni que se haya auditado cada posible combinación del producto.
