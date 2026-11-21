# Fase 5 (`PR-07` y `PR-08`) — Especificación: Asset Gate Registry, Diorama Mode y Materiales Codevember Aislados

- **Fase:** 5 (`PR-07`, `PR-08`)
- **Rama:** `feature/axx-evolution-3`
- **Dependencia:** `PR-03`, `PR-06` (`Gate G2` y `Gate G4` aprobados)
- **Gate objetivo:** `G5` (`MP-06`, `MP-07`, `MP-08`, `E2E-12`)

## 1. Archivos implementados

- `backend/spatial/asset_registry.py` (`PR-07`: almacén content-addressed `AssetRegistry` por SHA-256, validación de licencias/créditos/LOD/decoders/triángulos, bloqueo de descargas automáticas remotas y de modelos excluidos de MIT como Kervan, preservación de hashes antiguos con `upgrade_notice` `E2E-12` y búsqueda read-only sin `generate_asset` de pago).
- `backend/spatial/diorama_engine.py` (`PR-08`: modos Diorama y materiales selectivos Codevember restringidos a `magic_pen_scene`, protección `AvatarMaterialProtectedError` del avatar principal/tentáculos/hitmask `MP-06`, y QA por entidad `evaluate_diorama_qa` para actores congelados, teletransportados, fuera de cámara o sin atribución `MP-08`).
- `1.AXX/scripts/magic-pen/asset-browser.js` (panel frontend lazy-loaded de catálogo Asset Gate y selector Diorama).
- `backend/tests/test_asset_gate_and_diorama.py`.
