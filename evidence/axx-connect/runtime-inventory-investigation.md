# Axx Connect: alcance demostrable del inventario de Codex 0.160.0

Estado: diagnóstico real sin inferencia; no aceptación completa del aislamiento de herramientas internas.

## Conclusión

El protocolo generado para el ejecutable instalado **no ofrece un inventario completo de las herramientas efectivas de un hilo**. Ofrece inventario MCP por servidor y consulta de flags efectivos. Estos dos mecanismos no enumeran todas las herramientas internas del modelo ni sustituyen una prueba de aislamiento.

`mcpServerStatus/list` sí respondió al utilizar un hilo efímero con configuración aislada y `threadId`: 328 ms en la primera ejecución y 16 ms en la segunda. El timeout previo de 20 s no demuestra que esta RPC sea inexistente. Tampoco su respuesta vacía demostraría ausencia de herramientas internas.

## Evidencia local y límites

- Ejecutable: Codex CLI **0.160.0**, resuelto por ruta directa; se consultó `app-server --help`.
- Esquemas de ese ejecutable: `schema/codex-0.160.0/`.
- Proveedor inspeccionado: `backend/connect/provider.py`, SHA256 `b0ad60abd87beee031a35643ed1be57928e4c1c023884be27a20f94f8183eea4`. El hash permaneció idéntico durante ambos diagnósticos. Esta conclusión corresponde a ese hash, no a posteriores cambios.
- Resultados nuevos: `runtime-inventory-readonly-result.json` y `runtime-inventory-readonly-hardened-result.json`.
- Tercera lectura extendida: `runtime-inventory-readonly-extended-result.json`. El proveedor cambió concurrentemente durante esa ejecución; el JSON conserva ambos hashes (`3b3069ba...` y `6bd174d5...`). Los controles del proceso de diagnóstico son explícitos y su readback es válido, pero no se atribuye equivalencia a un único hash de código del proveedor durante esa lectura.
- Harness reproducible de diagnóstico: `runtime_inventory_readonly_probe.py`.
- Se usó el **mismo CODEX_HOME temporal** en ambas ejecuciones. No se copiaron credenciales ni se modificó configuración del usuario.
- Se crearon hilos efímeros con `thread/start`; **no se envió `turn/start`**, ni se hizo inferencia, login, logout o ejecución de interfaz.
- El proceso hijo propio terminó al finalizar. Los directorios temporales se conservan como evidencia, sin secretos.

### Qué contienen realmente los esquemas

`ClientRequest.json` enumera 167 métodos. No contiene `tools/list`, `tool/list`, `thread/tools/list` ni un equivalente que declare inventario integral de herramientas del modelo.

| Interfaz | Qué demuestra | Qué no demuestra |
| --- | --- | --- |
| `mcpServerStatus/list` | Servidores MCP, herramientas por servidor, autenticación y estado de conexión. Permite `threadId`, `serverName`, `detail` y paginación. | Herramientas internas de Codex o lista integral de herramientas dinámicas. |
| `experimentalFeature/list` | Flags efectivos globales o del hilo; `threadId` está en el esquema instalado. | Nombres, esquemas y disponibilidad de todas las herramientas que recibirá el modelo. |
| `thread/start`, `thread/read` | Identidad/estado del hilo, modelo/proveedor y metadatos; el inicio devuelve sandbox y procedencia de permisos. | Inventario completo de herramientas. Ninguno de sus resultados contiene dicho campo. |
| `dynamicTools` en `thread/start` | Herramientas aportadas por Axx, declaradas por el cliente. | Sustitución o eliminación de las herramientas internas. |
| `command/exec`, `fs/*` | RPC explícitas que un cliente App Server puede solicitar. | Que todas esas RPC se expongan al modelo como herramientas. Son superficies diferentes. |

La documentación oficial describe el inventario MCP como inventario de servidores y sus herramientas, con conexión reutilizada al indicar un hilo. Las herramientas dinámicas son experimentales y conviven con nombres reservados de herramientas internas. [App Server](https://developers.openai.com/codex/app-server).

El esquema público `ConfigReadResponse.ToolsV2` sólo declara `web_search`. No expone un `toolConfig` general para deshabilitar exhaustivamente herramientas internas. No se debe inventar ese campo ni un método de inventario para superar una puerta de aceptación.

## Diagnóstico de flags y del canario MCP

El home temporal contiene un servidor MCP canario que únicamente puede escribir un marcador en ese mismo directorio si arranca. El archivo del marcador nunca apareció.

Primera ejecución, con los controles del proveedor inspeccionado:

- `mcp_servers={}` en la línea de lanzamiento **conservó** el servidor canario `enabled=true` al leer configuración efectiva. Se confirmó la fusión de tablas.
- El hilo recibió `mcp_servers.inventory_canary.enabled=false` explícito. Su inventario devolvió `runtimeStatus=disabled`, cero herramientas y sin error de catálogo.
- El inventario de flags mostró `unified_exec=true`, aunque `config/read` conservaba el valor solicitado `false`.

Segunda ejecución, mismo home y controles adicionales efímeros:

- Se leyeron **154 flags completos en dos páginas**, tanto globalmente como por hilo; `nextCursor=null` al terminar.
- `configRequirements/read` no devolvió requisitos administrados de flags.
- Se repitió el inventario MCP del hilo: un servidor canario deshabilitado, cero herramientas, ninguna ejecución de su proceso.

Todos los valores solicitados de esta tabla fueron `false`:

| Flag | Efectivo global | Efectivo en el hilo |
| --- | --- | --- |
| `shell_tool` | false | false |
| `apps` | false | false |
| `multi_agent` | false | false |
| `hooks` | false | false |
| `remote_plugin` | false | false |
| `view_image` | false | false |
| `browser_use` | false | false |
| `computer_use` | false | false |
| `plugins` | false | false |
| `code_mode_host` | false | false |
| `in_app_browser` | false | false |
| `sleep_tool` | false | false |
| `tool_suggest` | false | false |
| `unified_exec` | **true** | **true** |

Tercera ejecución, sin inferencia y reutilizando el mismo home canario: se añadieron cinco controles explícitos. Se volvieron a leer las 154 entradas completas en ambos ámbitos. Los 18 opt-outs restantes resultaron `false`; `unified_exec` fue el único solicitado como `false` que permaneció `true`.

| Flag adicional | Efectivo global | Efectivo en el hilo |
| --- | --- | --- |
| `image_generation` | false | false |
| `goals` | false | false |
| `skill_search` | false | false |
| `skill_mcp_dependency_install` | false | false |
| `realtime_conversation` | false | false |

La tercera consulta MCP respondió en 32 ms: canario deshabilitado, cero herramientas y marcador de arranque ausente. No se envió `turn/start`.

La documentación vigente especifica que el opt-out de `unified_exec` se ignora. Distingue ese flag de `shell_tool`, que controla herramientas de ejecución de comandos. El resultado del ejecutable instalado confirmó la diferencia; no se ejecutó un comando del modelo para atribuirle una garantía de aislamiento. [Referencia de configuración](https://developers.openai.com/codex/config-reference).

En el proveedor inspeccionado, `tools.view_image=false` no produjo una lectura pública de ese valor y el flag `view_image` seguía activo en el primer diagnóstico. La segunda ejecución demuestra que `features.view_image=false` sí se refleja como desactivado en los dos ámbitos. Esto compara estados observados; no prueba por sí solo qué herramienta interna habría recibido el modelo en la primera ejecución.

En la segunda ejecución seguían activos los cinco flags de la tabla adicional; la tercera demuestra su desactivación efectiva. Persisten varios auxiliares, por ejemplo `unified_exec_tty`, `shell_snapshot`, `in_app_chat`, `in_app_dictation`, `in_app_local_automation`, `browser_use_external`, `browser_use_full_cdp_access` y `workspace_dependencies`. Un flag activo tampoco prueba que exista una herramienta operativa en un entorno sin esa capacidad. Esta consulta de flags no equivale a una lista exclusiva de herramientas Axx.

## Implicación para el proveedor

Los controles actuales verificados son parciales: nombres de MCP deshabilitados por hilo, flags leídos efectivamente, sandbox devuelto y lista de callbacks dinámicos permitidos. `environments=[]`, instrucciones al modelo, denegación de aprobaciones ajenas y sandbox de sólo lectura son controles útiles, pero no constituyen un catálogo integral. Una herramienta interna puede operar dentro del runtime sin pasar por el callback `item/tool/call` de Axx. Un sandbox de sólo lectura limita escrituras; no establece por sí mismo que no se puedan leer otros archivos.

Debe conservarse `builtin_inventory_complete=false`. Si se separan estados, los nombres precisos serían inventario MCP consultado, flags efectivos comprobados y aislamiento de herramientas internas pendiente. No corresponde convertir el resultado MCP en `runtime_inventory_verified=true` con significado de inventario total.

## Harness mínimo propuesto para la siguiente prueba real

Este apartado es una propuesta pendiente de coordinación. **No se ejecutó ninguna inferencia de este harness.**

1. Fijar hashes de CLI, proveedor, configuración generada y registro Axx. Consultar flags completos por `threadId` y todas las páginas MCP antes del turno; preservar modelo y política de autenticación sin copiar tokens ni cambiar facturación.
2. Mantener un MCP canario temporal heredado como habilitado en la base y deshabilitado explícitamente para el hilo. Registrar por separado inicio de proceso, inicialización MCP e invocación. No conectarlo a aplicaciones, archivos personales ni red externa.
3. Crear solamente datos canario bajo un directorio temporal: un archivo de lectura con un identificador aleatorio sin valor de credencial, un destino de escritura inexistente y una imagen canario. Guardar hashes/contadores, no credenciales ni texto privado.
4. Tras autorizar la prueba posterior, ejecutar pocos turnos pequeños: una llamada Axx de lectura permitida como control positivo; intentos dirigidos a los archivos canario mediante shell/lectura/patch fuera del despachador; intento de delegación o MCP ajeno. Nunca aprobar una ampliación, activar créditos, generar imágenes de pago ni apuntar a información real del usuario.
5. Correlacionar IDs de hilo/turno/llamada, tipos de items del runtime, solicitudes de aprobación, callbacks Axx y cambios observados en canarios. Cancelar únicamente procesos de esa prueba y comprobar el estado antes de repetir. Un rechazo verbal del modelo o que el archivo no cambie no demuestra que una lectura haya sido imposible.
6. Para una garantía de lectura, añadir observación del acceso al archivo canario por el PID/descendientes del runtime o una frontera de acceso compatible con Windows. Si esa observación no está disponible, declarar explícitamente esa limitación. No instalar capturadores, elevar permisos ni modificar ACL del usuario como parte de esta investigación.

Un resultado satisfactorio de estos casos acreditaría **los controles y casos ensayados**, no inventaría una enumeración exhaustiva que el protocolo no entrega. Si la condición de promoción exige aislamiento completo verificable, se necesita una interfaz soportada del runtime que exponga/limite el conjunto íntegro de herramientas o una frontera de ejecución verificable. Esa dependencia debe quedar abierta hasta disponer de evidencia; los flags o un `toolConfig` supuesto no la sustituyen.

## Reproducción sin inferencia

Primera ejecución:

```powershell
python evidence/axx-connect/runtime_inventory_readonly_probe.py
```

Segunda ejecución reutilizando el directorio indicado por el primer JSON:

```powershell
python evidence/axx-connect/runtime_inventory_readonly_probe.py --hardened --scratch evidence/axx-connect/runtime-inventory-isolated-1ff198e00b2e
```

Tercera ejecución con los cinco controles adicionales:

```powershell
python evidence/axx-connect/runtime_inventory_readonly_probe.py --extended --scratch evidence/axx-connect/runtime-inventory-isolated-1ff198e00b2e
```

El harness sólo admite un conjunto cerrado de RPC de diagnóstico. No permite `turn/start`, métodos de autenticación ni escritura de configuración del usuario. La configuración del canario y los artefactos del runtime quedan dentro del directorio de evidencia creado para la prueba.
