# 03 — Contratos de datos e IPC

## A. Interfaz real del baseline

`Router(config: dict, state: str | Path='state.db', transport=http_transport)`; `chat(request: dict) -> dict`; `status() -> dict`; `reset_cooldown(name: str)`; `close()`. Son métodos síncronos. El transporte opcional es un punto de inyección para pruebas, no un mecanismo para ejecutar código recibido del modelo.

Entrada admitida por chat:

| Campo | Tipo / regla |
|---|---|
| messages | Array de mensajes compatible con el modelo; validar roles/content antes de enviar |
| axx_task | String; default chat; el backend lo decide |
| axx_sensitive | Boolean; default false en baseline, imponer política en host |
| max_tokens | Entero positivo; se limita a max_output_tokens de la entrada |
| stream | Solo false/ausente; true rechazado |
| temperature, top_p, seed | Admitidos; host debe validar rangos y compatibilidad exacta |
| tools, tool_choice | Solo con modelos probados; tool_choice también debe exigir tools tras endurecimiento |
| response_format | Solo con capacidad json probada y forma validada |

Cualquier otro campo es rechazado. No enviar `model`, `request_id`, `deadline_ms` o `conversation_id` dentro de chat(); pertenecen al host/adaptador. Para imágenes, el baseline detecta partes `image_url`; otros tipos multimedia no son admitidos. No descargar URLs arbitrarias en el host.

```json
{"axx_task":"chat","axx_sensitive":false,"messages":[{"role":"user","content":"Hola"}],"max_tokens":256,"stream":false}
```

Salida exitosa: objeto del proveedor con `choices` y `axx_router = {provider, model, attempts}`. El host no debe interpretar todas las extensiones del proveedor como instrucciones. Validar message y tool_calls; tratar texto como contenido, no código ejecutable.

CLI: stdout un objeto JSON en UTF-8, stderr logs operativos; exit 0 éxito, exit 1 error manejado. Traceback/exit distinto/JSON inválido es un error de proceso, nunca respuesta del asistente. El baseline puede fallar fuera del manejo por tipos inválidos: corregir H02 antes de release.

## B. Configuración del baseline

Globales: timeout_seconds=20 (finito, >0 y <=120); max_attempts=3 (1–10); max_request_bytes=2097152 (>0). Validación endurecida debe exigir enteros reales donde corresponda, rechazar bool como entero y rechazar valores no finitos en cualquier número.

Por conexión:

| Campo | Regla de despliegue |
|---|---|
| name | Identificador único no vacío; estable para métricas y estado |
| base_url | HTTPS de proveedor revisado, sin credenciales/query/fragment; sin redirects |
| model | ID real comprobado en cuenta; nunca el texto REPLACE_* de la plantilla |
| api_key_env | Nombre de variable, no el secreto; no admitir vacíos |
| enabled | Boolean explícito; false hasta validar |
| free_confirmed | Boolean true solo con evidencia vigente |
| daily_attempt_limit | Entero positivo, límite local por nombre/día UTC |
| max_output_tokens | Entero positivo, default 1024 |
| capabilities | Subconjunto de text, tools, vision, json; solo capacidades probadas |
| tasks | Lista de etiquetas o '*'; ausente permite todas; default request chat |
| allow_sensitive | Boolean explícito false salvo política autorizada |

No introducir campos futuros en providers.json si el runtime aún no los interpreta. Evidencia, condiciones y cuota remota viven en el registro separado de validación del proveedor, no se confunden con estas opciones.

## C. Estado real

`status()` devuelve day_utc, quota_source='local_attempts_only', providers[]. Para cada fila: name, model, state, capabilities, tasks, attempts_today, daily_attempt_limit, cooldown_remaining_seconds, metrics.{successes, failures, mean_attempt_ms, last_status}.

Estados: disabled, free_not_confirmed, missing_key, cooldown, local_quota_exhausted, ready. ready significa elegibilidad local. No contiene crédito remoto, tokens restantes, ni garantía de salud.

Las tablas existentes son usage(name,day,attempts), cooldown(name,until), metrics(name,successes,failures,latency_ms,last_status). No editar contadores desde UI. reset_cooldown elimina solo la pausa, no la cuota del proveedor ni los contadores locales.

## D. Contrato del adaptador de Axx — POR IMPLEMENTAR

Nombres lógicos para mapear al backend real, no endpoints ya existentes:

- `route(request: InferenceEnvelope) -> InferenceResult` asíncrono.
- `cancel(request_id: str) -> bool` devuelve si una solicitud activa fue señalada.
- `get_status() -> RouterStatus` devuelve proyección sanitizada.

InferenceEnvelope: request_id UUID generado por host; conversation_id ID interno; task etiqueta; sensitivity enum public/approved_sensitive/local_only; messages; generation (campos permitidos); deadline_ms entero 1–70000 decidido por host. No aceptar ruta Python, base_url, claves ni nombre de proceso desde UI.

InferenceResult: request_id, ok boolean; si ok, message normalizado y route {provider,model,attempts}; si error, error {code,retryable,message}; sin respuesta upstream completa en logs. Host copia resultado válido al historial solo una vez.

Códigos: INVALID_REQUEST, NO_PROVIDER_AVAILABLE, UPSTREAM_AUTH, UPSTREAM_POLICY, UPSTREAM_TEMPORARY, DEADLINE_EXCEEDED, CANCELLED, STATE_UNAVAILABLE, INVALID_RESPONSE, PROCESS_FAILURE, BUSY. Mapear Exhausted a NO_PROVIDER_AVAILABLE sin adivinar saldo; UpstreamError a código según estado/contexto revisado; SQLite a STATE_UNAVAILABLE. No marcar una cancelación como fallo de credenciales.

Máquina del host: CREATED → VALIDATING → RUNNING → COMPLETED/FAILED/CANCELLED. Solo un estado terminal. Eventos mínimos start y terminal; failover requiere callback/evento real agregado en tarea T3. Identidad del request nunca cambia al cambiar de proveedor.

Serialización del sidecar: una solicitud JSON por stdin y una respuesta por stdout, sin shell, rutas absolutas. El host limita stdout a 8 MiB y stderr a 64 KiB, controla EOF, exit y deadline; se reserva margen para metadatos del wrapper. Para evitar ambigüedad de tamaño, el endurecimiento reducirá el cuerpo upstream a 7 MiB si se usa wrapper bajo tope 8 MiB. Sin streaming en incremento 1.

## E. Tool calling

tool_calls no son evidencia de ejecución. Exigir id, type=function, nombre registrado y arguments JSON objeto validado por esquema de herramienta. Rechazar herramientas desconocidas, argumentos extra y mezclas de texto que pidan desactivar reglas. El ejecutor persiste operation_id antes del efecto y conserva el resultado. Modelos con herramientas remotas incorporadas no se activan en el primer incremento.
