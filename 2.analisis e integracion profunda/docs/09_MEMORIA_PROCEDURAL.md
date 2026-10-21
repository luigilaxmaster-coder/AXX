# 09 — Incremento 2A: memoria procedural verificable

ESTADO: ESPECIFICADO, NO IMPLEMENTADO. No es requisito para demostrar el failover base. Objetivo: repetir procedimientos ya comprobados con menos llamadas a modelos y corregir recetas mediante evidencia. No modifica los pesos del modelo ni garantiza aprendizaje autónomo.

## Componentes y contratos propuestos

`find_recipe(intent_key, environment_fingerprint) -> Recipe | None`; `verify_preconditions(recipe, inputs) -> CheckResult`; `execute_recipe(recipe, inputs, operation_id) -> ExecutionResult`; `verify_postconditions(recipe, result) -> CheckResult`; `record_attempt(...)`; `promote_version(recipe_id, version)`.

Registrar herramientas reales del ejecutor de Axx. Un paso referencia tool_name y argumentos tipados, no una cadena de shell libre. Tool inexistente impide ejecutar. La receta procede de una ejecución que terminó y cuya postcondición fue verificada; texto generado por un modelo nunca entra directamente como receta activa.

## Modelo de almacenamiento propuesto

Base separada o migración versionada; no añadir estas tablas a la DB baseline sin implementar su manejo:

- recipes(id TEXT PRIMARY KEY, intent_key TEXT, version INTEGER, status TEXT, env_fingerprint TEXT, schema_json TEXT, steps_json TEXT, preconditions_json TEXT, postconditions_json TEXT, verified_at TEXT).
- recipe_attempts(id TEXT PRIMARY KEY, recipe_id TEXT, recipe_version INTEGER, operation_id TEXT UNIQUE, started_at TEXT, ended_at TEXT, outcome TEXT, evidence_json TEXT).
- operations(operation_id TEXT PRIMARY KEY, recipe_id TEXT, state TEXT, args_hash TEXT, result_json TEXT, updated_at TEXT).

status de receta: candidate, verified, deprecated, quarantined. Estado de operación: prepared, running, succeeded, failed, unknown, cancelled. Al reiniciar, running no se convierte automáticamente en failed/retry; primero reconciliar con estado de la app/herramienta. No almacenar contraseñas ni datos privados innecesarios en evidence_json.

## Ejecución

1. Normalizar intención a clave controlada por el host; extraer parámetros tipados. Si es ambiguo, consultar al usuario o al modelo sin ejecutar efectos.
2. Encontrar receta verified para versión de app/OS/herramientas compatible.
3. Validar entradas y precondiciones: destino existe, app correcta, herramienta disponible, operación autorizada.
4. Crear operation_id y estado prepared antes del primer efecto; transacción corta.
5. Ejecutar paso por paso con Esc/cancelación; persistir resultados y comprobaciones.
6. Verificar postcondiciones reales: archivo creado/ventana abierta/estado requerido. Una respuesta 'hecho' del modelo no es prueba.
7. Guardar intento. Si falla precondición, no ejecutar y considerar replanificación. Si falla postcondición, poner receta en revisión; si efecto desconocido, estado unknown y prohibir reintento automático.

Ejemplo apto: abrir una app instalada comprobando su proceso/ventana. Ejemplo que exige política específica: enviar mensaje, compra o eliminación. La autorización para una receta pasada no autoriza todas sus futuras variaciones ni destinatarios.

## Mejora de recetas

Nueva versión candidate se evalúa contra casos reproducibles aislados. Promoción solo si pasa las mismas postcondiciones, no reduce controles y no amplía permisos. Mantener versión anterior para rollback; no sobrescribir receta activa durante ejecución. Métricas: éxitos verificados/total, pasos, tiempo y llamadas a modelo ahorradas contando invocaciones reales; no inventar porcentaje de ahorro.

## Pruebas de aceptación

- Repetir operación determinista con mismo operation_id: una ejecución del efecto.
- Cambiar versión de app/env_fingerprint: receta no se utiliza automáticamente.
- Postcondición falla: nunca registrar éxito ni promover la versión.
- Reinicio entre efecto y persistencia: unknown hasta reconciliar, sin repetir.
- Esc entre pasos: no ejecutar el siguiente.
- Intento de inyectar shell o nombre de herramienta desconocido: rechazo.
- Evidencia/logs sin secretos; rollback conserva historial de intentos.

Aplicar después de validar el ejecutor real. No instalar ai-memory u otro proyecto por parecido de nombre como sustituto de estos contratos sin evaluación separada y autorización del alcance.
