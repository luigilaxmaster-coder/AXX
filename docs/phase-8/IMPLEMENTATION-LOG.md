# Ledger de implementación

A: preflight y baseline desde a750362, worktree/branch codex/axx-handy-dictation.
No merge automático con claude/axx-phase-7-ui ni con la rama de escritorio abierta.
Sin nueva versión, push, publicación ni reemplazo de instalación.

B: adaptador por modelo sobre supervisor ASR existente; selección por petición,
catálogo local fijado, prepare/unload/cancel, sidecar transcribe-cpp CPU aislado.
Validación SHA256 antes de cargar GGUF, ninguna descarga automática.

C: native-voice.acquireCapture común; el medidor cede su stream al capturador.
Global no desplaza captura activa; conversación/chat/comandos pueden pausarlo.
PCM, RMS calibrado, frases finales, segmentación sostenida, cola acotada,
secuencia, limpieza, cancelación por request_id y barrera de handoff.

D: actor UIA COM, guard de proceso/control/escritorio, epochs nativos,
SendInput Unicode + readback, recibos y no reintento ambiguo. Atajo reconfigurable
con registro de colisión y rollback, toggle/hold, Escape. Prueba nativa propia.

E: diccionario exacto, perfiles, selección de micrófono/idioma/modelo, copiar,
pendientes RAM, archivo local acotado y traducción explícita a inglés. Integración
mínima en voz existente y contrato para Claude. Sin reescritura remota, historial
persistente, fuzzy corrections ni descargas de pesos: no añadir autoridad ni
retención sin la autorización/datos que esas funciones necesitan.

F: suite de regresión, gate compañero y diseño PASS, benchmark reproducible,
ASR base real sintético y build PyInstaller/sidecar. Candidata privada aislada en
construcción/validación: consultar RELEASE-READINESS.md para el resultado final.

Fallos previos a corrección están registrados en VOICE-REGRESSION-RESULTS y
HANDY-SOURCE-AUDIT. Las mejoras de cifras y calidad no se dan por demostradas.

Mejoras de cierre: espera mientras conversa/habla AXX, auto-rearme de órdenes separado, colisiones con el chord de órdenes comprobadas antes de registrar atajo; medidor y micrófono visual dentro del lease común. application_data_path conserva producción y asigna namespace propio a candidatas, aunque se abran sin variables de perfil.

Preflight: referencias antiguas de 1.AXX/AGENTS.md a docs/01-REQUISITOS.md, docs/02-AUDITORIA-MIGRACION.md y docs/03-ARQUITECTURA.md no existen en esta base; se leyeron plan maestro real, fuentes, requisitos adjuntos y los informes existentes de Fase 6.

Commits de implementación: e069ce7 (adaptadores/catálogo/worker/benchmark), 0199284 (captura, dictado, UIA, atajos, pruebas y namespace aislado), 98e257f (idioma de origen obligatorio en modelos sin detección). Sin push. La UI de Claude requiere una integración posterior deliberada.

Commits de cierre: df4cd37 (AudioContext acotado y foreground del fixture), b2b927d (cancelar órdenes previas antes de dictar), 164e310 (estado de captura tras cambio de foco).

Preflight remoto: main confirmado por git ls-remote en dfe3d5a27e2830eb7cf1cb3a2aa0707d4e117dc4. Búsqueda del conector para PR abiertas devuelve #1–5; incluye Optical Glass (#5) y cambios de Magic Pen (#3–4). Ninguna PR o rama externa se modificó.

Entrega real: candidata privada compilada, sin firma, sin instalar, sin push ni publicación; gate final PASS y arranque aislado PASS. No READY: modelos/corpus físicos, compatibilidad de apps y aceptación de micrófono/Windows quedan abiertos. El propietario debe revisarlos antes de integrar/distribuir.

Verificación de cierre: módulo exacto en WebView2 real + IPC de lectura PASS; método complementario de diagnóstico, no sustituto de interacción física. Fuentes y resultados indexados en build/phase8/validation.json; firma NotSigned y estado final PARTIAL/NOT_READY.

Cierre de arquitectura: captura global movida del renderer a WASAPI en host Rust.
Sin dependencia adicional; mono 16 kHz, latido 3 s, guard nativo de escritorio/foco,
cancelación independiente y stop confirmado antes de los tres capturadores actuales.
El JS conserva segmentación/ASR e ignora eventos antiguos. Pruebas cubren release
demorado, error nativo, prioridad, no getUserMedia global y barrera de los callers;
27 Rust PASS/2 opt-in. Fixture Win32 repetido PASS (1.41 s) sin intervención esta vez.
No convertir estas pruebas sintéticas/de control en aceptación física del driver.

Autorización posterior del usuario: descargar Parakeet V3 y Whisper Small para
compararlos. Se descargaron 1009259712 bytes en perfil de candidata, revisión/
tamaño/hash exactos; se copió solo el modelo base existente para comparar.
La carga real descubrió ABI wrapper 0.4.0/sys 0.4.1 incompatible aunque compilaba.
b5bbaca fija ambos a 0.4.0 y comprueba ABI enlazada en test; nueva compilación
MSVC/Ninja fuera de junction. Inferencia sobre los mismos 3 clips sintéticos PASS
en base/Parakeet/Small; backend empaquetado preparó/transcribió/liberó ambos PASS.
Parakeet y Small dieron dígitos en la frase de dosis; Small abrevió la unidad.
No se usó esa muestra para decidir ganador ni simular 50 frases humanas.
Instalador privado reconstruido con sidecar corregido; sin nuevos pesos, firma,
instalación personal, push o publicación. Recibos y límites en RELEASE-READINESS.
