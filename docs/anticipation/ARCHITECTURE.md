# Anticipación contextual y perfiles de Axx

Contrato de integración derivado de los dos adjuntos del encargo. El bloque de tres perfiles sustituye las restricciones universales de presencia del informe inicial. La tabla final distingue lo integrado, lo comprobado y lo que falta; implementar el primer recorrido no completa ambos adjuntos.

## Un asistente y un recorrido de ejecución

`evento autorizado → contexto mínimo → rutina/candidato → probabilidad → capacidad → autorización → propuesta/preparación/ejecución → verificación → feedback`.

La política se añade sobre los servicios inventariados en [INVENTORY.md](INVENTORY.md). No crea otro agente, ejecutor, planificador de efectos ni memoria independiente. `CommandService` y `ActionExecutor` siguen siendo la frontera de los efectos y su journal SQLite es la autoridad de ejecución. La probabilidad de utilidad no concede capacidad ni autorización.

El primer recorrido es `artifact.generated → verificación adicional → resultado observado`, usando archivos de ensayo y verificadores existentes. Un hash confirma identidad/lectura; no demuestra que el contenido sea correcto. Una comprobación ya exigida por la orden original pertenece a esa orden, incluso en Discreto.

La [progresión de misiones con criterios verificables](GOAL-PROGRESS.md) amplía una misión existente con un sufijo registrado cuando su resultado aún no cumple el contrato. Conserva recibos y presupuesto, y reevalúa los permisos para la revisión nueva. Su cobertura actual son tres tipos de entregable; no completa por sí sola el alcance general de los adjuntos.

El [olvido por sesión y las correcciones naturales](SCOPED-MEMORY.md) invalidan memoria atribuible y sus derivados mediante referencias durables, conservando archivos, recibos, presupuesto y borradores. Las solicitudes de documentos y las salidas del modelo no modifican las reglas de selección por sí mismas.

El [recorrido documental hasta una habilidad comprobada](DOCUMENT-SKILLS.md) conserva identidades de fuente, sella el candidato y requiere ensayo y aprobación propios. La transferencia verificada con archivos no certifica la demostración semántica general de aplicaciones.

## Perfiles, ámbitos y permisos

| Perfil | Iniciativa predeterminada | Efecto sobre una orden explícita |
| --- | --- | --- |
| Discreto | Responder; no iniciar sugerencias espontáneas ni ampliar observación | Conserva la capacidad autorizada de la orden y sus comprobaciones. |
| Copiloto | Observar ámbitos habilitados, sugerir y preparar borradores reversibles aislados | Una iniciativa que cambie otra aplicación, un original o un sistema externo exige aceptación. |
| Full | Anticipar y ejecutar dentro de capacidades y autorizaciones vigentes | No repite confirmaciones cubiertas por un grant persistente; siempre revalida alcance y parámetros. |

Full puede persistir después de reiniciar. No concede por sí mismo permisos de envío, transferencia, borrado, instalación, compra o cambio de configuración. Esas categorías son independientes. El modo efectivo se resuelve por tarea y recurso; las exclusiones/revocaciones prevalecen y un conflicto nunca elige silenciosamente lo más permisivo.

La configuración implementada distingue ámbitos, fuentes soportadas, cadencia/horarios, iniciativa, interrupciones, retención y límites de admisión. Las fuentes todavía no integradas permanecen bloqueadas. Autonomía e interrupciones son controles distintos: Full silencioso puede realizar trabajo permitido sin narrar cada acción.

Los grants deben declarar tarea/ámbito, capacidad o categoría, destino, restricciones de parámetros y vigencia. Una autorización de carpeta no permite enviar su contenido; una autorización de una tarea no se transfiere a otra. Las aceptaciones puntuales se vinculan al hash y versión exactos del plan. Un plan modificado requiere nueva evaluación y el permiso correspondiente.

**Observar**, **conservar** y **enviar a un proveedor** son permisos distintos por fuente. Pantalla/ventana, aplicaciones, carpetas, micrófono y portapapeles son controles independientes. No guardar capturas/audio/contenido por haber permitido interpretación transitoria. Lo aprendido debe poder inspeccionarse y eliminarse. La interfaz muestra fuentes activas y una pausa global puede detener también observación.

Decisión humana: con **Conservar contexto desactivado**, no se guardan ni ejecutan planes derivados. El envío al modelo exige también retención autorizada, porque su respuesta puede repetir el contenido observado. Quitar la retención revoca el envío y sus leases activos; observar localmente no concede ese permiso. Conservar contexto puede permitir metadatos y resultados de tareas; no convierte las capturas originales en archivos durables.

## Persistencia, identidad y estados

Reutilizar la base SQLite existente con tablas aditivas y transacciones acotadas; los claims de cuota y presupuesto de inferencia adquieren primero BEGIN IMMEDIATE. Separar configuración persistente, eventos mínimos, rutinas/versiones, suppressions, sugerencias, grants y recibos de ejecución; no duplicar el journal del ejecutor. No persistir secretos ni contenido bruto por defecto.

- Evento: ID estable, tarea, procedencia autorizada, recurso lógico, instante y referencia al resultado observado. La deduplicación no depende del texto mostrado.
- Rutina: identidad estable, versión, trigger/condiciones positivas y negativas, secuencia, procedencia, frecuencias/resultados y expiración. Frecuencia no equivale a preferencia permanente.
- Sugerencia: ID, tarea, rutina/versión, evidencia, plan canónico, SHA-256 del plan, identidad del destino, TTL, decisión de probabilidad/capacidad/autorización y estado.
- Efecto: clave de idempotencia estable ligada a tarea, paso semántico y destino. Conservar referencias a `command_runs`/`operations` existentes.

La procedencia distingue trabajo de Axx iniciado por orden, sugerencia aceptada y rutina autónoma. Un efecto técnicamente verificado no prueba preferencia humana ni utilidad. Aceptación, utilidad explícita y corrección tienen señales y contadores distintos. El primer recorrido tiene profundidad/presupuesto de iniciativa uno y termina en su verificación; sus propias salidas no vuelven a alimentar una cadena ilimitada.

Estados de efecto exigidos: `INTENDED → DISPATCHED → EXECUTED → VERIFIED`, o `FAILED`/`UNCERTAIN`. El recibo de despacho no basta para `VERIFIED`: exige postcondiciones observadas. La UI presenta solo estados respaldados: `DETECTED`, `PREPARED`, `AWAITING_APPROVAL`, `EXECUTING`, `VERIFIED`, `FAILED` e incertidumbre explícita cuando corresponda.

Cooldown por rutina, presupuesto de interrupciones y límites por tarea evitan ruido. Descartar afecta a la instancia; «no volver a sugerir» persiste sobre la identidad de rutina, incluso tras cambiar de versión. Ignorar una tarjeta no autoriza nada.

## Cola, revocación, cancelación y recuperación

Antes de despachar, volver a resolver perfil efectivo, grant, vigencia, hash e identidad del destino. Tras adquirir un recurso compartido, repetir la comprobación relevante; nunca asumir que sigue siendo la misma ventana/archivo por haberlo observado antes del lock.

Bajar de Full invalida o retira trabajo pendiente que ya no esté permitido y cancela lo cancelable. Subir a Full no reactiva propuestas antiguas, rechazadas o caducadas. Revocar durante una tarea impide sus siguientes efectos. Escape cancela lo pendiente, pide cancelación de lo activo y pausa nuevos disparadores de esa ejecución; informa de efectos ya ocurridos. No deshacer ni repetir un efecto incierto automáticamente.

Después de timeout/crash se consulta primero la operación existente y el destino. Si el efecto ya está confirmado, se conserva su recibo; si sigue incierto, se mantiene `UNCERTAIN` y solo se inspecciona o solicita resolución. Recuperar una tarea usa el último paso **verificado**, no el último mensaje. La adquisición de un lease nuevo no demuestra éxito del lease anterior.

Los bloqueos M15 y la condición R02 del inventario permanecen. Las funciones independientes de input físico pueden verificarse sin promover candidatos bloqueados; cualquier camino que dependa de aislamiento aún no acreditado debe permanecer bloqueado.

## Interfaz, migración y rollback

Añadir selector compacto `Discreto · Copiloto · Full` y ajustes desplegables a las superficies existentes. Propuestas junto al avatar con una acción principal y detalles opcionales. No abrir superficies grandes durante dictado, llamadas o interacción incompatible. Conservar avatar, radial, Morph Reach, voz, preferencias, foco y apariencia aprobada.

Migración aditiva e idempotente: mantener las tablas y datos previos, emparejamiento, grants existentes, borradores, TLS e IDs pendientes. Las instalaciones previas comienzan con política conservadora si aún no eligieron perfil; nunca activar observación como efecto de migrar. Una selección Full guardada se conserva al reiniciar y se revalidan sus permisos.

Rollback operativo: pausar iniciativas/observación, conservar journal y recibos, desactivar la nueva política y volver al ejecutor explícito existente. Conservar copia verificada antes de instalar. No borrar tablas, restablecer credenciales ni bajar esquema a ciegas; para revertir binarios usar el procedimiento de entrega y datos compatibles.

## Estado de entrega y evidencia

La descarga Windows confirmada es **0.22.30 R3**, con fuente de publicación `38cad3827bc07b983c4a342ab99864a5e2776624`. GitHub confirmó el SHA-256 del instalador `b0ccebe6b725adf2170e5d2f40286f90bb0bb1a08ad6b2f91ac4d62af3cceff2`. El usuario aprobó avatar/herramientas, Ocultar/Invocar/atajo y Telegram; desde Telegram confirmó abrir Calculadora, denegar su cierre y aprobarlo. La aceptación del teléfono con Android 0.2.11 cubre por separado 65 segundos, movimiento inicial/final y DETENER. El instalador excluye pesos. Estos recorridos no certifican iniciativa física general ni las fuentes posteriores de misiones, olvido, documentos y atención agrupada.

Los recibos históricos R4 están en `C:\Users\luigi\.codex\worktrees\anticipation-stable\axx2\build\release-0.22.28-r4\`. `installed-files.json` registra concordancia de binarios; `native-api-profiles.json` acredita los tres perfiles por API y declara expresamente `physical_input_tested:false` y `visible_acceptance_tested:false`. `native-plan-guard.json` pasa la defensa de IDs de pasos reservados. El SHA-256 del EXE de esos recibos es `83c48efc512a4a04b2efa74d3e5d3fbc22163863ba31d8efaa8cc1a191daaf02`.

`restore-observation.json` contiene observación nativa de solo lectura. La prueba física humana de R4 **falló al ocultar o reaparecer con el botón**. La confirmación anterior de Invocar/avatar no aprueba esa transición. La carrera NTFS de sustitución de un directorio antes de la escritura se reprodujo también sobre aquella lógica; R4 quedó retenido. Sus recibos no acreditan las correcciones posteriores. Para 0.22.29 el usuario eligió excluir pesos y aprobó la aceptación nativa R3; el digest publicado fue confirmado por GitHub. Android conserva su ciclo separado.

## Trazabilidad de la fuente P1

| Requisito | Implementación actual | Evidencia y límite |
| --- | --- | --- |
| Tres perfiles persistentes, silencio y ámbitos | `AnticipationService.configure/_policy`, ajustes en `anticipation.js` | Perfil por tarea/recurso y contexto disponible; exclusión/conflicto se resuelven conservadoramente. Los tres perfiles R4 tienen recibo API; 0.22.29 tiene lectura instalada y regresiones de fuente, sin nueva aceptación física de iniciativas. |
| Carpetas y metadatos de aplicaciones opt-in | `_poll_sources`, observadores seleccionados y cadencia/horarios por perfil | Carpetas explícitas y procesos permitidos; metadatos de ventanas sin leer títulos globales. `retain:false` conserva solo estado RAM temporal y no genera propuestas; persistencia requiere consentimiento. No es vigilancia adaptativa general. |
| Verificación de artefactos | Escritor/journal existentes, `_verifier`, `accept`, `dispatch_guard` y filtro del ejecutor | SHA-256/identidad y lectores PDF, multimedia u OCR únicamente cuando su motor está disponible. PDF legible no acredita render; ffprobe no acredita decodificación completa. El filtro elimina contenido de salida y diagnósticos crudos antes del journal; los inputs explícitos y recibos previos conservan su política de auditoría. |
| Grants para múltiples planes futuros | `grant`, `authorize_mission_step`, `ActionLearning.execute_with_grant` | Tarea, comandos directos cerrados, raíces de lectura/escritura, parámetros exactos y vigencia `one_action/session/mission/until_revoked`. Cada plan conserva hash admitido y cada paso se revalida. Permite lectura, artefactos nuevos, bundles y adaptadores privados Office disponibles; no input, shell, MCP ni código generado. Office con cuota finita se abstiene si no puede acotar su salida. |
| Revocación, pausa y cierre | `_mission_cancellations`, cancelación de comandos fuera del lock de política, guard central de `CommandService` | Incluye misiones concedidas directamente sin tarjeta. Revocar/bajar perfil/pausar/excluir/Detener antes de la primitiva impide el archivo; no promete deshacer efectos ya entregados. Un permiso posterior no reactiva propuestas antiguas. |
| Recursos de proceso y almacenamiento | `assert_resource_admission`, `_sample_memory`, `_storage_admission/_reconcile_storage` | RSS observado de backend y descendientes por PID/fecha de inicio; excluye WebView padre, COM no descendiente y otras apps. Cuota de bytes lógicos por raíces con reservas SQLite, solapamientos, UTF-8 real y cota ejecutable de bundle. Escaneo incompleto, RSS desconocido o salida no acotable se abstienen. Son admisión/reservas, no límites duros de SO, disco físico ni monitorización/preempción continua; la ejecución manual explícita conserva su recorrido separado. |
| Inferencias configurables 0..2 | `mission_model_budgets/mission_model_calls`, reservas antes del proveedor, `inference_accounting`; Taller comparte el presupuesto padre | Límite persistido que no aumenta por defaults o snapshots viejos. Se reserva el saldo disponible y solo se devuelve coste demostrado por recibos fiables; fallos desconocidos mantienen reserva. El router aplica `min(config.max_attempts, axx_attempt_budget)` y transmite conteos por worker. La unidad es dispatch HTTP observable de Axx más fanout conocido de su gateway verificado; no prueba llamadas internas de proveedores ajenos. |
| Checkpoints, recurrencia y dependencias | `_observe_preparations/_prepare_existing`, `ActionLearning.resume/prepare_steps/link_dependencies` | Preparación local reutilizada; Full solo continúa checkpoints preparados e interrumpidos con grant anterior y revisión vigente. Una pausa humana no se transforma en permiso. Las dependencias enlazan orden y revisión de misiones completadas; no prueban que un archivo de origen siga igual ni sustituyen la verificación propia del destino. |
| Contexto por proyecto/tarea y olvido derivado | `SkillMemory.context/update_context/invalidate_context`, `read_context_state/read_skill_state` | Procedencia por campo, revisión, huella, caducidad y dependencias transitivas. Valores stale no se usan para vincular ni enviar contexto ambiental. El olvido invalida planes derivados, limpia snapshots y no resucita `model_data` tras inferencia en vuelo; no borra grants/journal. Una etiqueta de procedencia no sustituye un recibo observado. |
| Incidentes y correcciones | `record_lesson/lessons/forget_lesson` y rutas autenticadas/UI | Recibo fallido real, hipótesis explícita, corrección humana opcional y prueba posterior independiente de causalidad. `verified_test` nunca significa causa demostrada. Búsqueda local acotada; contexto de proveedor exige `allow_provider:true`, filtro por tarea antes del límite y máximo conjunto de tres fichas/3500 caracteres. |
| Salud y revalidación de habilidades | Evidencia por versión en `SkillMemory`; `ActionLearning.prepare_revalidation` y guard por paso | Fallo real pone en cuarentena la versión; ensayo explícito con inputs revisados, huella relevante y recibos posteriores puede revalidarla sin reescribir definición. Contexto olvidado/caducado exige revisión, no se borra para simular compatibilidad. Las rutas Windows del escritor se comparan con su representación canónica y el recibo sigue ligado exactamente al ledger. |
| Biblioteca documental y recuperación selectiva | Importador y `ProcedureLibrary`, referencias acotadas en planificación | Reutiliza registros/bindings existentes; referencias documentales se marcan `DOCUMENTED_NOT_EXECUTED`. Documentos e hipótesis entran como datos no confiables y nunca habilitan comandos, permisos o frameworks nuevos. No demuestra autooptimización ni generalización autónoma. |
| ComputerUse solo observación explícita | `begin(image_authorized=True, allow_input=False)`, status, `computer_vision.observe` y hook de cache propia | No usa foco, owner ni broker de entrada. Título solo del HWND/PID/instancia autorizado; act falla en admisión, claim y runtime, incluso con tickets/estado alterados. Cancelación/TTL/cambio de proceso impiden publicar captura tardía y limpian JPEG/IDs UIA propios. Solo pruebas con frames y Win32 sintéticos; no acredita captura real, input físico ni fuente automática ya conectada. |
| UI, compatibilidad y entrega | Selector, tarjetas, misión, grants, contexto, incidentes y revalidación sobre las superficies existentes | Pruebas de renderer y backend no reemplazan revisión visual nativa. Se conservan `/v1`, TLS, emparejamiento y baseline de diseño; el gate companion y la entrega final corresponden al dueño único. |

## Persistencia, concurrencia y recuperación actuales

El límite de dos inferencias incluye la planificación y la construcción de una capacidad nueva. Si ya consumieron una cada una y la continuación necesita otra planificación, la misión se detiene por presupuesto. Conserva objetivo, revisión y capacidad activada, sin una tercera llamada ni efectos. La capacidad puede usarse en una nueva petición explícita; no se reinicia el saldo de la misión anterior. Las pruebas funcionales con respuestas deterministas locales declaran cero upstream; no representan un ciclo LLM de tres llamadas dentro de un límite de dos.

Los archivos nuevos creados exclusivamente por Axx pueden apartarse a `.axx-quarantine` y restaurarse mediante comandos con aprobación normal y recibo exacto. Sólo se admite NTFS local con identidad, contenido e instancia de creación demostrados; no hay compensación retroactiva de archivos previos ni borrado. Los directorios se mantienen abiertos sin compartir eliminación durante creación y traslado. Claims vivos y CAS por operación/revisión impiden que una conciliación tardía sobrescriba otra más reciente. Un resultado incierto se concilia leyendo posiciones e identidad, sin repetir el traslado. La cuarentena no es una fuente de observación ni un destino de escritura genérico. Las misiones mantienen sus recibos históricos, pero dejan de contarse como completadas y bloquean dependencias mientras el archivo esté apartado o su restauración no esté verificada.

`anticipation_*`, contexto/habilidades/incidentes, presupuestos de misión y reservas de almacenamiento usan la SQLite existente. El claim de cuota adquiere `BEGIN IMMEDIATE` antes de leer límites, escanear metadatos y reservar; otro servicio no puede consumir simultáneamente el mismo saldo. La reserva liga operación, parámetros, grant, raíz y destino. No se libera por timeout: necesita recibo terminal y escaneo completo; `unknown` requiere la revisión manual ya existente antes de reconciliar. No se eliminan archivos del usuario para recuperar espacio.

El registro de envío observado amplía `mission_model_calls` con `source_dispatch_json` nullable; `state/charge/confirmed` conservan exclusivamente su significado de presupuesto. Guarda hasta cuatro referencias exactas, selección configurada, fechas y recibos HTTP cerrados, sin contenido ni diagnósticos. `unknown` se confirma en disco antes de abrir el canal; un terminal válido del worker acredita sólo recepción por Axx, y los headers HTTP acreditan respuesta del endpoint configurado, incluido un gateway sin prueba de sus proveedores internos. La consulta distingue `not_sent`, `unknown`, `runtime_delivered` y `upstream_confirmed`; envío incierto o sin referencia usa booleanos null, nunca un falso «no enviado». El micrófono local exige su recibo exacto de no envío/no retención cruda. Los metadatos caducan con el menor plazo existente entre perfiles; olvido y purga eliminan sólo esa columna, conservan los cargos y no permiten que un callback la recree. Caducar la captura en RAM no borra un envío anterior; perder su recibo conserva incertidumbre. El nuevo recorrido sigue desactivado y Codex se abstiene antes de reservar porque aún no proporciona este recibo.

La migración conserva las filas antiguas y añade una columna; los INSERT nuevos nombran sus campos. El binario 0.22.29 anterior usa INSERT posicional de ocho columnas, por lo que no debe ejecutarse sobre esta tabla ampliada para crear nuevas reservas. Cualquier reversión requiere la copia verificada y conciliación de operaciones posteriores; no borrar la columna ni sustituir la base activa a ciegas.

La declaración de cuota de una raíz no desaparece al consumir un permiso de una acción o terminar su sesión: los grants no revocados ni caducados siguen aportando ese límite conservador hasta revocación, caducidad o cambio de política. Conservar ese límite no reactiva la autorización de ejecutar.

Las comprobaciones bajo el lock de política usan SQL y proyecciones puras; no toman locks de aprendizaje/comandos. Cancelación y pausa de misiones se hacen después de soltarlo. El ejecutor mantiene vivo el filtro de privacidad hasta terminar también las lecturas paralelas. Los marcadores durables de procedencia/privacidad evitan que borrar una tarjeta convierta una ejecución autónoma en preferencia humana o deje pasar texto crudo.

La migración añade campos/tablas sin activar observadores ni conceder input. Full seleccionado persiste, pero scopes, grants, sesión y recursos se comprueban otra vez. Rollback conserva datos y recibos, pausa iniciativas y usa instalación compatible; nunca limpia credenciales, pairing, IDs pendientes o tablas para reparar una incompatibilidad.

## Pendientes reales

- **Integrado en fuente, sin aceptación física:** observación periódica de una ventana seleccionada y del portapapeles (`b2ba137`). Usa lectores existentes sin foco/input y descarta capturas tardías tras revocación. Texto e imagen permanecen transitorios; conservar actividad guarda sólo metadatos. Las huellas HMAC usan una clave únicamente de sesión; el historial nuevo tiene un máximo de 2048 eventos además de la retención por días. Ese límite no es una cuota de todo `state.db` ni modifica el journal de efectos.
- **Envío de observaciones desactivado:** `send_to_provider=true` se rechaza. Se integraron guardas de retención/revocación para planes, preguntas, parámetros y derivados que puedan repetir contenido observado. El gate permanece cerrado hasta completar la auditoría de egreso, señales y consumidores de retención; estas guardas no autorizan activarlo. Una captura temporal no hace temporal automáticamente su respuesta. El SDK confirmó una sesión efímera real con entrada sintética y excluye respuestas/deltas de contexto de sus tablas; no acredita transporte de pantalla, portapapeles o micrófono real.
- **Auditoría de egreso:** las rutas sensibles eliminan los identificadores de modelo/proveedor devueltos por upstream que no coinciden con los configurados, antes de publicarlos o guardarlos en SQLite. La cancelación tardía descarta también el diagnóstico de un worker fallido y conserva sus intentos consumidos o desconocidos. Las regresiones cubren canarios en respuesta/SQL/DB/WAL, cancelación y presupuesto; no acreditan envío observado ni cambian el gate. La aceptación nativa de una instalación no acredita automáticamente todas estas rutas.
- Observación continua/adaptativa general de pantallas y micrófono como fuentes de anticipación, y políticas completas de envío a proveedores por fuente. La ausencia de envío actual no implementa un consentimiento de envío futuro.
- Iniciativa física/multiaplicación: abrir o enfocar aplicaciones, mouse/teclado, organizar/modificar originales y las categorías de envío, transferencia, borrado, instalación, compra y configuración. Los grants actuales no las habilitan. M15 y la incertidumbre R02 permanecen; no promover el candidato bloqueado ni reutilizar pruebas históricas como holdout nuevo.
- Borradores/previews generales, condiciones negativas aprendidas y ranking calibrado abierto. Las reglas actuales y la recurrencia acotada son deterministas; su score no es una probabilidad empírica de intención.
- Evaluación de utilidad con universo definido/holdout nuevo y aceptación instalada de todo P1. Las distribuciones p50/p95 locales y contadores con fracción no acreditan utilidad humana ni consumo de todo el PC.
- Entrega Windows 0.22.30 R3 cerrada para sus recorridos registrados: build/instalación, aceptación humana y publicación con digest GitHub confirmado. Los cambios posteriores de fuente no forman parte de ese instalador. Esto no cierra los requisitos funcionales pendientes anteriores ni transfiere recibos R4 a P1.
- [Atención por misión](MISSION-ATTENTION.md): fuente nueva con agrupación y contabilidad durable, controles de grupo y separación entre respuesta solicitada y aviso proactivo. Su validación e instalación conservan recibos propios; no equivale a ranking de utilidad calibrado ni cierra los restantes módulos de los adjuntos.

## Revisión independiente registrada

No sumar ejecuciones repetidas como si fueran pruebas distintas. Esta revisión conserva categorías y recibos, no un total acumulado:

| Categoría | Evidencia examinada | Qué acredita |
| --- | --- | --- |
| Recursos P1 | `test_anticipation_resources`: 12 pruebas, 18,837 s, aprobadas sobre la integración examinada | Archivos temporales reales, reservas entre servicios, cuotas solapadas, crash/unknown con revisión y RSS con alcance declarado. No cuota dura del SO ni instalación P1. |
| Títulos y ComputerUse | 15 pruebas dirigidas de `test_window_title_scope`/`test_computer_observation`, 8,719 s; regresiones pertinentes aprobadas | API Win32 y frames sintéticos, ausencia de foco/input, cache propia y cancelación concurrente. No lectura física de pantalla. |
| Contexto, incidentes, misiones e inferencias | Suites permanentes `test_planning_context`, `test_skill_context`, `test_mission_dispatch`, `test_revalidation`, `test_mission_model_budget` y `inference/tests/test_attempt_budget` | Regresiones reproducibles sobre SQLite/ejecutor y transportes de ensayo; el responsable de integración ejecuta el conjunto final concordante. No inferir aceptación instalada de estas fuentes. |
| Binario estable R4 | `installed-files`, `native-api-profiles`, `native-plan-guard` y companion del worktree estable | Instalación 0.22.28, tres perfiles por API y defensa de pasos reservados. Sus propios recibos excluyen aceptación física/visible. |

Las reproducciones de identidad sustituida, operación ajena, olvido durante inferencia y revocación entre guard y primitiva motivaron correcciones y regresiones permanentes. El resultado de despacho, ausencia de excepción, aceptación de una tarjeta y utilidad humana continúan siendo señales distintas.
