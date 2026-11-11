# Resultados de regresión — Fase 6 (candidata `4f4e18b`)

Niveles: **[mock]** proveedor guionado · **[nav]** Chromium + IPC simulado con backend real · **[nativo]** WebView2 + backend empaquetado · **[real]** Ollama/OS reales · **[físico]** hardware (no ejecutado). Registros en `build/phase6/final/` (barrido sobre `4f4e18b`) y `build/phase6/`.

## 1. Barrido final sobre el commit exacto (`final/summary.txt`)

| Suite | Resultado |
|---|---|
| Python afectados (14 módulos: chat_store, commands_http, telegram_service, gateway móvil, Connect ×3, unified_execution, action_executor, desktop_commands, magic_pen ×2, phase6_tools, presentation_plan) | **217 OK** (119 s) |
| `test-chat-groups` (grupos, backend real) | PASS · antes FAIL (400) |
| `test-chat-workspace` | PASS · antes FAIL |
| `test-composer-tools` (página + backend real, proveedor guionado) | PASS (9) · antes FAIL |
| `test-chat-usability`, `test-command-library`, `test-internal-actions`, `test-axx-connect` | PASS |
| `test-magic-pen` (14 comprobaciones) | PASS (138 s) |
| `test-desktop-frontend` | PASS (42 comprobaciones) |
| `test-spatial-shapes`, `test-technical-shapes`, `test-explode` (WebGL/3D) | PASS |
| `test-tendril-geometry` | PASS |
| **Gate PC/Android** `validate_companion.py` | **PASS**: 15 contrato · 112 backend (1 omitida) · 58 navegador · 8 selector (305 s, solo, sin concurrencia) |
| Rust (`cargo test --lib`, sin recursos de bundle) | 21 OK, 1 ignorada (corrida de la fase anterior; `src-tauri/` sin cambios) |

## 2. Aplicación empaquetada [nativo] — Prueba D

| Área | Estado | Evidencia |
|---|---|---|
| Avatar / materiales / paneles / apariencia | PASS | `test-installed-appearance` (18 s), `tendril-quality` (60 casos, mediana 2.1 ms, p95 22 ms) sobre la candidata |
| Tentáculos | PASS (con salvedad) | `test-installed-tentacles` exit 0 (31 s) tras restablecer `reducedMotion` del perfil de prueba; falló antes por `Axx.flow.reduced===true` (ajuste latente de primer arranque, no regresión) |
| Magic Pen | Contratos PASS; nativo con visión BLOCKED | `test-magic-pen` PASS [nav]; `test-installed-magic-pen` llega a la visión y se detiene: sin proveedor visual autorizado |
| 3D / escena | PASS [nav] | WebGL (formas, técnico, despiece) + `test_presentation_plan` |
| Permisos | PASS [contratos] | Suites de Fase 4 sin cambios de código; Telegram/Android: aceptación física pendiente |
| MCP empaquetado | PASS | `verify-mcp-packaged.py` sobre el backend instalado (5 comprobaciones) |
| Recuperación del backend | **PASS [nativo]** | `axx-backend.exe` terminado → `axx-backend-lost` → supervisor → `axx-backend-ready`; nueva instancia (`27dab8bb…` → `0fffa8e6…`); chat funcional después |
| Cambios de diseño | Ninguno | Diff de Fase 6 sin CSS; gate de diseño protegido PASS; `mobile/design-baseline.json` intacto |

## 3. Pruebas pendientes de Fase 5 — clasificación

| Prueba | Fase 5 | Fase 6 | Clasificación y causa |
|---|---|---|---|
| `test-providers.cjs` | FAIL | FAIL (en otro punto) | **Fixture obsoleto preexistente.** El producto sondea por `POST /axx-api/providers/probe` (commit `cd0f681`) pero el fixture solo simulaba `/axx-api/chat`; el sondeo nunca terminaba (timeout, línea 138). Se migró esa parte del fixture (la petición ahora es `{model, provider_name}`; el prompt fijo lo comprueba `backend/tests/test_memory_http.py`). Tras ello la prueba avanza y **falla más adelante (línea 148, `AbortError: La memoria de esta conversación cambió`) también sobre el código de Fase 5**: otro desajuste de fixture/contrato de memoria, preexistente. **No aprobada.** |
| `test-tools-interaction.cjs` | FAIL | FAIL, idéntico | **Prueba obsoleta preexistente.** Exige que el botón del catálogo no tenga texto visible (`innerText===''`) y el producto muestra la etiqueta «Chat»; la prueba es de 23-oct (`a584284`), anterior a las capas `action11/orbit12`; `test-installed-appearance` (posterior) exige justo lo contrario («expone etiquetas de herramientas»). No es regresión. **No aprobada ni excluida.** |
| `test-skills.cjs`, `test-action-learning.cjs` | BLOCKED | BLOCKED | **Dependencia ausente/ruta obsoleta**: arrancan `dist\axx-backend.exe` (onefile) y el build oficial genera `dist\axx-backend\axx-backend.exe` (onedir). Sin cambio de código. |

## 4. Observaciones nuevas de la candidata (sin corregir)
Ver `WINDOWS-PACKAGED-ACCEPTANCE.md` §Hallazgos: reducción de movimiento latente de primer arranque; `providers.json` con BOM tumba el backend; `BUSY 409` ~16–25 s tras cancelar con un 7B en CPU; contraste insuficiente en `voices` (claro) y `chat` (oscuro: lista de hilos y `#cu-open`); arranque en frío del 7B supera 60 s (`OLLAMA-COMPOSER-END-TO-END.md`).
