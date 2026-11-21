Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Rendimiento medido y lÃ­mites

Escena fija ilustrativa de 2 s, 10 frames H.264 a 640Ã—360: cinco exportaciones, mediana 761.86 ms, mÃ¡ximo/p95 empÃ­rico 1295.24 ms, 5861 bytes por archivo. Hashes deterministas. Cinco muestras no caracterizan colas largas ni rendimiento sostenido.

No se compara velocidad con el export anterior como trabajo equivalente: antes no existÃ­a pista de vÃ­deo. Tampoco se presenta el CAD anterior como baseline de rendimiento Ãºtil: no generaba sÃ³lidos reabribles.

WebView2 nativa debug, visible, 1536Ã—816 CSS, DPR 1,25, durante otras regresiones: 120 intervalos con Code Studio cerrado y 120 abierto. Mediana 50.0 ms cerrado y 50.0 ms abierto; p95 66.7/83.2 ms. Esto equivale a unos 20 Hz de programaciÃ³n de frames en esa carga. **No acredita 45 FPS ni 30 FPS sostenidos.** No se midieron memoria GPU, calor o baterÃ­a y no se atribuye causalidad al editor con una sola muestra compartida.

No se redujo calidad artÃ­stica para mejorar nÃºmeros. Hace falta repetir con build de producciÃ³n, carga controlada y hardware/DPI documentados antes de certificar fluidez. Datos: `performance.json`, `native-frames.json`.
