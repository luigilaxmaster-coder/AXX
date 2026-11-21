# 19 — Mapa de integración por archivo y puntos de acoplamiento

> Todos los nuevos paths son **propuestos**, no módulos presentes. Cada tarea comienza comparando el checkout exacto con el SHA de baseline. No tocar más archivos de los necesarios y no editar otro agente's worktree.

## 19.1 Secuencia de integración con el AXX real

| Orden | Archivo o servicio actual | Cambio permitido | Contrato que debe conservarse |
|---|---|---|---|
| 1 | `AGENTS.md` | Leer, no editar salvo cambio de política humano | Author/release/Android/visual |
| 2 | `backend/server.py` | Agregar router autenticado aditivo/feature gated | Rutas legacy, auth y `/v1` |
| 3 | `backend/chat_store.py` | Enlazar AgentRegistry sin modificar semántica de chat | Conversaciones/TTL/forget/Connect |
| 4 | `1.AXX/scripts/chat-workspace.js` | Añadir agente/roster/teams tras feature flag | Nueva conversación/borrador/contexto/operations |
| 5 | `1.AXX/scripts/agent-profile.js` | Enlace a Agent Designer; perfil global sigue separado | Perfil global AXX intacto |
| 6 | `backend/action_learning.py` | Integrar TaskGraph/skills y trace | Acciones aprendidas ya disponibles |
| 7 | `backend/memory/skill_memory.py` | Punteros a skills/verificación de agente; no duplicar | Evidencias/versiones/select policy |
| 8 | `backend/commands.py` | Registrar IDs de acciones nuevas y permisos tipados | Un solo CommandService |
| 9 | `backend/actions/executor.py` | Añadir adaptadores aprobados y verificación | Journal y unknown/reconcile |
| 10 | `backend/inference/adapter.py` | Resolver profiles de agentes, budgets, cancelación | Proveedor manual y source policies |
| 11 | `backend/computer_use.py` | Añadir router/leases con hooks, nunca bypass | Grants efímeros, ventana/proceso, bloqueos |
| 12 | `backend/actions/desktop_input.py` | Solo posibles adaptadores por acción evaluada | Observación/target/TTL/resultado |
| 13 | `backend/actions/browser_bridge.py` | Multiprofile/session provider behind policy | Loopback, browser explicit, no personal profile |
| 14 | `backend/actions/file_workflows.py` | Integración con WorkspaceManager, root allowlist | No overwrite e idempotencia |
| 15 | `backend/actions/process_runner.py` | Reusar solo para procesos aprobados | No renombrarlo ni promocionarlo a sandbox |
| 16 | `backend/magic_pen.py` | Añadir Document v2/asset refs/revisions sin borrar viejo | Captura y origen inmutable |
| 17 | `backend/presentation_plan.py` | Versionar contratos v1/v2, no mutar semántica v1 | Plan v1 validado y legacy |
| 18 | `backend/spatial_pipeline.py` | Nuevos adaptadores CAD/Diagram, no reemplazar catálogo | Identificación y reparaciones actuales |
| 19 | `backend/shape_registry.py` | Registrar partes CAD importadas/versionadas | Catálogo de componentes actual |
| 20 | `1.AXX/scripts/magic-pen.js` | Nuevo módulo lazy-load por modo | Ink, DPI, gesture, undo/redo/stop |
| 21 | `1.AXX/scripts/spatial-scene.js` | SceneDocument adapter / material opt-in | Renderer legacy y performance |
| 22 | Renderer avatar real PC | Solo adaptador/miniaturas y transición aprobada | Apariencia, tentáculos, hit mask, hotkeys |
| 23 | `mobile/js/avatar-engine.js` | Catálogo/check compat, sin cambiar forma por agente | 24/9 y Android baseline |
| 24 | `docs/mobile/COMPATIBILITY-PROTOCOL.md` | Consultar en cada fase | No cambiar /v1 y pairing |
| 25 | `scripts/release.py` y release docs | Reusar proceso oficial, no editar versiones sueltas | Recibos, SHA, instalación |

## 19.2 Backend Agent Registry — integración mínima

1. `backend/agents/profiles.py`: DTOs y validación JSON schemas; refs opacas de modelos y secretos. No ejecutar efecto.
2. `backend/agents/registry.py`: transacciones SQLite breves, crear/leer/revisar/desactivar perfiles; revision CAS; sanitización y límites.
3. `backend/agents/bindings.py`: `conversation_id` a N perfiles; asegura que chat existe, está autorizado, `memory_scope/generation` vigente; desvincular no borra chat.
4. `backend/agents/policy.py`: resolver allowlist/intersección de permisos; backend authoritative y unit tests negativos.
5. `backend/agents/events.py`: outbox/journal de eventos por conversación; SSE replay, redaction y ACL.
6. `backend/agents/recovery.py`: reconcile de tareas y ledger sin duplicate effect.
7. `backend/server.py`: endpoints versionados detrás de `feature_flag`; no endpoints que acepten `python`, shell o scripts de modelo sin registro.

Tests nuevos candidatos: `backend/tests/test_agents_profiles.py`, `test_agents_bindings.py`, `test_agents_policy.py`, `test_agents_events.py`, `test_agents_recovery.py`; nombres a ajustar a runner actual. Comprobar PRAGMA y privacidad con BD sintética.

## 19.3 Multiagent Orchestrator

1. `backend/agents/task_graph.py`: DAG JSON validated, límites, dependencias, type sets, all immutable task IDs.
2. `backend/agents/orchestrator.py`: dispatch `ready`, lease, ejecución `CommandService`/worker, reporte de progreso, reconcilia.
3. `backend/agents/handoffs.py`: scope atenuado, artefactos por hash, review gates.
4. `backend/agents/scheduler.py`: recurso lease/fencing; owner host físico único, prioridades y quotas.
5. `backend/agents/routines.py`: schedules/eventos con opt-in, paused import, no auto-computer grant.

Tests: DAG cycle, dependency fail, retry pure job, unknown effect, permission revocation, event replay, crash restore, 2 agents mutate same target, 3 agents collaborate with reviewer. Mantener `ActionLearning` responsable de skills y procedimientos; TaskGraph no genera comandos sin permiso.

## 19.4 Code Studio integración por capa

**Frontend:** `1.AXX/scripts/code-studio/code-workspace.js` (mount/unmount panels), `code-editor.js` (Monaco), `code-diff.js` (diff editor), `git-panel.js`, `problems-panel.js`, `terminal-panel.js`. Todo lazy-loaded/local bundled y capaz de liberar recursos al cerrar; sin CDN.

**Backend:** `code_studio/projects.py` (project roots), `patch_engine.py` (CAS/hash/atomic write), `git_workspace.py` (worktrees), `language_servers.py` (LSP server lifecycle), `debug_adapters.py` (DAP opcional), `test_runner.py` (recibos), `indexer.py` (tree-sitter/symbol maps), `artifact_link.py` (resultados). Cada mutación se traduce a una acción tipada conforme al ejecutor; no invocar proceso arbitrario desde WebView.

**Orden correcto:** primero explorador/Monaco read-only -> guardado seguro humano -> Git diff/worktree -> patch proposal/verification -> LSP -> tests -> DAP. No construir DAP antes de que patch/gits sean confiables.

## 19.5 Computer Use background integración por capa

`workspaces/manager.py`: workspaces diferentes del root principal; `leases.py`: exclusividad; `focus_guard.py`: policy ask/queue/isolated/deny; `browser_sessions.py`: perfiles aislados; `vm_provider.py`: abstracción y capability probe real; `remote_protocol.py`: handshake + auth + artifact transfer. Cada capa expone `probe`, `prepare`, `execute`, `verify`, `cancel`, `release`. Adaptador Cua se integra detrás de `ComputerUse` y `CommandService`. No sustituir las rutas `computer_use` existentes ni asumir `SendInput` background.

### Condición de integración Cua

Debe pasar caso por caso: acción, ventana, versión del OS y app, sin cambio de cursor físico/foco, resultados visibles, no escalada. El protocolo del cursor de agente lleva IDs de sesión y herramientas, no inyecta entrada por dibujarse.

## 19.6 Magic Pen integración por capa

`spatial/scene_document.py` valida v2 e importa v1 no destructivamente; `spatial/patches.py` CAS; `spatial/asset_registry.py` hash/licencia/provenance; CAD worker parametrizado; `render_jobs.py` timeline/captura por frame. UI: `magic-pen/diagram-editor.js`, `cad-editor.js`, `asset-browser.js`, `scene-history.js`, `timeline-editor.js`; todos módulos aislados y cargados cuando se abren. Al cerrar, liberar listeners/contexts, conservar objetos y revisiones en backend.

**Prueba de no regresión decisiva:** desactivar todos los flags hace que Magic Pen siga actuando exactamente como v0.22.52 en su conjunto de pruebas de referencia.

## 19.7 Policy de modificabilidad de archivos

Archivos sensibles (`AGENTS.md`, `release.py`, manifests, `backend/server.py`, `1.AXX/Axx.html`, `src-tauri`, `mobile`, `docs/mobile`, renderer avatar) tienen **single-writer owner** durante integración. Módulos nuevos pueden desarrollarse en worktrees separados sin compartir output paths. PRs no mezclan Magic Pen, Chat, Code Studio y versión de release en un solo commit salvo integración final explícita.
