Fecha: 2026-11-21. Base: `2f177ea` (PR #6). Rama: `codex/axx-evolution-3-audit-visual-3d-chatgpt`. Mejoras: [Draft PR #7](https://github.com/luigilaxmaster-coder/AXX/pull/7).

# Registro de defectos

Cada fila describe causa, cambio, antes y después. Los logs privados están bajo `build/evolution-audit/`; los paths de código son relativos al repositorio. Riesgo general: nuevas dependencias nativas CAD requieren aceptación del paquete; los cambios que cierran resultados falsos deshabilitan capacidades que antes solo simulaban éxito.

| ID | Prioridad | Causa raíz | Solución/archivos de responsabilidad | Antes | Después | Evidencia |
|---|---|---|---|---|---|---|
| D01 | P1 | CI eliminaba subdirectorios de las URLs | 19 fixtures usan un resolvedor compartido con límites de raíz | ENOENT scene-history.js | 64 recursos originales y 65 actuales resueltos; internal-actions 6 casos | test-static-assets.cjs; CI |
| D02 | P1 | SHA de ceros usado como rango Git en push inicial | Merge-base con default branch; tip único si no hay divergencia; omitir borrados | git log devuelve 128 | Pruebas con repositorios Git reales; Author policy remoto aprobado en push | scripts/test_author_policy.py |
| D03 | P1 | OAuth legado podía cargar tokens y cambiar a API/Ollama | Fachadas inertes; conservar helpers DPAPI y archivos existentes | Código legado documentaba fallback automático; runtime activo ya usaba Codex | Pruebas prohíben red, borrado, refresh y todos los fallbacks | backend/tests/test_chatgpt_auth.py |
| D04 | P2 | Modelo seleccionado se perdía al reiniciar | Persistencia validada en connect_settings | selected_model siempre volvía al default | Reinicio sobre SQLite conserva selección, sin afirmar inferencia | backend/connect/tests/test_provider.py |
| D05 | P1 | Cambio de modelo reanudaba hilo del modelo anterior | Iniciar hilo nuevo cuando cambia el modelo | MODEL_MISMATCH real: solicitado terra, servido sol | Respuesta real AXX_MODEL_SWITCH_OK con terra solicitado/servido | provider/model-switch-after.json |
| D06 | P1 | MP4 sin pista de vídeo; PNG concatenados | Codificación H.264 con PyAV existente | Decodificador encuentra cero streams | Frames decodificados, tiempos ordenados y hash determinista | backend/tests/test_motion_studio.py |
| D07 | P1 | STEP inválido validado mediante regex | Sólidos CadQuery/OpenCascade y relectura independiente | Validador antiguo true; lector encuentra cero sólidos | Volúmenes y bounds de sólidos reabiertos | step-before.json; cad-final.log |
| D08 | P1 | Cada pieza GLB repetía toda la malla; escala y rotación incorrectas | Mallas independientes, normales, metros glTF, transformaciones y Z-up a Y-up | Accesor POSITION compartido por todas las piezas | Pruebas mm/cm/m/in/ft, rotación y congruencia de posiciones binarias | backend/tests/test_cad_studio.py |
| D09 | P1 | PATCH HTTP pasaba un dict donde se requiere SceneDocumentStore | Usar almacén persistente compartido; GET, historial, undo/redo | Firma de apply_scene_patch incompatible | Editar, conflicto 409, undo/redo y reinicio conservan documento | backend/tests/test_evolution_audit_http.py |
| D10 | P1 | Registro HTTP de assets usaba parámetros inexistentes | Mapear contrato real y conservar aliases; dimensiones ausentes null | TypeError por filename/license_spdx/lods | Import glTF por HTTP y dimensiones desconocidas verificadas | backend/tests/test_evolution_audit_http.py |
| D11 | P0 | Rutas de exportación se construían antes de validar IDs | Validación antes de mkdir; nombres por hash sin ADS | Datos sin validar influían en directorios de salida | Payloads traversal rechazados sin crear destinos | backend/tests/test_evolution_audit_http.py |
| D12 | P0 | Re-registro reemplazaba proyecto e historial; CAS entre hilos no serializado | Registro idempotente con raíz inmutable, FK por conexión y mutex de guardado | INSERT OR REPLACE y ventana entre hash/escritura | Historial conservado, raíz no reasignable, conflicto real preserva archivo | backend/tests/test_code_studio_core.py; test_code_studio_ui.py |
| D13 | P0 | Crear/eliminar worktree borraba carpetas y cambios con fuerza | Rechazar destinos existentes, git -b y remove sin force | shutil.rmtree y git -B/--force | Dirty worktree y destino existente conservan bytes | backend/tests/test_code_studio_core.py |
| D14 | P1 | Test runner admitía hermanos no autorizados y HTTP ignoraba worktree | Raíz o worktree registrado activo; ejecutar en cwd correcto | Autorización por parent y cwd omitido | Pruebas de proyectos/worktrees y suite funcional | backend/code_studio/test_runner.py; http_api.py |
| D15 | P1 | Browser/UIA respondían completed sin controlador | Responder unsupported_mode, executed false; bloquear escape de perfil | Solo cambiaban diccionarios | Tests exigen no efecto y no navegación ficticia | backend/tests/test_background_workspaces.py |
| D16 | P1 | DAP inventaba locales y LSP running sin proceso | Estados degradado/no disponible; no resultados fabricados | counter=3 hardcoded; sin spawn LSP | Guards y estado honesto probados | backend/tests/test_code_studio_pro.py |
| D17 | P1 | WSL/hipervisores detectados se confundían con escritorio aislado | Separar backends utilizables; rechazar UI WSL y snapshot sin digest | Log de clic se reportaba como acción; digest sintético ante fallo | Lifecycle WSL real acotado; capacidades explícitas | backend/workspaces/vm_provider.py |
| D18 | P0 | Flags no impedían llamadas HTTP; string false activaba flags | Gates en nuevos despachos y booleanos estrictos; permitir cleanup | bool("false") es true | OFF deniega y payload mal tipado no activa | backend/tests/test_evolution_audit_http.py |
| D19 | P0 | execute-task alcanzable sin aprobación | Exigir tarjeta aprobada ligada a operation/tool/args | Ejecución HTTP directa posible | Denegación sin archivo; aprobación permite archivo y readback | backend/tests/test_evolution3_full_functional_audit.py |
| D20 | P1 | Code Studio no montaba un editor | Monaco 0.57 local, UI accesible, explorador, diff, CAS y controles Git/tests | Solo adapters de estado | Archivo CRLF editado y leído en WebView2 real; conflicto de disco en navegador | native-ui.json; code-ui-final.log |
| D21 | P1 | Rutinas y benchmark OpenVINO fingían trabajo | Rutina no ejecutada sin dispatcher; benchmark etiquetado Python | completed_readonly y benchmark_passed sin respectivos motores | Pruebas exigen estado bloqueado y ninguna inferencia acreditada | routines-openvino.log |

## Pendientes que bloquean release

- **P1 / OPEN:** integración del compositor con perfiles/modelos individuales, equipo conversacional y Agent Designer completo.
- **P1 / OPEN:** montar Diagram/CAD/Motion/Diorama/SceneDocument v2 en el flujo real de Magic Pen, incluido visor/import/export y edición geométrica incremental.
- **P1 / OPEN:** scheduler/dispatcher de rutinas, LSP/DAP reales y drivers background aprobados.
- **P1 / OPEN:** binario empaquetado con CAD y licencias, aceptación prolongada de rendimiento y recuperación de borradores no guardados.
- **BLOCKED:** hardware Android, micrófono/altavoz, multi-monitor y sesiones Windows gráficas independientes.
- **EXTERNAL_PROVIDER_BLOCKED:** SIWC sin registro acreditado, API sin autorización de facturación y ChatGPT web/túnel sin asociación demostrada.

## D22 — Bundle de editor y sanitización (P1)

Causa: Monaco 0.57.0 fija DOMPurify 3.4.15 en sus recursos precompilados. Cambiar solo package-lock no corrige esos bytes. Solución: override exacto 3.4.18 y build ESM local con esbuild 0.28.2, comprobando la entrada del sanitizer en el grafo. Antes: npm audit reporta dos paquetes con severidad baja. Después: cero avisos conocidos y test de editor real aprobado. Archivos: package.json, package-lock.json, scripts/prepare-monaco.cjs, code-ui.js. Riesgo: nuevo empaquetado ESM/worker exige aceptación WebView2; se repite sobre la candidata aislada.


## D23 — Carga de módulos del editor en Windows (P1)

El job remoto de `45e3100` detectó que el editor ESM no se montaba (timeout en la prueba real de navegación/guardado). La extensión `.mjs` depende del MIME registrado por el host Windows; el entorno local no reproducía la misma asociación. Se conservan módulos ESM, pero se generan y solicitan con extensión `.js`, admitida por ambos servidores. El worker mantiene `type: module`. No se elimina la prueba ni se incrementa su timeout. Evidencia: ejecución 44949881476, nueva prueba `test_code_studio_ui` y aceptación WebView2. Los paquetes generados anteriores se apartaron dentro del build privado para evitar su distribución accidental.


## D24 — Metadatos Git y normalización Windows (P1)

Reproducción: `.GIT/config` y `nested/.git/hooks/post-checkout` eran aceptados por el resolvedor de archivos; solo se bloqueaba `.git/config` con esa capitalización y profundidad. Causa: comparación sensible a mayúsculas y posición fija de los componentes. Solución: rechazar cualquier componente `.git`, en cualquier profundidad, sin distinguir mayúsculas y normalizando puntos/espacios finales de Windows. Se mantiene `.github` accesible. El mismo resolvedor protege edición, parches e indexación. Test previo falla con archivos sintéticos; suite Core/Pro/UI/HTTP posterior aprueba y conserva los bytes de config. Evidencias privadas: `git-path-before.log`, `git-path-after.log`.


## D25 — Activación ChatGPT conservando el contexto (P1)

Al aprobar un modelo, `axx-connect.js` sustituía `c.brain` por un cliente de prueba. Esa sustitución descartaba los wrappers ya instalados por chat-workspace y prompt-contracts. Se reproduce con el flujo real de selección del navegador: cambia la identidad del cliente y pierde sus wrappers. Corrección mínima: copiar el estado comprobado del cliente de prueba al cliente activo, conservando sus métodos decorados. Regresión en test-providers exige identidad estable, mismo método chat y que una nota de grupo sintética llegue a la petición del proveedor tras activar el modelo. Prueba dirigida aprobada; la inferencia de este test es controlada, no se presenta como servicio externo real. Evidencias: model-client-before.log y model-client-after.log.

D24, cierre adicional: la raíz elegida también se comprueba. Antes, seleccionar directamente una carpeta `.git` y abrir `config` evitaba la validación de los componentes relativos. La prueba reproduce ese acceso; la corrección incluye root.parts en el mismo guard normalizado. La suite Core/Pro/UI/HTTP repite 13 casos con PASS (`git-root-before.log`, `git-root-after.log`).


## D26 — Guardado, aplicación y restauración concurrentes (P1)

Los locks de apply/rollback/restore solo protegían consultas SQLite; se liberaban antes de escribir archivos. Tres pruebas de intercalado determinista reprodujeron un guardado aceptado que luego quedaba sobrescrito por la mutación en curso. Las tres operaciones mantienen ahora el mismo RLock de CodeProjectService durante validación, snapshots y escritura; el guardado posterior recibe conflicto de CAS. El alcance es el backend actual; no se afirma exclusión de editores externos ni de otros procesos. Evidencias: mutation-before.log y mutation-final.log.

## D27 — Coerción insegura de force en rollback (P1)

HTTP convertía bool("false") en True, permitiendo sobrescribir una edición posterior. Se pasa el valor original al motor compartido y se exige un bool real. Las pruebas rechazan strings, números y null; un POST real con force string devuelve 400 y conserva bytes del cambio externo. El booleano False válido mantiene la protección de conflictos. No se eliminaron snapshots ni datos.

## D28 — Integridad de snapshots y escritura verificada (P1)

Restore no comprobaba el hash del blob antes de sobrescribir el archivo. Rollback validaba snapshots uno a uno después de empezar a restaurar; un segundo snapshot corrupto dejaba el primero modificado. Se validan todos antes de escribir. atomic_write_bytes relee los bytes reemplazados y rechaza diferencias antes de devolver éxito o registrar la revisión posterior. Las pruebas inyectan corrupción controlada en SQLite y una edición externa en la frontera de replace: detectan el fallo y conservan archivos. Ocho nuevas regresiones; 21 casos Core/Pro/UI/HTTP/mutaciones aprobados.

La sustitución es atómica por archivo. Un corte de proceso o error de E/S a mitad de varios archivos aún requiere reconciliación; falta journal de grupo. No se acredita un commit multiarchivo atómico ante crash ni CAS absoluto frente a procesos externos que no colaboran. Esta limitación sigue bloqueando integración automática y release.
