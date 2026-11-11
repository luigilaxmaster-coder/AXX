# Fase 6 · Resultados de regresión

Código: `f07f1ba` (rama `claude/axx-phase-6`, desde `9e5850c`). Todas las ejecuciones son de esta fase, sobre copias/worktree propios, con datos temporales; evidencia privada en `build/phase6/` (ignorada por git). Nivel: **[mock]** proveedor guionado · **[nav]** Chromium con shim IPC + backend real · **[real]** modelo/OS reales · **[físico]** hardware/WebView2 empaquetado (no ejecutado).

## Python

| Suite | Resultado |
|---|---|
| `test_chat_store test_commands_http test_telegram_service backend.mobile.tests.test_gateway backend.connect.tests.{test_service,test_http,test_mcp} test_unified_execution actions.tests.test_action_executor test_desktop_commands test_magic_pen test_magic_pen_http test_phase6_tools test_presentation_plan` | **217 pruebas OK** (104 s) · `build/phase6/python-final.log` |
| `test_phase6_tools` sobre el código anterior | 4 FAIL de 8 · sobre el actual 8 OK |
| Telegram/Android: `test_telegram_service`, `test_gateway`, `test_commands_http` | OK (permisos separados de Fase 4 intactos) |

Primera tanda: 1 FAIL real que **introduje yo** (`test_selected_chat_model_uses_connect_and_cannot_approve_a_write`: mi tolerancia a argumentos aceptaba `{"channel":"desktop","approved":true}`); se restringió a eco de esquema y la prueba pasó sin tocarla. Un error de carga `test_spatial_plan` es un módulo inexistente en este árbol (nombre de la lista de Fase 4), no un fallo.

## Navegador contra backend real [nav]

| Prueba | Resultado |
|---|---|
| `scripts/test-chat-groups.cjs` (9) | PASS · antes FAIL con el 400 |
| `scripts/test-chat-workspace.cjs` | PASS · antes FAIL |
| `1.AXX/scripts/test-composer-tools.cjs` (9) | PASS · antes FAIL («No encontré … en la bandeja») |
| `test-desktop-frontend.cjs` | PASS, 42 comprobaciones (una versión intermedia mía lo rompió y se corrigió) |
| `test-chat-usability`, `test-command-library`, `test-internal-actions`, `test-axx-connect` | PASS |
| `test-magic-pen` (14 comprobaciones; captura/proveedor/IPC controlados) | PASS (143 s) |
| `scripts/test-tendril-geometry.cjs` | PASS |
| `test-providers.cjs`, `test-tools-interaction.cjs` | **FAIL, idéntico a la línea base Fase 5** (mismas primeras líneas de error); no relacionados con estos cambios, no corregidos |
| `test-skills.cjs`, `test-action-learning.cjs` | **BLOCKED** igual que en la línea base: requieren `dist/axx-backend.exe` empaquetado, ausente en fuente |

## Gate PC/móvil (`scripts/validate_companion.py`, `companion-validation.json`)

**PASS**: contrato 15 (17.7 s) · backend móvil 112 (1 omitida, 26.3 s) · navegador móvil 58 (240 s) · selector de escritorio 8 (17.4 s). Mismos conteos que Fase 5. Incluye el gate de diseño protegido (`mobile/design-baseline.json`, sin cambios en hashes ni en CSS).

## Rust

`cargo test --offline --locked --lib` con `TAURI_CONFIG` sin recursos de bundle: **21 aprobadas, 1 ignorada** (helper), igual que Fase 5. `src-tauri/` no se modificó.

## Ollama real [real] — prueba obligatoria

Ollama aislado en `127.0.0.1:11485` (sin nube, sin descargas, pesos ya instalados; detenido al final), backend Python real con perfil temporal, `Axx.html` real en Chromium, casilla de herramientas activada, modo `auto_safe`, frase exacta «AXX, muéstrame el estado actual de CPU y memoria RAM.»

| Modelo | Resultado |
|---|---|
| **qwen2.5:7b-instruct** | **PASS** en las ejecuciones con warm-up. Capacidad `axx.system.telemetry` identificada por llamada estructurada `{}`, ejecutada por el ejecutor existente (`origin=axx-provider`), `state=succeeded`, `postconditions_passed=true`, recibo persistido en el diario. Tarjeta (ejemplo real): `CPU: 45.5 % (12 núcleos lógicos) · RAM: 14.2 GB en uso de 15.7 GB (90.5 %) · Disco libre: 118.06 GB de 952.6 GB`. **Primer intento tras reposo: timeout 502** (evaluación del prompt en CPU > 60 s); dos reintentos posteriores PASS. Es un límite de latencia del modelo local, no del sistema. |
| llama3.2:1b | Variable: 4 PASS (todos antes del cambio final de presentación en tarjeta), 1 recibo `blocked` (el modelo emitió argumentos inválidos → «Resultado de herramienta sin confirmar», **sin ejecución ni éxito inventado**), 1 sin respuesta en 150 s (único intento con el código final; qwen residente en memoria) (intercambio de modelos en 16 GB). Con el código anterior la misma petición produjo el esquema como texto o `TOOL_REJECTED`. No es modelo de aceptación. |

Datos reales contrastados: `cpu_percent` y memoria provienen de `GetSystemTimes`/`GlobalMemoryStatusEx`; el chat no incluye esos números (privacidad), la tarjeta sí.

Acciones rechazadas, argumentos inválidos, cancelación y sin soporte [mock, mismo flujo de página]: herramienta desconocida y argumentos inválidos → sin operación creada, sin archivo; JSON roto → rechazado por el router; escritura en `auto_safe` → `awaiting_approval`, archivo ausente; proveedor sin `tools` → solo texto + aviso «Herramientas no disponibles», sin recibo (el número inventado «12 %» no se cuenta como ejecución); casilla apagada → no se ofrecen herramientas; cancelación mientras el proveedor responde → compositor utilizable.

## Observaciones nuevas (no corregidas)
- Una respuesta de herramienta mal formada hace que el router ponga a ese proveedor en *cooldown* y la siguiente petición reciba `502 No eligible provider` (visto en el test; relacionado con el `NO_PROVIDER_AVAILABLE` de Fase 5). Riesgo de UX con modelos pequeños.
- Primer turno con modelo local de 7B en CPU puede superar el timeout de 60 s del router.
- La tolerancia a modelos pequeños se limitó a un caso (eco de esquema); no se «repara» ninguna otra salida del modelo.

## No ejecutado
Paquete Windows nuevo, WebView2 empaquetado en perfil aislado, Android físico, voz física, Telegram E2E, visión/Magic Pen con modelo (ver `UPDATED-RELEASE-GATE.md`).
