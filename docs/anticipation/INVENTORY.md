# Inventario de anticipación contextual

Fecha: 29 de octubre de 2026. Este inventario describe las fuentes inspeccionadas; no acredita implementación nueva ni aceptación física.

## Baseline y propiedad

- `work_id`: `anticipation-contextual-20261029`; integración y entrega: agente raíz de este chat.
- Worktree: `C:\Users\luigi\.codex\worktrees\anticipation-contextual\axx2`; rama `codex/anticipation-contextual`.
- Commit base: `2d1f668fb2753d14c7d454141b351b767532ed43`, procedente de `codex/mobile-companion-20261028`. El worktree nuevo comenzó limpio.
- El checkout original `C:\Users\luigi\Desktop\axx2` tenía cambios previos de Telegram, empaquetado, servidor, Android y evidencia. No se incorporan ni se revierten desde este trabajo.
- Propietarios: raíz, `backend/server.py`, `backend/commands.py`, `backend/action_learning.py`, transporte HTTP/aceptación instalada e integración/entrega; trabajador backend, `backend/anticipation.py` y `backend/tests/test_anticipation.py`; trabajador UI, `1.AXX/scripts/anticipation.js`, su inclusión y pruebas, integración de voz/sorpresas; trabajador de gates, estos dos documentos y revisión independiente. Nadie más cambia versiones, construye, instala ni publica.
- No se reservaron recursos físicos en el inventario. Las pruebas de teclado, ratón, foco y ventanas requieren propietario único y comprobar que el broker esté libre. Un lock expirado no demuestra que terminó otro trabajo.
- A la inspección inicial, los demás chats visibles del proyecto estaban inactivos. Eso no transfiere propiedad sobre sus cambios.

## Interfaces reales reutilizables

| Responsabilidad | Fuente y contrato observado | Uso y límite |
| --- | --- | --- |
| Ejecución y journal | `backend/actions/executor.py`: `ActionExecutor(db_path, workspace_root)`, `execute_action(tool_name, inputs, operation_id, cancel_event, delivery_mode=...)`, `get_operation()` | Tabla SQLite `operations`; validación de entradas, precondiciones, postcondiciones y cancelación. Reinicio convierte operaciones incompletas en `unknown`; no las repite. |
| Catálogo, aprobación e idempotencia | `backend/commands.py`: `CommandService(executor)`, `prepare(..., operation_id=..., conversation_id=...)`, `execute(operation_id, approved=False)`, `reconcile()`, `cancel()` | Tabla `command_runs`, TTL de preparación, revalidación antes del efecto y un `execution_gate`. Reutilizar este recorrido; no llamar herramientas directamente. |
| Planes y recuperación | `backend/action_learning.py`: `ActionLearning(commands, adapter)`, `prepare_steps()`, `execute()`, `pause()`, `resume()`, `cancel_all()`, `retry_waiting()` | Tablas `learning_plans` y `learned_actions`; hash de plan y registros por paso. El hilo `start_recovery()` reintenta planificación, no efectos. |
| Memoria de rutinas | `backend/memory/skill_memory.py`: `SkillMemory(db, lock)`, `insert()`, `search()`, `record()`, `context()` | Memoria de procedimientos existente con identidad/versiones. `ProceduralMemory` conserva recetas y huella de entorno; no crear otra memoria de agentes. |
| Artefactos | `axx.artifact.write` usa `file_artifact_writer`; `file_inspection` ya calcula SHA-256; `backend/actions/artifact_verification.py` ofrece inspectores acotados | Los inspectores especializados tienen límites explícitos: parseo PDF no prueba apariencia; ffprobe no prueba decodificación completa. Seleccionar solo verificadores realmente disponibles. |
| Observación de escritorio | `backend/actions/desktop_observation.py`: `observe_desktop(window_id, expected_pid, ..., cancelled)`; `backend/computer_use.py`: `ComputerUse(commands)` | Observar con autorización existente. El inventario no habilita captura ni concede input. |
| Propiedad física | `backend/mobile/control.py`: `automation(cancelled)`; `backend/mobile/windows_input.py`: `WindowsInput` | Un hilo propietario maneja leases, TTL, cancelación y teclas/botones. Los locks Python son locales al proceso; toda prueba instalada debe usar el broker compartido y exclusión de su recurso físico. |
| MCP | `backend/mcp_host/client_manager.py`: `McpHost(state_dir, commands)`, `activate()`, `validate()`, `call()` | Publica herramientas habilitadas en el mismo catálogo. Una capacidad descubierta no es un permiso para ejecutarla. |
| Servidor y parada | `backend/server.py`: `run_server()` construye servicios; `/axx-api/actions/cancel` cancela comandos, aprendizaje y captura/input relacionados | Integrar aquí el servicio y su cierre. No alterar los contratos móviles `/v1`. |
| Interfaz | `1.AXX/scripts/command-library.js`, `quick-reply.js`, `Axx.html` | `Axx.backendRequest`, tarjetas y cancelación Escape existentes. Conservar avatar, disposición radial, Morph Reach, voz y autoridad `axx-studio-v2`. |

## Gates encontrados

- **M15 de entrenamiento, bloqueado:** `docs/REVISION-CONJUNTA-20261027.md`, sección «Evaluación independiente M11», registra inicio anterior al audit sin observación suficiente y cierre transitivo de `asyncio` hacia Windows. Conserva `no_promotion:true`; no se integra el candidato del laboratorio. El M15 de `docs/mobile/TRAZABILIDAD.md` es un requisito móvil distinto.
- **R02:** no se encontró el checkpoint de laboratorio en este checkout. Su estado queda **desconocido/material de diseño**, sin contarlo como holdout ni como ejecución observada. Tampoco se encontraron aquí los artefactos externos `CURRENT-TRAINING.json` y `M15-STATIC-DECISION.md`.
- Existe evidencia histórica privada de UIA/input en `build/release-0.22.0-final/run-Xw9ggx/computer-use.json` y del ensayo aislado `build/computer-use/installed-acceptance.json`. No acredita esta integración ni cierra M15.
- Fuentes e instalación inspeccionadas: Desktop `0.22.27`; Android `0.2.7-companion`, `versionCode 28`. Son observaciones de baseline, no versiones prometidas para la entrega.

## Verificación y entrega

Pruebas existentes pertinentes: `backend/actions/tests/test_action_executor.py`, `test_executor_guards.py`, `backend/tests/test_action_learning.py`, `test_computer_use.py`, `test_desktop_observation.py` y tests de memoria. La aceptación instalada dispone de `scripts/test-installed-computer-use.cjs`, `test-installed-checkpoints.cjs`, `test-installed-appearance.cjs` y `test-installed-uia-timeout.cjs`; requieren runtime real y escena de ensayo.

La entrega sigue `docs/RELEASING.md` y `docs/mobile/COMPATIBILITY-PROTOCOL.md`: pruebas pertinentes, gate conjunto sobre fuentes finales, build, instalación, aceptación nativa, push y publicación con recibos concordantes y digest de GitHub confirmado. Solo la raíz cambia versión con `release.py sync`, construye, instala y publica. Nunca se actualiza `mobile/design-baseline.json` para ocultar una regresión.

Este inventario no ejecutó pruebas físicas, no cerró M15 y no promovió R02.
