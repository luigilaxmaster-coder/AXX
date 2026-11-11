# Validación con modelos reales

Código candidato: `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`. Rama local: `codex/axx-phase-5`. Fecha: 10 de noviembre de 2026, America/Santo_Domingo. Evidencia privada en `build/phase5/`; no se publica con los informes.

Resultado: **PASS para transporte real y ejecución estructurada de telemetría; FAIL para la aceptación general de herramientas desde frases del compositor**.

Se levantó un Ollama independiente en loopback :11485, sin nube ni descargas, usando pesos ya instalados. Se seleccionó `ollama-local` / `llama3.2:1b` en un perfil aislado con capacidades text/tools. El servicio de prueba se detuvo al terminar; no se cambió el servicio personal ni se copiaron claves.

| Ruta / proveedor | Estado | Evidencia / requisito |
|---|---|---|
| Chat normal, UI WebView2 → backend empaquetado → Ollama | PASS | Mensaje completo `source=model`, `inferenceVerified=true`, ruta manual; `real-model-native.json` |
| Calidad conversacional de llama3.2:1b | FAIL | Un saludo obtuvo una respuesta de privacidad/contexto poco pertinente. Recibir texto no acredita obediencia ni calidad general |
| Chat normal con opt-in de herramientas y prompts de prueba | FAIL | En `windows-native.json`, salida malformada y posteriores rutas a `axx.learned`/`waiting_capacity`; no se presentan como éxito |
| `/axx-api/chat` empaquetado → herramienta del modelo | PASS | Tres peticiones reales independientes, tercera con una sola llamada estructurada válida y recibo confirmado |
| Connect UI calculadora/avatar/panel | PASS | Handlers existentes y heartbeat; esta prueba no hizo inferencia |
| MCP stdio empaquetado → misma instancia | PASS | `mcp-native.json`, SDK real, descubrimiento, telemetría y rechazo de aprobación falsificada; 4.516 s |
| qwen2.5:7b-instruct / qwen2.5:latest | NOT_TESTED | Pesos locales detectados; no elegidos/configurados en la candidata. No se infiere aceptación por presencia |
| Codex / Axx Connect como proveedor de inferencia | NOT_TESTED | Requiere perfil seleccionado y vínculo oficial en la candidata; MCP cliente sí fue probado. No se reutilizaron sesiones del perfil personal |
| OpenRouter y otros proveedores remotos | BLOCKED | No configurados en perfil aislado; requieren selección del propietario y configuración local autorizada |
| Visión y generación 2D/3D con modelo real | BLOCKED | Sin proveedor/modelo visual autorizado; los modelos de texto encontrados no satisfacen el gate visual |

## Intentos de herramientas del chat empaquetado

| Intento | Duración | Estado del recibo | Poscondiciones |
|---|---|---|---|
| 1 | 13.318 s | blocked | False |
| 2 | 5.721 s | sin recibo | False |
| 3 | 3.725 s | succeeded | True |

El rechazo inicial `TOOL_REJECTED` conservó la validación del esquema; la segunda respuesta no produjo un efecto confirmado. La tercera llegó al ejecutor existente, con `origin=axx-provider`, operación `chat-tool-e750296aeb6d647c9f7903f7034c71c4c8ca9463983f4beef3654d360e7d0c0f`, `state=succeeded`, `postconditions_passed=true`. No se ejecutó manualmente esa telemetría para simular una llamada del modelo.

Una sonda anterior recibió NO_PROVIDER_AVAILABLE durante el cooldown posterior a timeouts del planificador. Se conserva `real-model-native-cooldown.json`. La repetición se realizó después del cooldown, sin borrar cuotas ni modificar el router. Ollama informó respuestas HTTP reales en sus logs. La ruta declara `unverified_profile` para identidad: no se convierte una etiqueta de configuración en certificación criptográfica del modelo remoto.

## Descubrimiento y disponibilidad explícita

El catálogo del chat API conserva exactamente tres herramientas: telemetría, arquitectura y escritura de texto revisada. El registro vivo completo se descubre con `axx_list_capabilities`; `axx_execute_action` conserva esquemas, permisos, operation_id e idempotencia. La prueba MCP real llamó al backend empaquetado ya activo: no creó un segundo ejecutor.

`FINAL-CAPABILITY-MATRIX.md` enumera las rutas por canal. Aplicaciones instaladas, listado de ventanas y estado de proceso pueden reutilizar sus adaptadores para una futura selección acotada del catálogo API. Lectura de archivos/OCR/observación requieren permiso de datos; shell, procesos y Computer Use mantienen sus límites. Cálculo/conversión/texto ya tienen handlers UI con heartbeat. No se habilitaron comandos sensibles ni se amplió el catálogo de inferencia en una fase de aceptación.

Los estados unsupported, blocked, unknown y errores del proveedor deben seguir siendo visibles. La falta de recibo en los prompts de interfaz es un gate pendiente, aunque el endpoint estructurado haya pasado. La reparación requiere prueba del flujo de usuario completo con proveedor elegido y sin sortear el resolver ni los permisos.
