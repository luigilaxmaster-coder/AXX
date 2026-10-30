# Progresión de misiones con criterios verificables

Una misión conserva su `operation_id`, pasos confirmados, recibos, dependencias y
presupuesto de inferencia. Al terminar sus pasos, puede quedar en `goal_pending`:
las acciones están verificadas y el resultado acordado todavía está pendiente.
Ese estado no significa entrega completa.

El contrato opcional `goal_spec.criteria` admite hasta ocho criterios con ID
único, tipo y parámetros explícitos. El contrato completo conserva su límite de
16.000 bytes. Los tipos actuales son:

| Tipo | Parámetros | Comprobación independiente |
| --- | --- | --- |
| `text_exact` | `path`, `text` | Bytes UTF-8 del archivo real. |
| `xlsx_from_csv` | `source`, `destination`, `delimiter`, `numeric_column` | Celdas, tipos, fórmula y total del OOXML reabierto, frente al CSV. |
| `file_bundle` | `paths`, `destination`, opcionales `archive_name`, `max_output_bytes` | Fuentes, copias, manifiesto y miembros/contenido del ZIP, cuando se solicita. |

Las rutas pertenecen al workspace del ejecutor, sin enlaces ni destinos
superpuestos. Un criterio devuelve `satisfied`, `unsatisfied` o `indeterminate`
con un motivo cerrado. Un archivo existente incorrecto no se sobrescribe para
forzar el éxito. La disponibilidad del productor y sus permisos se comprueban
por separado: que el evaluador pueda leer OOXML no demuestra Excel disponible.

El generador selecciona el productor registrado de un criterio pendiente cuyo
destino aún no existe y cuyas entradas están disponibles. No requiere haber
ejecutado antes esa secuencia. Puede producir una entrada que necesita otro
criterio en un avance posterior. No interpreta objetivos arbitrarios fuera de
estos contratos: una condición no representable necesita revisión humana.

## Preparación y aprobación

`POST /axx-api/learning/propose` y `/prepare` aceptan `goal_spec` opcional.
Un contrato explícito entra en la identidad idempotente y queda fijado frente
a sustituciones del modelo. La corrección humana conserva el flujo `/repair`
con texto y revisión vigente del objetivo, sujeto al presupuesto existente.
Una reparación archiva las admisiones del sufijo descartado. Conserva las del
prefijo confirmado si el contrato sigue siendo el mismo; una corrección humana
a un contrato distinto archiva los vínculos anteriores. Los recibos e IDs se
conservan y la revisión nueva sigue exigiendo su hash exacto.

`POST /axx-api/learning/goal-progress` recibe `operation_id`, `plan_hash` y,
opcionalmente, `criterion_id` y `candidate_hash`. El último corresponde al
`fingerprint` presentado en `plan.goal_progress`. Prepara un único sufijo en la
misma misión y devuelve una nueva revisión `awaiting_approval`. No ejecuta.
La cola de iniciativa siempre vincula el candidato y el hash de origen.

El nuevo hash incluye la identidad de los pasos y las versiones de sus entradas
(ruta relativa, SHA-256, tamaño, identidad de archivo y fecha). Se revalidan
antes del despacho y al verificar la entrega. Un cambio detiene la continuación.
En Windows se mantienen los bloqueos nativos de escritura/borrado de las fuentes
durante toda la llamada al productor, cerrando el intervalo entre admisión y
copia. Si una plataforma no ofrece este bloqueo, se abstiene de continuar con
entradas de archivos; no se sustituye por una garantía basada sólo en rutas.
La aprobación manual de un sufijo requiere `plan_hash` exacto en `/execute` o
`/resume`; un cliente que sólo conserve el ID no puede ampliarla accidentalmente.

Se mantiene el máximo de ocho pasos totales y el presupuesto de inferencia
acumulado. Generar este sufijo determinista no consume ni reinicia llamadas al
modelo. No crea una habilidad, preferencia ni permiso a partir del éxito
autónomo. Los recibos de un efecto parcial o incierto se conservan sin repetirlo.

## Perfiles y límites de verificación

Discreto conserva su política de no iniciar propuestas espontáneas. Copiloto
presenta/prepara el avance para revisión. Full puede continuar con un permiso
genérico vigente que ya cubra tarea, categoría, parámetros, rutas y recursos.
Un permiso ligado a la revisión anterior de un plan no se amplía al añadir pasos.
La pausa, cancelación, exclusiones y revocaciones siguen prevaleciendo.

Se reutilizan la cola residente y sus revisiones de eventos/comandos para
reevaluar misiones. No se añade un planificador paralelo ni un sondeo continuo
de archivos. Las dependencias enlazadas conservan su revisión y recibos.

Las pruebas usan archivos temporales, un servidor HTTP local aislado y fixtures
OOXML. QA reservó misiones ZIP antes de congelar el productor; sus primeros
resultados y hashes se conservan en evidencia privada, y los datos sintéticos
se versionan para reproducir las regresiones en CI. Esto no certifica control
de Windows completo, Excel físico, voz, Telegram, teléfono ni aceptación visual
nativa. Los permisos de envío de contexto observado continúan tras sus gates
cerrados; esta progresión no los activa.
