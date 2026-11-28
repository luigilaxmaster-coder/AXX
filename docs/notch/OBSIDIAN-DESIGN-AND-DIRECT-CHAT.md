# Project Obsidian — diseño y chat directo

Fecha: 2026-11-27. Rama de trabajo: `feat/notch-singularity`; base `dd44ef2fe598ce593741a0c1ef92e30690e5474c`.

## Alcance y estado

Implementación sobre el trabajo local previo, conservando sus cambios en HTML/Rust y los módulos Singularity. No se cambia la versión 0.23.5, el flag continúa desactivado por defecto y no se instala ni publica sobre producción. La solicitud posterior del propietario sustituye el símbolo abstracto por **el personaje real**, pide interacción más sencilla y añade escritura a conversaciones de aplicaciones desde el notch.

Hechos: hay código, capturas de Chromium, una candidata Tauri/WebView2 aislada, descubrimiento real de conversaciones y consulta real de cuotas de Codex. Hay una prueba real de respuesta de Codex en una sesión temporal sin herramientas y conservando su ID. Claude Code 2.1.111 está instalado; se detectan conversaciones locales. Antigravity no tiene todavía una conexión de sesiones verificada en este entorno.

Límites: las respuestas y cuotas de las capturas `*-fixture.png` son datos controlados para pruebas de UI. No demuestran una respuesta real de Claude o Antigravity. La captura nativa no certifica dictado físico, interacción entre aplicaciones ni multimonitor físico. El informe antiguo de Phase II no es aceptación automática de este incremento.

## Auditoría y correcciones

| Defecto anterior | Evidencia / causa | Implementación y comprobación |
| --- | --- | --- |
| La identidad era un círculo SVG genérico | `createIdentitySvg` anterior; objeción explícita del propietario | Retrato PNG del `SoftwareRenderer` existente, mismos materiales y forma; prueba de cero llamadas a tentáculos y restauración del renderer |
| Navegación de diez etiquetas diminutas en una fila | Captura anterior `06-intent-palette.png` | Inicio, Acciones, Archivos, Más, Chat y Ajustes; comprobación de pie visible en diez vistas a 480 DIP |
| Encabezado de Intent mostraba el temporizador | Captura anterior: título «Temporizador» sobre el buscador | Identidad AXX + nombre de la vista; la actividad mantiene su representación compacta |
| Inicio no orientaba la siguiente acción | Bloque genérico con tres botones equivalentes | Muñeco de 64 px, tres filas con verbo y explicación; chat a un clic mediante «Escribir» en compacto |
| Superficies repetidas y bordes excesivos | Media, agentes y recursos usaban bloques semejantes | Composición multimedia horizontal; timeline operativo; cifras grandes de recursos; filas de continuidad; área de archivos con recepción clara |
| Ajustes como lista de controles técnicos | Tarjeta anterior sin jerarquía | Perfiles Equilibrado / Enfoque / Cómodo, vista previa y ajustes avanzados plegables; cambios persistentes inmediatos |
| Dos relojes avanzaban el mismo spring | RAF fijo `1/60` más avance desde proyecciones | Una autoridad RAF basada en timestamps; perfil directo amortiguado; retarget conserva posición/velocidad |
| Un clic podía expandir y contraer en el mismo evento | El botón sustituía el SVG; el listener padre perdía su ancestro | `composedPath()` conserva el origen del clic; regresión de expansión/contracción |
| Los ticks podían reemplazar controles activos | Firma del body incluía tiempo multimedia | Parches de texto/seek; se conserva el compositor montado y su borrador |
| Resource Lens no recibía la última medición | `telemetryCache` no se incluía en `collectContext` | Se proyecta la caché real; valores ausentes se muestran como «—» |
| Las aprobaciones competían con el DOM del compositor | Reconstrucción del body para cada estado | Host independiente de aprobación; no destruye el texto que se está escribiendo |

Antes: `build/obsidian/before/screenshots/`. Después: `build/obsidian/after/`. Son capturas de la aplicación renderizada, con transportes controlados donde se indica; no son maquetas de una implementación inexistente.

## Dirección visual y sistema de diseño

Predomina Obsidian Precision: grafito estable, superficies continuas, poca ornamentación y separación mediante espacio. Living Material aporta la identidad material del personaje, sin una segunda escena animada. Spatial Instrument aporta composiciones distintas según actividad y métricas tabulares. Las variantes de personalización permiten comparar materiales/acento/contraste sobre el mismo renderer; no se presentan como tres productos separados.

- Superficie: `#151619`; texto: `#f2f2f4`; secundario: `#aaaeb8`. Variante de contraste: superficie `#090a0c`, texto blanco, secundario `#d4d6de`.
- Acentos: avatar, hielo, iris, salvia, ámbar. `readableAccent()` valida RGB hexadecimal y eleva luminancia hasta 4,5:1 sobre `#24272c`. Esto verifica esa combinación, no todos los píxeles de una superficie translúcida sobre cualquier fondo.
- Material sólido por defecto. Translucidez opcional, con fallback opaco; no se captura el escritorio para simular blur.
- Tipografía del sistema / familia existente; títulos 21 px, contenido 12–14 px y metadatos 10–11 px. Temporizadores y cuotas usan cifras tabulares.
- Espaciado semántico 4 / 8 / 12 / 16 / 20 px. Cabecera expandida 40 px y pie 48 px. Controles compactos de 24 px y controles principales de 32 px.
- Geometría centralizada en `notch-layout.js::GEOMETRY`. La conversación admite más altura que música porque contiene selectores, respuesta y compositor; la pantalla limita sus dimensiones y el contenido puede desplazarse.
- Los ajustes de apariencia son aditivos y separados de los del personaje. Los valores desconocidos se normalizan; restablecer el notch no borra la identidad 3D.

### Retrato real del personaje

`SoftwareRenderer.captureIdentityPNG()` utiliza la misma instancia, geometría y pipeline de materiales, incluida la pasada de Optical Glass. Produce una imagen de 128 px para mostrar a 32–64 px. Durante esa captura puntual se sustituye temporalmente el destino raster y se excluyen órbita, droplets y tentáculos. Un `finally` restaura canvas, contexto, raster, imagen, estado oculto y campos de morph. Se encuadra la silueta con margen del 16%.

El PNG vive en memoria. La caché cambia por identidad/material/época de acoplamiento; no se guarda en las preferencias ni se ejecuta otra escena. El renderer libre sigue suspendido al terminar el acoplamiento. El flag apagado no genera un retrato. La posición/cámara del avatar original no se reemplaza por la miniatura.

### Movimiento e interacción

Un solo RAF mide `dt` real, limitado a 50 ms tras una pausa. Perfil suave: rigidez 300 y amortiguación 34; directo: 460 y 43, sin overshoot geométrico. El cambio de perfil conserva valores y velocidades. El contenido se revela según el espacio efectivo que ha abierto la superficie; los cambios de vista añaden 180 ms de desplazamiento de 5 px. El modo reducido del sistema o de preferencias elimina esas animaciones.

El muñeco abre Inicio; «Escribir» abre directamente el compositor. La cabecera admite clic y arrastre hacia abajo para desacoplar. Escape cierra primero la personalización y restaura el foco al control que la abrió. La captura de micrófono requiere una pulsación explícita; cerrar/cambiar de superficie la detiene y nunca envía lo dictado.

Exploraciones comparables renderizadas: `after/direction-obsidian-home.png`, `direction-living-home.png` y `direction-spatial-home.png`. Comparten contenido y viewport; comparan material, acento, contraste y densidad. No representan tres temas independientes ni aceptación artística del propietario.

## Chat directo: arquitectura e interfaz

`notch-chat.js` es una proyección de transporte sobre Connect. No crea un historial paralelo, no cambia el chat activo de AXX y no altera la selección de modelo de AXX. La aplicación de origen conserva la conversación. El usuario elige:

1. Codex, Claude Code o el estado de conexión de Antigravity.
2. Proyecto descubierto en las conversaciones del proveedor.
3. Conversación concreta.
4. Texto o dictado revisable; Intro envía, Mayús+Intro crea línea.

Las listas tienen paginación. Al pasar a otra superficie se conserva el estado del compositor en memoria. No se envía al cargar, elegir proveedor, cambiar de proyecto, acoplar, expandir o reconectar. Los controles de destino se bloquean durante un envío para evitar respuestas asignadas a otro chat.

Si el backend termina de arrancar después de abrir el compositor, su evento de disponibilidad recarga solo las listas y el saldo. Un rechazo confirmado antes de admisión conserva el texto y permite corregirlo. Un resultado incierto mantiene el envío bloqueado y permite reconciliar el mismo ID.

### Contratos añadidos

Todos utilizan la autenticación local existente; no se modifica `/v1`.

| Ruta | Responsabilidad |
| --- | --- |
| `GET /axx-api/connect/sessions?provider=...&cursor=...` | Metadatos paginados de conversaciones, proyecto, modelo cuando existe y estado ocupado |
| `GET /axx-api/connect/usage?provider=...` | Cuota normalizada con procedencia y timestamp; ausencia explícita de datos |
| `POST /axx-api/connect/session/start` | Exactamente `provider`, `session_id`, `request_id`, `message`; sin cwd ni ejecutable arbitrario desde UI |
| `GET /axx-api/connect/run?request_id=...` | Seguimiento existente de Connect |
| `POST /axx-api/connect/cancel` | Cancelación existente de Connect |

Se reutilizan los IDs, eventos, límites de concurrencia, idempotencia, validación de memoria, cancelación y almacenamiento de resultados de `CodexProvider`. El mensaje no se almacena como argumento de proceso ni se interpola en shell. Un fallo HTTP conserva el ID y el borrador: se consulta el mismo ID; no hay reenvío automático ni cambio silencioso de proveedor.

### Codex

Se consultó el schema generado por el CLI instalado, además de la documentación oficial. Se usa `thread/list`, se verifica `thread/read` antes de enviar y se continúa el `threadId` seleccionado. Un hilo ocupado se rechaza. `thread/resume` no cambia las instrucciones o ajustes guardados del hilo. Una sesión efímera ya cargada se utiliza directamente: el experimento real mostró que no tiene un rollout persistido que se pueda reabrir.

El rechazo por ocupación depende del estado informado por ese transporte. No se ha certificado escritura simultánea del mismo hilo desde dos procesos distintos; el test real utilizó una sesión temporal propia. El selector no certifica una sincronización con todos los proyectos/chats alojados en la nube.

Antes de inferir se conserva el chequeo existente de uso ordinario incluido. Se verifican modelo, proveedor e ID de destino. Una respuesta de otro hilo se rechaza. El chat externo no sustituye `selected_model` ni la verificación del modelo del chat AXX.

### Claude Code

La CLI oficial administra su propio inicio de sesión; AXX no lee ni copia tokens. El descubrimiento lee bloques acotados de metadatos de sus JSONL locales y devuelve título/proyecto/ID, no el cuerpo de las conversaciones. `--resume` continúa el ID elegido.

El adaptador usa stdin, `shell=False`, ventana de consola oculta, salida limitada y cancelación supervisada. Desactiva herramientas, slash commands, hooks y MCP del proceso de conversación. No permite a un texto recibido convertirse en un comando o edición. Se filtran las variables de claves API y rutas de proveedores cloud heredadas. Es **conversación con Claude Code local**, no acceso universal a los chats de Claude Desktop/web ni ejecución automática de código.

La CLI conserva las condiciones de uso de su cuenta. Esta sesión de desarrollo no ejecutó una inferencia real de Claude para certificar su comportamiento de facturación o disponibilidad. Los tests de transporte y lifecycle son controlados.

### Antigravity

La documentación actual ofrece CLI, headless y ACP; no se declara que carezca de API. No se encontró una CLI `agy` en las rutas revisadas y no se ha establecido un transporte autenticado. Su vista informa esa falta y bloquea el envío. Falta aportar/conectar el ejecutable y validar listado, sesión, permisos, respuesta y cuota sobre esa instalación. No se accede a tokens privados del IDE ni se finge que un botón abre una conexión real.

## Semántica de las cuotas

- Se muestra porcentaje **disponible**, nunca una estimación inventada de mensajes, tokens u horas restantes.
- «5 horas» corresponde solo a una ventana de 300 minutos informada; «Semanal», a 10.080. Otras duraciones conservan su valor real.
- Se conserva la fecha de reinicio del proveedor y se muestra la hora de actualización. Un dato de más de 120 s se identifica como último dato disponible.
- Codex: `account/rateLimits/read`, con protección ante cambio de cuenta durante la consulta.
- Claude: eventos oficiales que realmente incluyan porcentajes. Un simple aviso de rate limit no se convierte en 0% o 100%. Si la versión instalada no informa los dos saldos, aparecen como no disponibles.
- Antigravity: sin lectura verificada todavía. No se reutiliza el saldo de Codex ni el de Claude como sustituto.
- El polling de cuota solo ocurre con la vista visible y como máximo una vez por minuto, además de actualización explícita o fin de solicitud. No hay compra ni consumo de créditos de reset.

## Fuentes consultadas

La documentación describe contratos; la evidencia local determina qué se verificó aquí.

- [Codex App Server](https://learn.chatgpt.com/docs/app-server): listado/lectura/reanudación, eventos y `account/rateLimits/read`.
- [Claude Code programático](https://code.claude.com/docs/en/headless): print, streaming y continuidad.
- [Claude status line](https://code.claude.com/docs/en/statusline): campos de ventanas de cinco horas/semanales y ausencia de datos.
- [Antigravity CLI headless](https://antigravity.google/docs/cli/headless/), [ACP](https://antigravity.google/docs/cli/acp/) y [cuotas](https://antigravity.google/docs/cli/commands/usage).
- [Apple Motion](https://developer.apple.com/design/human-interface-guidelines/motion), [Material Motion](https://m3.material.io/styles/motion/overview/how-it-works): referencias de interacción, sin atribuirles APIs de Windows.
- [Dynamic](https://github.com/JustKoal/Dynamic-releases): documentación pública de producto; no se descargaron ni ejecutaron sus binarios.

## Verificación y ejecución

Desde la raíz del repositorio:

```powershell
node 1.AXX/scripts/notch/test-notch-core.cjs
node 1.AXX/scripts/notch/test-notch-ui.cjs
node 1.AXX/scripts/notch/test-notch-phase2.cjs
node 1.AXX/scripts/notch/test-notch-obsidian.cjs
python -m unittest backend.connect.tests.test_desktop_sessions backend.connect.tests.test_provider backend.connect.tests.test_http -q
python scripts/validate_companion.py --output build/obsidian/companion-validation.json
```

Evidencia privada: `build/obsidian/live-readonly.json`, `live-session-probe.json`, `after/browser-report.json`, `native/native-report-expanded.json`, capturas y recibo Companion. El historial de fallos y repetición se registra en `EXECUTION-STATE.md`.

## Reversión y pendientes

Desactivar `axx.notch.v1` devuelve la presentación libre; el snapshot preserva identidad y los cambios legítimos hechos mientras estaba acoplado. No se borran chats, pairings, credenciales, borradores existentes ni operaciones para reparar una conexión.

Pendientes independientes: conexión real de Antigravity; inferencia real de Claude y exposición de cuota por su versión; dictado físico; foco/click-through entre procesos; monitor secundario/escala y sesiones largas. La cartera completa de innovaciones del documento original no se etiqueta como terminada por este rediseño. No hay aceptación final de producción ni autorización para publicar automáticamente.
