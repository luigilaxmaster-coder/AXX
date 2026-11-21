# Auditoría Inicial y Baseline de Ingeniería — AXX Evolution 3.0

- **Fecha:** 2026-11-21
- **Repositorio:** `https://github.com/luigilaxmaster-coder/AXX`
- **SHA base auditado:** `508bceabc718905db9bcf4042992d91f4c6c0705` (versión escritorio `0.22.52`, Android `0.2.14` / `versionCode 35`)
- **Entorno verificado:** Windows 11 x64, Python `3.12.10`, Node.js `v24.14.1`, Rust `1.96.0`, Cargo `1.96.0`
- **Worktree aislado:** `build/evolution-3-worktree` (rama `feature/axx-evolution-3`)

---

## 1. Clasificación de capacidades del sistema base (`508bceabc718905db9bcf4042992d91f4c6c0705`)

| Subsistema / Capacidad | Clasificación | Evidencia comprobada |
|---|---|---|
| **ChatStore (`backend/chat_store.py`)** | `EXISTING_VERIFIED` | Persistencia SQLite, grupos, notas compartidas explícitas, TTL de 90 días, `forget` con generaciones de memoria y renovación de IDs de Connect (`test_chat_store`, `test_chat_forgetting` PASS). |
| **CommandService + ActionExecutor (`backend/commands.py`, `backend/actions/executor.py`)** | `EXISTING_VERIFIED` | Catálogo cerrado, aprobación vinculada a inputs inmutables, estado `prepared -> running -> succeeded/failed/unknown`, bloqueo de re-ejecución ante `unknown` (`test_unified_execution`, `test_commands_http`, `test_command_library` PASS). |
| **ActionLearning + SkillMemory (`backend/action_learning.py`, `backend/memory/skill_memory.py`)** | `EXISTING_VERIFIED` | Planes asistidos, verificación de postcondiciones, memoria procedimental y de tareas con revocación por generación (`test_skill_learning`, `test_task_memory` PASS). |
| **Sistema de Voz y Streaming (`backend/speech/*`, `1.AXX/scripts/native-speech-stream.js`)** | `EXISTING_VERIFIED` | Encolado WebAudio sin huecos, reproducción desde el segundo paquete en frases cortas, condicionamiento nativo en español (`- Language: Spanish`) en `moss_worker.py`, preservación de oclusivas (ataque 2 ms), normalización fonética y prosodia contextual de 8 registros (`test_speech_text`, `test_moss_stream`, `test_piper_tts`, `test-custom-speech.cjs` PASS). |
| **Magic Pen Captura + Análisis 2D/3D v1 (`backend/magic_pen.py`, `backend/presentation_plan.py`)** | `EXISTING_VERIFIED` | Contexto DPI físico por hilo (`PER_MONITOR_AWARE_V2`), rectángulo/punto/lazo, tinta editable, `PresentationPlan v1`, visor Three.js local empaquetado (`test_magic_pen`, `test_magic_pen_http`, `test-magic-pen.cjs`, `test-spatial-shapes.cjs` PASS). |
| **Companion Mobile / `/v1` (`backend/mobile/*`, `mobile/*`, `scripts/companion_contract.py`)** | `EXISTING_VERIFIED` | Contrato `axx-companion-v1`, 10 superficies protegidas en `mobile/design-baseline.json`, sincronización de personaje y permisos sin escalada (`companion_contract.py` PASS). |
| **Computer Use UIA Nativo (`backend/computer_use.py`, `backend/actions/desktop_input.py`)** | `PARTIALLY_IMPLEMENTED` | Admisión efímera con ticket, observación con HWND+PID+FILETIME y selección semántica con abstención implementadas; falta `BackgroundInteractionRouter` completo, `AttentionGuardian` multiagente, `WindowLease`/`DesktopLease` por agente y overlay de cursor virtual correlacionado con eventos reales. |
| **Superpowers / TaskGraph Declarativo Multi-Rol (Fase 1)** | `PARTIALLY_IMPLEMENTED` | `ActionLearning` ejecuta planes secuenciales y presupuestos por misión, pero falta el motor `TaskGraph` DAG declarativo con estados tipados, `Superpowers` workflow stages (`brainstorm -> plan -> tdd -> execute -> review -> verify`) y `VerifierService` independiente. |
| **SceneDocument v2 + Diagram Studio Editable (Fase 2)** | `PARTIALLY_IMPLEMENTED` | `PresentationPlan v1` soporta nodos 2D y parches básicos, pero falta `SceneDocument v2` con CAS por `revision`, parches inversos undo/redo deterministas, modelo semántico de puertos/capas/constraints y exportación editable SVG/PNG/HTML-safe. |
| **CAD Studio Paramétrico + STEP/GLB (Fase 3)** | `MISSING` | `backend/shape_registry.py` ofrece catálogo de componentes conceptuales, pero falta el contrato y worker aislado de CAD paramétrico (`cad_contracts.py`, generación/validación STEP + malla GLB, cotas verificadas y separación estricta entre `conceptual`, `measured` y `cad_verified`). |
| **Motion / Simulation Studio Determinista (Fase 4)** | `PARTIALLY_IMPLEMENTED` | Existe narración por pasos, pero falta timeline determinista con `freeze(t)`, pistas de cámara/transformación/corte, simulación reproducible por semilla y exportación sincronizada con voz. |
| **Asset Gate + Diorama + Material Engine (Fase 5)** | `PARTIALLY_IMPLEMENTED` | Existe `optical-glass.js` y `shape_registry.py`, pero falta `AssetRegistry` content-addressed con validación de licencias/provenance, conector MCP read-only de Asset Gate, modo de renderizado Diorama con QA por entidad (`frozen/teleport/offscreen`) y adaptador de materiales Codevember aislado del avatar principal. |
| **OpenVINO + Splat Preview Opcional (Fase 6)** | `MISSING` | Falta worker/adaptador opcional de inferencia local OpenVINO con detección de hardware/benchmark y representación `splat` opcional en `SceneDocument v2`. |
| **Agent Designer + Perfiles de Agente sobre Chats (Fase 8)** | `PARTIALLY_IMPLEMENTED` | `agent-profile.js` gestiona un único perfil global; falta `AgentRegistry` SQLite (`agent_profiles`, `agent_conversation_links`, `agent_permissions`, `agent_teams`), catálogo canónico 24 formas / 9 paletas por agente y conversión reversible de chats existentes sin cambiar `conversation_id`. |
| **AXX Code Studio Core & Pro (Fases 9 y 12)** | `MISSING` | Falta gestión de proyectos autorizados, `GitWorkspaceService` con `git worktree` por agente, `PatchEngine` con CAS SHA-256 y escritura atómica, indexador estructural AST/símbolos, adaptadores LSP/DAP, `TestRunner` supervisado y paneles de UI de Code Studio. |
| **Orquestación Multiagente + EventHub SSE (Fase 11)** | `MISSING` | Falta `HandoffRouter` con atenuación estricta de permisos, `ResourceLease` con fencing tokens monotónicos, `EventHub` transaccional por conversación con replay `Last-Event-ID` y `RecoveryManager` ante crash. |
| **Routines Proactivas + Continuidad Remota + ResourceGovernor (Fase 13)** | `PARTIALLY_IMPLEMENTED` | Existe `anticipation.py` y `spend_budget.py`, pero falta `AgentRoutines` por perfil con importación pausada por defecto, `ResourceGovernor` unificado (CPU/RAM/GPU/CostLedger), `FlightRecorder` y protocolo de worker remoto con mTLS/grants temporales. |

---

## 2. Resultados de Pruebas Baseline (Fase 0)

- `docs/evolution-3/qa/validate_bundle.py`: **PASS** (`6 JSON schemas, 38 QA rows, 29 upstream entries; 0 errors`)
- `python scripts/companion_contract.py`: **PASS** (`{'desktop': '0.22.52', 'android': '0.2.14', 'android_code': 35}`)
- Suite unitaria e integración Python base (`test_chat_store`, `test_commands_http`, `test_command_library`, `connect.tests.test_service`, `test_magic_pen`, `test_magic_pen_http`, `test_unified_execution`, `test_speech_text`, `test_moss_stream`, `test_piper_tts`): **PASS** (`159 tests in 129.152s — OK`)
- Suite `backend.tests.test_evolution_flags`: **PASS** (`3 tests — OK`)
