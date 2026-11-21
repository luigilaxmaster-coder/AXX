# Fase 0 (PR-00) — Especificación: Baseline, Auditoría, Feature Flags y Manifiesto Upstream

- **Fase:** 0 (`PR-00`)
- **Rama de trabajo:** `feature/axx-evolution-3` (worktree aislado en `build/evolution-3-worktree`)
- **SHA base:** `508bceabc718905db9bcf4042992d91f4c6c0705` (`v0.22.52`)
- **Gate objetivo:** `G0`

## 1. Alcance y archivos de `PR-00`

1. Incorporación íntegra del paquete técnico `AXX_EVOLUTION_3_TECHNICAL_PACK` bajo `docs/evolution-3/`.
2. Auditoría completa de las capacidades existentes en `508bceabc718905db9bcf4042992d91f4c6c0705` clasificadas por estado (`EXISTING_VERIFIED`, `EXISTING_UNVERIFIED`, `PARTIALLY_IMPLEMENTED`, `MISSING`, `BROKEN`, `BLOCKED_BY_ENVIRONMENT`).
3. Registro de feature flags no intrusivos (`backend/evolution_flags.py`) con los 12 flags requeridos en `docs/14_DESPLIEGUE_Y_ROLLBACK.md`, todos con default `OFF` (`False`), control de concurrencia CAS por `revision`, bitácora de auditoría SQLite y validador del manifiesto upstream (`records/upstream-lock.json`).
4. Pruebas unitarias de `PR-00` en `backend/tests/test_evolution_flags.py`.

## 2. Invariantes verificados

- `I-01`: Ningún segundo ejecutor; `CommandService` y `ActionExecutor` siguen siendo autoridad única.
- `I-04` / `I-05`: Ninguna superficie protegida en `mobile/design-baseline.json` ni ruta `/v1` ha sido alterada.
- `I-12`: `main` permanece intacto en `508bceabc718905db9bcf4042992d91f4c6c0705`; todo el desarrollo ocurre en `build/evolution-3-worktree`.
