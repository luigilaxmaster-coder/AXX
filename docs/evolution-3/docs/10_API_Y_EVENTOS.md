# 10 — APIs y eventos de AXX Agent Workspace (propuesta)

**Todos los endpoints de esta página son propuestos; no se han visto implementados en `main` v0.22.52.** Seguir el middleware/autenticación del host AXX. No publicarlos en red pública por defecto. Las rutas `/v1` existentes conservan contrato original; las nuevas se añadirán bajo namespace versionado si fuera necesario.

## 10.1 Rutas propuestas

| Método y ruta | Descripción | Efecto |
|---|---|---|
| `GET /axx-api/agents/v1/profiles` | Lista de agentes sin secretos | lectura |
| `POST /axx-api/agents/v1/profiles` | Crear agente validado | DB mutación con operation_id |
| `GET /axx-api/agents/v1/profiles/{id}` | Detalle con capacidades efectivas | lectura |
| `PATCH /axx-api/agents/v1/profiles/{id}` | CAS por revision/If-Match | mutación |
| `POST /axx-api/agents/v1/profiles/{id}/disable` | Bloquear nuevas tareas | mutación |
| `POST /axx-api/agents/v1/conversations/{id}/members` | Vincular miembro al chat original | mutación |
| `DELETE /axx-api/agents/v1/conversations/{id}/members/{agent_id}` | Revocar vínculo | mutación |
| `POST /axx-api/agents/v1/runs` | Crear run de tarea o equipo | prepara, no concede herramientas |
| `GET /axx-api/agents/v1/runs/{run_id}` | Estado y evidencias | lectura |
| `POST /axx-api/agents/v1/runs/{run_id}/cancel` | Solicitud idempotente cancelación | mutación |
| `POST /axx-api/agents/v1/runs/{run_id}/resume` | Validar y reanudar seguro | condicionado |
| `POST /axx-api/agents/v1/handoffs` | Handoff scope atenuado | mutación |
| `GET /axx-api/agents/v1/conversations/{id}/events` | SSE por chat; Last-Event-ID | lectura |
| `GET /axx-api/agents/v1/conversations/{id}/snapshot` | Estado/cursor de eventos | lectura |
| `GET /axx-api/workspaces/v1` | Lista entornos permitidos | lectura |
| `POST /axx-api/workspaces/v1/lease` | Reserva tipada de workspace | control |
| `GET /axx-api/code/v1/projects` | Proyectos autorizados | lectura |
| `POST /axx-api/code/v1/changesets` | Generar propuesta patch/diff | prepara |
| `POST /axx-api/code/v1/changesets/{id}/apply` | Aplicar a worktree con CAS | mutación revisada |
| `GET /axx-api/spatial/v2/scenes/{id}` | SceneDocument v2 | lectura |
| `POST /axx-api/spatial/v2/scenes/{id}/patches` | Edición incremental/CAS | mutación |

Rutas exactas se deben armonizar con `backend/server.py`, scopes y pruebas HTTP reales antes de implementar. No crear handlers que admitan comandos arbitrarios ni introducir lógica de autorización solo en frontend.

## 10.2 Envelopes HTTP

Requests mutantes usan `operation_id` estable, `idempotency_key`, `expected_revision` cuando corresponde, `conversation_id`, `agent_id` y token/autorización host; *validación de sesión real* la adjunta el backend, no se cree a partir de valores enviados por el modelo.

Éxito:

```json
{ "schema_version":"1.0", "operation_id":"op-123", "status":"accepted", "resource_id":"agent-456", "revision":2, "request_id":"req-123" }
```

Error:

```json
{ "schema_version":"1.0", "error": {"code":"stale_revision", "message":"El recurso cambió desde la lectura", "retryable":false, "request_id":"req-123"}}
```

Códigos sugeridos: `400 invalid_request`, `401 unauthorized`, `403 forbidden`, `404 not_found`, `409 stale_revision|resource_conflict|unknown_effect`, `412 stale_observation`, `422 unsupported_mode`, `423 resource_locked`, `429 rate_or_budget_limit`, `503 backend_unavailable|capability_missing`, `504 tool_timeout`. Evitar retornar detalles sensibles de rutas internas, prompts o tokens.

## 10.3 SSE y event sourcing

`Content-Type: text/event-stream`, `Cache-Control: no-cache`, autenticación según diseño del host. Cada frame:

```text
id: 184
event: task.progress
data: {"schema_version":"1.0","seq":184,"event_id":"evt-184","conversation_id":"chat-001","agent_id":"dev-001","run_id":"run-001","type":"task.progress","timestamp":"2026-11-21T16:00:00Z","payload":{"message":"3/5 pruebas","completed_steps":3,"total_steps":5}}
```

SSE por **conversation_id** con `seq` monotónica, no `seq` global de instalación. `Last-Event-ID` se valida contra la conversación autorizada, límites de antigüedad y snapshot. Si replay expiró, responder snapshot + marcador de hueco, no inventar eventos perdidos. Manejar reconexión de WebView, duplicados y desorden de llegada.

## 10.4 API de aprobaciones

Usar circuito `CommandService` actual para acciones de host y efectos. Las tarjetas de agentes son proyecciones de solicitudes preparadas. El backend asegura `approval_request_id` ligado a tool ID, argumentos, ventana/recurso, actor y permiso vigente. Reintentar HTTP de aprobar con `operation_id` no despacha dos veces. Revocar/deshabilitar agente invalida aprobaciones pendientes antes de dispatch.

## 10.5 Code Studio

Una edición propuesta produce ChangeSet y devuelve `preview`, `before_sha256`, `after_sha256`, `file_count`, `diff_digest` y riesgo. `apply` requiere `base_sha256` vigente y permiso de `workspace_write`. No se permite pasar `shell_command` arbitrario como argumento del patch. Tests se ejecutan con adaptador de toolchain registrado, ruta aprobada y un worker con límites.

## 10.6 Escenas y assets

`SceneDocument` lleva `revision`, `units`, `fidelity`, `objects`, `asset_refs`, `timeline`, `source`; `ScenePatch` incluye `base_revision` y target whitelist; API rechaza operaciones a IDs no existentes. `AssetDescriptor` conserva `license`, `credit`, `origin`, `sha256`, `size_bytes`, `dimensions`, `decoders` y `redistribution_allowed`. Un asset externo nunca se monta con acceso remoto a host sin download autorizado.

## 10.7 API security tests

No-cors/CSRF/origen indebido, host auth ausente, 2 clientes con misma revision, 2 approvals same ID, SSE de otra conversación, payload>limits, malformed ID/UTF-8/JSON, path traversal/symlinks, disabled agent, expired grant, revoked context, tool response con HTML malicioso. Test GET nunca provoca inferencia/coste/descarga de assets por accidente.
