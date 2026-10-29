# Procedencia de los medios del README

Este registro describe los archivos presentes. Una imagen de interfaz no acredita por sí sola una acción nativa, conectividad ni aceptación física.

## Presentación actual · cinco imágenes de 0.22.23

El README principal utiliza cinco composiciones nuevas del 29 de octubre de 2026:
avatar, catálogo de herramientas, conexión API, Magic Pen y apariencia. Los
componentes proceden del frontend del proyecto en Chromium aislado, con títulos
y encuadre editorial. No muestran sesiones nativas ni datos personales.
[Archivos, método, alcance y hashes](v0.22.23/README.md).

## Nuevas capturas del candidato Windows 0.22.12

Capturadas el 27 de octubre de 2026 desde el WebView del EXE instalado, durante
la aceptación de Magic Pen. Se copiaron sin retoques y conservando sus hashes.
No son capturas de escritorio completo: la transparencia del WebView se representa
en negro. No son imágenes de 0.22.23. La aceptación posterior de Magic Pen en
0.22.14 se describe en sus [notas de versión](../../releases/0.22.14.md);
el estado de la distribución actual se recoge en [0.22.23](../../releases/0.22.23.md).

| Archivo | Alcance |
| --- | --- |
| [magic-pen-native-response-0.22.12.png](magic-pen-native-response-0.22.12.png) | Resumen del proveedor real sobre la selección de una ventana descartable con el texto público MAGIC PEN 4279 y una forma azul. La imagen muestra sólo el WebView. |
| [magic-pen-native-toolbar-0.22.12.png](magic-pen-native-toolbar-0.22.12.png) | Barra compacta instalada, con seis controles. |
| [magic-pen-native-tools-0.22.12.png](magic-pen-native-tools-0.22.12.png) | Menú secundario del mismo candidato. |

No se publica la vista del historial: contiene una captura del entorno personal.
Las imágenes seleccionadas no incluyen conversaciones, rutas, credenciales ni
voces personales. No acreditan reproducción acústica ni el nuevo alcance de PC.

## Galería de presentación en Chromium

Capturada el 22 de octubre de 2026 desde la revisión `9a9d05d`.

| Archivo | Fuente | Método y alcance |
| --- | --- | --- |
| [desktop-orbit.png](desktop-orbit.png) | `1.AXX/Axx.html` | Avatar y menú circular existentes; 500 × 500 píxeles CSS a resolución 2×. Geometría del host suministrada por fixture. |
| [mobile-pairing.png](mobile-pairing.png) | `mobile/client.html` y scripts operativos | Diálogo antes de introducir un enlace; fixture nativo que declara el dispositivo no emparejado. |
| [mobile-trackpad.png](mobile-trackpad.png) | `mobile/js/remote-control.js` | Superficie de control antes de la autorización del PC. |
| [mobile-keyboard.png](mobile-keyboard.png) | `mobile/js/remote-control.js` | Texto y atajos antes de la autorización del PC. |

Las vistas móviles usan el bundle operativo `mobile/www`, con viewport de 412 × 780 píxeles CSS a resolución 2×. No proceden del prototipo histórico.

Son capturas de presentación en Chromium aislado. No incluyen códigos de emparejamiento activos, conversaciones personales ni credenciales. No se inyectó entrada real al PC. Los píxeles del personaje y de la interfaz proceden del renderer y componentes existentes; no fueron generados ni retocados.

## Imágenes históricas reutilizadas

| Archivo | Registro en Git | Alcance disponible |
| --- | --- | --- |
| [axx-dock.png](../axx-dock.png) | `a97ce1f`, 21 de octubre de 2026 | Imagen histórica de conversación. El método de captura no está documentado aquí; no se presenta como evidencia del ejecutable instalado actual. |
| [axx-settings.png](../axx-settings.png) | `a97ce1f`, 21 de octubre de 2026 | Imagen histórica de herramientas y conexiones. No demuestra autenticación, inferencia ni operaciones ejecutadas. |

## Video actual de presentación

[axx-presentation.mp4](../../media/axx-presentation.mp4) y su [portada](../axx-video-preview.jpg)
se renovaron el 27 de octubre de 2026. El video se compone de las tres capturas
nativas de 0.22.12 descritas arriba: títulos, encuadres y fundidos creados fuera
de la aplicación, sin nuevas interacciones ni capturas de escritorio. La portada
es el frame del segundo 2. Los PNG originales permanecen sin retocar.

Se comprobaron los 450 frames decodificados, resolución 1280 × 720, duración
de 15 segundos y ausencia de audio. SHA-256 del MP4:
`2169646f59d9b3e55dd34e7f222c14fcc02e03d485aae2ab04346cbbd72f0589`.
Los títulos indican la versión y el alcance de presentación. No demuestra
gestos nuevos, latencia de una tarea, reproducción de voz ni aceptación de 0.22.14.

Sustituye al video conceptual de 10 segundos con audio incorporado en `d81e595`
el 21 de octubre; ese registro histórico no describe el archivo actual.

## Renovación y validación

Al sustituir un medio, actualizar su revisión, método de captura y alcance en este registro. Distinguir una captura del navegador de una del escritorio Windows instalado, y conservar las limitaciones de la escena probada. No publicar datos personales, voces de referencia, claves, tokens ni estado de ejecución privado.

Estas imágenes no certifican permisos Android, control remoto ni voz. Los resultados ejecutados y pendientes se describen en [verificación móvil](../../mobile/PAIRING-VERIFICATION.md), [Magic Pen](../../MAGIC-PEN-DESKTOP.md) y [voz MOSS](../../voice/xxx-default.md).
