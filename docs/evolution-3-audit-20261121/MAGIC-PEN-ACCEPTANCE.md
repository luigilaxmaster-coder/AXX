Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Aceptación Magic Pen

El recorrido legacy conserva sus pruebas de captura sintética, selección, geometrías WebGL, picking, cámara, explode, export PNG, limpieza de 20 montajes, undo/redo y cancelación. Son pruebas de navegador con fronteras nativas declaradas como fixtures; no sustituyen lápiz físico ni captura multimonitor.

Se corrigió la API v2: crear/leer documento persistente, aplicar parches al SceneDocumentStore real, devolver 409 ante revisión antigua, undo/redo y recuperar revisión 4 tras reinicio. Se usa el almacén que ya posee MagicPenService. El registro HTTP de assets ahora invoca el contrato correcto y no inventa dimensiones cuando faltan.

Motion exporta vídeo H.264 real, decodificado por PyAV y determinista para la escena de referencia. El render actual es una proyección ilustrativa Pillow, no una exportación del renderer 3D con materiales/cámara. No se declara Magic Pen Evolution completo: faltan los flujos de UI para v2, regeneración paramétrica incremental, reabrir/importar/exportar y selección entre representaciones con estado íntegro.

Evidencia local: `magic-pen.log`, `ci/14.log`, `http-ui-final.log`, `evolution-final.log`, `motion-after.log`. No se enviaron capturas privadas del escritorio al proveedor.
