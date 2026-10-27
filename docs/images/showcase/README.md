# Procedencia de los medios del README

Este registro describe los archivos presentes. Una imagen de interfaz no acredita por sí sola una acción nativa, conectividad ni aceptación física.

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

## Vídeo conceptual actual

[axx-presentation.mp4](../../media/axx-presentation.mp4) y su [portada](../axx-video-preview.jpg) se incorporaron en `d81e595`, el 21 de octubre de 2026. Es una presentación conceptual con audio: 10 segundos, 1280 × 720. No se usa como aceptación funcional ni como demostración de voz física.

## Renovación y validación

Al sustituir un medio, actualizar su revisión, método de captura y alcance en este registro. Distinguir una captura del navegador de una del escritorio Windows instalado, y conservar las limitaciones de la escena probada. No publicar datos personales, voces de referencia, claves, tokens ni estado de ejecución privado.

Estas imágenes no certifican permisos Android, control remoto ni voz. Los resultados ejecutados y pendientes se describen en [verificación móvil](../../mobile/PAIRING-VERIFICATION.md), [Magic Pen](../../MAGIC-PEN-DESKTOP.md) y [voz MOSS](../../voice/xxx-default.md).
