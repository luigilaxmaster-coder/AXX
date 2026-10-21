# 10 — Incrementos 2B/2C: cuotas reales y cola persistente

ESTADO: ESPECIFICADO, NO IMPLEMENTADO. Estas ampliaciones se entregan después del incremento base y con flags separados. No afirmar que status() del baseline conoce saldo remoto o reprograma tareas.

## 2B: ámbito de cuota compartido

Cada conexión declara una referencia privada `quota_scope_id` de la cuenta/organización real y un identificador de modelo. La referencia no contiene credenciales. Reserva de presupuesto local se hace de forma atómica por scope, no solo por nombre de proveedor. Varias conexiones del mismo scope comparten el límite que corresponda; un límite adicional por modelo se representa explícitamente.

Contrato propuesto del adaptador oficial:

`read_quota(scope_id) -> QuotaSnapshot` con source=official_api|headers|local_only|unknown; fetched_at; requests_remaining/tokens_remaining/credit_remaining como número o null; currency si corresponde; reset_at UTC o null; scope; confidence=observed|declared|unknown. No estimar dinero restando solicitudes: cada una puede costar distinto.

Proveedores sin endpoint oficial confirmado devuelven unknown. El implementador debe consultar la documentación primaria y probar autenticación, shape y errores antes de escribir el adaptador. No inventar `/quota` ni reutilizar un endpoint de otro proveedor. Cache TTL inicial 60 s; no hacer una consulta de saldo por cada turno. No loguear cuerpo autenticado entero.

Si los headers solo informan límite por minuto, no presentarlos como saldo diario. Si consumo local y remoto difieren, elegir la restricción más conservadora y mostrar fuente/fecha. Un contador viejo no debe habilitar llamadas que el proveedor acaba de bloquear.

## Máquina de pausa propuesta

Estados del scope: eligible, rate_limited, quota_exhausted, auth_blocked, policy_blocked, unknown. rate_limited usa Retry-After válido; quota_exhausted usa reset_at oficial cuando exista; sin reset conocido no inventar fecha. auth_blocked requiere corregir clave/permisos; policy_blocked no se resuelve reenviando para eludir restricciones. Mantener jitter solo en workers diferibles, no en bucles interactivos.

Pruebas: dos modelos/scope no duplican presupuesto; reservas concurrentes no exceden límite; snapshot desconocido conserva null; reloj/reset UTC; datos obsoletos no habilitan capacidad; 429 sin headers no produce saldo inventado.

## 2C: cola de tareas diferibles

Solo contenido/operaciones que puedan esperar y estén marcadas por host/usuario. Chat interactivo no se encola silenciosamente. No reanudar acciones sensibles automáticamente al reiniciar. Separar request_id (intento de inferencia), task_id (trabajo durable) y operation_id (efecto idempotente).

Contrato propuesto: `enqueue(task, idempotency_key) -> task_id`; `claim(worker_id, lease_until) -> task | None`; `complete(task_id, result)`; `retry(task_id, next_run_at, reason)`; `cancel(task_id)`.

Tabla tasks propuesta: id PRIMARY KEY, idempotency_key UNIQUE, payload_ref, state, attempts, max_attempts, next_run_at, expires_at, lease_until, worker_id, last_error_code, created_at, updated_at. Estados queued, leased, waiting_quota, succeeded, failed, cancelled, expired, unknown_effect. No guardar prompts privados sin política de retención; preferir referencia a datos locales existentes.

Transiciones:

- queued/waiting_quota → leased mediante transacción de claim, un worker propietario.
- leased → succeeded solo después de verificación; error recuperable → waiting_quota con próximo tiempo elegible.
- attempts>=max_attempts o error definitivo → failed; expires_at alcanzado → expired.
- cancel → cancelled, worker respeta token y no ejecuta siguiente paso.
- lease vencido sin efectos: volver a queued; con efecto potencial desconocido: unknown_effect hasta reconciliar.

Valores iniciales de diseño: un worker, máximo 5 intentos de trabajo, TTL 24 h, lease 90 s con heartbeat cada 15 s, y backoff de 60 s, 300 s, 900 s, 3600 s entre intentos; si Retry-After oficial es mayor, respetarlo. No ejecutar después de expires_at. Un intento de trabajo puede consumir hasta 3 intentos de proveedor del router; mostrar ambos contadores para no aparentar un único consumo.

## Aceptación de cola

Cancelar evita nuevos pasos; dos workers no reclaman la misma tarea; reinicio no duplica operación; expiración vence espera; todos los proveedores agotados deja waiting_quota sin bucle; reset remoto desconocido no inventa horario; trabajo sensible no cambia de política al reanudarse; borrar payload no deja tareas ejecutables huérfanas. Probar con datos sintéticos y reloj controlado.
