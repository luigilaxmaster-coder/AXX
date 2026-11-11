# Gate de release actualizado (Fase 6)

Código: `f07f1ba` sobre `9e5850c` (código empaquetado de Fase 5: `b99d8bd`). Rama local `claude/axx-phase-6`. Solo evidencia nueva de esta fase; lo no repetido conserva el estado de `docs/phase-5/FINAL-RELEASE-GATE.md`.

## Recomendación: **NOT_READY (los dos bloqueadores P0 están corregidos en fuente y verificados en navegador/backend; falta validar un paquete Windows nuevo)**

No se declara READY porque (a) los paquetes de Fase 5 **no contienen** estas correcciones, (b) no se construyó ni validó una candidata nueva en WebView2 con perfil aislado, y (c) siguen abiertos los pendientes físicos y de distribución de Fase 5.

## Bloqueadores

| Bloqueador | Estado Fase 5 | Estado ahora | Evidencia |
|---|---|---|---|
| P0-01 Grupo/contexto → HTTP 400 | FAIL | **CORREGIDO en fuente; PASS [nav]** contra backend real. Pendiente: confirmación en WebView2 empaquetado | `ROOT-CAUSE-GROUP-HTTP400.md`; `test-chat-groups` (antes FAIL / después PASS); `test-chat-workspace` PASS |
| P0-02 Herramientas desde el compositor | FAIL | **CORREGIDO en fuente; PASS [nav] con proveedor guionado y [real] con Ollama qwen2.5:7b-instruct** (llama3.2:1b variable). Pendiente: confirmación en WebView2 empaquetado | `ROOT-CAUSE-COMPOSER-TOOLS.md`; `test-composer-tools` (antes FAIL / después PASS); recibo `chat-tool-…` `succeeded` + `postconditions_passed` en el diario |

## Estado por entorno (cambios respecto a Fase 5)

| Capacidad / entorno | Estado | Evidencia nueva / nota |
|---|---|---|
| Grupo / contexto / borradores | PASS [nav] | 9 comprobaciones; borrador conservado; escritura obsoleta sigue rechazada (400 deliberado); persistencia tras recarga |
| Compositor natural → herramienta | PASS [nav+real qwen7b] | Petición obligatoria ejecutada por el ejecutor existente; datos reales de CPU/RAM en la tarjeta de recibo; poscondiciones verificadas |
| Herramientas: rechazos, argumentos inválidos, cancelación, sin soporte | PASS [mock] | Sin operación ni archivo ante argumentos inválidos/desconocida; escritura espera aprobación; proveedor sin `tools` = texto + aviso |
| Calidad conversacional/herramientas con modelo 1b | FAIL (sin cambio) | llama3.2:1b variable; no es modelo de aceptación. qwen2.5:7b-instruct funciona pero su primer turno en CPU puede exceder 60 s |
| Gate PC/Android `/v1` | PASS | 15 / 112 (1 omitida) / 58 / 8, mismos conteos que Fase 5; hashes de diseño protegidos sin cambio |
| Rust | PASS | 21 aprobadas, 1 ignorada |
| Python afectado | PASS | 217 pruebas |
| Contratos de chat/Connect/Magic Pen/tentáculos [nav] | PASS | `test-chat-usability`, `test-command-library`, `test-internal-actions`, `test-axx-connect`, `test-magic-pen`, `test-desktop-frontend` (42), `test-tendril-geometry` |
| Permisos Telegram / Android separados | PASS [contratos] | Sin cambios de código; suites de Fase 4 en verde. Aceptación física pendiente |
| Apariencia / avatar / materiales / tentáculos / paneles | Sin regresión detectada [nav] | Ningún CSS, avatar, material, tentáculo ni panel modificado; gate de diseño PASS. Aceptación visual nativa no repetida |
| `test-providers.cjs`, `test-tools-interaction.cjs` | FAIL (preexistente, idéntico a Fase 5) | No relacionados; sin corregir |
| `test-skills.cjs`, `test-action-learning.cjs` | BLOCKED (preexistente) | Requieren `dist/axx-backend.exe` empaquetado |
| **Paquete Windows nuevo + aplicación en perfil aislado** | **NOT_TESTED** | No se construyó: requiere reconstruir backend PyInstaller + Tauri/NSIS con el overlay paralelo de Fase 5 (herramienta privada en `build/phase5` de Codex) y repetir `acceptance-native.cjs`. Los instaladores de Fase 5 **no incluyen** las correcciones |
| Magic Pen visión / 2D/3D con modelo | BLOCKED (sin cambio) | Sin proveedor visual autorizado |
| Voz física, Telegram E2E, Android físico, instalador estándar limpio, firma | MANUAL_REQUIRED / BLOCKED / NOT_TESTED (sin cambio) | Ver Fase 5 |

## Para pasar a READY
1. Construir una candidata desde `f07f1ba` (o su sucesor) con identidad paralela, **sin** sustituir el Axx instalado ni los paquetes de Fase 5; vincular commit y hashes (`build-windows.ps1` ya registra commit y árbol limpio).
2. En ese paquete, perfil aislado y Ollama de prueba: repetir (a) crear/asignar grupo desde la UI real y enviar un mensaje, (b) la petición obligatoria desde el compositor con qwen2.5:7b-instruct (con modelo caliente o timeout del router acordado), (c) cierre limpio y comprobación del Axx personal.
3. Decidir si se añade timeout configurable/primer turno para modelos locales 7B en CPU, y el *cooldown* tras una respuesta de herramienta malformada.
4. Si cambia versión: `python scripts/release.py sync --version X.Y.Z`, reconstrucción y recibos nuevos; no sobrescribir el asset 0.22.46.
5. Cerrar los pendientes físicos de Fase 5 (voz, Telegram, Android, instalador estándar limpio).

## Límites
Sin merge a `main`, sin push, sin publicación, sin instalación sobre el Axx actual, sin cambios de credenciales ni de `main`. La shim de Chromium no es WebView2; el proveedor guionado no es un proveedor real; llama3.2:1b y qwen2.5:7b-instruct se probaron en una sola máquina (CPU, 16 GB).
