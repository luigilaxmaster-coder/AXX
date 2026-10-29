# Anticipación contextual y perfiles de Axx

Contrato de integración derivado de los dos adjuntos del encargo. El bloque de tres perfiles sustituye las restricciones universales de presencia del informe inicial. La tabla final distingue lo integrado, lo comprobado y lo que falta; implementar el primer recorrido no completa ambos adjuntos.

## Un asistente y un recorrido de ejecución

`evento autorizado → contexto mínimo → rutina/candidato → probabilidad → capacidad → autorización → propuesta/preparación/ejecución → verificación → feedback`.

La política se añade sobre los servicios inventariados en [INVENTORY.md](INVENTORY.md). No crea otro agente, ejecutor, planificador de efectos ni memoria independiente. `CommandService` y `ActionExecutor` siguen siendo la frontera de los efectos y su journal SQLite es la autoridad de ejecución. La probabilidad de utilidad no concede capacidad ni autorización.

El primer recorrido es `artifact.generated → verificación adicional → resultado observado`, usando archivos de ensayo y verificadores existentes. Un hash confirma identidad/lectura; no demuestra que el contenido sea correcto. Una comprobación ya exigida por la orden original pertenece a esa orden, incluso en Discreto.

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

Hay dos estados distintos. El candidato estable **R4 / Windows 0.22.28**, fuente `08a03d2`, fue instalado y comprobado por el responsable único de entrega. El desarrollo **P1** descrito abajo está en `codex/anticipation-profiles`; los recibos R4 no acreditan sus cambios posteriores.

Los recibos privados están en `C:\Users\luigi\.codex\worktrees\anticipation-stable\axx2\build\release-0.22.28-r4\`. `installed-files.json` registra concordancia de binarios; `native-api-profiles.json` acredita los tres perfiles por API y declara expresamente `physical_input_tested:false` y `visible_acceptance_tested:false`. `native-plan-guard.json` pasa la defensa de IDs de pasos reservados. El SHA-256 del EXE de esos recibos es `83c48efc512a4a04b2efa74d3e5d3fbc22163863ba31d8efaa8cc1a191daaf02`.

`restore-observation.json` contiene observación nativa de solo lectura; no aprueba ocultación ni atajo. La confirmación humana previa de Invocar/avatar pertenece a otro candidato. Los cuatro pasos humanos de R4 siguen pendientes del dueño de entrega. `build/companion-validation-final.json` del worktree estable pasa para aquella fuente; P1 requiere un gate nuevo concordante. Publicación Windows pendiente de aceptación y de resolver la excepción Tiny; no se afirma publicación ni autorización para distribuir pesos o estado privado. Android conserva su ciclo separado.

## Trazabilidad de la fuente P1

| Requisito | Implementación actual | Evidencia y límite |
| --- | --- | --- |
| Tres perfiles persistentes, silencio y ámbitos | `AnticipationService.configure/_policy`, ajustes en `anticipation.js` | Perfil por tarea/recurso y contexto disponible; exclusión/conflicto se resuelven conservadoramente. Los tres perfiles R4 tienen recibo API; las ampliaciones P1 solo fuente. |
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

`anticipation_*`, contexto/habilidades/incidentes, presupuestos de misión y reservas de almacenamiento usan la SQLite existente. El claim de cuota adquiere `BEGIN IMMEDIATE` antes de leer límites, escanear metadatos y reservar; otro servicio no puede consumir simultáneamente el mismo saldo. La reserva liga operación, parámetros, grant, raíz y destino. No se libera por timeout: necesita recibo terminal y escaneo completo; `unknown` requiere la revisión manual ya existente antes de reconciliar. No se eliminan archivos del usuario para recuperar espacio.

La declaración de cuota de una raíz no desaparece al consumir un permiso de una acción o terminar su sesión: los grants no revocados ni caducados siguen aportando ese límite conservador hasta revocación, caducidad o cambio de política. Conservar ese límite no reactiva la autorización de ejecutar.

Las comprobaciones bajo el lock de política usan SQL y proyecciones puras; no toman locks de aprendizaje/comandos. Cancelación y pausa de misiones se hacen después de soltarlo. El ejecutor mantiene vivo el filtro de privacidad hasta terminar también las lecturas paralelas. Los marcadores durables de procedencia/privacidad evitan que borrar una tarjeta convierta una ejecución autónoma en preferencia humana o deje pasar texto crudo.

La migración añade campos/tablas sin activar observadores ni conceder input. Full seleccionado persiste, pero scopes, grants, sesión y recursos se comprueban otra vez. Rollback conserva datos y recibos, pausa iniciativas y usa instalación compatible; nunca limpia credenciales, pairing, IDs pendientes o tablas para reparar una incompatibilidad.

## Pendientes reales

- **Integrado en fuente, sin aceptación física:** observación periódica de una ventana seleccionada y del portapapeles (`b2ba137`). Usa lectores existentes sin foco/input y descarta capturas tardías tras revocación. Texto e imagen permanecen transitorios; conservar actividad guarda sólo metadatos. Las huellas HMAC usan una clave únicamente de sesión; el historial nuevo tiene un máximo de 2048 eventos además de la retención por días. Ese límite no es una cuota de todo `state.db` ni modifica el journal de efectos.
- **Envío de observaciones desactivado:** `send_to_provider=true` se rechaza. Los helpers de contexto/leases y el cableado del planificador permanecen bajo un gate cerrado hasta proteger también planes, preguntas y parámetros que puedan repetir contenido observado. Una captura temporal no hace temporal automáticamente su respuesta. El SDK ya usa sesiones efímeras verificadas por contrato y excluye respuestas/deltas de contexto de sus tablas; eso no completa la retención de `ActionLearning` ni acredita el transporte real.
- Observación continua/adaptativa general de pantallas y micrófono como fuentes de anticipación, y políticas completas de envío a proveedores por fuente. La ausencia de envío actual no implementa un consentimiento de envío futuro.
- Iniciativa física/multiaplicación: abrir o enfocar aplicaciones, mouse/teclado, organizar/modificar originales y las categorías de envío, transferencia, borrado, instalación, compra y configuración. Los grants actuales no las habilitan. M15 y la incertidumbre R02 permanecen; no promover el candidato bloqueado ni reutilizar pruebas históricas como holdout nuevo.
- Borradores/previews generales, condiciones negativas aprendidas y ranking calibrado abierto. Las reglas actuales y la recurrencia acotada son deterministas; su score no es una probabilidad empírica de intención.
- Evaluación de utilidad con universo definido/holdout nuevo y aceptación instalada de todo P1. Las distribuciones p50/p95 locales y contadores con fracción no acreditan utilidad humana ni consumo de todo el PC.
- Gates finales de entrega: integración congelada, pruebas pertinentes, companion concordante, build/instalación y aceptación nativa/humana, publicación Windows con digest confirmado. Los recibos R4 no se transfieren a una fuente P1 modificada.

## Revisión independiente registrada

No sumar ejecuciones repetidas como si fueran pruebas distintas. Esta revisión conserva categorías y recibos, no un total acumulado:

| Categoría | Evidencia examinada | Qué acredita |
| --- | --- | --- |
| Recursos P1 | `test_anticipation_resources`: 12 pruebas, 18,837 s, aprobadas sobre la integración examinada | Archivos temporales reales, reservas entre servicios, cuotas solapadas, crash/unknown con revisión y RSS con alcance declarado. No cuota dura del SO ni instalación P1. |
| Títulos y ComputerUse | 15 pruebas dirigidas de `test_window_title_scope`/`test_computer_observation`, 8,719 s; regresiones pertinentes aprobadas | API Win32 y frames sintéticos, ausencia de foco/input, cache propia y cancelación concurrente. No lectura física de pantalla. |
| Contexto, incidentes, misiones e inferencias | Suites permanentes `test_planning_context`, `test_skill_context`, `test_mission_dispatch`, `test_revalidation`, `test_mission_model_budget` y `inference/tests/test_attempt_budget` | Regresiones reproducibles sobre SQLite/ejecutor y transportes de ensayo; el responsable de integración ejecuta el conjunto final concordante. No inferir aceptación instalada de estas fuentes. |
| Binario estable R4 | `installed-files`, `native-api-profiles`, `native-plan-guard` y companion del worktree estable | Instalación 0.22.28, tres perfiles por API y defensa de pasos reservados. Sus propios recibos excluyen aceptación física/visible. |

Las reproducciones de identidad sustituida, operación ajena, olvido durante inferencia y revocación entre guard y primitiva motivaron correcciones y regresiones permanentes. El resultado de despacho, ausencia de excepción, aceptación de una tarjeta y utilidad humana continúan siendo señales distintas.
