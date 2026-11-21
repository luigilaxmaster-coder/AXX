# Fase 1 (`PR-01` y `PR-02`) — Especificación: TaskGraph Declarativo, Superpowers y VerifierService

- **Fase:** 1 (`PR-01`, `PR-02`)
- **Rama:** `feature/axx-evolution-3`
- **Dependencia:** `PR-00` (`Gate G0` aprobado)
- **Gate objetivo:** `G1` (`ORCH-01`, `ORCH-02`, `ORCH-04`, no bypass `CommandService`)

## 1. Archivos implementados

- `backend/agents/__init__.py`
- `backend/agents/task_graph.py` (`PR-01`: `TaskGraphEngine`, validación topológica DAG Kahn, detección de ciclos `CycleDetectedError`, límite de profundidad `max_delegate_depth <= 2`, máquina de estados de 18 estados, persistencia previa al despacho, bloqueo de re-ejecución ante `unknown` `UnknownEffectBlockedError`, reconciliación de crash contra el journal de `ActionExecutor`).
- `backend/agents/superpowers.py` (`PR-02`: `IndependentVerifierService` y `SuperpowersWorkflowService` con etapas `plan -> tdd_red -> implement_green -> review`, separación de roles `planner`/`tester`/`implementer`/`reviewer`/`verifier`, prohibición de auto-verificación y de completado por texto del LLM sin evidencia de postcondiciones).
- `backend/action_learning.py` (integración aditiva de `self.task_graph`, `self.verifier` y `self.superpowers` con reconciliación automática al iniciar y cierre ordenado en `close()`).
- `backend/tests/test_task_graph_and_superpowers.py` (pruebas unitarias, de presupuesto y de inyección de fallos/crash).
