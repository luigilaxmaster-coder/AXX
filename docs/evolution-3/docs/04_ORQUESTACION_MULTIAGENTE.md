# 04 — Orquestación, TaskGraph, handoff, eventos y recuperación

## 4.1 Fuentes y decisión

Superpowers (`obra/superpowers`) aporta el proceso brainstorming/planificación/TDD/revisión/verificación. OpenMausBot (`server/harness/registry.ts`, `bus.ts`, `group-goal-run.ts`) aporta patrones de agentes persistentes, fan-in de eventos, coordinación de grupos, historial por equipo, fallback explícito. OpenDots (`src/server/dot-agent.ts`, `runner.ts`, `runtime-scope.ts`) aporta scopes, trabajos persistentes, revisión humana y canal de eventos. AXX ya tiene `ActionLearning`, `SkillMemory` y `CommandService`: se **componen** estos enfoques, no se monta una flota paralela.

## 4.2 Agente, rol y modelo no son lo mismo

- **AgentProfile:** identidad persistente y restricciones.
- **RoleCapability:** contrato de skill, tools y verificación.
- **ModelRuntime:** proveedor temporal que interpreta/resuelve tareas.
- **ExecutionEnvironment:** sandbox/worktree/VM/browser/físico.
- **Conversation:** comunicación y trazabilidad.
- **TaskGraph:** DAG versionado que ejecuta trabajo independiente.

Un agente puede cambiar de modelo sin cambiar de identidad. Un mismo modelo puede servir a varios agentes sin exponer su memoria. Una tarea puede ejecutarse sin cursor ni VM.

## 4.3 Modelo de tareas

```text
submitted -> validated -> planned -> ready -> leased -> running
                                  |                   |
                                  v                   v
                             waiting_input       verifying -> completed
                                  |                   |
                             ready (revision)         +-> repairable_failed -> ready
                     running -> waiting_approval -> running
                     running -> interrupted -> reconcile -> (completed|ready|blocked)
                     any pre-effect -> cancelled
                     dispatched-effect -> cancelled_with_effects | unknown
```

No permitir estados terminales ambiguos. Las mutaciones deben registrar su operación **antes** de despachar y verificar postcondición **después**. `cancelled` no implica rollback, y `unknown` nunca vuelve a `ready` por timeout simple. `READY` exige que dependencias hayan terminado con evidencia o que las dependencias se hayan dispensado explícitamente.

### Reglas TaskGraph

- DAG acíclico, `node_id` estable, `graph_version`, `task_id`, `parent_id`, `inputs` como refs con SHA y revision.
- Máximos configurables iniciales: 2–3 workers en portátil según benchmark; profundidad de delegación <= 2; límite de reintentos por clase de error; presupuesto total del grafo.
- `task_result` debe incluir estado + evidencias + qué **no** se pudo comprobar.
- Pueden ejecutarse simultáneamente lecturas independientes, ramas Git aisladas, navegadores/perfiles distintos. Las mutaciones compiten por recursos y solo entran si Scheduler otorga lease.
- Prohibido declarar completado por el mensaje del LLM: el verificador requiere postcondiciones independientes.

## 4.4 Handoff tipado

Consultar `schemas/handoff.schema.json`. El padre emite paquete con `task_id`, origen/destino, scopes/permissions delegados (no editables por el modelo), refs de artefactos de entrada, objetivos, formato de salida, límites de tiempo/coste, deadline, criterios de aceptación, `idempotency_key` y `correlation_id`.

La respuesta incluye `handoff_id`, estado, `artifact_refs`, `evidence_refs`, errores estructurados y consumo real. No transferir chats enteros por defecto; preferir resumen mínimo autorizado del proyecto. La transcripción de un agente nunca se convierte en instrucciones de sistema para otro. Tratarla como contenido no confiable.

### Handoff no autorizado

Ejemplo: agente A puede leer un repo pero agente B solicita editar un archivo fuera del proyecto. Resultado: `permission_denied` verificable y posible solicitud de aprobación al usuario. El coordinador no puede elevar scopes reescribiendo un prompt.

## 4.5 Routing de agentes

1. Filtros deterministas de tipo de tarea, tools, modality y scopes.
2. Evaluar `capability_certifications` y disponibilidad real; modelos con herramienta declarada pero no probada se etiquetan experimental.
3. Seleccionar candidatos por coste/p95, compatibilidad con archivo/entorno y política de riesgo.
4. Si ambiguo: lead original, no transferir permisos.
5. Registrar decisión (modelo/versión/criterios) sin exponer razonamiento privado.
6. Fallos de proveedor: solo fallback si previamente autorizado; no cambiar de modelo manual seleccionado sin avisar.

## 4.6 Recursos y locks

`ResourceLease` = `(resource_type, resource_key, owner_run_id, expires_at, fencing_token, state)`; tipos `host_input`, `window(hwnd+pid+start)`, `browser_profile`, `workspace_write`, `repo_branch`, `gpu_heavy`, `vm_instance`, `microphone`, `remote_worker`. Fencing token monotónico, revalidación al despacho. TTL no garantiza deshacer una acción: un lease expirado solo autoriza reasignación tras conciliación del estado real.

**Orden global de locks:** scope de proyecto -> workspace/repo -> archivo -> ventana/host_input -> GPU/worker. Implementadores no deben mantener transacción SQLite abierta mientras aguardan proceso externo.

## 4.7 EventHub

`agent.created`, `agent.updated`, `run.queued`, `task.started`, `task.progress`, `tool.prepared`, `approval.requested`, `approval.resolved`, `tool.dispatched`, `tool.verified`, `artifact.created`, `handoff.created`, `handoff.completed`, `run.failed`, `run.unknown`, `run.completed`, `run.cancelled`. Schema en `schemas/runtime-event.schema.json`.

SSE `Last-Event-ID`, snapshots idempotentes, secuencia por conversación en transacción, límites de payload, poda según política. No guardar tokens/keys o eventos gigantes. Deltas textuales opcionales y efímeros, eventos terminales persistidos antes de notificación. El render de una tarjeta nunca supone una aprobación.

## 4.8 Crash/reinicio y recovery

- En startup, marcar sesiones `running` sin lease confirmado como `interrupted` y listar trabajos pendientes.
- Comparar dispatch journal del CommandService para cada efecto. Si no hubo dispatch, puede replanificar conservando ID/contrato. Si pudo haber efecto externo: `unknown`; no repetir hasta reconciliación específica.
- Se pueden reanudar cálculos puros con inputs versionados/hashes. Para tasks costosas usar checkpoint y semilla determinista.
- Antes de reanudar, comprobar caducidad de grants, scope memory generation, revisión de archivo, existencia de modelo/worker, presupuesto y conexiones.
- Si se perdió un worker remoto: autenticar la identidad, confirmar logs/artefactos firmados antes de aceptar `completed`.
- Errores de verificador se etiquetan `verification_unavailable`, no éxito.

## 4.9 Revisión de código y Magic Pen

Un agente constructor propone; un verificador independiente inspecciona contra contrato. Checks mínimos: `spec_compliance` y `quality`. En código: diff, tests, permisos, dependencia y regresiones. En CAD: geometría y unidad. En escena: hashes, snapshots, animación, FPS. En Computer Use: observación postefecto. La revisión es complementaria a pruebas reales, no reemplazo.

## 4.10 Pruebas de orquestación

DAG cíclico rechazado; 2 tareas independientes en paralelo; 2 mutaciones mismo archivo serializadas; cross-agent intent read denied; scopes revocados a mitad de run; timeout de proveedor; crash antes/después de despacho; pérdida SSE + replay; reintentos idempotentes puros; `unknown` permanece bloqueado; cost budget cancela trabajos pendientes; cancelación no confunde con undo; tool output malicioso no modifica políticas; relay a PC sin grant bloqueado.
