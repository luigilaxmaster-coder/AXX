# Integración de razonamiento y autonomía · estado técnico

Este informe conserva el alcance original de los adjuntos. Distingue contratos
implementados de generalizaciones y aceptaciones pendientes. La fuente candidata
es Windows 0.22.32 / Android 0.2.13-code34; la descarga confirmada anterior es
[Windows 0.22.31](../releases/0.22.31.md). Cambiar fuentes no actualiza por sí solo
una instalación ni permite reutilizar sus recibos para otro binario.

## Arquitectura y autoridad

Se mantienen `ActionLearning`, `CommandService`, `ActionExecutor`, sus journals,
`SkillMemory`, la memoria de sesiones y el gateway móvil existentes. Los tres
perfiles modifican política; no crean tres asistentes o ejecutores.

Discreto limita la iniciativa espontánea; Copiloto propone/prepara y conserva la
aceptación requerida; Full admite iniciativa cubierta por permisos vigentes.
Autonomía, fuentes, retención e interrupciones siguen siendo decisiones distintas.
Un perfil no concede nuevas categorías de input, shell, MCP, envío o borrado.

La planificación general desde observaciones continúa cerrada con
`SOURCE_PLANNING_READY=False`; M15 no se sustituye por pruebas de lógica. Cuando
Conservar contexto está desactivado, tampoco se guardan ni ejecutan respuestas o
planes derivados de pantalla, micrófono o portapapeles. Un documento aporta datos
y procedencia, no autoridad para cambiar permisos.

## Contratos por requisito

| Requisito | Implementado en el alcance actual | Límite pendiente |
| --- | --- | --- |
| M1 · Misiones persistentes | Operación, objetivo, criterios, progreso, dependencias, recibos y presupuesto; continuación acotada. Familias `text_exact`, `xlsx_from_csv`, `file_bundle`. | Generalización a otras familias y aplicaciones con verificadores propios. |
| M2 · Aprendizaje causal | Actor/origen/causa, aceptación distinta de utilidad y cadenas de iniciativa limitadas. Una acción autónoma no acredita preferencia humana. | Atribución comprobada de nuevas fuentes manuales/externas; un evento del SO no identifica por sí solo al usuario. |
| M3 · Enseñar una vez | Documento/revisión/hash → candidato revisado → ensayo → habilidad con procedencia. La entrega .31 verificó reutilización de archivos tras reinicio sin llamadas al modelo. | Demostración semántica visual entre aplicaciones; esa prueba de archivos no acredita el escritorio completo. |
| M4 · Contexto por proyecto | Dos recursos elegidos explícitamente, identidad/versiones, leases de archivos y aprobación exacta. Cambios y revocaciones invalidan el plan. | Resolver libremente «este/el otro» entre aplicaciones y observación adaptativa con identidad real. |
| M5 · Capacidades comprobadas | Huellas de SO/Python/adaptadores, cuarentena, exclusión de lecciones obsoletas y ensayo explícito de revalidación. Recibos concretos registran versiones de aplicaciones. | Vincular la versión real vigente de cada aplicación al catálogo y a la reutilización; invalidación selectiva y alternativa equivalente comprobada. La huella actual no hace todo esto. |
| M6 · Preparación vigente | PREPARE sin ejecutar el efecto, entradas versionadas y revisión antes de cambios en las familias existentes. | Borradores/checklists especulativos generales y preview completo en otras aplicaciones. |
| M7 · Colaboración física | Broker, foreground/background, cancelación, pausa y corrección de la parte pendiente; conserva los efectos anteriores. | Iniciativa física multiaplicación y aislamiento/M15. La automatización física detenida con Escape no se reactiva mediante APIs internas. |
| M8 · Recuperación/deshacer | Journal y conciliación sin reenvío; compensación revisada para un archivo nuevo propio en NTFS. Detener y compensar son operaciones distintas. | Compensaciones verificables para otras operaciones; no restaurar versiones sobre cambios posteriores del usuario. |
| M9 · Memoria editable/olvido | Ámbitos, generaciones, preferencias explícitas, dependencias transitivas, limpieza reanudable y proyección cerrada de auditoría. | Procedencia irrecuperable en registros heredados y aceptación integrada adicional. No promete borrar copias externas ni efectos históricos. |
| M10 · Atención independiente | Agrupación por misión/revisión, presupuesto durable de interrupciones, descartar/silenciar/restaurar. | Utilidad humana y todos los recorridos físicos nuevos; una solicitud de voz no prueba reproducción audible. |
| M11 · Continuidad PC/móvil | Misma misión, corrección exacta, propietario durable, una sola admisión y conciliación de respuestas perdidas. La PC es el ejecutor. | Binarios nuevos, instalación con datos y aceptación física de esta extensión. El control de .2.11 no acredita M11 nuevo. |
| M12 · Trabajo humano | Feedback idempotente y evaluador offline de pares declarados con costes, fracasos, datos ausentes y salida atómica. | Pares humanos equivalentes reales, revisión del contenido de recibos, utilidad observada y holdout independiente. No hay cronómetro automático ni ahorro humano demostrado. |

## Continuidad de misiones: contrato técnico

El gateway añade rutas opcionales; conserva las rutas y permisos anteriores:

| Ruta | Función |
| --- | --- |
| `GET /v1/work/missions?conversation_id=...` | Misiones de la conversación original compartida. |
| `GET /v1/work/mission?operation_id=...` | Revisión y estado de la misma operación en la PC. |
| `POST /v1/work/mission-correct` | Preparar una corrección exacta, sin aprobar sus efectos. |
| `GET /v1/work/mission-correction?command_id=...` | Conciliar el ID original; no reenvía la corrección. |

La solicitud incluye `command_id`, `operation_id`, `conversation_id`, `plan_hash`,
`goal_revision`, `text`, `goal_spec`, `memory_scope` y `memory_context_id`. El
servidor conserva la validación estricta y no admite un proveedor, modelo,
aprobación, permiso o identidad de dispositivo impuestos por el cliente.

Se exige `tools.control`, historial compartido y procedencia vigente. El gateway
registra la vinculación antes de llamar al backend. SQLite compara el snapshot
durable para admitir un solo propietario; cancelación, olvido o cambio de dueño
invalidan una respuesta tardía. El journal de correcciones está acotado a 32
solicitudes y rechaza una nueva antes que eliminar evidencia de idempotencia.

El móvil guarda el cuerpo exacto y el dispositivo/certificado antes del POST.
Cambiar de PC, recargar o perder el ACK conserva el seguimiento y usa GET del ID
original. Otra revisión numérica no basta como prueba: la confirmación debe
coincidir con solicitud, operación, origen, revisión/hash anteriores y recibo
`awaiting_approval`. La revisión y ejecución continúan en la PC.

## Verificación reproducible y límites

El gate permanente es `python scripts/validate_companion.py --output ...`.
Incluye contrato, renderer, backend móvil, navegador y selector de archivos.
Las pruebas M11 de backend usan SQLite, HTTP/TLS y archivos temporales reales;
sus modelos son fixtures declaradas. El ensayo corta respuestas tras preparar
y tras el efecto, concilia el mismo ID y compara hashes sin repetirlo.

La matriz abre el editor y su revisión en 10 ventanas × 2 temas × 3 escalas de
texto × 2 DPR: 120 combinaciones. Incluye destino largo, controles táctiles y
borrador bajo altura de teclado de 299 px. Se conservaron referencias de
geometría, estilos y hashes; no equivale a teclado Android, plegable o iPhone.

La prueba MOSS de bytecode crea e importa un módulo temporal real con `-B`; no
carga un modelo ni produce voz. Cada guard de CI es independiente para que un
comando posterior no oculte un fallo anterior.

El evaluador de esfuerzo reutiliza `scripts/evaluate_reasoning.py` con
`--human-episodes ARCHIVO --output INFORME`. Solo calcula sobre los datos
declarados. Mantiene denominadores incompletos, tiempo desconocido y ahorro
negativo; no convierte latencia del modelo en trabajo humano ahorrado.
`independent_holdout_verified` y `physical_acceptance_verified` permanecen
falsos en ese informe descriptivo.

## Documentos de implementación

- [Objetivos y progreso](GOAL-PROGRESS.md).
- [Identidad y selección de recursos](RESOURCE-BINDINGS.md).
- [Memoria con ámbito y olvido](SCOPED-MEMORY.md).
- [Atención por misión](MISSION-ATTENTION.md).
- [Continuidad móvil](../mobile/MISSIONS.md).
- [Esquema y límites del esfuerzo humano](HUMAN-EFFORT.md).
- [Entrega y recibos exigidos](../RELEASING.md).

Los recibos privados contienen hashes y resultados de cada checkout/binario.
No se publican bases de datos, credenciales, voces, pesos ni datos de ejecución.
Una entrega parcial verificada no cierra automáticamente los pendientes de esta
tabla ni autoriza levantar los gates de observación o aislamiento.
