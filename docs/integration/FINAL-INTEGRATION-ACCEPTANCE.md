# AXX · aceptación de integración Fases 6 + 7 + 8

Fecha: 2026-11-11. Revisión y pruebas propias de Codex.

**Dictamen: NOT_READY para aceptación completa.** La integración real está
implementada y tiene una candidata Windows privada compilada e instalada.
Faltan las pruebas físicas críticas del dictado; los contratos y la inferencia
con audio sintético no las sustituyen. No se publicó ni se sustituyó AXX personal.

## Fuentes verificadas y commits

| Referencia | SHA completo |
| --- | --- |
| Fase 6, código | `4f4e18bffb22096b0dec380b29630464e0fc1d09` |
| Base común 6/7/8 | `a7503624cbefaa9a125331ef3bdcc3b3afdf0101` |
| Fase 7, congelación propia | `9f87f7fcaa1ecb06ec87747c233308d1aa7b8c13` |
| Fase 7, fuente empaquetada | `a1eb51d76978c99185d0dfc43cda7e6f51930b9d` |
| Fase 7, informe final | `d18f8272112b2f3434491497da9add8d6221e539` |
| Plan inicial | `d4a7dff9a67ece2cd8e8f99f77a9875471cf4fb9` |
| Fase 8, código | `b5bbaca0590700a5d090520ee544e558c7b34ec2` |
| Fase 8, rama Handy comprobada | `898df5f48f236b23148d203fc558f9ea0e80c0b1` |
| Merge de integración revisado | `4b20abaac2934b96f19ef1ce9320e7fb581bb189` |
| Integración de controles/identidad privada | `3d4c8d6d05bdbb94d66c42b0599c35bfd99cef2d` |
| Orden de historial compartido y contrato de voz | `5e7d03d0c5f59baf8701d7b213a53d62fbddbb3d` |
| Contraste del selector de archivo | `6f72d2514c3ed51cf6b55feb557a8b0919854bfb` |
| Fuente final empaquetada; campo auto corregido | `bb523221b68fc68cdf43caf37dea4051cd59525b` |

Trabajo exclusivamente en `codex/axx-phase-6-7-8-integration`, reutilizando el
worktree propio `C:\Users\luigi\.codex\worktrees\axx-phase-7-finish\axx2`.
Fase 6 ya era ancestro de ambas ramas; no se aplicó dos veces. Entre congelación
y fuente empaquetada de Fase 7 solo había lib.rs y su config de candidata.
Se verificaron estados, SHAs, ancestros y WIP antes de integrar. Los documentos
antiguos de requisitos/inventario referidos por 1.AXX/AGENTS.md no existen en
esas rutas; se consultaron README, PLAN-MAESTRO y las fuentes/contratos vigentes.

## Conflictos y resolución aplicada

| Conflicto | Resolución |
| --- | --- |
| Axx.html, tail de scripts | Conservar todas las cargas y el diseño de Fase 7; cargar dictation-engine antes de phase7-ui, que sigue último. Mantener la clave efectiva de layout y las correcciones funcionales de Fase 6. |
| lib.rs, ruta de datos y tests | Unificar en application_data_path sin cambiar las rutas productivas. Probar namespaces phase7, phase8 e integration678, conservar módulos/handlers/hooks/cancelación/heartbeat de Fase 8 y el supervisor de backend existente. Sin comandos duplicados. |
| DOM, panel movido | Un único nodo axx-dictation en Personalizar AXX → Sonidos y respuesta → Voz y dictado. La guarda de montaje busca en todo el documento para evitar duplicarlo al moverlo. Los controles de voz mantienen un botón de acceso rápido al mismo nodo. |
| Motor/modelo y preferencias | Selector de motor derivado del catálogo real y del único modelo ASR guardado. Opciones ausentes deshabilitadas; micrófono ausente conservado como no disponible. Actualizar catálogos no abre captura. Modelo ASR separado del proveedor de chat. |

No se reconstruyó la interfaz ni se alteraron geometría, shaders, cámara,
materiales, valores del avatar, `/v1`, pairing, grants ni IDs de operaciones.
La configuración productiva conserva Axx / com.axx.desktop. La identidad de
prueba existe únicamente en tauri.integration-candidate.conf.json.

Hallazgos adicionales corregidos:

- **Historial compartido:** el primer gate reveló dos fallos con pregunta y
  respuesta en el mismo tick. La inversión por ID se reprodujo en el baseline
  intacto 8371e01. El snapshot desempata ahora por orden de llegada SQLite;
  no migra ni borra datos y no expone el campo interno. Un test determinista
  comprueba orden de mensajes y de eventos. Es un defecto previo descubierto
  durante esta integración, separado de los cinco fallos conocidos.
- **Contraste:** las capturas nativas mostraron el selector de archivos oscuro
  sobre el tema claro. Se aplicaron los tokens existentes, solo en el grupo de
  dictado, y se añadió comprobación de contraste mínimo 4.5 en ambos temas.
- **Idioma:** el input admitía 3 caracteres y no permitía volver a escribir
  `auto` (4). Se corrigió el límite y se probó el recorrido es → auto → guardar.
- **Prueba antigua de voz:** esperaba visibilidad del panel en Voces; ahora
  comprueba el único propietario en Sonidos y el acceso rápido visible desde
  Voces. Conserva las comprobaciones de captura, borrador, cancelación y permisos.

## Contratos funcionales y pruebas

Raíz de recibos privados: `build/integration/`. Código de salida 0 en los PASS.

| Comprobación | Resultado y evidencia |
| --- | --- |
| Python ASR/speech/modelos | 32 PASS; python-voice.log |
| Python chat, memoria, comandos, MCP y Telegram | 88 tests, 1 omisión previa; python-functional.log |
| Python Fase 6 | 8 PASS; python-phase6.log |
| Corrección temporal de historial | 20 PASS focalizados; mobile-tie-fix-final.log; reproducción previa en baseline-timestamp-tie.log |
| Rust lib/Tauri | 27 PASS, 2 opt-in; rust.log |
| Fixture Win32 real | 1 PASS; native-edit-fixture-recheck.log. Primer intento salió 101 al no recibir foreground; repetición 0, sin relajar guards ni escribir en otra ventana. |
| Sidecar CPU release | 2 PASS, incluido ABI exacto; compilación 0; sidecar-build.log |
| JavaScript puro de dictado | 2 suites PASS; engine y global-runtime, voice-regressions/ |
| Voz/navegador existente | PASS tras actualizar ubicación autorizada; dictation-runtime-recheck.log |
| Contratos DOM, layout y nueva integración | 30 PASS; ui-contract-complete-final.log. OFF, único nodo, modelo persistido, idioma, foco, tamaños, contraste y permisos. |
| Regresión de interfaz | 14 suites PASS; ui-regressions/results.json. Incluye desktop 42, chat/grupos/workspace, compositor, comandos, sonido, Computer Use, quick reply, misiones, procedencia, runtime, tentáculos y Magic Pen. |
| Gate PC/móvil | PASS; 15 contratos / 113 servicio (1 omitida) / 58 navegador / 8 selector. companion-validation-final.json. Inputs y diseño protegido cotejados de nuevo tras los ajustes locales finales. |
| Backend empaquetado | PyInstaller, QR, gateway help e inventario onedir PASS; backend-build-final.log y package-final/. Primera compilación invalidada por cambiar la fuente durante el hallazgo temporal; nunca se instaló ese paquete. |
| Reutilización verificada del backend | PASS; backend-reuse-final.log. Backend/worker no cambiaron con los ajustes locales de UI. |
| Tauri/NSIS final | Compilación e instalación privada 0; candidate-build-complete-final.log, private-install-final.log. |

Los contratos cubren propietario único, cesión y cierre confirmado del micrófono,
OFF por defecto, ausencia de envío/comandos/permisos desde dictado, foco viejo
retenido como pendiente, cancelación sin inserción tardía, conversación/órdenes
independientes y ausencia de rearme automático. Son pruebas de contrato con
audio sintético; no acreditan driver físico, audio humano ni todas las apps.

El motor anterior permanece seleccionable y se prueba explícitamente; no se
promete un cambio silencioso de modelo ante un error del motor seleccionado.
Diccionario y perfiles usan las capacidades reales existentes, sin postproceso
LLM remoto ni envío implícito del dictado.

## Windows real y comparación con baselines

WebView2 157.0.4341.46, IPC genuino y backend instalado, sin host simulado.
Pantalla disponible: 120 DPI / 125%, 1536×816 lógicos. La app informa vista
compatible sin WebGL: no se certifica GPU con estas pruebas.

La última candidata supera **14/14 grupos de aceptación nativa automatizada**
(salida 0 del proceso de pruebas). native-acceptance.json conserva el alcance
READY_WITH_LIMITATIONS de estos checks; el dictamen de entrega de este informe
es NOT_READY por las pruebas físicas críticas pendientes.

Los recibos nativos comprueban assets servidos contra hashes de fuente, los
tres paneles, cinco pestañas, ambos temas, 424 IDs previos únicos, geometría
estable, guardado/descartar y persistencia. También apariencia instalada,
18 chats en ambos temas, tentáculos/retracción y 60 casos analíticos de calidad.
Los movimientos de puntero de esas suites son instrumentación del WebView2
real; no equivalen a entrada física de ratón.

La primera ejecución nativa integrada pasó 13 de 14 grupos: guardar conexión IA
y esperar estado conectado agotó 40 s. La prueba explícita posterior recibió
respuesta real y marcó «Respuesta comprobada» (7.28 s); no demuestra calidad de
instrucciones. El mismo tipo de espera inicial se conservaba en los recibos
nativos de Fase 7. El recorrido final comprueba además la configuración tras
recarga; no se ha corregido ni se declara garantizada la conexión inmediata
posterior a guardar. Los fallos iniciales se conservan en native-first-run.*.

ASR por backend empaquetado: preparar/transcribir/liberar Parakeet V3 y Whisper
Small, más inferencia con faster-whisper anterior. Mismo clip inglés sintético
existente de 4.35 s; texto no vacío, external_calls=0, automatic_actions=false.
No hay ganador demostrado para español, francés, Spanglish o cifras. Los pesos
autorizados previamente se usaron mediante enlaces privados de lectura; no se
descargaron modelos ni se incluyeron en el instalador.

Se verifican atajo de Android Ctrl+Alt+Shift+V y atajo de dictado registrados,
modelo persistido, OFF tras recarga y micrófono cerrado. Se termina únicamente
el PID del backend hijo con ejecutable/ruta propietarios, y se exige una nueva
backendInstance, catálogo ASR y preferencias recuperadas sin abrir captura.

Los cinco fallos preexistentes siguen separados y con salida 1:

| Suite | Firma coincidente con baseline |
| --- | --- |
| tools-interaction | L75, Chat frente a cadena vacía |
| providers | L148, AbortError por cambio de memoria de conversación |
| skills | ENOENT de dist/axx-backend.exe; el empaquetado real es onedir |
| capability-workshop | Timeout en L16 |
| goal-cycle | Timeout en L23 |

Las 18 alertas de texto sobre gradientes en Voces permanecen fuera del cierre,
sin relajar el medidor. Los contornos de chat permanecen en cero. Cuando se
incluye Voces dos veces en el harness, el total duplica esas mismas 18 alertas;
no se cuentan como 36 defectos distintos. Capturas anteriores de Fase 7 siguen
en build/phase7 y las de integración en build/integration/screenshots/.

## Artefactos, hashes y estado final

| Artefacto | Bytes | SHA-256 |
| --- | --- | --- |
| Instalador NSIS final | 705913808 | `04826d71ba1d394298169594dad8f39e19572c8362d6ad33167d360c947ad2bd` |
| Host independiente | 22075392 | `2e55211d28343948374fd09e8678ab7fe51f3ba06962ec6876430d414183d0fe` |
| Host instalado | 22075392 | `e21aef5bbafcb1a5337815d794dc8cb2f140f3965cc6ea212c053b0079ad1c91` |
| Backend instalado | 23239942 | `6bf9a6864132dfb28e389f91481d099f896e1e52a4c39c5d397fb765edb8dccb` |
| Worker ASR instalado | 3707392 | `ddba4868f98f457f215cb6bfb01bf74aa64bf59680f28a1001b35b8702b3c181` |

La candidata se instala solo en `build/integration/installed`, con producto
Axx Integration Candidate, host AxxIntegration.exe, identifier
com.axx.integration678 y su propio registro de desinstalación. Backend y worker
tienen procesos, jobs, puertos y rutas propietarios. Perfil de aceptación:
`build/integration/native-profile/local/com.axx.integration678/Axx`; WebView y
APPDATA también aislados. Identidad productiva sin cambios; no se avanzó versión
de escritorio ni Android. Depuración sin firma, no instalador público.

El host instalado difiere del host independiente únicamente por el marcador
UNK → NSS del empaquetador NSIS. Se cotejaron todos los bytes tras esa única
sustitución en memoria, sin modificar los binarios. Backend onedir, worker y
ausencia de pesos/audio se verifican en verify-install.py. Los instaladores
intermedios se preservan identificados como superados, sin publicarlos.

`build/integration/final-validation.json` indexa hashes de artefactos, capturas,
logs, recibos y scripts privados de reproducción. El SHA de documentación y el
estado Git final se registran allí después del commit; la fuente empaquetada
anterior es la autoridad para los binarios.

## Pendientes que bloquean aceptación completa

1. Micrófono físico y permisos Windows, corpus humano 50+ frases ES/EN/Spanglish,
   cifras/fechas/código; incluir francés antes de afirmarlo validado.
2. Sesión física de 10 minutos, carga, bloqueo/suspensión, modificadores y hold,
   y matriz real de campos/apps. Los fixtures no certifican estas condiciones.
3. Teléfono físico y flujos reales de Telegram; no hay APK nuevo ni cuenta
   externa autenticada para esta aceptación.
4. Entrada OS de ratón: Sky devolvió coordinate input geometry is unavailable;
   sin clic certificado. GPU, otros DPI y monitores físicos siguen pendientes.
5. Revisar la conexión inmediata al guardar y los cinco fallos históricos antes
   de una entrega que dependa de esas funciones. El flujo explícito y la recarga
   se documentan por separado.

Siguiente paso: aceptación física guiada sobre esta misma candidata y corpus
consentido; investigar cualquier regresión antes de volver a dictaminar. Una
entrega pública posterior necesita integrar/verificar el empaquetado productivo
del sidecar, firma, versión nueva mediante release.py y todos los gates propios
de publicación. Nada de ello está autorizado ni se ejecutó en esta tarea.

Se conservan ramas Claude/Fase 7/Handy/main y sus WIP, instalación y registro de
AXX personal. No se borraron configuraciones ni se otorgó Computer Use por
activar dictado. Al terminar se cierran solo procesos propietarios de prueba.

## Lista de archivos integrada frente al plan inicial

```text
1.AXX/Axx.html
1.AXX/scripts/dictation-engine.js
1.AXX/scripts/native-voice.js
1.AXX/scripts/phase7-ui-harness.cjs
1.AXX/scripts/phase7-ui.css
1.AXX/scripts/phase7-ui.js
1.AXX/scripts/test-dictation-engine.cjs
1.AXX/scripts/test-dictation-runtime.cjs
1.AXX/scripts/test-global-dictation-runtime.cjs
axx-backend.spec
backend/mobile/shared_state.py
backend/mobile/tests/test_shared_state.py
backend/server.py
backend/speech/dictation-models.json
backend/speech/dictation_models.py
backend/speech/offline_asr.py
backend/speech/transcribe_cpp.py
backend/tests/test_asr_http.py
backend/tests/test_dictation_models.py
docs/integration/FINAL-INTEGRATION-ACCEPTANCE.md
docs/integration/PHASE-6-7-8-PLAN.md
docs/integration/PHASE-6-7-8-SOURCES.json
docs/phase-8/ASR-MODEL-COMPARISON.md
docs/phase-8/CLAUDE-UI-INTEGRATION-CONTRACT.md
docs/phase-8/DICTATION-ARCHITECTURE.md
docs/phase-8/HANDY-SOURCE-AUDIT.md
docs/phase-8/IMPLEMENTATION-LOG.md
docs/phase-8/PERFORMANCE-RESULTS.md
docs/phase-8/RELEASE-READINESS.md
docs/phase-8/VOICE-REGRESSION-RESULTS.md
docs/phase-8/WINDOWS-FOCUS-INJECTION.md
docs/phase-8/licenses/Handy-MIT.txt
docs/phase-8/licenses/transcribe.cpp-MIT.txt
docs/phase-8/licenses/transcribe.cpp-THIRD-PARTY.md
scripts/benchmark_dictation.py
src-tauri/Cargo.lock
src-tauri/Cargo.toml
src-tauri/src/dictation.rs
src-tauri/src/dictation_audio.rs
src-tauri/src/dictation_shortcut.rs
src-tauri/src/lib.rs
src-tauri/tauri.dictation-candidate.conf.json
src-tauri/tauri.integration-candidate.conf.json
workers/dictation-asr/Cargo.lock
workers/dictation-asr/Cargo.toml
workers/dictation-asr/README.md
workers/dictation-asr/src/main.rs
```
