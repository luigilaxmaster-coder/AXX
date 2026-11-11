# P0-02 · Herramientas desde el compositor — causa raíz

Base `9e5850c` (código `b99d8bd`). Prueba obligatoria: «AXX, muéstrame el estado actual de CPU y memoria RAM.» desde el compositor normal. Evidencia privada en `build/phase6/`.

## Dónde se interrumpe la ruta

`Entrada → Compositor → Proveedor → Tool calling → Registro → Permisos → Ejecutor → Recibo → Chat`

La ruta de fondo (`/axx-api/chat` con `axx_tools` → `chat_tools.catalog/dispatch` → `ConnectService.execute` → `CommandService/ActionExecutor`) **ya funcionaba** y es la misma que usa Connect: la prueba directa de Fase 5 pasaba. Fallaba **antes de llegar a ella** y, cuando llegaba, **no entregaba datos reales**. Cinco causas demostradas:

| # | Causa | Evidencia |
|---|---|---|
| 1 | **La bandeja de Alcance intercepta la frase.** `parseReachCommand` (`Axx.html`, `externalCommand`) trata cualquier «muéstrame / abre / busca … <algo>» como búsqueda de un objeto de la bandeja y responde «No encontré «estado actual de CPU y memoria RAM» en la bandeja…». El modelo nunca recibe la petición. | Prueba de compositor real sobre `9e5850c`: respuesta exacta citada, sin recibo, sin llamada al proveedor (`build/phase6/composer-mock-before.log`) |
| 2 | **El planificador absorbe las frases con verbo de acción.** En `command-library.js`, `resolve → match:'none'` + `isActionRequest(raw)` (verbos como *usa, abre, busca, ejecuta…*) iba a `plan(raw)` (planificador con modelo → `axx.learned` / `waiting_capacity`), nunca a las herramientas del chat. Es lo que le ocurrió a los prompts de la aceptación de Fase 5 («Usa la función axx_system_telemetry…»). | `commands.resolve` devuelve `none` para esa frase; el código ramifica a `plan()` |
| 3 | **La telemetría no entrega CPU actual.** `SystemTelemetryTool` calculaba `cpu_percent` (en realidad el % de memoria) y lo descartaba; la salida solo tenía totales/uso de memoria y disco. Aunque la herramienta se ejecutara, «CPU» no podía responderse con datos reales. | Salida real: `os, release, version, architecture, python_version, disk_*, memory_total_mb, memory_used_mb, pid` |
| 4 | **Modelos pequeños fallan con el esquema.** Con llama3.2:1b real: la petición literal produjo el *esquema de las herramientas como texto* (sin `tool_calls`), y otra produjo `tool_calls` con `{"type":"object","properties":{…}}` como argumentos de una herramienta sin parámetros → `TOOL_REJECTED`. | `real_tool_probe.py` contra backend real + Ollama real (antes/después) |
| 5 | **El resultado no se mostraba.** Tras un recibo verificado el chat solo decía «Acción verificada… Consulta sus detalles en Comandos». | `Axx.html` (mensaje de estado) |

Descartado con evidencia: el catálogo (3 herramientas, registro único), la normalización de proveedor (OpenAI-compatible), la correlación de IDs (`chat-tool-<sha256(request_id)>`, idempotente), los permisos (`auto_safe`/`ask`/`unrestricted` de Fase 4 intactos) y el ejecutor (recibo `succeeded`, `postconditions_passed=true`, persistido en el diario).

## Diferencias chat normal ↔ Axx Connect

El chat normal solo ofrece al modelo tres herramientas tipadas (telemetría, estado de arquitectura, escritura revisada) y **solo con la casilla «Herramientas de Axx en el chat local» activada** (decisión de permisos de Fase 4, conservada), proveedor `bridge`, selección manual y capacidad `tools` configurada. Connect expone el registro completo a clientes MCP/Codex. Ambos terminan en `ConnectService.execute` → `CommandService` → `ActionExecutor`. El resultado **no vuelve al modelo** (un turno por solicitud, una llamada por turno): se muestra al usuario en la tarjeta de recibo. Es una decisión de privacidad/seguridad vigente (los resultados locales no se añaden al contexto enviado a proveedores) y la prueba existente `test-desktop-frontend.cjs` la exige.

## Correcciones (sin nuevo ejecutor, sin ejecutar texto)

1. `Axx.html` — `chatToolsEnabled()` (un único predicado: nativo + proveedor `bridge` + casilla); la bandeja cede la frase al chat cuando no coincide con ningún objeto, no hay alcance explícito (*archivo/app*) y las herramientas están activas.
2. `command-library.js` — con herramientas activas, `none` + verbo de acción pasa al chat con herramientas, no al planificador. Sin herramientas el comportamiento anterior no cambia.
3. `backend/actions/tools.py` — la telemetría añade `cpu_percent` real (dos muestras de `GetSystemTimes`, `None` si no puede medirse), `cpu_count`, `memory_percent`; la poscondición rechaza CPU fuera de 0–100 o memoria incoherente. Campos aditivos.
4. `backend/connect/chat_tools.py` — descripción «Sin argumentos: arguments es {}», guía de sistema corta (no ejecuta nada; pide la llamada estructurada y prohíbe inventar valores) y tolerancia **estrecha**: en una herramienta sin parámetros solo se descartan argumentos que sean *únicamente palabras clave de JSON Schema* (`type, properties, required…`). Cualquier otra clave (`approved`, `channel`, `origin`…), JSON roto, no-objeto, claves duplicadas, herramienta desconocida o argumentos inválidos en herramientas con parámetros siguen bloqueados. Espera de recibo 2 s → 8 s.
5. `chat-workspace.js` — la tarjeta de recibo (`origin=axx-provider`, verificada) muestra los datos reales; **no** se copian al historial del chat.

## Resultado

Con Ollama real `qwen2.5:7b-instruct` el compositor normal ejecuta telemetría y muestra CPU/RAM reales con recibo persistido. Con `llama3.2:1b` el resultado es variable (el modelo, no el sistema): cuando no emite una llamada válida el chat dice «Resultado de herramienta sin confirmar» y no se registra ejecución. Detalle de runs en `REGRESSION-RESULTS.md`.
