# 20 — Plan de Pull Requests y tareas ejecutables

## Regla de alcance

Un PR tiene un objetivo verificable, lista de archivos, schema/migration impact, feature flag, tests y rollback. **Ningún PR mezcla una gran reestructuración de la app con una nueva capacidad.** El integrador revisa conflictos y merge gate por gate. Cada PR se abre primero en draft hasta pasar pruebas. No se asume que PR, build o publicación puedan completarse desde este paquete.

| PR | Fase | Objetivo | Dependencia | Gate individual |
|---|---|---|---|---|
| PR-00 | 0 | Inventario, baseline, flags no intrusivos, upstream manifest | AXX current HEAD | G0 |
| PR-01 | 1 | TaskGraph declarativo, estado y journal adapter | PR-00 | DAG/recovery |
| PR-02 | 1 | Superpowers skills + verifier service | PR-01 | no bypass CommandService |
| PR-03 | 2 | Scene Document v2 y CAS, adapter v1 | PR-02 | edición reversible |
| PR-04 | 2 | Diagram Studio nodos + export + QA | PR-03 | editor real |
| PR-05 | 3 | CAD worker y modelos paramétricos | PR-03 | STEP/GLB validación |
| PR-06 | 4 | Motion timeline/cutaway/export | PR-03/05 | freeze/render real |
| PR-07 | 5 | Asset Gate Registry y MCP read | PR-03 | licencia/LOD/caches |
| PR-08 | 5 | Diorama/Codevember material mode | PR-06/07 | QA visual/tentáculos |
| PR-09 | 6 | OpenVINO opcional/splat optional | PR-08 | benchmark real |
| PR-10 | 7 | Integración Magic Pen, Windows acceptance, rollback | PR-03–09 | G7 full |
| PR-11 | 8 | Agent Profile SQL/JSON schema/store | PR-10 | no migration loss |
| PR-12 | 8 | Chat membership/Agent Designer/UI | PR-11 | no chat regression |
| PR-13 | 9 | Monaco editor + project read + safe save | PR-12 | editing real |
| PR-14 | 9 | Git worktrees/patch CAS + tests | PR-13 | no dirty overwrite |
| PR-15 | 10 | WorkspaceManager/leases/browser & focus guard | PR-14 | no focus theft |
| PR-16 | 10 | Cua optional/VM provider + telemetry cursor | PR-15 | real Windows QA |
| PR-17 | 11 | Handoff/agent coordinator/event hub | PR-12/15 | ACL/recovery |
| PR-18 | 12 | LSP/DAP/indexer/CI/git review integrations | PR-14/17 | code production QA |
| PR-19 | 13 | Routines/proactive/remote/mobile continuity | PR-17/18 | grants/cost/recovery |

## PR checklist estandarizado

- [ ] Baseline y SHA confirmados, `git status` documentado.
- [ ] Propósito y files owned exactos; no cambios colaterales.
- [ ] Cambios detrás de feature flag (si aplica).
- [ ] API/DB backwards compatible y scopes de seguridad comprobados.
- [ ] Tests positivos/negativos y receipts reales.
- [ ] Crash/cancel/retry `unknown` evaluado.
- [ ] Avatar/Magic Pen/voz/Chat/Android visual y funcional regresiones según scope.
- [ ] Dependencias/asset licenses/SHAs y secretos auditados.
- [ ] Performance baseline vs after con entorno y dataset.
- [ ] Rollback probado; migraciones reversibles sin pérdida.
- [ ] Reviewer independiente aceptó diff.
- [ ] Autoría y release protocol `AGENTS.md` respetados.
- [ ] Reporte PASS/FAIL/BLOCKED/SKIPPED, sin confundir script mock con hardware real.

## Orden de verificación por PR

1. `format / static / schema`.
2. Unit tests focalizados y adversariales.
3. Integration tests en sandbox y datos sintéticos.
4. Legacy regression en fuente.
5. Windows native acceptance si toca UI/PC/voz.
6. Companion compatibility si toca API/mobile.
7. Merge en branch de integración mediante owner único.
8. Release solo cuando haya suma de gates y documentación oficial de AXX cumplida.

## Ejemplo de ticket de PR-14

**Meta:** permitir a agente de código proponer/editar archivos de `worktree` sin sobrescribir trabajo humano. **Entradas:** project_id, branch, allowed roots, base_sha256 y task scope. **Archivos:** `code_studio/git_workspace.py`, `patch_engine.py`, `code_changeset` schema, tests. **Acceptance:** dos worktrees paralelos, editor humano con cambios sin guardar, patch stale revision rechazado; pruebas y diff/rollback verificados. **No hacer:** `git reset --hard` o `git clean -fd` contra repo humano, bypass de CommandService, force push, auto merge, acceso fuera root. **Rollback:** feature OFF, branches intactas, sin daño al workspace principal.
