Fecha: 2026-11-22. Rama: `claude/acts-architecture-integration-d303e9`, base `1f026a0` (HEAD del PR #7).

# AXX Evolution 3.1 · Acts — primer incremento integrado

## Estado declarado

| Estado | Alcance |
|---|---|
| `SOURCE_VERIFIED` | Esquema Act aditivo, `ActInferenceService`, `act_id` en `/axx-api/chat` y `/axx-api/connect/start`, permisos, equipos, Acts Studio, selector de Act y `@mención` en el chat, "Pedir a un Act" en Code Studio. |
| `INTEGRATION_VERIFIED` | Servidor AXX real + router + transporte HTTP real + navegador real (Playwright sobre `Axx.html`). Inferencia real con dos modelos locales distintos (Ollama `llama3.2:1b` y `qwen2.5:7b-instruct`). |
| `NATIVE_VERIFIED` | **No.** No se compiló, instaló ni probó en la app Tauri/WebView2 instalada. |
| `EXTERNAL_BLOCKED` | ChatGPT/Codex para Acts (`axx-connect`): código y contrato listos, sin turno real ejecutado en esta sesión. Escenario multiproveedor (proveedores de distintos fabricantes) no probado: solo había Ollama local. |
| `RELEASE_BLOCKED` | Sin cambio de versión, build, instalación ni publicación. Faltan aceptación nativa y los casos marcados abajo como pendientes. |

No se declara `RELEASE_READY`.

## 1. Recuperación del trabajo de Codex

- Worktree original: `C:\Users\luigi\.codex\worktrees\axx-evolution-3-audit\axx2`, rama `codex/axx-evolution-3-audit-visual-3d-chatgpt`.
- `git status`: limpio. HEAD local `1f026a0` = `origin/codex/axx-evolution-3-audit-visual-3d-chatgpt` (divergencia 0/0).
- El trabajo que el informe daba por pendiente (`recovery.py`, `test_code_recovery.py`, `code-ui.js`, borradores) **ya está confirmado y publicado** en `1f026a0` *feat(code-studio): add multi-file crash journal recovery and persistent editor drafts* (11 archivos, +665/−104). El PR #7 (draft, abierto) apunta a ese commit.
- Comparación con el último HEAD comprobado del handoff (`9d0d938`): `1f026a0` es su hijo directo; no hay más trabajo local.
- No se tocó el worktree de Codex. Esta rama se adelantó (fast-forward) a `1f026a0` y el trabajo nuevo se apila encima.
- Verificación: `test_code_recovery`, `test_code_mutation_safety`, `test_code_studio_core`, `test_agent_profiles_and_chat_bindings`, `test_multiagent_orchestration` → **31 passed, 13 subtests**.

## 2. Arquitectura

```
Acts Studio (view-agent) ──/axx-api/agents/v1/profiles|permissions|teams|preview|catalog──► AgentRegistry (SQLite, misma state.db)
Chat existente ──BrainClient.chat(p + act_id)──► /axx-api/chat ──ActInferenceService.resolve──► router.adapter.route (proveedor/modelo del Act)
                                              └► /axx-api/connect/start ──► CodexProvider (hilo propio del Act, modelo del Act)
                         ActInferenceService.verify_router ──► axx_act {modelo pedido, servido, informado, model_verified}
                         EventHub ◄── run.started / run.completed / run.failed (agent_id = act_id, run_id = request_id)
Code Studio ──"Pedir a un Act"──► composer del chat (selección como datos) ──► mismo flujo
Code Studio ──"Delegar archivo al Act"──► /axx-api/code/v1/worktrees/create (act_id) ──► worktree axx/agent/<act>/<tarea>
            └► Axx.acts.chatAs ──► /axx-api/chat (modelo del Act) ──► archivo completo ──► worktrees/propose-apply
            └► GET changesets (diff) ──► tests/run en su worktree (recibo) ──► worktrees/integrate (grant + recibo)
            └► "Pedir revisión" ──► changesets/review (Act QA) ──► AXX envía diff + recibos al modelo del QA ──► veredicto guardado
            Progreso del equipo ──► notas de AXX en el chat existente (〔Dev〕 → 〔QA〕, veredicto, integración)
            Puerta: EvolutionHTTP._gate_act_code ──► ActInferenceService.authorize_code (grant axx.code por paso)
```

Reglas aplicadas:

- **Un solo chat, un solo router.** `act_id` es un campo opcional de los endpoints existentes. Sin `act_id`, el comportamiento es idéntico al anterior.
- **El servidor decide el modelo.** El proveedor/modelo del cliente se reemplaza por el del perfil. Ruta manual: el router solo acepta ese proveedor+modelo, sin fallback. Ruta `policy`: selección automática gratuita del router (nunca de pago, nunca Codex).
- **Verificación del modelo.** Si el proveedor informa otro modelo, la respuesta se convierte en `MODEL_MISMATCH` y no se entrega.
- **Personalidad = datos.** El texto del Act va como mensaje `system` **después** de la política de AXX. Termina con: no concede permisos ni demuestra acciones.
- **Permisos.** Un Act recibe herramientas de AXX solo con un grant activo `axx.commands`. El grant se vuelve a comprobar antes de despachar (`ACT_PERMISSION_REVOKED`). Ser miembro de un equipo no concede nada. Duplicar o importar no hereda grants.
- **Perfil global intacto.** Un turno de Act en Codex no modifica `selected_model`. Usa la clave de hilo `…:axx-direct-v2:act:<id>`, y el hilo de AXX conserva su clave original.
- **Flag.** Todo pasa por `agent_profiles_v1`, que arranca desactivado. Acts Studio muestra "Activar Acts" para que el propietario decida.

### Herramientas de código para Acts (CODE-04..10)

- **Mismos endpoints, misma maquinaria.** Los Acts usan `worktrees/create`, `worktrees/propose-apply`, `tests/run`,
  `worktrees/integrate` y `worktrees/remove` de Code Studio. No hay un segundo motor de parches ni de pruebas.
- **Permiso por paso.** El grant `axx.code` lleva `operation_kinds` ⊆ `worktree`, `patch`, `test`, `integrate` y un
  `resource_pattern` sobre el `project_id` (`*` desde la UI). Se relee en cada petición; revocarlo bloquea el siguiente paso.
- **Identidad.** Si la petición trae `act_id`, o si el `agent_id`/worktree/cambio pertenece a un Act registrado, la puerta
  aplica aunque falte `act_id`. Un Act solo usa su propio worktree y sus propios cambios. Sin Act de por medio, las acciones
  del propietario en Code Studio no cambian. El propietario siempre puede retirar un worktree.
- **Nunca en la copia principal directamente.** `changesets/propose|apply|rollback` están vetados a los Acts. Su trabajo
  entra al proyecto solo por `worktrees/integrate`.
- **Pruebas antes de integrar.** `integrate` exige `test_report_ids` con recibos del runner supervisado: superados, del mismo
  worktree y proyecto, y posteriores al cambio. La protección existente contra archivos sucios y la CAS por SHA-256 se mantienen.
- **El modelo escribe datos, no permisos.** La respuesta del Act solo aporta el contenido del archivo. AXX lo aplica en el
  worktree, enseña el diff y pide confirmación antes de ejecutar pruebas y antes de integrar.
- **Revisión por otro Act (Dev → QA).** `POST code/v1/changesets/review {act_id, changeset_id}`: el revisor necesita
  `review` en su grant `axx.code` y nunca puede ser el autor. AXX, no el cliente, envía al modelo del revisor el diff y los
  recibos de pruebas posteriores al cambio, con una política que trata ese contenido como datos. Solo vota la **primera
  línea** (`VEREDICTO: APROBADO|CAMBIOS`); cualquier otra respuesta queda como `unclear`. El veredicto se guarda en
  `code_changeset_reviews` con el modelo verificado. Si el Act autor tiene `collaboration.review_required`, integrar exige que
  la **última** revisión sea `approved` y de otro Act. Se publican `handoff.created` (autor → revisor) y `handoff.completed`.
- **Eventos.** Cada paso autorizado publica `tool.dispatched` (`kind: act_code`, operación, ruta, proyecto) cuando la
  petición trae `conversation_id`.

## 3. Contratos y migraciones (aditivos)

- `AgentProfile v1`: campos opcionales `personality` (11 enums + 3 textos + `default_language`), `autonomy.mode` (`manual|assisted|auto_safe|background|scheduled|isolated`), `collaboration` (`mention`, `accepts_handoffs`, `review_required`, `rules`). Los perfiles que no los traen se devuelven igual que antes.
- SQLite: `ALTER TABLE agent_profiles ADD COLUMN behavior_json TEXT NOT NULL DEFAULT '{}'`, condicionado a `PRAGMA table_info`. Sin tablas nuevas de perfiles, conversaciones ni permisos.
- `/axx-api/chat`: entrada `act_id`, `act_revision`; salida `axx_act`. Errores: `ACT_NOT_FOUND` 404, `ACT_DISABLED` 403, `ACT_STALE_REVISION` 409, `ACT_MODEL_UNSET`/`ACT_TRANSPORT_MISMATCH` 400, `MODEL_MISMATCH` 502.
- `/axx-api/connect/start`: entrada `act_id`, `act_revision`. `act_thread` lo asigna solo el servidor (si llega del cliente: 400).
- Rutas nuevas bajo el flag existente: `GET agents/v1/catalog`, `GET|POST agents/v1/profiles/permissions[/grant|/revoke]`, `POST agents/v1/profiles/preview`, `GET|POST agents/v1/teams`. La revocación siempre se permite (ruta de limpieza).
- Code Studio: entrada opcional `act_id` (y `test_report_ids` en `worktrees/integrate`) en las rutas existentes; nuevo `GET code/v1/changesets?changeset_id=` (cambio + diffs); el recibo de pruebas añade `created_at_ms`. Grant nuevo por convención: `tool_id: axx.code` (`worktree|patch|test|integrate|review`). Nueva ruta `POST code/v1/changesets/review`; `GET code/v1/changesets` añade `reviews`. Tabla nueva aditiva `code_changeset_reviews` (CREATE IF NOT EXISTS). Errores de la puerta: 403 `FORBIDDEN`, 404 si el Act/recibo no existe.
- `/v1` móvil y `design-baseline.json`: sin cambios (`companion_contract.check_contract` OK).

## 4. Archivos

| Archivo | Cambio |
|---|---|
| `backend/agents/act_inference.py` | Nuevo: resolución, persona, aplicación a router/Codex, verificación, eventos. |
| `backend/agents/profiles.py` | Validación de secciones Act. |
| `backend/agents/registry.py` | Migración `behavior_json`, persistencia, `revoke_permission`, reemplazo de secciones Act. |
| `backend/agents/http_api.py` | Servicio en runtime, rutas de catálogo/permisos/equipos/preview. |
| `backend/server.py` | `act_id` en `/axx-api/chat`, comprobación de grant antes de despachar, mapeo de errores. |
| `backend/connect/http_api.py`, `backend/connect/provider.py` | `act_id` en Codex, hilo por Act, sin escribir el modelo global. |
| `1.AXX/scripts/agents/acts-studio.{js,css}` | Nuevo: biblioteca, editor de 11 pestañas, selector y `@mención` en el chat. |
| `1.AXX/Axx.html` | Reenvío de `act_id` en `BrainClient.chat` y carga del módulo (sin tocar estilos inline protegidos). |
| `1.AXX/scripts/axx-connect.js` | Reenvío de `act_id` a Codex. |
| `1.AXX/scripts/code-studio/code-ui.js` | "Pedir a un Act"; "Delegar archivo al Act", "Probar en su worktree", "Integrar trabajo del Act"; vista de diff compartida. |
| `backend/agents/act_inference.py` (`authorize_code`), `backend/agents/http_api.py` (`_gate_act_code`, `GET code/v1/changesets`) | Puerta `axx.code` y lectura de diffs. |
| `backend/code_studio/patch_engine.py` (`get_diffs`), `backend/code_studio/test_runner.py` (`created_at_ms` en el recibo) | Campos aditivos. |
| `1.AXX/scripts/agents/acts-studio.js` | Casillas `axx.code` en Herramientas; `Axx.acts.chatAs` compartido por chat y Code Studio. |
| `backend/tests/test_acts_inference.py`, `backend/tests/test_acts_code_tools.py`, `backend/tests/test_acts_ui.py` | Nuevas pruebas. |

## 5. Pruebas ejecutadas

| Comando | Resultado |
|---|---|
| `pytest backend/tests/test_acts_inference.py` | 7 passed + 1 real (Ollama) passed en ejecución separada (62 s) |
| `pytest backend/tests/test_acts_ui.py` | 2 passed (Playwright, `Axx.html` real, backend real; el segundo: permiso `axx.code` → delegar → diff → pruebas → integrar) |
| `pytest backend/tests/test_acts_code_tools.py` | 2 passed (controlado: herramientas + revisión QA) + 1 real passed (60 s): `qwen2.5:7b-instruct` escribió la corrección, pasó las pruebas en su worktree, `llama3.2:1b` la revisó como QA y se integró |
| **Regresión completa** `pytest backend/tests` (incremento de herramientas de código, Ollama activo) | **1757 passed, 14 skipped, 0 failed**, 1188 subtests (23 min). Skips: fixtures nativos opcionales (Edge, Office, Blender, OCR privado, symlinks) |
| **Regresión completa** tras la revisión Dev → QA (Ollama activo) | **1758 passed, 14 skipped, 0 failed**, 1188 subtests (30 min) |
| Regresión: agentes, auditoría HTTP, auditoría funcional, rutinas, smoke, `backend/connect/tests`, Code Studio core/UI/recovery, task graph, Acts | 188 passed, 1 skipped, 3 failed → ver abajo |
| `node test-providers / test-static-assets / test-chat-usability / test-desktop-frontend` | PASS |
| `companion_contract.check_contract` | OK |

Las 3 fallas de la regresión, comprobadas contra la base `1f026a0` en un worktree aparte:

- `test_evolution3_full_functional_audit::test_02` y `test_provider_capability::test_invalid_images…`: timeouts bajo carga (la misma ejecución incluía el modelo 7B). Ejecutadas aisladas en esta rama: **2 passed**.
- `test_code_studio_ui`: el worktree no tenía el bundle Monaco generado (`1.AXX/scripts/vendor`, ignorado por git). Copiado desde el worktree de Codex: **passed**. Para reproducirlo en limpio: `npm ci` y `node scripts/prepare-monaco.cjs`.
- Además, `test-axx-connect.cjs` falla con `axx-translation-` **también en la base**: es preexistente y no lo introduce este cambio.

Evidencia real de Dev → QA (salida de la prueba, recortada):

```
[ACT-CODE-REAL] qwen2.5:7b-instruct wrote calc.py:
def add(a, b):
    return a + b
[ACT-REVIEW-REAL] llama3.2:1b verdict=changes:
VEREDICTO: CAMBIOS
La modificación ... ha alterado su comportamiento con respecto a la suma. ...
```

El revisor de 1B pidió cambios sobre una corrección correcta y con pruebas superadas. AXX guarda el veredicto tal cual: la
calidad de la revisión depende del modelo que el propietario asigne al Act QA.

Evidencia de inferencia real (salida de la prueba):

```
[ACT-REAL] act-dev via llama3.2:1b: Necesito confirmar que aún estoy funcionando...
[ACT-REAL] act-qa via qwen2.5:7b-instruct: Mi nombre de Act es QA.
```

Cada respuesta llegó con `axx_act.responder_model` igual al modelo del Act y `model_verified: true`. La precarga de los modelos en Ollama se hace fuera de AXX y no se cuenta como evidencia.

## 6. Matriz de aceptación

Entorno: Windows 11, Python 3.12, Chromium (Playwright), servidor AXX lanzado por la prueba, no la app instalada.

| Caso | Estado | Evidencia / motivo |
|---|---|---|
| ACT-01 identidad | PASS | UI crea "Dev" y la BD lo relee. |
| ACT-02 forma (24) | PASS | Helix desde la UI. El esquema valida 0..23. |
| ACT-03 paleta y material | PASS | Ocean + material validado. |
| ACT-04 personalidad e instrucciones | PASS | La persona servida contiene las instrucciones y "Usa un tono formal". |
| ACT-05 proveedor/modelo reales | PASS (router) | Proveedores reales de la config del router. Codex: solo SOURCE. |
| ACT-06 persistencia tras reinicio | PASS | El registro reabierto sobre la misma `state.db` conserva todas las secciones. |
| ACT-07 avatar/modelo global intactos | PASS (UI) | `prefs.provider/model` sin cambios tras un turno de Act. En Codex, `selected_model` no se escribe: solo SOURCE. |
| ACT-08 convertir chat existente | PENDIENTE | `bindings/convert` de Codex existe con prueba backend; no está conectado a la UI de Acts. |
| ACT-09 respuesta real del modelo del Act | PASS | Ollama real, dos Acts. |
| ACT-10 cambio de modelo sin hilo viejo | PASS (router) | Revisión vieja → 409; la nueva usa `model-beta`. Codex: clave de hilo por Act + D05 existente, solo SOURCE. |
| ACT-11 Team con dos Acts | PASS | `POST/GET agents/v1/teams`; sin permisos implícitos. |
| ACT-12 modelos independientes | PASS parcial | Dos modelos reales distintos del mismo motor (Ollama). Multiproveedor: EXTERNAL_BLOCKED. |
| ACT-13 handoffs/progreso en el chat | PASS (Dev → QA en Code Studio) | `handoff.created/completed` en EventHub y notas de AXX en el chat existente: cambio aplicado, pruebas, traspaso a QA, veredicto e integración. Sin vista dedicada de handoffs para otros flujos. |
| ACT-14 revocar → bloquear | PASS | Grant/revocación por HTTP; la siguiente resolución no concede herramientas. El bloqueo en el despacho está en el código, pero no se ejercitó con una herramienta real. |
| CODE-01/02 Monaco + proyecto real | PASS | `test_code_studio_ui` (Codex). |
| CODE-03 selección → Act | PARCIAL | "Pedir a un Act" coloca la selección en el chat y el Act responde con su modelo. Sin prueba de UI propia. |
| CODE-04 worktree propio del Act | PASS | Rama `axx/agent/act-dev/<tarea>`; sin grant → 403; el nombre de un Act registrado no sirve de etiqueta libre. |
| CODE-05 parche escrito por el modelo del Act | PASS | Controlado + **real**: `qwen2.5:7b-instruct` escribió la corrección por `/axx-api/chat` con `model_verified`. Solo cambia el worktree. |
| CODE-06 diff | PASS | `GET code/v1/changesets` y editor de diferencias de Monaco (UI). |
| CODE-07 pruebas en su worktree | PASS | Subprocesos reales del runner supervisado: falla antes del parche y pasa después. |
| CODE-08 revisión | PASS | El propietario revisa el diff. Revisión por un Act QA ejecutada por AXX: controlada (aprobado/cambios/sin veredicto) y **real** (`llama3.2:1b` revisó el cambio de `qwen2.5:7b-instruct` con modelo verificado). Con `review_required`, sin aprobación de otro Act → 403. |
| CODE-09 integración | PASS | Sin grant `integrate`, sin recibos, con recibo fallido o anterior al cambio → 403. Con recibo válido, el archivo del proyecto coincide con el SHA propuesto. |
| CODE-10 aislamiento y revocación | PASS | Otro Act no puede parchear ni probar en ese worktree; `changesets/*` vetado; revocar bloquea el siguiente paso; las acciones del propietario siguen igual. |
| CODE-11..14 borradores, recuperación multiarchivo, ediciones externas, metadatos Git | PASS | Pruebas recuperadas de Codex (31 passed). |
| PC-01..05 | PENDIENTE | Este incremento no los aborda. Codex ya marcó Browser/UIA/VM como `unsupported_mode` (D15/D17). |
| ROUTINE-01..03 | PENDIENTE | No hay dispatcher real (D21 sigue abierto). |
| VISUAL-01 24 formas × 9 paletas | PARCIAL | Catálogo y validación completos. Las miniaturas son el SVG genérico del backend, no del renderer real de AXX. |
| VISUAL-02 renderer principal intacto | SOURCE_VERIFIED | Ningún archivo del renderer modificado; línea base de diseño OK. |
| VISUAL-03 rendimiento | PENDIENTE | No medido. |
| Demo final Dev/Visual/QA | NO ALCANZADA | Dev → QA funciona desde Code Studio con el progreso en el chat. Faltan el Act Visual (Magic Pen/3D), lanzar el equipo con una sola frase escrita en el chat y la aceptación nativa. |

## 7. Funciones no disponibles en este incremento

Vista dedicada de handoffs fuera de Code Studio. Act Visual en el equipo. Ejecución de equipo desde una sola frase con TaskGraph. Miniaturas desde el renderer real. Voz por Act conectada al TTS (los campos se guardan, el motor aún no los lee). Límites del ResourceGovernor por Act. Scheduler de rutinas. LSP/DAP reales. Computer Use por Act.

## 8. Rollback

1. Desactivar `agent_profiles_v1` ("Desactivar Acts" o `POST /axx-api/agents/v1/flags/set`): los turnos con `act_id` se rechazan y el chat responde solo como AXX; los pasos de Code Studio de un Act también se rechazan. Los worktrees de Acts quedan en disco y el propietario puede retirarlos.
2. Revertir los commits de esta rama. La columna `behavior_json` es aditiva y el código anterior la ignora, así que no hace falta revertir la BD.
3. Los hilos Codex de Acts usan claves propias y no alteran el hilo de AXX.
