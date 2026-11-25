Fecha: 2026-11-23. Rama `claude/acts-architecture-integration-d303e9`. Verificación del handoff «AXX Acts — Evolution 3.1» contra el código y las pruebas.

# Verificación del handoff Evolution 3.1

Estados: **CUMPLE** (implementado y probado), **PARCIAL** (funciona con límites declarados), **BLOQUEADO** (depende de algo externo),
**PENDIENTE** (no implementado). Las pruebas «controladas» usan un responder local; las «reales» usan Ollama o la sesión de
ChatGPT/Codex del propietario.

## Parte I — Recuperación del trabajo de Codex
| Punto | Estado | Evidencia |
|---|---|---|
| Worktree de Codex localizado, sin pérdida | CUMPLE | `1f026a0` publicado y limpio; esta rama parte de él (`ACTS-INTEGRATION.md` §1). |
| Recuperación multiarchivo, borradores, CAS, metadatos Git | CUMPLE | `test_code_recovery`, `test_code_mutation_safety`, `test_code_studio_core` en la regresión completa. |

## Parte II — Producto Acts
| Punto | Estado | Evidencia / límite |
|---|---|---|
| 3.1 Identidad, plantillas sin permisos, duplicar | CUMPLE | Acts Studio; duplicar crea copia deshabilitada sin grants (`test_acts_inference`). |
| 3.2 Personalidad → instrucciones del modelo | CUMPLE | `persona_prompt`; la persona llega al modelo (prueba UI y real). |
| 3.3 24 formas, 9 paletas, material | CUMPLE | `act-avatar.js` dibuja cada Act con el `SoftwareRenderer` de AXX (mismas 24 formas y colores de `Axx.PALETTES`, materiales → acabados), con un renderer oculto para retratos en caché y uno vivo para el Act editado o trabajando. Ajustes por Act (`appearance.studio`, tamaño, energía) y gesto por estado; `test_act_appearance`, `test_acts_ui`. |
| 3.4 Modelo por Act con el router existente | CUMPLE | `ActInferenceService`; `model_verified` en cada turno; real Ollama + real Codex (`gpt-6.1-terra` sin tocar `gpt-6.1-sol`). |
| 3.5 Voz por Act | PARCIAL | Voz/velocidad/idioma aplicados al lector existente (`502182a`); sin clonación ni micrófono automático. Sin prueba de audio nativa. |
| 3.6 Memoria por alcance | PARCIAL | `memory_scope` persistido y aplicado al chat; sin almacén de memoria privado por Act separado del existente. |
| 3.7 Herramientas por permiso (intersección) | CUMPLE | `axx.commands`, `axx.code` (worktree/patch/test/integrate/review), `axx.spatial`, `axx.computer`; se relee en cada paso. |
| 3.8 Autonomía separada del rol | CUMPLE | `autonomy.mode` independiente de `role`. |
| 3.9 Recursos | PARCIAL | `ResourceGovernor` limita concurrencia y coste por Act; CPU/RAM se informan, no se imponen por proceso. |

## Parte III — Experiencia visual
| Punto | Estado | Evidencia / límite |
|---|---|---|
| Acceso desde las herramientas radiales | CUMPLE | Lanzador «¿Qué necesitas?» → Crear: **Acts** y **Code Studio**; también en el dock (`FEATURES`). |
| Biblioteca con forma, nombre, rol, modelo, estado, revisión | CUMPLE | Tarjetas en rejilla con chips; el color de estado sale de eventos reales (`run.*`, governor). |
| Estados idle…disabled | PARCIAL | Se muestran los nueve; `planning`/`paused`/`blocked` solo si el backend los emite. |
| Editar → previsualizar → aplicar → verificar | CUMPLE | «Aplicar y verificar» relee el perfil y muestra la persona servida. |
| Modo de trabajo amplio | CUMPLE | Panel de 1240×860 (ajustado al área real) con Acts o Code Studio abiertos; uno a la vez. |
| Sin renderizadores 3D por tarjeta | CUMPLE | Dos instancias en total (retratos + vivo), nunca una por tarjeta; el avatar principal no se toca. |
| Act visible mientras trabaja | CUMPLE | Franja de presencia en el chat y en Code Studio con la forma animada por estado, modelo, reloj, duración y modelo verificado; ficha técnica por Act. |

## Parte IV — Acts en el chat existente
| Punto | Estado | Evidencia |
|---|---|---|
| Selección por chat, `@mención`, cambiar sin perder chat | CUMPLE | `test_acts_ui`, `test_acts_complete_handoff` (ACT-08). |
| Varios Acts y equipo desde una frase | CUMPLE | `teams/run`; real Ollama Dev → QA. |
| Handoffs y resultados en el chat | CUMPLE | Notas de AXX en el chat + drawer de actividad (EventHub). |

## Parte V — Inferencia real por Act
| Punto | Estado | Evidencia |
|---|---|---|
| Turno real con el modelo del Act, verificado | CUMPLE | Ollama (2 modelos) y Codex reales. |
| Nuevo hilo al cambiar de modelo, sin pagar ni cambiar de proveedor | CUMPLE | Revisión CAS → 409; hilo por Act en Codex; sin fallback automático. |
| Multiproveedor de distintos fabricantes | BLOQUEADO | Solo Ollama + ChatGPT disponibles en este equipo. |

## Parte VI — Code Studio con Acts
| Punto | Estado | Evidencia / límite |
|---|---|---|
| Layout IDE: explorador, pestañas, editor, diff, estado, panel Acts plegable | CUMPLE | Nuevo layout de tres columnas; Monaco a altura completa. |
| Selección → Act, delegar archivo, equipo | CUMPLE | «Pedir a un Act», «Delegar archivo al Act», «Equipo Dev → QA». |
| Worktree / parche / diff / pruebas / revisión / integración | CUMPLE | `test_acts_code_tools` (controlado + real); tira de pasos con estado real. |
| Modos review / worktree / apply | CUMPLE | Diff sin escribir; parche en worktree; integrar con permiso, CAS y protección de archivos sucios. |
| LSP: completion, diagnostics, hover, definition, references | PARCIAL | Cliente JSON-RPC stdio real y Monaco conectado; probado con servidor stdio de prueba. **Ningún servidor LSP real funciona en este equipo** (falta instalar). Rename/formatting: no expuestos. |
| DAP (breakpoints, variables) | PENDIENTE | Solo la guarda de loopback existente. |
| GitHub (issues, PR, CI) | PENDIENTE | No conectado desde Acts. |
| Varios archivos / carpeta como contexto | CUMPLE | Selección múltiple en `context-files` y botón `Añadir carpeta actual al contexto` (hasta 8 archivos sin credenciales vía `context/build`, usado en `ask-act`, `act-task` y `act-team-run`); probado en `test_guidance_ui`. |

## Parte VII — Windows
| Punto | Estado | Evidencia / límite |
|---|---|---|
| PC-01 archivos sin ratón físico | CUMPLE | Operaciones de Code Studio y artefactos por API. |
| PC-03 Act usando una aplicación real (UIA) | CUMPLE | `act_computer.py`: AXX observa la ventana autorizada, el modelo del Act elige un gesto sobre un control real y AXX lo ejecuta y verifica por `ComputerUse` + `ConnectService` + ejecutor; exige la autorización «Controlar PC» con entrada y el permiso `axx.computer/uia` del Act, releído antes de cada gesto. Cursor propio del Act desde pasos ejecutados e indicador nativo con su material. `test_act_computer` (controlado, UI y nativo real con `AXX_REAL_COMPUTER=1`: botón Win32 real pulsado y verificado). |
| PC-02/04/05 navegador aislado, VM, primer plano | PARCIAL | Puerta `axx.computer` y política de foco (403 sin permiso); sin adaptador de navegador aislado ni VM ejecutando acciones reales en esta rama. |

## Partes VIII–X — Equipos, rutinas, Magic Pen
| Punto | Estado | Evidencia |
|---|---|---|
| Teams con coordinador, TaskGraph, revisor | CUMPLE | `teams/run`, `test_acts_complete_handoff`, real Ollama. |
| Rutinas con dispatcher y reinicio | CUMPLE | `RoutineDispatcher` (`test_acts_complete_handoff`, ROUTINE-01..03). Sin worker remoto con el equipo apagado. |
| Equipos como grafo de nodos (Acts conectados) | CUMPLE (navegador) | `team.graph` validado (miembros, sin ciclos, revisión CAS); `teams/run` en orden topológico, un Handoff v1 por conexión y cada Act lee solo lo conectado aguas arriba (`test_team_graph`). Editor con arrastre real de conexiones, ejecución en vivo por eventos y resultado por nodo (`test_team_flow_ui`, Chromium). Falta recorrido en la app instalada (WebView2). |
| Rutinas: horario real, equipo y aprobación | CUMPLE (navegador) | Cron de 5 campos real (antes `0 9 * * *` se trataba como «cada 60 s»), vista previa del planificador, rutina de equipo completo, aprobar/omitir reanuda la ranura (antes quedaba en `awaiting_approval` para siempre). `test_team_graph`, `test_team_flow_ui`. |
| Act visual con SceneDocument y Diorama QA | PARCIAL | Lee la escena y su QA en el equipo; edición de escena por un Act: puerta `axx.spatial`, sin prueba nativa. |

## Parte XIII–XV — Aceptación y demostración
| Punto | Estado |
|---|---|
| Regresión backend completa | CUMPLE (ver `ACTS-INTEGRATION.md` §5). |
| Demostración Dev/Visual/QA | PARCIAL: integración HTTP + navegador real y equipo real con Ollama; falta recorrido completo en la app instalada (sin permiso para escribir en WebView2 durante la prueba nativa). |
| `RELEASE_READY` | No se declara. |

## Explicación señalizada (Visual Guidance Engine, guide.v1)

Navegador = Chromium headless con el `Axx.html` y el backend reales; no equivale a WebView2 instalado.

| Prueba | Estado | Evidencia |
|---|---|---|
| GUIDE-01..06 | CUMPLE (nativo, Edge) | `test_guide_native` (`AXX_REAL_GUIDE=1`): ventana Edge real, UI Automation y teclado/ratón reales; sin posición para elementos inexistentes; la contraseña no aparece en documento, sesión ni prompts. No es el overlay de la app instalada. |
| DRAW-01, DRAW-02 | CUMPLE (navegador) | `test_guidance_ui`: regiones de color reales de la selección, «morado» devuelve cero zonas. |
| DRAW-03 | PARCIAL | `test_guidance.DrawingGuideTests` compara antes/después; el botón «Actualizar guías» no tiene prueba de navegador. |
| DIAGRAM-01, 02, 03 | CUMPLE (navegador) | Flujo animado en la conexión del paso; doble clic/F2 renombra un nodo validado por el mismo validador del plan, conserva ids, enlaces y el paso de la sesión, y persiste tras reabrir. |
| 3D-01..05, 3D-07, 3D-08 | CUMPLE (navegador, SwiftShader) | 12 piezas con geometría propia, etiqueta anclada que sigue la cámara, movimiento ilustrativo, despiece/reensamblado, reanudación en el último paso, geometría marcada como conceptual. |
| 3D-06 | CUMPLE (navegador) | `test_three_pillars_integration`: GLB exportado con `extras.object_id` por nodo, mismos ids que la escena reabierta. |
| Code Studio: guías sobre líneas | CUMPLE (navegador) | Respuesta del Act con bloque `axx-guide`: solo rangos reales del archivo abierto (los inventados se descartan), tipos explicación/referencia/error/recorrido y navegación por pasos. |
| SYSTEM-01..04 | PENDIENTE | Requiere instalar la build en WebView2; no autorizado en este encargo. |
| Demostraciones A/B/C con grabación | PENDIENTE | Capturas de prueba en `build/`; faltan grabaciones en la app instalada. |



---

## Actualización de verificación y mejoras (2026-11-24 · post-`6431433`)

- **Code Studio — contexto multiarchivo/carpeta (`CUMPLE`)**: `1.AXX/scripts/code-studio/code-ui.js` integra selección múltiple y botón `Añadir carpeta actual al contexto` (`[data-code=context-folder]`, excluyendo credenciales y respetando el límite `MAX_FILES = 8` de `CodeContextService.build`) tanto para `ask-act` (`Pedir a un Act`) como para `act-task` y `act-team-run`; verificado en Chromium (`backend.tests.test_guidance_ui.GuidanceUiTests.test_code_guide_from_an_act_reply_marks_only_real_lines`).
- **Code Studio — colores CSS de guías de línea (`CUMPLE`)**: `1.AXX/scripts/code-studio/code-ui.css` preserva tintes y bordes distintos cuando un paso está activo (`.axx-code-guide-{focus,reference,error,flow}.axx-code-guide-current`); verificado en Chromium comprobando 4 `backgroundColor` y 4 `boxShadow` computados distintos más decoración `axx-code-guide-n`.
- **Magic Pen — `DRAW-03` botón «Actualizar guías» (`CUMPLE`)**: `backend.tests.test_guidance_ui.GuidanceUiTests.test_drawing_tutor_marks_colour_zones_from_the_image` ahora pulsa el botón visible `Actualizar guías` tras cambiar la figura capturada y comprueba `comparison.changed === true`, mensaje de estado y nuevas regiones pintadas en el canvas.
- **Equipos — contratos por conexión y políticas aplicadas en ejecución (`CUMPLE`)**:
  - `backend/agents/registry.py` (`checked_team_graph`) valida en cada arista `label` (`<= 80` chars) y `transfer` (`full | summary | artifact_only`).
  - `backend/agents/http_api.py` (`_execute_team_pipeline` / `_team_flow`) propaga `label`, `transfer`, `delegation_rules` y `review_criteria` al `Handoff v1` y al turno del Act receptor.
  - `1.AXX/scripts/agents/acts-studio.js` + `acts-studio.css` añaden en el inspector de conexiones campo `Contrato de entrega`, chips rápidos y selector `Qué comparte hacia adelante`; probado extremo a extremo en `backend.tests.test_acts_ux_improvements`.

### Siguientes pasos pendientes para Claude / entrega nativa

1. **WebView2 instalada (`SYSTEM-01..04`) y pruebas con modelos reales**: repetir `AXX_REAL_CODEX=1` y las pruebas locales de Ollama (`qwen2.5:7b-instruct`, `llama3.2:1b`) en entorno con sesión/Ollama activo, y validar en la aplicación desktop empaquetada tras autorización explícita del propietario (`scripts/validate_companion.py --output build/companion-validation.json` antes de cualquier build/release).
2. **Code Studio DAP UI y edición visual `axx.spatial`**: conectar los controles visuales de depuración (`dap/*`) en el panel derecho de Code Studio y añadir prueba de UI/equipo para parche `ScenePatch` + `DioramaQA` aplicado sobre `axx.spatial`.
