# Axx 20 · Validación ejecutada y límites

Fecha: 18 de octubre de 2026. Base: fuentes de Axx 19; publicación 0.20.0. Se conserva el adjunto original sin sobrescribirlo.

## Resultados

- Compilación TypeScript y HTML autocontenido: correcta (`docs/v20/build-final.log`).
- Suite completa Node: **268 aprobadas, 0 fallos, 0 canceladas, 0 omitidas** (`docs/v20/tests-final.log`).
- **252 comprobaciones de navegador/contratos aprobadas**, distribuidas en los informes completos siguientes. No son dispositivos distintos ni conversaciones físicas.
- Cero errores JavaScript no capturados en esos informes; los contadores del renderer comprobados permanecen sin fallos.
- Servidor loopback real: GET `/`, `/Axx.html` y `/Axx-20.html` retornan 200 y los mismos bytes del HTML (`server-smoke.json`). Esto es HTTP desde Node, no navegación gráfica.
- Paquete extraído: comprobación final de recompilación y hashes en `REPRODUCIBILIDAD.json` del distribuible. No atribuir resultado antes de consultar ese registro.

| Informe en docs/v20 | Resultado |
|---|---|
| `identity-browser.json` | 26/26 |
| `persistence-browser.json` | 7/7 |
| `chat-browser.json` | 18/18 |
| `jitter-browser.json` | 3/3 |
| `polish-browser.json` | 6/6 |
| `layout-chat-appearance.json` | 43/43 |
| `captures-final.json` | 4/4 |
| `regression-timer-browser.json` | 24/24 |
| `regression-record-browser.json` | 23/23 |
| `regression-additional-edges.json` | 11/11 |
| `regression-layout-browser.json` | 40/40 |
| `regression-voice-regression-dictation-results.json` | 31/31 |
| `regression-voice-regression-chat-results.json` | 7/7 |
| `regression-voice-regression-music-return-results.json` | 9/9 |

`final-summary.json` enumera únicamente informes completos aprobados. Los archivos rojos, primeros intentos y registros históricos no se cuentan. El conjunto mantiene 268 pruebas unitarias aunque se modifique la presentación; los controles nuevos están además cubiertos por recorridos DOM.

## Fallos reproducidos antes de corregir

La base cambiaba forma guardada 3 a efectiva 6 en éxito, y a 8 en concentración. El regreso acababa en paso1 y Herramientas visible (`baseline-probe.json`). El conflicto de superficie se probó reinstalando deliberadamente parámetros antiguos de Experience antes de cargar el almacén Studio canónico.

Se reprodujeron fallos nuevos esperados antes de implementación (`red-tests.log`, `red-cache.log`), diferencias de redondeo en formas tubulares (`cache-test.log`), menú interceptado por arrastre (`chat-first.log`), movimiento pequeño convertido en acción (`jitter-red.log`), tres columnas de paletas desbordadas en320px (`layout-chat-first.log`), y solapamiento de actividad/base y figura tras cambiar a móvil (`polish-red.log`, `polish-body-red.log`). Los recorridos finales vuelven a comprobarlos.

## Identidad, navegación y preferencias

Se ejercitaron previsualizar/aplicar/descartar, cambio rápido de formas, estados de tarea, estilo completo con nombre, cámara, figura no reemplazada por estados y símbolos opcionales que siguen pausando una tarea. Una página nueva recibió la serialización del almacén de prueba: restauró la misma forma/superficie/tamaño y rechazó la precedencia de la superficie obsoleta.

Se probaron los 24 IDs, formas nuevas finitas y distinguibles, transiciones y seis perfiles. La geometría estático/caché coincide numéricamente con la ruta directa en los puntos de prueba de todas las formas. `resolve2x` coincide byte a byte con la referencia, incluida alfa fraccionaria.

Se comprobó primer toque desde base, ligera variación del puntero de dos píxeles, menús, nota guardada, cálculo250, temporizador real enviado desde chat, borrador, conflicto/selección de dictado y ausencia de envío automático. Los controles de tamaño utilizan los editores anteriores, no clones. Disposición en1440×960,976×807,390×844,320×568 y760×360. El ajuste móvil no reemplaza las dimensiones de escritorio.

## Qué fue real en multimedia y qué estuvo sustituido

**Música:** HTMLAudioElement reproduce WAV reales, con reloj/pausa/continuación. Llamar y volver no reinician la pista. El micrófono no participa en el sonido de prueba.

**Vídeo:** Canvas.captureStream produce un MediaStream animado640×360; MediaRecorder codifica, pausa, continúa y finaliza. Se descarga un archivo real y se reproduce verificando dimensiones y avance (`evidence/v20/capture-real-canvas.webm`). `getDisplayMedia` de la prueba devuelve esa fuente conocida: **no se grabó una pantalla física**.

**Guardado:** el Blob de vídeo es real; los límites de selector/directorio/writable se sustituyen por implementaciones controladas que verifican permisos, orden write/close, errores y no duplicación. **No se escribió en una carpeta real de Windows mediante un diálogo de sistema.** La descarga del navegador sí creó bytes reales en el contenedor.

**Voz:** SpeechRecognition y síntesis usan eventos controlados. Un oscilador WebAudio alimenta un MediaStream real para el analizador. Se verifica la inserción y los recursos, no la precisión de reconocimiento. No se realizó traducción lingüística real, inferencia de IA ni login Spotify/YouTube.

Los scripts `regression20-` cargan esta compilación, no el HTML anterior. Sus ayudantes detienen el rasterizador o añaden un ticker de prueba para aislar las tareas. Los nuevos recorridos de identidad/chat/layout/polish y las capturas utilizan el ciclo de producción. No usar los tiempos de un escenario con raster detenido para prometer fluidez.

## Medición de rendimiento sin pérdida de fotograma

Prueba aislada, no benchmark sostenido de toda la aplicación: dos instancias nuevas e idénticas del renderer antes/después, mismo estado y cámara, salida430×430, malla112×72, raster860×860, LUT512×512. Doce dibujos de calentamiento y48 dibujos medidos por versión.

| Magnitud | Axx19 | Axx20 |
|---|---:|---:|
| Mediana de dibujo | 26.90 ms | 24.55 ms |
| Percentil90 observado | 33.60 ms | 25.80 ms |
| Malla |112×72|112×72|
| Antialias por dimensión |2×|2×|
| Tabla de material |512×512|512×512|

**Reducción observada de la mediana: 8.74 %.** Los PNG `benchmark-before.png` y `benchmark-after.png` contienen **los mismos píxeles RGBA** en el fotograma controlado. Se conserva resolución, contorno y sombreado en esa comparación. Las pruebas numéricas de caché/resolución complementan el caso visual.

No se midió un aumento universal de FPS. Aumentar el límite de programación a60 no convierte60 en un resultado; la malla sigue pudiendo costar tiempo en equipos modestos. La mejora aislada no garantiza igual porcentaje en cada forma, sonido, panel o máquina. No se rebaja la calidad automáticamente para ocultar un coste alto.

Un primer intento con instancias de aplicación ya iniciadas arrojó distinta pose por el historial de estado; se conserva como diagnóstico. El informe final `benchmark.json` procede de instancias nuevas con condiciones iguales. No se cuentan como comparación los primeros PNG compuestos de inspección.

## Entorno y límites

Linux; Nodev22.16.0; TypeScript5.8.3; Chromium 144.0.7559.96 built on Debian GNU/Linux 13 (trixie); Python Playwright. El cuerpo mantiene rasterizado por software y los recorridos utilizan aceleración/WebGL desactivados.

La navegación directa `file://` devolvió **ERR_BLOCKED_BY_ADMINISTRATOR**. No se cambiaron políticas para eludirla. El HTML se cargó mediante `page.set_content` y una **Map declarada que sustituye localStorage**. Por tanto, **no se valida doble clic, almacenamiento físico por origen, permisos de un Windows real ni persistencia entre cierres del navegador del usuario**.

No se incluyen instalador, overlay nativo validado ni atajos globales. Hey Axx está documentado como futuro y no activa escucha de fondo. Tampoco se afirma unión topológica entre torso y brazo, simulación física de fluidos, accesibilidad certificada o reproducción exacta de cada ángulo de una imagen conceptual.

Se hizo revisión manual de referencias DOM, autoridad de ajustes, identidad frente a tarea, borradores, selección, límites, cancelación y diff. **No hubo revisor externo independiente.**

## Integridad y reproducibilidad

SHA-256 de la base Axx19 usada:
`de43ec7b65cdf80cea9f5bb24403b8a10edd9bbaf38954f6564cae2dc1068082`

SHA-256 del HTML Axx20:
`c93c68ea9e9a63ee392487384941b5ee85c8d3e1f88e024ffd081cbe287458eb`

`Axx.html`, `Axx-20.html` y `dist/index.html` tienen bytes idénticos. Los archivos anteriores se conservan como referencia versionada; no representan pruebas nuevas. Para repetir el benchmark, colocar la base del ZIP anterior junto al código. Los scripts de prueba requieren adaptarse a un navegador y permisos físicos para la aceptación en Windows.
