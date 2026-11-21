Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Registro de defectos

Cada fila describe causa, cambio, antes y despuÃ©s. Los logs privados estÃ¡n bajo `build/evolution-audit/`; los paths de cÃ³digo son relativos al repositorio. Riesgo general: nuevas dependencias nativas CAD requieren aceptaciÃ³n del paquete; los cambios que cierran resultados falsos deshabilitan capacidades que antes solo simulaban Ã©xito.

| ID | Prioridad | Causa raÃ­z | SoluciÃ³n/archivos de responsabilidad | Antes | DespuÃ©s | Evidencia |
|---|---|---|---|---|---|---|
| D01 | P1 | CI eliminaba subdirectorios de las URLs | 19 fixtures usan un resolvedor compartido con lÃ­mites de raÃ­z | ENOENT scene-history.js | 64 recursos originales y 65 actuales resueltos; internal-actions 6 casos | test-static-assets.cjs; CI |
| D02 | P1 | SHA de ceros usado como rango Git en push inicial | Merge-base con default branch; tip Ãºnico si no hay divergencia; omitir borrados | git log devuelve 128 | Pruebas con repositorios Git reales; Author policy remoto aprobado en push | scripts/test_author_policy.py |
| D03 | P1 | OAuth legado podÃ­a cargar tokens y cambiar a API/Ollama | Fachadas inertes; conservar helpers DPAPI y archivos existentes | CÃ³digo legado documentaba fallback automÃ¡tico; runtime activo ya usaba Codex | Pruebas prohÃ­ben red, borrado, refresh y todos los fallbacks | backend/tests/test_chatgpt_auth.py |
| D04 | P2 | Modelo seleccionado se perdÃ­a al reiniciar | Persistencia validada en connect_settings | selected_model siempre volvÃ­a al default | Reinicio sobre SQLite conserva selecciÃ³n, sin afirmar inferencia | backend/connect/tests/test_provider.py |
| D05 | P1 | Cambio de modelo reanudaba hilo del modelo anterior | Iniciar hilo nuevo cuando cambia el modelo | MODEL_MISMATCH real: solicitado terra, servido sol | Respuesta real AXX_MODEL_SWITCH_OK con terra solicitado/servido | provider/model-switch-after.json |
| D06 | P1 | MP4 sin pista de vÃ­deo; PNG concatenados | CodificaciÃ³n H.264 con PyAV existente | Decodificador encuentra cero streams | Frames decodificados, tiempos ordenados y hash determinista | backend/tests/test_motion_studio.py |
| D07 | P1 | STEP invÃ¡lido validado mediante regex | SÃ³lidos CadQuery/OpenCascade y relectura independiente | Validador antiguo true; lector encuentra cero sÃ³lidos | VolÃºmenes y bounds de sÃ³lidos reabiertos | step-before.json; cad-final.log |
| D08 | P1 | Cada pieza GLB repetÃ­a toda la malla; escala y rotaciÃ³n incorrectas | Mallas independientes, normales, metros glTF, transformaciones y Z-up a Y-up | Accesor POSITION compartido por todas las piezas | Pruebas mm/cm/m/in/ft, rotaciÃ³n y congruencia de posiciones binarias | backend/tests/test_cad_studio.py |
| D09 | P1 | PATCH HTTP pasaba un dict donde se requiere SceneDocumentStore | Usar almacÃ©n persistente compartido; GET, historial, undo/redo | Firma de apply_scene_patch incompatible | Editar, conflicto 409, undo/redo y reinicio conservan documento | backend/tests/test_evolution_audit_http.py |
| D10 | P1 | Registro HTTP de assets usaba parÃ¡metros inexistentes | Mapear contrato real y conservar aliases; dimensiones ausentes null | TypeError por filename/license_spdx/lods | Import glTF por HTTP y dimensiones desconocidas verificadas | backend/tests/test_evolution_audit_http.py |
| D11 | P0 | Rutas de exportaciÃ³n se construÃ­an antes de validar IDs | ValidaciÃ³n antes de mkdir; nombres por hash sin ADS | Datos sin validar influÃ­an en directorios de salida | Payloads traversal rechazados sin crear destinos | backend/tests/test_evolution_audit_http.py |
| D12 | P0 | Re-registro reemplazaba proyecto e historial; CAS entre hilos no serializado | Registro idempotente con raÃ­z inmutable, FK por conexiÃ³n y mutex de guardado | INSERT OR REPLACE y ventana entre hash/escritura | Historial conservado, raÃ­z no reasignable, conflicto real preserva archivo | backend/tests/test_code_studio_core.py; test_code_studio_ui.py |
| D13 | P0 | Crear/eliminar worktree borraba carpetas y cambios con fuerza | Rechazar destinos existentes, git -b y remove sin force | shutil.rmtree y git -B/--force | Dirty worktree y destino existente conservan bytes | backend/tests/test_code_studio_core.py |
| D14 | P1 | Test runner admitÃ­a hermanos no autorizados y HTTP ignoraba worktree | RaÃ­z o worktree registrado activo; ejecutar en cwd correcto | AutorizaciÃ³n por parent y cwd omitido | Pruebas de proyectos/worktrees y suite funcional | backend/code_studio/test_runner.py; http_api.py |
| D15 | P1 | Browser/UIA respondÃ­an completed sin controlador | Responder unsupported_mode, executed false; bloquear escape de perfil | Solo cambiaban diccionarios | Tests exigen no efecto y no navegaciÃ³n ficticia | backend/tests/test_background_workspaces.py |
| D16 | P1 | DAP inventaba locales y LSP running sin proceso | Estados degradado/no disponible; no resultados fabricados | counter=3 hardcoded; sin spawn LSP | Guards y estado honesto probados | backend/tests/test_code_studio_pro.py |
| D17 | P1 | WSL/hipervisores detectados se confundÃ­an con escritorio aislado | Separar backends utilizables; rechazar UI WSL y snapshot sin digest | Log de clic se reportaba como acciÃ³n; digest sintÃ©tico ante fallo | Lifecycle WSL real acotado; capacidades explÃ­citas | backend/workspaces/vm_provider.py |
| D18 | P0 | Flags no impedÃ­an llamadas HTTP; string false activaba flags | Gates en nuevos despachos y booleanos estrictos; permitir cleanup | bool("false") es true | OFF deniega y payload mal tipado no activa | backend/tests/test_evolution_audit_http.py |
| D19 | P0 | execute-task alcanzable sin aprobaciÃ³n | Exigir tarjeta aprobada ligada a operation/tool/args | EjecuciÃ³n HTTP directa posible | DenegaciÃ³n sin archivo; aprobaciÃ³n permite archivo y readback | backend/tests/test_evolution3_full_functional_audit.py |
| D20 | P1 | Code Studio no montaba un editor | Monaco 0.57 local, UI accesible, explorador, diff, CAS y controles Git/tests | Solo adapters de estado | Archivo CRLF editado y leÃ­do en WebView2 real; conflicto de disco en navegador | native-ui.json; code-ui-final.log |
| D21 | P1 | Rutinas y benchmark OpenVINO fingÃ­an trabajo | Rutina no ejecutada sin dispatcher; benchmark etiquetado Python | completed_readonly y benchmark_passed sin respectivos motores | Pruebas exigen estado bloqueado y ninguna inferencia acreditada | routines-openvino.log |

## Pendientes que bloquean release

- **P1 / OPEN:** integraciÃ³n del compositor con perfiles/modelos individuales, equipo conversacional y Agent Designer completo.
- **P1 / OPEN:** montar Diagram/CAD/Motion/Diorama/SceneDocument v2 en el flujo real de Magic Pen, incluido visor/import/export y ediciÃ³n geomÃ©trica incremental.
- **P1 / OPEN:** scheduler/dispatcher de rutinas, LSP/DAP reales y drivers background aprobados.
- **P1 / OPEN:** binario empaquetado con CAD y licencias, aceptaciÃ³n prolongada de rendimiento y recuperaciÃ³n de borradores no guardados.
- **BLOCKED:** hardware Android, micrÃ³fono/altavoz, multi-monitor y sesiones Windows grÃ¡ficas independientes.
- **EXTERNAL_PROVIDER_BLOCKED:** SIWC sin registro acreditado, API sin autorizaciÃ³n de facturaciÃ³n y ChatGPT web/tÃºnel sin asociaciÃ³n demostrada.

## D22 â€” Bundle de editor y sanitizaciÃ³n (P1)

Causa: Monaco 0.57.0 fija DOMPurify 3.4.15 en sus recursos precompilados. Cambiar solo package-lock no corrige esos bytes. SoluciÃ³n: override exacto 3.4.18 y build ESM local con esbuild 0.28.2, comprobando la entrada del sanitizer en el grafo. Antes: npm audit reporta dos paquetes con severidad baja. DespuÃ©s: cero avisos conocidos y test de editor real aprobado. Archivos: package.json, package-lock.json, scripts/prepare-monaco.cjs, code-ui.js. Riesgo: nuevo empaquetado ESM/worker exige aceptaciÃ³n WebView2; se repite sobre la candidata aislada.


## D23 — Carga de módulos del editor en Windows (P1)

El job remoto de `45e3100` detectó que el editor ESM no se montaba (timeout en la prueba real de navegación/guardado). La extensión `.mjs` depende del MIME registrado por el host Windows; el entorno local no reproducía la misma asociación. Se conservan módulos ESM, pero se generan y solicitan con extensión `.js`, admitida por ambos servidores. El worker mantiene `type: module`. No se elimina la prueba ni se incrementa su timeout. Evidencia: ejecución 44949881476, nueva prueba `test_code_studio_ui` y aceptación WebView2. Los paquetes generados anteriores se apartaron dentro del build privado para evitar su distribución accidental.
