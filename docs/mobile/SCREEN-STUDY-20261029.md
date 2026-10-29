# Estudio de pantallas y adaptación futura de Axx Mobile

Fecha: 29 de octubre de 2026. Objetivo: extender la apariencia actual a más teléfonos sin perder legibilidad, funciones, datos ni compatibilidad con Desktop. Este documento es un análisis de implementación con pruebas de navegador; no una certificación de todos los modelos físicos.

## Criterio de diseño

Se conserva el inicio con personaje, entrada única a chat, navegación compacta, ajustes secundarios agrupados y temas claro/negro. Adaptar significa redistribuir espacio cuando cambia la ventana, no sustituir la identidad por otra interfaz ni aumentar todo proporcionalmente.

No existe una lista finita de «todas las pantallas»: un mismo teléfono puede cambiar zoom, orientación, teclado, multiventana y escala de texto. Se estudia el espacio disponible para la aplicación y sus restricciones, separando píxeles físicos, píxeles CSS, dp Android y puntos iOS. No se supone una equivalencia universal entre esas unidades.

Android clasifica el ancho disponible en compacto (<600 dp), medio (600–839), expandido (840–1199), grande (1200–1599) y extra grande (≥1600). La altura se clasifica por separado: <480, 480–899 y ≥900 dp. Estas clases dependen de la ventana, no del nombre comercial del equipo. Para Axx son referencias de diseño; los tests web usan píxeles CSS medidos. [Guía oficial de clases de ventana](https://developer.android.com/develop/ui/views/layout/use-window-size-classes).

## Inventario y brechas actuales

| Área | Estado observado en el código |
| --- | --- |
| Plataforma | Capacitor; proyecto nativo Android. No hay proyecto iOS en este checkout. |
| Android | minSdk 29, targetSdk 36 en `mobile/android/variables.gradle`. No se declara soporte Android anterior a API 29. |
| Layout | Viewport con `viewport-fit=cover`, `100dvh`, safe-area CSS, contenedores flexibles, paneles desplazables y ajustes por altura. Inicio/contenido con ancho máximo. |
| Tipografía | Opción estándar o tamaño del teléfono. Los tests simulan escalado de fuentes; no reproducen todas las decisiones de TextZoom, Dynamic Type ni cada fuente nativa. |
| Personaje | Geometría/material extraídos del escritorio, rasterización GPU y respaldo CPU. La resolución interna y el refresco físico no equivalen al ancho CSS. |
| Plugins propios | AxxTransportPlugin, AxxVoicePlugin, AxxFilesPlugin y widget Android. Las funciones nativas necesitan equivalentes y pruebas propios para iOS. |
| Evidencia física existente | Samsung A21s; las comprobaciones históricas están en los documentos de 0.2.4 y Transfer. No se extienden automáticamente a otros modelos, iOS o todas las funciones. |

## Matriz ejecutada

Se ejecutaron **120 escenarios**: diez ventanas × dos temas × texto 100/170/200 % × DPR 1/3, con transporte nativo declarado como fixture. Cada escenario recorre las pestañas principales, comprueba navegación, entrada a chat, hoja del personaje y compositor con una ventana de teclado de 299 píxeles CSS. No envía órdenes a un PC real ni cambia ajustes de un teléfono.

Resultado: **96 escenarios pasan las comprobaciones geométricas y 24 presentan una incidencia**. Esto no representa porcentaje de teléfonos soportados ni certificación de accesibilidad.

| Ventana CSS | Función en el estudio | Pasa / falla | Hallazgo |
| --- | --- | --- | --- |
| 280 × 653 | Pantalla exterior estrecha / ventana reducida | 4 / 8 | «Acciones» desborda con texto 170/200 %. |
| 320 × 568 | Teléfono compacto | 4 / 8 | Mismo desborde con texto 170/200 %. |
| 339 × 673 | Referencia de ancho Samsung | 8 / 4 | Pasa 100/170 %; «Acciones» desborda al 200 %. |
| 390 × 844 | Teléfono vertical estándar | 12 / 0 | Sin las incidencias geométricas buscadas. |
| 440 × 956 | Teléfono vertical grande | 12 / 0 | Sin las incidencias geométricas buscadas. |
| 568 × 320 | Horizontal de altura reducida | 8 / 4 | Entrada a chat queda fuera de la ventana al 200 %. |
| 844 × 390 | Horizontal ancho | 12 / 0 | Pasa geometría; no acredita rotación nativa. |
| 600 × 720 | Ventana media / plegable | 12 / 0 | Pasa layout de una columna; bisagra no simulada. |
| 840 × 900 | Interior amplio de plegable | 12 / 0 | Pasa geometría; postura física no comprobada. |
| 1024 × 768 | Tableta / multiventana | 12 / 0 | Pasa una columna centrada; no implica optimización específica. |

Se conserva el resultado por caso en `docs/mobile/evidence/screen-matrix-20261029.json`. Reproducción:

```powershell
python -m mobile.tests.test_screen_contract --study --output build/screen-study-20261029.json
```

La matriz exigida para no retroceder en la entrega actual es más pequeña: 339/390/440 en vertical, temas claro/negro, texto 100/170 % y teclado de 299 puntos (**12 combinaciones**). Los casos que fallan en el estudio siguen declarados pendientes; no se eliminan del informe ni se presentan como soporte universal. Ampliar soporte exigirá corregirlos y promoverlos a la matriz obligatoria.

Los fixtures v1 prueban además snapshot básico sin capacidades nuevas, personalización opcional y campos futuros desconocidos, conservando identidad y borrador. Un test TLS aislado comprueba los campos reales del snapshot, null al arrancar, método permitido y denegación antes de mutar. No constituye una prueba binaria de todos los APK históricos.

## Ejes que necesita cubrir la adaptación

| Eje | Regla de implementación y prueba |
| --- | --- |
| Ancho y altura disponibles | Decidir por espacio real, incluyendo ventanas estrechas y teclado. Probar límites de cada breakpoint, no solo medidas cómodas. |
| Densidad y zoom de pantalla | Mantener tamaños lógicos de controles; limitar memoria del canvas. DPR 1/3 está simulado; 2/4 y zoom nativo requieren ampliación. |
| Texto y localización | Permitir crecimiento/reflujo y textos largos sin tapar acciones. Añadir idiomas RTL y fuentes nativas; el estudio actual no los certifica. |
| Teclado | Compositor y Enviar accesibles, borrador conservado; verificar teclado flotante, dividido, hardware y cambios de altura. Un teclado simulado de 299 no cubre todos. |
| Recortes y barras | Respetar cada inset, también los asimétricos y navegación por gestos/botones. No compensar con alturas fijas por marca. |
| Orientación/multiventana | Preservar estado y operación al rotar, redimensionar o recrear la actividad. Horizontal no debe ocultar la entrada principal. |
| Plegables | Medir ventana y postura, evitar controles sobre una bisagra; probar apertura/cierre durante chat, grabación y transferencia. Una ventana de 840 no reproduce una bisagra. |
| Color | Conservar ambos temas y contraste del acento. Probar alto contraste, inversión, perfiles de pantalla y filtros del usuario; no compensarlos cambiando los colores globales. |
| Rendimiento y energía | Medir GPU/CPU, temperatura, batería, memoria y varios personajes/materiales. El panel de 120 Hz no garantiza 120 FPS; los datos históricos del A21s son específicos de su escena. |
| Accesibilidad e interacción | Verificar foco, lector de pantalla, tamaño táctil y alcance con una mano; el canvas no debe impedir usar chat/acciones. Añadir pruebas TalkBack/VoiceOver físicas. |
| Sistema y permisos | Probar denegación de cámara/micrófono/archivos, selección limitada, segundo plano y muerte del proceso. Conservar enlace, IDs y recibos. |

Apple recomienda layouts reconocibles que se adapten a orientación, texto, safe areas y variaciones de ventana. Las zonas seguras son esenciales para recortes e interfaces del sistema; una prueba Chromium de ancho similar no acredita ese comportamiento en un iPhone. [Guía de layout de Apple](https://developer.apple.com/design/human-interface-guidelines/layout).

El targetSdk actual hace relevante el tratamiento de insets: Android aplica edge-to-edge en Android 15 y posteriores al apuntar a SDK 35 o superior. Es necesario probar API 35/36 físicamente o en emulador apropiado; una aceptación en API 31 no lo sustituye. [Edge-to-edge oficial](https://developer.android.com/develop/ui/views/layout/edge-to-edge).

## Accesibilidad como criterio de aceptación

El objetivo para futuras adaptaciones es conservar funcionalidad al 200 % de texto y reflujo a 320 píxeles CSS. Las incidencias encontradas impiden declarar ese objetivo cumplido en toda la interfaz actual. El mínimo de WCAG 2.2 para objetivos táctiles tiene excepciones y no debe confundirse con la política de Axx de mantener controles principales amplios: la matriz comprueba navegación de al menos 44 CSS px. [Resize Text](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html), [Reflow](https://www.w3.org/WAI/WCAG21/Understanding/reflow), [Target Size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

## Plan de implementación sin rediseño

1. Corregir las etiquetas a 280/320 px y texto grande mediante reflujo y espacio de navegación, conservando iconos, jerarquía, tema y tamaños legibles. Verificar que no se resuelva ocultando texto o desactivando la accesibilidad.
2. Ajustar la altura mínima del escenario 3D en horizontal/teclado para mantener visible la entrada principal. No cambiar la identidad ni recortar controles para ampliar el personaje.
3. Añadir pruebas de safe areas, DPR/zoom nativo, textos largos y RTL; extender también Archivos, Actividad, panel de control, teclado remoto, voz y scanner nativo. Sus suites funcionales existentes no sustituyen esta matriz física.
4. Probar Android API 29, 31, 35 y 36 con al menos un equipo de recursos limitados, uno moderno, un fabricante alternativo y un plegable. Son clases de selección de QA, no una afirmación de disponibilidad de esos equipos.
5. Mantener una columna centrada donde siga funcionando bien. Evaluar dos paneles solo cuando el espacio y el uso lo justifiquen, con revisión visual explícita; una tableta no obliga a un rediseño.
6. Para iOS: crear y mantener el proyecto nativo y los plugins equivalentes de transporte seguro, voz, archivos y elementos del sistema; probar firma, enlaces, permisos, conservación de datos y comportamiento de WebKit con Xcode/equipos Apple. El CSS compartido es reutilizable, los plugins Java no lo son. [Plataforma iOS de Capacitor](https://capacitorjs.com/docs/ios), [plugins iOS](https://capacitorjs.com/docs/plugins/ios).
7. Promover cada clase al soporte declarado solo después de pasar geometría, funciones, actualización con datos y aceptación nativa. Vincular esa evidencia al [protocolo de compatibilidad](COMPATIBILITY-PROTOCOL.md).

## Lo que este estudio no acredita

No acredita todos los modelos comerciales, versiones de WebView/WebKit, fuentes, lectores de pantalla, teclados, bisagras, espacios de color ni funciones nativas. No existe build iOS entregada aquí. No se ha modificado la interfaz aprobada para producir resultados positivos: se conservan las 24 incidencias para la adaptación futura solicitada.
