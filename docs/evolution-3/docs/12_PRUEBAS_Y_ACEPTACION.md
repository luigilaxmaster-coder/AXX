# 12 — Plan maestro QA / aceptación / evidencia

## 12.1 Política de evidencia

`PASS` solo cuando la prueba fue ejecutada con resultado guardado. `FAIL` incluye error, repro, logs, responsable. `BLOCKED` significa prerequisito ajeno que impide verificar; `SKIPPED` necesita motivo y no se computa como PASS. `NOT_RUN` por defecto para todo componente nuevo. No convertir pruebas unitarias de mocks en éxito Windows instalado. Incluir artefacto SHA, timestamp, versión, equipo, línea de comandos y evidencia.

## 12.2 Baseline antes de intervenir

Confirmar rutas/comandos existen en la copia real; guardar inventario y ejecutar suites aplicables. Documentación de AXX observada recomienda:

```powershell
python -m unittest backend.tests.test_chat_store backend.tests.test_commands_http backend.tests.test_command_library backend.connect.tests.test_service -q
python -m unittest backend.tests.test_magic_pen backend.tests.test_magic_pen_http -v
python -m unittest backend.tests.test_unified_execution backend.tests.test_commands_http -v
node 1.AXX/scripts/test-magic-pen.cjs
node 1.AXX/scripts/test-spatial-shapes.cjs
node 1.AXX/scripts/test-axx-connect.cjs
node 1.AXX/scripts/test-providers.cjs
python scripts/validate_companion.py --output build/companion-validation.json
```

Algunos scripts instalados se documentan como `scripts/test-installed-chat.cjs`, `scripts/test-installed-magic-pen.cjs`, etc. **Verificar que existen en HEAD** antes de ejecutarlos; requieren instalador Windows/configuración de CDP/backup de preferencias. No correr suites instaladas en PC equivocada o sin control del proceso. Rust/test/package: ejecutar gates oficiales según `docs/RELEASING.md` actual, no inventar comandos.

## 12.3 Matrix QA por subsistema

| ID | Dominio | Caso y criterio |
|---|---|---|
| CHAT-01 | Chat legacy | Todos los chats existentes siguen abriendo con mismas identidades/mensajes/drafts/adjuntos |
| CHAT-02 | Contexto | Grupo no comparte otro chat sin consentimiento explícito |
| CHAT-03 | TTL/forget | 90 días y revocación de contexto conservados |
| AGENT-01 | Agent Designer | Crear, cambiar, clonar y desactivar sin tocar AXX global |
| AGENT-02 | Apariencia | Catálogo 24/9, miniaturas reales, preview descartable y saved settings intactos |
| AGENT-03 | Team | Handoff entre 3 agentes sin fuga de mensajes/credenciales |
| AGENT-04 | Modelo | Cambio de proveedor conserva identidad pero no reutiliza auth/conversation incorrectos |
| AGENT-05 | Import | Package no transporta grants, memory, secrets ni rutinas activas |
| ORCH-01 | TaskGraph | Topological scheduling, timeout, cancel, retry, DAG validation |
| ORCH-02 | Effects | Un crash tras dispatch genera unknown y no repetición automática |
| ORCH-03 | SSE | Seq/replay/snapshot, doble cliente, duplicate events idempotentes |
| ORCH-04 | Costs | Budget max detiene nuevas tareas y no cambia proveedor pagado |
| SEC-01 | Auth | No route new unauthenticated; CSRF/origin constraints según host |
| SEC-02 | Delegación | Subagente no escala permisos al modificar prompt/tool response |
| SEC-03 | FS | No path traversal, symlink/reparse, fuera de root, race ni secrets |
| SEC-04 | Prompt injection | README HTML tool response no dispara ejecución no autorizada |
| PC-01 | Background | Ratón físico, foco y texto sin guardar usuario no cambiaron |
| PC-02 | Host collision | Solo un lease de ratón/teclado global; conflictos denegados |
| PC-03 | Window target | HWND+PID+start/TTL invalida observaciones obsoletas |
| PC-04 | Policy | ask/queue/isolated_only/deny sin fallback oculto |
| PC-05 | VM | Diferente sesión gráfica, credenciales limitadas, guest stop/restore |
| CODE-01 | Editor | UTF-8/UTF-16/CRLF/BOM y archivos grandes controlados |
| CODE-02 | Worktree | Dos agentes no tocan dirty files usuario; integración detecta conflictos |
| CODE-03 | Patch | CAS por SHA/revision, rollback de archivo local, diff verificado |
| CODE-04 | Tools | LSP crash, DAP debug autorizado, toolchain con límites |
| CODE-05 | Git | PR/push requiere aprobación independiente, no force-push |
| MP-01 | Captura | DPI, lazo/rect/punto, ink, undo/redo, PNG, cancelar intactos |
| MP-02 | Scene | Patch incremental, concurrencia, hash de binarios y undo/redo |
| MP-03 | CAD | Parametría exacta, STEP + GLB coherente, unidades/tolerancias |
| MP-04 | Diagram | SVG export, nodos editables, no clip ni scripts activos |
| MP-05 | Motion | frame determinista, MP4 real, time seek, replay |
| MP-06 | Materials | Materiales aprobados del AXX principal no cambian por toggle |
| MP-07 | Asset Gate | URL/LOD/decoders/licencia y ninguna descarga automática sensible |
| MP-08 | Diorama | actor animation QA frozen/teleport/offscreen/credits |
| PERF-01 | GPU | FPS baseline/after, context lost, release de texturas |
| PERF-02 | Voz | VAD/ASR/TTS, dictado y micrófono no bloqueados por workers |
| MOBILE-01 | Pairing | `/v1`, Android y Telegram continúan autorizados correctamente |
| RELEASE-01 | Installer | Binario instalado probado + SHA + rollback + recibo companion |

La lista `qa/acceptance-matrix.csv` contiene la matriz operativa inicial con status NOT_RUN.

## 12.4 Pruebas de crash e idempotencia

Simular crash antes de despacho, durante E/S, después de acción externa y antes de escribir recibo. Para efecto ambiguo no aceptar `completed`, no reintentar ni «aplicar de nuevo» por otra clave. Para tareas puras, reejecutar con mismos inputs/versiones y comprobar hash determinista. Para tools con soporte de idempotencia del proveedor, utilizar identidad nativa de operación; donde no existe, no asumirla.

## 12.5 Pruebas Windows nativas

Matriz: Windows 11 x64 + entorno real del usuario, DPI 100/125/150, segundo monitor, RDP si aplica, cambio de foco, UAC (debe bloquear), ventana minimizada, usuario arrastra con mouse, race de proceso, pantallas de permisos, foreground ownership, GPU integrada, atajos, audio, overlay/hitmask, path con Unicode/espacios, Windows Defender/SmartScreen y reinicio. Probar AXX instalado, no solo HTML fuera del host nativo.

## 12.6 Regression gates por fase

Cada fase: pruebas nuevas, pruebas de áreas tocadas, baseline completa estable antes del merge, comparaciones visuales y manual acceptance. Un test de visualización hecho en browser sin el proceso instalado **no acredita** integración Win32. Si hay flakiness, aislar y resolver; no cambiar baseline a imagen equivocada.

### Métricas

p50/p95 de latencia de chat/voz/Computer Use; memory RSS/peak; GPU/render FPS; time-to-first-verifiable artifact; tests code pass/fail y reintentos; SQL replay recovery; percentage de acciones con proof; costs; false-positive de verificador. Metadata de ejecución acompaña cualquier cifra.

## 12.7 Release gate

No publicar si: hubo cambios de UI no aprobados, rutas `/v1` incompatibles, `validate_companion.py` falló/no existe recibo matching, migración perdedora, prueba de escritorio nativa pendiente en función que declara soporte, regresión de voz, `unknown` auto-retry, leaks de secretos, licencia no revisada o integrador no posee fuente exacta. Informe final con tabla PASS/FAIL/BLOCKED/SKIPPED y link a evidencia (no links ficticios).
