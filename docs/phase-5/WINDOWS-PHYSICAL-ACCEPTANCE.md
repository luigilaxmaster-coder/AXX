# Aceptación nativa de Windows

Código candidato: `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`. Rama local: `codex/axx-phase-5`. Fecha: 10 de noviembre de 2026, America/Santo_Domingo. Evidencia privada en `build/phase5/`; no se publica con los informes.

Resultado global: **FAIL**. Se ejecutó el instalador paralelo y su WebView2 real en este equipo; se encontró un defecto reproducible al crear/asignar grupos. Las pruebas aprobadas conservan su alcance individual.

## Entorno y aislamiento

Windows 11 Home, WebView2 instalado, escala observada 125 %. Windows Sandbox no está disponible en esta edición. Se eligió instalación paralela con `AxxPhase5.exe`, producto `Axx Phase5 Candidate`, identificador `com.axx.phase5`, ruta `build/phase5/installed-parallel`. El entorno del proceso fija LOCALAPPDATA, APPDATA y WEBVIEW2_USER_DATA_FOLDER bajo `build/phase5/profile`.

La identidad de paquete separa mutex/eventos/registro; **el perfil de datos requiere además esas variables de entorno**. Usar el lanzador preparado; no abrir directamente el ejecutable ni instalar el paquete estándar sobre este equipo. No se copiaron sesiones, claves, muestras de voz ni credenciales al perfil aislado. El modelo genérico ASR se copió sólo para prueba privada y queda fuera de los instaladores.

Se verificaron el PID 18568, el hash del Axx original y su registro de instalación antes/después. Permanecen iguales. Al cerrar no quedan procesos de la candidata ni del Ollama de prueba. Evidencia: `environment-final.json`, `original-before.json`, `original-registry-after.json`.

## Resultados observados

| Capacidad / entorno | Estado | Evidencia y alcance | Duración |
|---|---|---|---|
| Instalar en paralelo | PASS | `parallel-launch.json`; backend real incluido, ruta propia | 87.534 s iniciales |
| Arranque, WebView2, IPC Python empaquetado | PASS | `windows-native.json`; instancia privada y versión 0.22.46 | 0.226 s de comprobación; no mide arranque frío |
| Catálogo vivo | PASS | 69 adaptadores; descubrimiento de telemetría | 0.614 s |
| Chat con modelo real | PASS | `real-model-native.json`; transporte real y mensaje completo; calidad limitada del modelo pequeño | 25.416 s |
| Herramienta solicitada por modelo | PASS | `/axx-api/chat` empaquetado, receipt `origin=axx-provider`; dos intentos sin ejecución confirmada y tercero confirmado | 22.990 s conjunto de intentos |
| Lenguaje natural en compositor → herramientas | FAIL | `windows-native.json`; prompts derivaron al planificador/`waiting_capacity`; no recibo verificable | Ver intentos del log; no se infiere éxito del endpoint |
| Calculadora por Connect | PASS | `12*(3+4)=84`, readback del handler UI existente | 1.431 s |
| Escritura revisada, denegación y cancelación | PASS | Sin aprobación no aparece archivo; aprobar escribe bytes/hash; cancelar conserva archivo ausente | 1.793 s |
| UIA y gestión de archivos empaquetadas | PASS | `unified/installed-unified.json`; ventana WPF propia, control único/ambiguo/ausente, lectura independiente y archivo real | No instrumentada en fixture histórico |
| Invoke genérico | MANUAL_REQUIRED | El botón tuvo efecto observado mediante lectura posterior; el recibo de dispatch permanece `unknown`, poscondiciones falsas | Incluido en prueba UIA |
| Dictado con micrófono físico | MANUAL_REQUIRED | No se grabó al usuario; ASR sólo recibió audio SAPI sintético | No ejecutado |
| SAPI + ASR local | PASS | WAV real privado y transcripción no vacía; no acredita escucha humana ni precisión de dictado | 5.998 s |
| Magic Pen: captura física | PASS | `capture-native.json`; monitor real, ventana propia de estímulo; hash y cuatro esquinas verificados | 10.999 s junto a grabación |
| Magic Pen: visión/selección → inferencia | BLOCKED | Perfil aislado sin proveedor visual autorizado/disponible | Requiere configuración de visión |
| Generación nueva 2D/3D mediante modelo | BLOCKED | Sin ruta visual/generativa aceptada; renderizar fixtures no acredita generación real | No ejecutada |
| Grabación de pantalla | PASS | MP4 físico 640×400, 41 frames, SHA-256 y decodificación independiente | 3.109 s de vídeo |
| Avatar, acabados y paneles | PASS | Formas 0/11/23, paletas 0/4/8, obsidian/smoke/prism, cinco paneles; no se prueban todas las combinaciones | 13.309 s |
| Apariencia, teclado y tamaño por panel | PASS | `appearance/installed-appearance.json`; seis comprobaciones y capturas nativas | No instrumentada en fixture histórico |
| Tentáculos y enlace a paneles | PASS | `tentacles/receipt.json`; siluetas, temas, distancias y retracción observados | No instrumentada en fixture histórico |
| Configuraciones tras reinicio real | PASS | `restart-native.json`, `reinstalled-native.json`; temas, modo de chat y nuevo backend | 4.341 s y 15.197 s de comprobación |
| Borrador tras desinstalar/reinstalar | PASS | Texto de prueba recuperado desde el mismo perfil y SQLite | Incluido en 15.197 s |
| Crear/asignar grupo desde UI | FAIL | `group-native.json` y `group-native.png`; backend guarda group_id nuevo, UI queda sin grupo y muestra HTTP 400 | 2.790 s |
| Caída de backend con trabajo en curso | PASS | `native-recovery.json`; un reemplazo, eventos lost/ready, `unknown` visible, pendientes `expired`, proceso hijo eliminado | No instrumentada; script/log conservados |
| Segunda caída inmediata | PASS | Recuperación acotada, cero hijos, interfaz informa backend no disponible | Incluida en script de recuperación |
| Cierre nativo y limpieza | PASS | Cierre real incluso con backend caído; comprobación de procesos independiente | `environment-final.json` |
| Atajos globales en paralelo | BLOCKED | Axx actual conserva las combinaciones; candidata informa error Windows 1409. Se usó la UI del perfil de prueba | No se roba el atajo actual |
| Instalador estándar en Windows limpio | NOT_TESTED | Se construyó/verificó por hashes; aceptación nativa realizada con overlay paralelo explícito | Requiere VM/equipo aislado |

## Defecto de contexto reproducido

Desde el chat: abrir Chats y grupos → Crear grupo → escribir nombre → crear. El backend rota `connect_id` al cambiar `group_id` (`backend/chat_store.py`). Los handlers de grupo en `1.AXX/scripts/chat-workspace.js` llaman a `select()` después del cambio; `select()` llama primero a `flush()` con el contexto anterior. Esa escritura es rechazada correctamente por la protección de memoria. La UI no llega a adoptar la identidad nueva y queda mostrando un estado anterior.

El fixture histórico `scripts/test-installed-chat.cjs` lo encontró primero; se reprodujo después pulsando el botón real del producto. No es sólo un selector o un timeout del test. El cierre por esta fase no modifica ese código: la reparación debe adoptar la nueva identidad/contexto antes de cualquier guardado pendiente, preservar borradores y conservar el rechazo de resultados antiguos. Añadir regresión del flujo UI y repetir aceptación sobre el nuevo commit.

## Rendimiento y límites

Muestra de 29.4 s durante chat/pruebas: suma máxima de RSS del árbol candidato **2.39 GiB**, incluyendo WebView2 y excluyendo el servicio Ollama externo. RSS suma páginas compartidas; no equivale a memoria privada comprometida. Datos por PID/CPU en `resources-native.json`.

Tras reinstalar, requestAnimationFrame midió 498 frames en 10.003 s, media 49.63 FPS e intervalo máximo 33.7 ms, con el chat visible. No acredita carga sostenida, rendimiento 3D complejo, GPU, batería ni ausencia de fugas. Esas cargas quedan NOT_TESTED; no se inventa un presupuesto de rendimiento aprobado.

Las capturas son evidencia de WebView2 nativo; se inspeccionó visualmente la captura de ajustes. No acreditan validación humana de audio ni pantallas/dispositivos no usados.
