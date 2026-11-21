# Fase 3 (`PR-05`) — Especificación: CAD Studio Paramétrico, STEP/GLB y Worker Aislado

- **Fase:** 3 (`PR-05`)
- **Rama:** `feature/axx-evolution-3`
- **Dependencia:** `PR-03` (`Gate G2` aprobado)
- **Gate objetivo:** `G3` (`MP-03`, `I-07`, `I-08`)

## 1. Archivos implementados

- `backend/spatial/cad_contracts.py` (`validate_geometry_task`, `generate_parametric_step_bytes`, `validate_step_bytes`, `generate_parametric_glb_bytes`, `validate_glb_bytes`, `verify_step_glb_congruence`, `execute_cad_geometry_task`, `IsolatedCadWorker`).
- `workers/cad-worker/worker.py` (proceso worker aislado supervisado por `IsolatedCadWorker` con timeout, kill y recuperación).
- `1.AXX/scripts/magic-pen/cad-editor.js` (panel frontend lazy-loaded para edición paramétrica, corte transversal, factor de explosión, badges de procedencia y etiqueta `engineering-unverified`).
- `backend/tests/test_cad_studio.py`.

## 2. Revisión legal y de seguridad

- **Licencia:** Implementación 100% original bajo licencia MIT del proyecto AXX; no se ha copiado código GPL-3.0 de `SOMA`.
- **Seguridad (`I-08`):** Rechazo estricto de `runpy`, `exec`, `eval`, scripts o código arbitrario generado por modelos.
- **Fidelidad (`I-07`):** Diferenciación automática entre cotas documentadas/observadas (`cad_verified`) y cotas inferidas/estimadas (`conceptual`), etiquetando toda estimación estructural como `engineering-unverified`.
