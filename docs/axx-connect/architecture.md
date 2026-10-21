# Arquitectura de Axx Connect

## Dos flujos y un ejecutor

Desde Axx: barra existente → proveedor interno → Codex App Server stdio → herramientas dinámicas Axx → ConnectService → CommandService/ActionExecutor o handler UI existente → verificador/readback → eventos de respuesta e historial.

Desde host: plugin → SDK MCP stdio → descriptor DPAPI de la instancia activa → backend HTTP loopback autenticado → el mismo ConnectService → el mismo handler y evidencia → resultado estructurado al host.

App Server y MCP son protocolos distintos. `backend/connect/provider.py` correlaciona peticiones/eventos RPC, persiste thread IDs y usa resume tras reiniciar. La interfaz `start/get/cancel/status/login/disconnect/reconnect` permite reemplazar transporte sin cambiar los módulos UI. `logout` se conserva como alias de desconexión local; nunca invoca account/logout. La versión fijada es Codex 0.160.0 con esquemas generados en `evidence/axx-connect/schema`. Su API experimental se declara como tal.

El paquete privado lleva manifiestos portable y Codex separados. El override de instancia de prueba `AXX_CONNECT_DATA_DIR` se permite en `.mcp.json` mediante `env_vars`, según la [documentación de plugins](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins). El esquema portable 1.0.0 no acepta esa propiedad; conserva el lanzamiento normal del usuario sin inventar extensiones ni suponer fusión de manifiestos.

La compatibilidad Codex fija startup/tool timeout en 30 segundos. El [tiempo de gracia de catálogo opcional](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) es independiente: una prueba sin inferencia puede esperar la conexión con `mcpServerStatus/list`, o el host de prueba usar `mcp_optional_startup_grace_ms=0` sólo en su proceso. Los aliases de lectura se generan del registro; no se relajan permisos para hacer pasar una prueba.

## Registro

`backend/commands.py` conserva ADAPTERS y ejecutores actuales. `backend/connect/registry.py` amplía ese mismo mapa con adaptadores UI tipados y genera las cinco herramientas base y los aliases concretos de lectura. El catálogo documental sigue bloqueado. No se interpreta texto libre como código, shell, import ni nombre dinámico de método.

La UI anuncia handlers y renueva un heartbeat. Una capacidad UI sólo aparece disponible cuando su handler está anunciado en una instancia activa. El backend entrega una tarea con claim único y plazo acotado; la UI llama el handler existente y confirma readback. Una pérdida de respuesta conserva estado desconocido y bloquea reintentos ciegos.

## Seguridad y recursión

- Backend limitado a 127.0.0.1; Host, Origin, bearer, tamaños y entradas validados.
- Descriptor local de conexión cifrado DPAPI del usuario Windows; no token en manifest, frontend, argumentos ni logs. El plugin no lee las credenciales de Codex.
- Identificadores de operación vinculados a parámetros, origen, padre y límite de delegación. Una herramienta no reenvía al chat ni solicita otro agente.
- El proveedor deshabilita herramientas shell, MCP/plugins heredados y delegación; sus herramientas Axx ejecutan operaciones concretas. No hay ejecución directa de respuestas textuales.
- Una traducción que necesite otra inferencia no se delega recursivamente desde la misma ejecución de agente.
- El permiso se comprueba en el ejecutor; una skill no autoriza escrituras ni aprueba automáticamente eventos del runtime.

## Resultados e historial

Estados aceptado/preparado, en curso, esperando intervención, verificado, fallo, cancelado y desconocido se mantienen separados. Sólo `succeeded` con `postconditions_passed:true` representa un efecto verificado. Inferencia terminada usa el estado terminal documentado `completed` del runtime.

Tablas Connect en el SQLite de Axx conservan ejecuciones/eventos/conversaciones y tareas. CommandService y ActionExecutor mantienen resultados e IDs originales. Las recetas se crean desde evidencia del ejecutor, con versión y fingerprint; nunca se promueve una afirmación del modelo. ai-memory existente sigue opcional. El consumo sólo se guarda cuando llega en un evento del proveedor; no se estima facturación.

La repetición del mismo operation_id devuelve el resultado persistido sin repetir el efecto. Una tarea nueva con otro ID es otra ejecución: MCP puede realizarla de manera determinista sin inferencia, y la biblioteca existente permite buscar/preparar una receta compatible revalidando permisos. El chat libre no dispone de reutilización automática general de recetas antes de consultar al proveedor; no se declara esa optimización como completada.

## Límites de operación

MCP se inicia por host y no crea otra instancia de Axx. Una tarea larga devuelve ID; UI se reclama con plazo acotado. El proveedor comparte un plazo global de 70 segundos desde admisión entre arranque, autenticación, cuota, modelo, hilo y turno; cada RPC recibe sólo el tiempo restante. La UI consulta hasta 75 segundos y solicita cancelación correlacionada si se agota. La limpieza dispone de hasta 3 segundos para pedir interrupt. Un efecto incierto se conserva como `unknown` y el texto parcial no se borra.

Detener o el AbortSignal de la solicitud propia transmite interrupt y detiene sus acciones pendientes sin declarar rollback. Esc sólo cierra interfaz/seguimiento y no cancela tareas. Sólo se terminan procesos propios del runtime. La desconexión local persiste en SQLite y no toca la sesión compartida de Codex.

La UI exige selección explícita de modelo: una preferencia vacía o ausente del catálogo bloquea la prueba sin sustituirla. El runtime debe devolver tanto modelo como proveedor exactos; la ausencia produce MODEL_UNVERIFIED. La cuenta se vuelve a comprobar tras consultar cuota, antes de iniciar el turno y antes de cada despacho de herramienta.

La admisión del servicio se sincroniza con la cuenta en el punto de persistir y programar la tarea; preparación y ejecución prolongadas quedan fuera de ese bloqueo. Se revalida el plazo antes y después del commit. Si se rechaza, no se programa un worker y una fila UI comprometida queda bloqueada incluso si falla guardar su cancelación. Una actualización posterior no puede deshacer una tarea ya admitida; se conservan su ID, evidencia y vía de cancelación. El plazo es un límite cooperativo del software, no una garantía de planificación en tiempo real del sistema operativo.

Los esquemas/controlados son evidencia de contrato; audio, micrófono, pantalla, ventanas y experiencia visual requieren aceptación nativa aparte. El ZIP del plugin mantiene bootstrap y skill; necesita Axx compatible instalado o la instalación fuente registrada.
