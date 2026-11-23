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
| 3.3 24 formas, 9 paletas, material | PARCIAL | Validado y seleccionable; miniaturas SVG paramétricas en caché, no capturas del renderer 3D real. Reacciones por estado: no implementadas. |
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
| Sin renderizadores 3D por tarjeta | CUMPLE | Miniaturas SVG. |

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
| Varios archivos / carpeta como contexto | PARCIAL | Selección o archivo actual; varios archivos no. |

## Parte VII — Windows
| Punto | Estado | Evidencia / límite |
|---|---|---|
| PC-01 archivos sin ratón físico | CUMPLE | Operaciones de Code Studio y artefactos por API. |
| PC-02..05 navegador aislado, UIA real, VM | PARCIAL | Puerta `axx.computer` y política de foco (403 sin permiso); sin adaptador UIA/VM ejecutando acciones reales en esta rama. |

## Partes VIII–X — Equipos, rutinas, Magic Pen
| Punto | Estado | Evidencia |
|---|---|---|
| Teams con coordinador, TaskGraph, revisor | CUMPLE | `teams/run`, `test_acts_complete_handoff`, real Ollama. |
| Rutinas con dispatcher y reinicio | CUMPLE | `RoutineDispatcher` (`test_acts_complete_handoff`, ROUTINE-01..03). Sin worker remoto con el equipo apagado. |
| Act visual con SceneDocument y Diorama QA | PARCIAL | Lee la escena y su QA en el equipo; edición de escena por un Act: puerta `axx.spatial`, sin prueba nativa. |

## Parte XIII–XV — Aceptación y demostración
| Punto | Estado |
|---|---|
| Regresión backend completa | CUMPLE (ver `ACTS-INTEGRATION.md` §5). |
| Demostración Dev/Visual/QA | PARCIAL: integración HTTP + navegador real y equipo real con Ollama; falta recorrido completo en la app instalada (sin permiso para escribir en WebView2 durante la prueba nativa). |
| `RELEASE_READY` | No se declara. |
