# Fase 6 · Correcciones y pruebas

Rama aislada `claude/axx-phase-6` (worktree `.claude/worktrees/axx-phase-6`), creada desde `9e5850c` (código `b99d8bd`). Las ramas `codex/*`, el instalador existente y `build/phase5/` no se tocaron. Sin merge, push, publicación ni instalación.

## Commits

| Commit | Contenido |
|---|---|
| `f07f1ba` | Correcciones P0-01 y P0-02 + pruebas + pasos de CI |
| (siguiente) | Informes `docs/phase-6/` |

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `1.AXX/scripts/chat-workspace.js` | `syncContext()`, `rotate()`, guarda `rotating`; `select`, `c.send`, `brain.chat` adoptan el contexto antes de guardar/capturar; manejadores de grupo usan `rotate`; la tarjeta de recibo muestra datos verificados de herramientas del modelo |
| `1.AXX/Axx.html` | `chatToolsEnabled()`; la bandeja cede frases sin coincidencia al chat con herramientas; `Axx.describeToolOutput` |
| `1.AXX/scripts/command-library.js` | `none` + verbo de acción → chat con herramientas (no planificador) cuando están activas |
| `backend/actions/tools.py` | Telemetría: `cpu_percent` real, `cpu_count`, `memory_percent`; poscondiciones adicionales |
| `backend/connect/chat_tools.py` | Descripción/guía, tolerancia estrecha a eco de esquema, espera de recibo 8 s |
| `backend/server.py` | Guía de sistema cuando hay catálogo de herramientas (1 línea) |
| `.github/workflows/version-consistency.yml` | Tres pasos nuevos de CI |
| `scripts/test-chat-groups.cjs` *(nuevo)* | UI real + backend real: grupos |
| `1.AXX/scripts/test-composer-tools.cjs` *(nuevo)* | Página real + backend real + proveedor guionado o Ollama real |
| `backend/tests/test_phase6_tools.py` *(nuevo)* | 8 pruebas: argumentos, telemetría, persistencia de grupo |

No se modificó CSS, avatar, materiales, tentáculos, paneles, versiones, `mobile/design-baseline.json`, permisos de Telegram/Android ni el ejecutor.

## Pruebas antes / después

«Antes» = misma prueba sobre el código `9e5850c` sin corrección. «Después» = rama `f07f1ba`.

| Prueba | Qué prueba | Antes | Después |
|---|---|---|---|
| `scripts/test-chat-groups.cjs` (9 comprobaciones) | Crear/asignar/borrar grupo con botones reales; contexto adoptado; borrador conservado; guardado con contexto previo rechazado; cambio con guardado pendiente; rotación externa + `select`; error visible sin reintento; filtros sin mezcla; persistencia tras recarga | **FAIL**: `POST /axx-api/chat/save → 400 «El contexto de la conversación cambió; descarta el resultado anterior»` | **PASS** (solo 2 rechazos del servidor, ambos deliberados) |
| `scripts/test-chat-workspace.cjs` (existente) | Contexto, aislamiento, políticas Ask/Auto | **FAIL** (400 en línea 34; después `AbortError` en la 44) | **PASS** |
| `1.AXX/scripts/test-composer-tools.cjs`, proveedor guionado (9 comprobaciones) | Petición natural → telemetría real con recibo; verbos de acción llegan al chat; eco de esquema; JSON roto; argumentos inválidos y herramienta desconocida sin operación; escritura espera aprobación; proveedor sin herramientas = solo texto marcado; casilla apagada = sin herramientas; cancelación | **FAIL**: «No encontré «estado actual de CPU y memoria RAM» en la bandeja…» | **PASS** |
| `1.AXX/scripts/test-composer-tools.cjs` con Ollama real (`AXX_TEST_OLLAMA_*`) | La petición obligatoria, compositor real | no aplicable (nunca llegaba al modelo) | **PASS** qwen2.5:7b-instruct (ver `REGRESSION-RESULTS.md`) |
| `backend/tests/test_phase6_tools.py` (8) | Argumentos de herramientas, telemetría, persistencia | 4 FAIL (catálogo/guía, eco de esquema, telemetría ×2) | 8 PASS |
| `test-desktop-frontend.cjs` (42, existente) | Contrato del chat, incluido «sin copiar la salida de la herramienta al historial» | PASS | PASS (una versión intermedia mía lo rompió; se corrigió mostrando los datos en la tarjeta) |
| `test_commands_http` `…cannot_approve_a_write` (existente) | Un modelo no puede inyectar `approved/channel` | PASS | PASS (una versión intermedia más permisiva lo rompió; se restringió) |

### Cobertura de los requisitos de P1
- *Reproducen los dos errores sobre el código anterior:* `test-chat-groups`, `test-composer-tools`, `test_phase6_tools` (tabla de arriba).
- *Contextos obsoletos tras operaciones concurrentes:* pasos 3, 5, 6 y 6b de `test-chat-groups` (guardado obsoleto rechazado por el servidor; escritura pendiente durante el cambio; rotación externa; petición posterior a un cambio de perfil).
- *Cambio de grupos durante conversaciones activas:* paso 4–5 (dos grupos, dos chats, filtro, asignación con borrador pendiente).
- *Herramientas desde el compositor real:* página completa `Axx.html` + IPC → backend real; no desde endpoints especializados.
- *Separación Telegram/Android:* sin cambios de código; `test_commands_http`, `test_telegram_service` y `backend.mobile.tests.test_gateway` (Fase 4) siguen en verde.
- *Contratos del resto del chat:* `test-chat-usability`, `test-command-library`, `test-internal-actions`, `test-axx-connect`, `test-magic-pen`, `test-desktop-frontend`.

## Límites de los tests nuevos (honestidad)
- El «compositor real» es `Axx.html` completo en Chromium con una shim IPC de Tauri que reenvía a un **backend Python real**; no es WebView2 nativo.
- El proveedor guionado es un servidor OpenAI-compatible de prueba (contrato); los modelos reales solo se ejercen con las variables `AXX_TEST_OLLAMA_URL/MODEL` (aceptación, no CI).
- La prueba de grupos usa el fixture HTTP existente (`ChatStore` + servidor), no el backend empaquetado.
