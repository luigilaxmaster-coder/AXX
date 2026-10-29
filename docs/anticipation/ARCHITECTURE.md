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

Cada perfil conserva ajustes de ámbito, fuentes/cadencia de observación, iniciativa, interrupciones, interacción física, memoria/retención, vigencia, procesamiento, recursos y excepciones. Autonomía e interrupciones son controles distintos: Full silencioso sigue realizando trabajo permitido y presenta resultados comprobados.

Los grants deben declarar tarea/ámbito, capacidad o categoría, destino, restricciones de parámetros y vigencia. Una autorización de carpeta no permite enviar su contenido; una autorización de una tarea no se transfiere a otra. Las aceptaciones puntuales se vinculan al hash y versión exactos del plan. Un plan modificado requiere nueva evaluación y el permiso correspondiente.

**Observar**, **conservar** y **enviar a un proveedor** son permisos distintos por fuente. Pantalla/ventana, aplicaciones, carpetas, micrófono y portapapeles son controles independientes. No guardar capturas/audio/contenido por haber permitido interpretación transitoria. Lo aprendido debe poder inspeccionarse y eliminarse. La interfaz muestra fuentes activas y una pausa global puede detener también observación.

## Persistencia, identidad y estados

Reutilizar la base SQLite existente con tablas aditivas y transacciones cortas. Separar configuración persistente, eventos mínimos, rutinas/versiones, suppressions, sugerencias, grants y recibos de ejecución; no duplicar el journal del ejecutor. No persistir secretos ni contenido bruto por defecto.

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

## Trazabilidad de la integración

| Requisito | Implementación observada | Comprobación y límite |
| --- | --- | --- |
| Discreto, Copiloto y Full persistentes | `backend/anticipation.py`: `DEFAULTS`, `configure()`, `_policy()`; `1.AXX/scripts/anticipation.js` | Pruebas locales de los tres resultados, persistencia y silencio. Aceptación instalada pendiente. |
| Ámbitos/exclusiones y grants | `AnticipationService._policy()`, `grant()`, `revoke()`, `_grant()` | Tarea y carpeta para la verificación SHA-256; conflicto falla cerrado. No concede efectos amplios de Full ni convierte una fuente ausente en disponible. |
| Primer archivo real de ensayo | `_observe()` lee escritor/journal existentes; `accept()` usa `CommandService.prepare/execute`; `dispatch_guard()` valida el comando real | Hash y archivo temporal reales en tests; Copiloto exige hash exacto y Full grant previo ligado a tarea/carpeta. No prueba calidad semántica o visual. |
| Estado, identidad e idempotencia | Tablas `anticipation_*`, hash canónico, claim condicional y referencias al journal existente | Doble aceptación/dos servicios, crash, cambio de archivo y sustitución con bytes idénticos. El guard compara comando, parámetros, tarea, modo y hash aceptado. |
| Retención y feedback | `_purge()`, `feedback()`, `forget()` | Retención por perfil, no volver a sugerir, descartar y olvido del contexto de anticipación. El journal de comandos y los grants se conservan expresamente. |
| Procedencia, utilidad y olvido derivado | `_command_provenance()`, `_forgotten_source()`, `initiative_chain`, feedback separado | Distingue Axx/causa de inicio; ejecutar/aceptar no confirma utilidad. Las rutinas derivadas excluyen ejecuciones iniciadas por anticipación y fuentes anteriores al olvido. |
| Cambio de perfil, revocación y pausa | `_invalidate()`, `cancel()`, guard en `backend/commands.py`; ruta de parada en `backend/server.py` | Prueba de revocación mientras espera al ejecutor y no reactivación al subir perfil/añadir grant. Escape está conectado en UI; tecla física pendiente. |
| Tarea incompleta | `_checkpoint()`, `_observe_preparations()`, `_prepare_existing()` sobre `ActionLearning.resume(approved=False)` | Propone preparar desde último paso contiguo verificado; no repite el efecto anterior ni ejecuta el siguiente. Cancelar antes o durante la preparación conserva cancelación y deja el plan en pausa. |
| Rutina recurrente | Lectura de `learning_plans`/`SkillMemory` y `ActionLearning.prepare_steps()` | Tres ocurrencias verificadas de la misma tarea, versión e inputs; solo prepara un plan sujeto a aprobación. No aprende pesos ni ejecuta la rutina por iniciativa autónoma. |
| Misión persistente | `ActionLearning._mission()`, `_save()`, `get()`, `list_plans()` y panel de misión en `anticipation.js` | Es una vista del plan existente: objetivo, ámbito, entregables, dependencia, pendiente/bloqueo, permiso exacto, presupuesto y parada. Completa solo con pasos y contrato de objetivo verificados; conserva utilidad humana separada. |
| Planificador y cierre | Tick en el hilo `ActionLearning.start_recovery()`; construcción/cierre en `backend/server.py` | Reutiliza el hilo residente; se detiene aprendizaje antes de cerrar anticipación. Validación de origen usa snapshots SQL sin adquirir el lock de aprendizaje bajo el de política. |
| Selector y tarjeta junto al avatar | `1.AXX/scripts/anticipation.js`, inclusión en `Axx.html`, control de voz en `voice-conversation.js` | Código presente y pruebas de navegador separadas. La revisión backend no acredita diseño nativo ni gate companion. |
| API móvil y diseño protegido | No se añaden rutas ni permisos `/v1` | Gate companion sobre la fuente final, capturas y aceptación instalada pendientes del responsable de entrega. |

## Alcance todavía no implementado

- Observación de pantalla, ventana activa, micrófono, portapapeles, eventos de otras aplicaciones o carpetas vigiladas; cadencia continua/adaptativa. La capacidad informa esas fuentes como no disponibles y rechaza activarlas. Un checkbox deshabilitado no es una implementación.
- Ejecución proactiva amplia de Full: abrir otras aplicaciones, cambiar foco, teclado/ratón, modificar/organizar originales, enviar, transferir, borrar, instalar, comprar o cambiar configuración. El único grant nuevo ejecutable es verificación de un artefacto dentro del directorio de Axx. M15 sigue bloqueado para cualquier promoción que dependa de su aislamiento.
- Controles de envío por fuente/proveedor, presupuesto de modelos, límites CPU/memoria/almacenamiento, horarios, excepciones automáticas por aplicación/llamada y política de foco. No se envía contexto de anticipación a un proveedor; esto evita esa exposición, pero no implementa esos controles futuros.
- Preparación autónoma general de borradores/previews y ejecución autónoma de rutinas o reanudaciones. Los seguimientos añadidos preparan planes existentes tras aceptación, con nueva revisión antes de sus efectos.
- Resolución de todos los recursos de un plan para aplicar políticas de carpeta al seguimiento. Cuando existe un ámbito de carpeta relevante, `_preparation_scope_allowed()` se abstiene de proponer reanudaciones/rutinas; estos seguimientos solo usan ámbitos de tarea. La verificación de archivos sí evalúa su carpeta concreta.
- Modelado de rutinas abierto con condiciones negativas aprendidas, excepciones temporales y ranking calibrado. La regla de archivo y la detección acotada de tres ocurrencias tienen reglas deterministas; su score no es una probabilidad empírica de intención.
- Estudio de utilidad con holdout nuevo, precisión/cobertura, latencias p50/p95 y consumo continuo. R02 no se cuenta como evidencia nueva.

## Evidencia de revisión independiente

Se ejecutaron `python -m unittest backend.tests.test_anticipation backend.tests.test_anticipation_http -v`: **35/35** en **50,121 s** sobre el servicio estable revisado, con **32** pruebas de servicio y **3** de transporte autenticado. Incluye archivos reales temporales, journal/ejecutor de producción, procedencia, olvido derivado, cancelación concurrente y pruebas con dobles de planificación; no prueba el binario instalado ni hardware.

`python -m unittest backend.tests.test_missions -v`: **2/2** en **1,113 s**. Una prueba crea y verifica un archivo real, reinicia el servicio de aprendizaje y comprueba no repetición; la otra comprueba con un plan sintético que despacho/aprobación sin postcondiciones no completan la misión. Los límites de presupuesto mostrados son los existentes del planificador, no nuevos controles de coste o consumo.

Dos reproducciones independientes usaron archivos reales y alteración controlada del momento de despacho: sustitución por otro archivo con bytes idénticos y un `operation_id` de sugerencia ocupado por otro comando. Tras las correcciones observadas, la primera queda `FAILED` y la segunda no crea el archivo ajeno. Se repitió además el caso con hilo detenido antes de preparar: tras cancelar, la sugerencia queda `CANCELLED`, el plan original sigue `paused` y `preparation_complete` permanece falso. Seis regresiones dirigidas pasaron **6/6** en **8,237 s**, incluidas identidad, payload, cancelación antes/durante preparación, abstención por carpeta y orden de locks. Estos resultados no sustituyen los recibos finales vinculados al commit de entrega.

Pendiente en este documento: aceptación instalada nueva, persistencia tras reiniciar el proceso, tarjeta/aceptación visible, Escape real, regresión visual y gate companion final. `scripts/test-installed-anticipation.cjs` ejercita IPC, scheduler y hashes del runtime instalado y declara por separado las funciones que no prueba; la existencia del script no acredita su ejecución.

Las métricas de utilidad deben tener fracción y universo; cero sugerencias no demuestra utilidad. Separar siempre unitarias, integración con dobles, runtime instalado y hardware, y publicar solo lo respaldado por su recibo.
