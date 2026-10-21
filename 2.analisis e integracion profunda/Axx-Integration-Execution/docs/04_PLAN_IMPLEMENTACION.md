# Integración del router en Axx — plan de implementación

> Para ejecutores: usar ejecución secuencial en el proyecto real; aplicar la guía de ejecución de planes disponible en el entorno. Cada tarea deja pruebas y evidencia antes de avanzar. No se requiere delegación para este paquete.

**Goal:** Axx debe responder mediante dos proveedores aprobados, continuar ante fallos elegibles y cancelar sin efectos duplicados.

**Architecture:** adaptador en backend existente, router privado y SQLite local. Sidecar por solicitud si no existe un backend Python reutilizable. La UI conserva su diseño y solo recibe contenido/metadatos sanitizados.

**Tech Stack:** stack real de Axx por inspeccionar; baseline Python 3.11+ sin dependencias externas; herramientas de procesos y empaquetado nativas del host.

**Spec:** [02_ESPECIFICACION.md](02_ESPECIFICACION.md), contratos en [03_CONTRATOS.md](03_CONTRATOS.md).

## Restricciones globales

Una entrada por cuenta en incremento 1; máximo 3 intentos por solicitud; deadline de pared 70 s; timeout socket 20 s; 1 solicitud en vuelo por conversación, 2 globales; sin streaming; sin herramientas remotas incorporadas; sin pagos; sin claves en frontend; no modificar UI salvo estado discreto y conexión al chat.

## Review Focus

1. JSON/configuración malformados: error manejado sin traceback ni llamada a red; T1.
2. Proceso colgado o resultado posterior a Esc: cancelación terminal, sin respuesta tardía ni huérfano; T2/T4.
3. Cuota compartida por modelos/cuentas: no aparentar cuota extra; T3/T5.
4. Reinicio en mitad de acción: no repetir un efecto desconocido; T4/T6.
5. Rutas con espacios, instalación limpia y datos bajo Program Files: sidecar y DB funcionan desde el binario empaquetado; T6.

## Mapa de archivos

El baseline real está en `baseline/axx-api-router/`. En el proyecto de destino, proponer `backend/inference/` solo si coincide con la convención existente. No copiar esa ruta sin inspección.

| Símbolo lógico | Responsabilidad | Resolución obligatoria |
|---|---|---|
| ROUTER_SOURCE | Copia endurecida de router.py y pruebas | Ruta nueva bajo backend real |
| INFERENCE_ADAPTER | route/cancel/get_status, límites, normalización | Módulo backend existente o nuevo próximo a él |
| CHAT_CALLSITE | Llamada actual al modelo | Archivo y símbolo descubiertos |
| SECRET_RESOLVER | Obtención de credenciales sin frontend | Implementación nativa existente o nueva |
| APP_DATA_RESOLVER | Directorio de configuración y DB | API real del framework |
| UI_STATE | Render mínimo de estados existentes | Componente/store descubierto |
| TOOL_EXECUTOR | Ejecutor de herramientas si existe | Ruta real, o explícitamente ausente |
| PACKAGE_CONFIG | Recursos/sidecar del instalador | Manifest real del stack |

Completar rutas concretas antes de editar T1. No dejar el mapa lógico como si fuera un mapa real terminado.

## T0 — Descubrimiento y línea base

**Files:** templates/PROJECT_MAP.md y evidencia; no modificar producto todavía.

**Interfaces:** consume repo abierto; produce mapa de rutas, comandos de build/test y punto de reversión.

- [ ] Registrar root, rama, commit y cambios del usuario. Leer instrucciones locales.
- [ ] Localizar CHAT_CALLSITE, worker/backend, secretos, persistencia, Esc y empaquetado con búsqueda de texto y lectura.
- [ ] Ejecutar pruebas/build actuales; registrar fallos previos con nombre. No atribuirlos al router.
- [ ] Ejecutar `scripts/verify_baseline.ps1` en Windows o los comandos equivalentes del documento 05.
- [ ] Crear rama aislada o mecanismo de aislamiento que el proyecto soporte; no limpiar cambios del usuario.
- [ ] Completar PROJECT_MAP; ninguna ruta inferida se marca como verificada.

Salida: G0 satisfecho, evidencias del punto de entrada y decisión de integración Python/sidecar.

## T1 — Endurecer contrato y transporte

**Files:** ROUTER_SOURCE, tests/test_validation.*, tests/test_transport.* en el layout real.

**Interfaces:** consume config/request del contrato A/B; produce las mismas firmas Router más errores normalizados. No cambia las claves admitidas sin actualizar contratos.

- [ ] Escribir tests de config null/lista, bool en enteros, capacidades no-string, modelo de plantilla, roles/content inválidos y temperature NaN. Afirmar que no se invoca transporte y el CLI devuelve JSON de error.
- [ ] Escribir tests de Retry-After='inf', 'NaN', negativo y fecha sin zona: finito 0 para inválidos, máximo 86400. Tests de message={} y tool_calls inválidos: no éxito.
- [ ] Escribir tests de body excesivo y stdin tope+1: rechazo controlado sin deserializar la entrada completa.
- [ ] Ejecutar los nuevos tests y registrar el fallo que reproduce cada defecto antes de corregir.
- [ ] Implementar validadores estrictos; `json.loads` rechazará constantes no estándar; normalizar fallos de protocolo. Limitar la lectura de upstream a 7 MiB para el sidecar.
- [ ] Corregir 403 desconocido para detener con UPSTREAM_POLICY; mantener prueba de no fallback ante políticas. Registrar el cambio frente al baseline.
- [ ] Ejecutar suite completa más las 20 regresiones; registrar comando y total. Commit específico sin claves ni DB.

Salida: H02/H03/H05/H06/H07 cerrados con evidencias; parte de H01/H10 cubierta.

## T2 — Adaptador, deadline y secretos

**Files:** INFERENCE_ADAPTER, SECRET_RESOLVER, APP_DATA_RESOLVER, tests/test_adapter.*.

**Interfaces:** produce route(InferenceEnvelope), cancel(request_id), get_status() del contrato D. Consume Router.chat/status o CLI privado.

- [ ] Test con proveedor simulado que nunca termina: a deadline de prueba 100 ms termina DEADLINE_EXCEEDED y no deja proceso vivo; usar reloj controlado donde sea posible.
- [ ] Test con stdout inválido, exit 1 y stderr de 100 KiB: PROCESS_FAILURE/error mapeado, capture stderr limitado y sin imprimirlo entero al usuario.
- [ ] Test con config/DB/script en rutas con espacios: arranque por vector de argumentos, shell desactivado.
- [ ] Test con dos solicitudes misma conversación: segunda BUSY; dos conversaciones se permiten hasta límite global 2.
- [ ] Implementar launcher/worker cancelable, deadline de pared, EOF y terminación de proceso. Python import: si no se puede interrumpir un hilo de red de forma fiable, ejecutar la llamada bloqueante en proceso cancelable; no afirmar que cancelar una future detuvo el socket.
- [ ] Resolver rutas absolutas en datos de usuario; validar directorio escribible. Obtener claves dentro del backend y pasarlas solo al proceso requerido, sin logs de entorno.
- [ ] Mapear errores; si DB falla antes de reserva, STATE_UNAVAILABLE sin enviar. Si falla después del envío, no repetir fuera del router.
- [ ] Ejecutar tests de adaptador y suite global; guardar evidencia y commit.

Salida: H01/H08/H10 cubiertos en adaptador. Cancelación no garantiza retractar una solicitud que ya llegó al proveedor; garantiza detener el flujo local y no aceptar resultado tardío.

## T3 — Selección, diagnóstico y progreso real

**Files:** ROUTER_SOURCE / INFERENCE_ADAPTER, pruebas de selección y status.

**Interfaces:** produce eventos internos {request_id, type, provider?, attempt?, reason?}; type start/attempt/failover/completed/failed/cancelled. No añadir estos campos a chat upstream.

- [ ] Test 429 en A + éxito B: mismo historial, attempts=2, eventos ordenados y pausa de A persistida.
- [ ] Test visión/herramientas: no elegir B si carece de capacidad, incluso si A agotó cuota.
- [ ] Test same-account: configuración inicial rechaza dos entradas activas para la misma cuenta registrada por el host; referencia privada no contiene clave.
- [ ] Test 400, cancelación y política 403: sin fallback. Test SQLite no disponible: sin envío.
- [ ] Implementar proyección de estado y callback/evento por intento según IPC existente; no inventar progreso desde un temporizador UI.
- [ ] Mantener priorización determinista; no consultar un LLM para seleccionar otro LLM.
- [ ] Ejecutar suite, registrar y commit.

Salida: status distingue local/remoto y no filtra secretos. H04 mitigado por registro de cuentas sin introducir cuota remota ficticia.

## T4 — Conectar chat y cancelar en Axx

**Files:** CHAT_CALLSITE, UI_STATE, TOOL_EXECUTOR si existe, pruebas de flujo.

**Interfaces:** consume adaptador; produce respuesta en historial existente y estado visual real.

- [ ] Test envío desde conversación existente: se invoca route una vez y se agrega una respuesta completa una vez.
- [ ] Test Esc durante A lento y durante cambio a B: terminal CANCELLED, sin respuesta tardía ni nuevo intento.
- [ ] Test historial de tool_calls: resultado de herramienta ya ejecutada se conserva; no reejecutar operation_id existente al continuar con B. Si no existe ejecutor, herramienta permanece deshabilitada.
- [ ] Implementar flag `api_router_enabled` en la configuración real; default desactivado hasta G4. Reutilizar persistencia y menú de Axx.
- [ ] Agregar estado discreto; no cambiar disposición radial, cuerpo o dimensiones. Conservar dictado sin autoenvío y atajos.
- [ ] Ejecutar pruebas funcionales existentes y nuevas; documentar cómo se observaron desde UI. Commit.

Salida: INTEGRADO_DEV sin declarar VALIDADO_LIVE todavía.

## T5 — Validar dos proveedores reales

**Files:** config local fuera de git, PROVIDER_VALIDATION por cuenta sin secretos, evidencia sanitizada.

**Interfaces:** consume claves locales y modelos reales; produce registro PASS/FAIL por capacidad/fecha.

- [ ] Verificar documentos oficiales y consola: modelo, precio/tier, cuota, región, condiciones y política de datos.
- [ ] Probar cada proveedor solo con prompt sintético y salida de 64 tokens. No usar documentos personales para smoke tests.
- [ ] Activar capabilities únicamente para funciones probadas. No habilitar herramientas remotas ni pagos.
- [ ] Probar fallback mediante inyección controlada de 429 en dev; no agotar cuota real intencionadamente. Probar también principal desactivado → B, distinguiéndolo de un 429 live.
- [ ] Demostrar desde Axx con claves locales el éxito de A y de B; registrar modelo, fecha, provider y resultado, sin prompts privados.
- [ ] Si faltan credenciales: marcar BLOCKED_CREDENTIALS, continuar T6 offline, no simular un live exitoso.

Salida: VALIDADO_LIVE solo con evidencia real separada de mocks.

## T6 — Windows, release y rollback

**Files:** PACKAGE_CONFIG, pruebas de instalador, DELIVERY_STATUS.

**Interfaces:** consume flags/config/sidecar; produce artefacto instalable y procedimiento de reversión.

- [ ] Test binario desde acceso directo con cwd distinto: recursos se resuelven y DB no se crea en carpeta de instalación.
- [ ] Test usuario sin Python si el instalador promete independencia: incluir runtime privado o sidecar empaquetado; si requiere Python, declararlo y verificar versión antes de habilitar.
- [ ] Test reinicio: contadores/pausas sobreviven; ninguna acción pendiente se ejecuta automáticamente sin reconciliación.
- [ ] Probar flag off y rollback de versión/config sin borrar historial/DB ni afectar módulos existentes.
- [ ] Medir en Acer arranque, memoria del módulo, tiempo y respuesta de Esc bajo fallo. Reportar mediciones reales, no estimaciones presentadas como benchmarks.
- [ ] Ejecutar todas las pruebas/build del proyecto, matriz 07 y verificación de artefactos. Completar DELIVERY_STATUS.

Salida: RELEASE_READY solo si G0–G6 PASS; de lo contrario entregar artefacto de desarrollo con bloqueos explícitos.

## Incrementos siguientes

Aplicar 09 y 10 como planes independientes después del release base. No introducir memoria que reejecute acciones ni una cola persistente sin pruebas de idempotencia y recuperación propias.
