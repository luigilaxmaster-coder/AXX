# Olvido por sesión y correcciones de memoria

Esta unidad implementa M9 de los adjuntos sobre los repositorios existentes. No completa las otras extensiones pendientes ni acredita una instalación nueva.

## Recorrido

`petición humana completa → referencia de tarea/contexto capturada → revisión concreta → transacción de generación → invalidación atribuible → recibo idempotente`.

`memory_task_scopes` comparte la base de estado. El olvido incrementa la generación y publica `forgetting` antes de limpiar derivados. Los escritores, respuestas tardías, continuaciones y comandos vuelven a comprobar su referencia original. Una referencia antigua nunca se sustituye por la generación actual para terminar una operación pendiente. El contexto opaco de conversación también rota: una respuesta de B que dependía de A no se vuelve válida sólo porque B conserve su propia generación.

Los checkpoints de limpieza son durables. El mismo ID reanuda un olvido interrumpido sin incrementar otra vez la generación. El arranque intenta terminar los checkpoints pendientes; mientras tanto se rechaza reutilizar su memoria. Repetir una operación ya terminada devuelve su recibo y no cancela trabajo posterior.

Una exclusión por tarea entre procesos impide dos limpiezas simultáneas. Se distingue la procedencia durable de un conocimiento del token capturado por una petición: rotar B para retirar contexto de A no elimina conocimiento independiente de B. El historial A0 ya archivado tampoco invalida trabajo nuevo e independiente de A1.

`chat_context_ids` conserva la atribución original de cada ID opaco al crear o rotar una conversación, incluso tras borrar o purgar su historial. Connect consulta esa atribución antes de admitir o reanudar un hilo; un ID antiguo no se convierte en otra tarea legacy. La migración recupera tokens explícitos de ejecuciones con procedencia conocida. No puede reconstruir IDs históricos ya purgados y sin esa evidencia.

Las reparaciones, las versiones configuradas y los comandos recordados conservan las dependencias de su fuente. Una habilidad heredada con operación conocida expone las referencias originales sin reescribir su fila ni actualizar su generación. Al cambiar sólo metadatos de una habilidad, la transferencia interna de evidencia lee los recibos almacenados bajo la petición nueva; no permite publicar una respuesta tardía con el token anterior.

## Qué alcanza y qué conserva

| Repositorio | Tratamiento |
| --- | --- |
| Historial, adjuntos, notas y vínculos de chat | Invalida memoria reutilizable y dependencias causales. El historial local queda disponible mediante lectura histórica explícita. Conserva el borrador. |
| Contexto, aliases, valores aprendidos, incidentes y habilidades | Retira el origen conocido y sus dependencias. Conserva conocimiento independiente con procedencia vigente. |
| Planes y cachés de inferencia del plan | Impide reparar, reanudar, aprobar o publicar resultados derivados de una referencia revocada. Conserva identidad, recibos y presupuesto consumido. |
| Taller y transformaciones generadas | Revoca revisiones atribuibles y su disponibilidad en el catálogo. El comando vuelve a comprobar el origen antes de ejecutar. |
| Iniciativas y rutinas | Retira aprendizaje atribuible y bloquea observaciones/respuestas pendientes. No amplía ni reinicia grants o cuotas. |
| Memoria de procedimientos y adaptador externo | Usa procedencia y autoridad local para bloquear reutilización. No afirma haber eliminado páginas externas. |
| Connect, Bridge y Telegram | Capturan tarea y contexto antes de esperar. Rechazan publicación y herramientas tardías sin borrar el journal de efectos. |
| Sincronización del teléfono | Filtra mensajes y eventos reutilizables por procedencia; conserva filas, IDs, cursores y recibos. El espejo espera el guardado y conserva el token anterior a cada espera. |

No se borran archivos creados, recibos de comandos, compensaciones, credenciales, emparejamientos ni preferencias de apariencia. Una compensación de un archivo conserva su recorrido de revisión independiente aunque su sesión de aprendizaje se haya olvidado. Las filas de presupuesto no se reinician para conseguir inferencias adicionales.

Los planes olvidados exponen una lista cerrada de encabezados de recuperación: identidad, estado, revisión, recibos y contadores históricos. No copian mensajes, destinos, entregables, verificaciones con contenido, parámetros de habilidades ni campos futuros del snapshot. La misma proyección se aplica al consultar un plan, listar planes, recuperar operaciones del chat y devolver una mutación descartada por olvido. Se comprueban las referencias originales de tarea, contexto y dependencias, incluso antes de terminar la limpieza. La proyección no reescribe el journal; conserva disponibilidad de archivos apartados y no restaura una aprobación.

El contenido heredado sin procedencia comprobable se conserva y queda fuera de selección automática y envío como referencia hasta revisarlo. No se atribuye mediante coincidencias de texto. Los valores iniciales vacíos del contexto no se consideran conocimiento heredado. Esta política puede reducir la reutilización de procedimientos antiguos después del primer olvido.

## Correcciones naturales

Se reconocen sólo solicitudes humanas completas, sin extraer instrucciones de documentos, citas o respuestas del modelo:

| Solicitud | Cambio |
| --- | --- |
| «Eso era solo para este proyecto.» | Reduce el procedimiento seleccionado al proyecto actual. |
| «No uses más ese procedimiento.» | Retira la selección automática; un nuevo uso manual por ID todavía debe prepararse y revisarse. |
| «Hazlo así de ahora en adelante en esta carpeta.» | Registra una preferencia para la carpeta exacta y el proyecto actual; no incluye descendientes. |
| «Olvida lo que aprendiste de esta/esa sesión.» | Invalida la memoria atribuible y sus derivados. |

Si falta un procedimiento, versión, proyecto o carpeta concreta, la vista previa devuelve `needs_input` sin modificar memoria. Aplicar exige el hash de la revisión, la versión y la revisión de selección vigentes. Una corrección no concede permisos ni ejecuta comandos. Una regla cuya procedencia se olvida queda retirada para revisión; el olvido nunca amplía su ámbito.

## Verificación y límites

Las pruebas usan SQLite temporal, archivos reales de ensayo, transformaciones puras, servidores HTTP locales y navegadores con transporte controlado. Cubren dos tareas, causalidad A→B, generaciones/contextos, callbacks retenidos, interrupción/reintento, selección manual/automática, carpetas exactas y conservación del journal. La contabilidad comprobada corresponde a solicitudes observables de Axx, no a llamadas internas desconocidas del proveedor.

Ejecutar las pruebas de esta unidad:

```powershell
python -m unittest backend.tests.test_task_memory backend.tests.test_command_task_memory backend.tests.test_skill_task_memory backend.tests.test_chat_forgetting backend.tests.test_selection_policy backend.tests.test_session_memory backend.tests.test_workshop_task_memory backend.tests.test_anticipation_task_memory backend.tests.test_legacy_task_memory backend.tests.test_memory_http backend.tests.test_telegram_task_memory -q
python -m unittest backend.tests.test_forgotten_plan_projection -q
python -m unittest discover -s backend/connect/tests -q
node 1.AXX/scripts/test-task-memory.cjs
```

El gate permanente `scripts/validate_companion.py` sigue siendo obligatorio sobre la fuente final; sus huellas incluyen la autoridad de memoria compartida y el espejo del escritorio. Las pruebas de fuente y navegador no sustituyen aceptación física de Windows/Android, escucha, entrada real o un proveedor externo. No se puede retirar una solicitud ya recibida por un tercero ni prometer eliminación de sus copias.

La migración añade columnas/tablas; conserva IDs y datos anteriores. Si hay un olvido pendiente no se debe volver a un ejecutable que ignore estas referencias: terminar primero la operación o recuperar una copia comprobada del estado completo. No se reparan incompatibilidades borrando emparejamientos o credenciales.
