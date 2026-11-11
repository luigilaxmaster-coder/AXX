# Gate final de release — Fase 6

Candidata: **`4f4e18bffb22096b0dec380b29630464e0fc1d09`** (rama `claude/axx-phase-6`; correcciones en `f07f1ba`). Instaladores privados en `build/phase6/packages/` con `SHA256SUMS.txt`; evidencia con sumas en `build/phase6/EVIDENCE-SHA256.txt`. Sustituye al `UPDATED-RELEASE-GATE.md` previo (que era NOT_READY por falta de paquete). Sin push, merge, publicación ni instalación sobre el Axx personal (hash y registro del Axx personal idénticos antes y después).

## Dictamen: **READY_WITH_LIMITATIONS**

Para una **candidata de escritorio Windows en aceptación/uso controlado**: los dos bloqueadores P0 de Fase 5 están corregidos y **demostrados en el WebView2 empaquetado con Ollama real**. **No autoriza publicar**: quedan límites de distribución y de hardware (abajo) y defectos conocidos no resueltos. No se declara READY.

## Bloqueadores originales

| Bloqueador | Fase 5 | Fase 6 | Evidencia |
|---|---|---|---|
| P0-01 Grupos/contexto → HTTP 400 | FAIL | **PASS [nativo]** | Crear grupo, asignar, cambiar con texto pendiente, enviar, 0 HTTP 400, sin mezcla, persistencia tras reinicio real; regresión [nav] antes FAIL / después PASS |
| P0-02 Herramientas desde el compositor | FAIL | **PASS [nativo+real]** con qwen2.5:7b-instruct | Petición obligatoria → telemetría por el ejecutor existente → CPU/RAM reales → recibo persistido verificable → tarjeta en la UI; sin datos locales hacia el proveedor |

## Estado por capacidad (solo evidencia de esta fase; lo no repetido conserva Fase 5)

| Capacidad | Estado | Nota |
|---|---|---|
| Construcción oficial desde `4f4e18b` (estándar + paralela) | PASS | Árbol limpio, hashes distintos de Fase 5, 4 pasos con código 0 |
| Aislamiento de instalación | PASS | Identidad/clave/ruta/mutex distintos; `/D` en el repo, `/NS`; Axx personal intacto |
| Gate PC/Android `/v1` | PASS | 15 / 112 (1 omitida) / 58 / 8 sobre el commit final |
| Python afectado | PASS | 217 |
| Rust | PASS | 21 + 1 ignorada |
| Chat con grupos [nativo] | PASS | A1–A3 |
| Compositor + herramientas [nativo+real] | PASS | B1–B8 (B7 con la limitación `BUSY`) |
| Caída del backend [nativo] | PASS | lost → ready, nueva instancia, chat funcional |
| Avatar, tentáculos, apariencia [nativo] | PASS | Salvedad de `reducedMotion` latente |
| MCP empaquetado | PASS | 5 comprobaciones |
| Arranque en frío del 7B con timeout 60 s | **FAIL por latencia (documentado)** | 66.6 s medidos: carga 10.2 + prompt 52.5 + generación 3.9; herramienta 0.3 s; no se subió el timeout |
| Magic Pen con visión / generación 2D-3D con modelo | BLOCKED | Sin proveedor visual autorizado |
| Telegram E2E, voz física, Android físico/APK firmado | MANUAL_REQUIRED / BLOCKED | Sin cambios respecto a Fase 5 |
| Instalador **estándar** en Windows limpio, SmartScreen, sin WebView2 | NOT_TESTED | Solo se aceptó la paralela |
| `test-providers`, `test-tools-interaction` | FAIL preexistentes (fixtures/pruebas obsoletas) | Clasificadas en `PHASE6-REGRESSION-RESULTS.md`; no aprobadas |
| `test-skills`, `test-action-learning` | BLOCKED | Ruta/binario `dist\axx-backend.exe` obsoleto |
| Auditoría de contraste (68 vistas) | 2 vistas con fallos | `voices` claro, `chat` oscuro |

## Limitaciones y condiciones (explícitas)

1. **Latencia local:** un primer turno de 7B en CPU supera el timeout de 60 s (y el 20 s por defecto del producto es inalcanzable). Funciona con el modelo caliente (4–6 s) o con un modelo/hardware más rápidos. Decisión pendiente: recortar el prompt local, precalentar al conectar, o indicar «cargando modelo».
2. **Herramientas de chat:** opt-in (casilla), solo `bridge`/manual, 3 herramientas (telemetría, estado de arquitectura, escritura revisada), un turno por solicitud, **el resultado no vuelve al modelo** (se muestra al usuario en la tarjeta). Con llama3.2:1b el resultado es errático (el sistema lo marca «sin confirmar»).
3. **Cancelación:** libera la UI, no la capacidad de inferencia (hasta ~25 s con 7B en CPU: `BUSY 409`).
4. **Primer arranque:** `reducedMotion` se fija con la preferencia del sistema y apaga tentáculos hasta cambiarlo; `providers.json` con BOM impide arrancar el backend.
5. **No probados:** el instalador estándar con identidad de producción, la firma/SmartScreen, el escenario sin WebView2, la migración entre versiones y el corte eléctrico durante la instalación.
6. **Pendientes físicos:** voz con micrófono, Telegram real, Android.
7. **No publicar** sin: nueva versión vía `python scripts/release.py sync --version X.Y.Z`, reconstrucción, instalación verificada sobre un Windows limpio, gate sobre el commit final y decisión del propietario sobre los puntos 1–4 (`AGENTS.md`).

## Para pasar a READY
Cerrar 1 (latencia), instalar y aceptar el instalador **estándar** en Windows limpio, completar voz/Telegram/Android físicos, corregir o descartar con decisión los fixtures obsoletos y los dos hallazgos de contraste, y repetir el gate sobre el commit definitivo.
