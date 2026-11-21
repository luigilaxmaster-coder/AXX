# Fase 2 (`PR-03` y `PR-04`) — Especificación: SceneDocument v2, Parches CAS y Diagram Studio

- **Fase:** 2 (`PR-03`, `PR-04`)
- **Rama:** `feature/axx-evolution-3`
- **Dependencia:** `PR-02` (`Gate G1` aprobado)
- **Gate objetivo:** `G2` (`MP-02`, `MP-04`)

## 1. Archivos implementados

- `backend/spatial/__init__.py`
- `backend/spatial/scene_document.py` (`PR-03`: validador estricto de `SceneDocument v2`, invariante `I-07` que impide afirmar `cad_verified` desde capturas de imagen sin sólidos BRep ni unidades verificadas, importador no destructivo `import_presentation_plan_v1`, `SceneDocumentStore` SQLite).
- `backend/spatial/patches.py` (`PR-03`: `apply_scene_patch` con CAS `base_revision`, inmutabilidad de hashes binarios de assets `MP-02`, generación de parches inversos `undo_scene_patch` / `redo_scene_patch` e invalidación incremental por objeto/timeline).
- `backend/spatial/diagram_studio.py` (`PR-04`: modelo semántico AST de nodos/puertos/edges/grupos/capas, 12 plantillas declarativas de `diagram-design`, parser/exportador Mermaid con preservación visible de elementos no soportados, QA geométrica y de seguridad anti-XSS/foreignObject, exportación SVG y PNG sin recortes de etiquetas `MP-04`).
- `1.AXX/scripts/magic-pen/scene-history.js` y `1.AXX/scripts/magic-pen/diagram-editor.js` (módulos frontend cargados bajo demanda con limpieza completa de listeners en `unmount()`).
- `backend/tests/test_scene_document_and_diagram_studio.py`.
