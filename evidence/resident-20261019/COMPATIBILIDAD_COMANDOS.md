# Compatibilidad del backend residente y la biblioteca de comandos

Fecha: 2026-10-19. Revisión de solo lectura de fuentes, recibos y evidencias existentes. No se modificó código ni se ejecutaron herramientas con efectos durante esta revisión. Este archivo es el único entregable nuevo de la revisión.

## Decisión de entrega

**Entregar el snapshot residente aislado y ya validado; conservar la biblioteca canónica para una versión posterior coordinada.** Esta es la decisión comunicada por el responsable de la entrega después de revisar la incompatibilidad de Blender. No se recomienda mezclar el HTML residente anterior con el backend nuevo.

| Conjunto | Identidad y evidencia |
| --- | --- |
| Residente que se conservará | Backend SHA-256 `8312ce40f16db6b024cf2a8bac1268b0ae15f867e089002138e1f16884d909ac`; HTML del stage SHA-256 `1cc9a0e4f2b54c9b3012226b39e832882b266ef2bcbab9b3302b7c1fa592ad45`; shell 0.20.3. [Stage aislado](<C:/Users/luigi/Desktop/Axx assistant/build/resident-release-0.20.3>) y [recibo del backend](<C:/Users/luigi/Desktop/Axx assistant/build/resident-release-0.20.3/build/backend-build-receipt.json>). |
| Biblioteca canónica posterior | Backend SHA-256 `90e704b164e4fb8184407ee2a5e378aeb39da6da58245edd38ce00a18e56feb0`, 170.604.316 bytes según su [resultado final](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/RESULTADOS.json>). [Recibo compartido](<C:/Users/luigi/Desktop/Axx assistant/build/backend-build-receipt.json>). |

La elección conserva el render Blender autorizado y realmente comprobado en la orden original. No invalida la importación documental ni las mejoras de seguridad de la biblioteca; evita introducir un cambio de contrato incompleto en esta instalación. No se sobrescribe ni revierte la fuente canónica para obtener el snapshot anterior.

## Comparación efectiva

La comparación directa de bytes entre `backend/` y `build/resident-release-0.20.3/backend/` encontró **nueve módulos críticos idénticos**:

- `speech/windows_tts.py` y `speech/offline_asr.py`.
- `memory/ai_memory_adapter.py` y `memory/procedural_memory.py`.
- `inference/router.py`, `inference/adapter.py` e `inference/process_manager.py`.
- `actions/cli_blender.py` y `sync/identity_sync.py`.

Los cambios de producción se concentran en `server.py`, `actions/executor.py`, `actions/tools.py` y el módulo nuevo `commands.py`. El spec incorpora además el catálogo documental. La igualdad de los módulos anteriores indica continuidad de implementación; **no sustituye una prueba empaquetada de voz o MCP sobre el binario nuevo**.

### Comportamiento que se conserva

El código de SAPI, transcripción tiny CPU/int8, protocolo y proceso propio de ai-memory, almacenamiento procedural, inferencia, cancelación de trabajadores e identidad no cambia. Las comprobaciones de bearer, rechazo de orígenes de navegador y loopback del servidor permanecen en el diff; no se observó apertura de CORS ni exposición nueva del token del host.

### Mejoras que añade la biblioteca

- Catálogo como datos: 7.562 registros documentales permanecen deshabilitados, sin ejecución de texto, shell ni recetas importadas. Se seleccionan adaptadores mediante una tabla cerrada.
- Preparación, parámetros inmutables, aprobación por operación, caducidad, consulta posterior y cancelación previa al despacho.
- JSON con rechazo de claves duplicadas, además de constantes no estándar.
- Escritura exclusiva de archivos nuevos; rechazo de nombres Windows reservados, ADS, rutas de red/dispositivo y enlaces/reparse observados. Las precondiciones dejan de crear directorios.
- Consulta de PID mediante API Windows en lugar de interpretar `tasklist`.
- Excepciones de ejecución o verificación conservan `unknown`, evitando presentar como fallo reversible un efecto posiblemente realizado.

Estas mejoras están descritas con sus pruebas en [backend-safety-note.md](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/backend-safety-note.md>) y [INTEGRACION.md](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/INTEGRACION.md>). No se propone eliminarlas de la fuente canónica.

## Incompatibilidad que impide adoptar ahora el backend nuevo

**El render Blender queda inaccesible por todas las rutas HTTP admitidas.** El módulo que realiza el render sigue presente, pero la política nueva impide alcanzarlo:

1. [ADAPTERS](<C:/Users/luigi/Desktop/Axx assistant/backend/commands.py:25>) habilita únicamente telemetría, consulta de PID y escritura de archivo.
2. [axx.blender.fixture](<C:/Users/luigi/Desktop/Axx assistant/backend/commands.py:93>) se crea explícitamente deshabilitado con motivo «Pendiente de validación física del adaptador».
3. [La ruta antigua de acciones](<C:/Users/luigi/Desktop/Axx assistant/backend/server.py:278>) devuelve `403 USE_COMMAND_POLICY` para Blender y escritura.
4. [La preparación de recetas](<C:/Users/luigi/Desktop/Axx assistant/backend/server.py:334>) exige un adaptador incluido en ADAPTERS; por tanto, una receta Blender tampoco permite ejecutar el render. La ejecución antigua de recetas con efectos también devuelve 403.

El bloqueo es una decisión explícita de la nueva política, no un fallo del motor Blender. Sin embargo, para la orden original de conservar funciones constituye una regresión: el [backend residente empaquetado pasó el render real](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/packaged-runtime.json>) mediante Blender 4.5.5 LTS y verificó su PNG de 256×256, 37.697 bytes y SHA-256. Esa evidencia ya existe y no debe confundirse con ausencia de comprobación del adaptador.

### Otros cambios de contrato

- Un cliente anterior que llame directamente a `/actions/execute` para escribir recibe 403. Debe preparar y aprobar la operación mediante `/commands/prepare` y `/commands/execute`.
- Una receta de escritura anterior necesita `/recipes/prepare` y la aprobación de su operación; `/recipes/execute` ya no basta para producir el efecto.
- La biblioteca exige rutas relativas nuevas, contenido de hasta 65.536 bytes y no permite sobrescribir. El transporte anterior aceptaba rutas absolutas confinadas a artifacts y un límite mayor. Es una política más restrictiva que debe reflejarse en sus controles y mensajes.
- Las recetas múltiples o con herramientas fuera de la tabla de adaptadores quedan bloqueadas. No desaparecen de SQLite, pero no conservan automáticamente su ejecutabilidad.

El verificador residente de ocho casos usa los contratos anteriores. Que falle su primera escritura contra el backend nuevo no demostraría una regresión de SAPI o ai-memory: primero hay que adaptar ese verificador a la nueva preparación/aprobación. No debe modificarse una prueba para ocultar la pérdida de Blender.

## Revisión frontend coordinada

El responsable de la entrega transmitió el resultado de la revisión independiente del frontend; se incorpora aquí sin repetir su inspección:

- `ResidentDesktop` y el código de voz son byte-idénticos entre los conjuntos comparados.
- La interfaz canónica sí intercepta telemetría, archivos y recetas antiguas y los dirige a preparación/aprobación. No se encontró un bypass de la nueva política en esos controles. La incompatibilidad descrita arriba afecta a clientes anteriores que conserven los contratos directos.
- Se confirmó la pérdida de Blender ya descrita.
- El HTML canónico añade `body.native`/`axx-resident` de forma incondicional y rompe la presentación de navegador. El snapshot residente no tiene esa regresión.
- Órdenes locales como «abre lector» consultan el resolver antes de `externalCommand`; si el backend está caído o devuelve 403, falla una función local que debería conservar su recorrido. El próximo release debe preservar los comandos locales aunque el servicio de catálogo no responda.

Estos dos últimos puntos refuerzan la decisión de mantener unido el snapshot validado. La revisión corresponde al [frontend canónico](<C:/Users/luigi/Desktop/Axx assistant/1.AXX/Axx.html>) y sus integraciones de [biblioteca](<C:/Users/luigi/Desktop/Axx assistant/1.AXX/scripts/command-library.js>); no se atribuyen al motor SAPI, ASR o MCP.

## Evidencia disponible y alcance

| Evidencia | Resultado real y límite |
| --- | --- |
| [Backend residente empaquetado](<C:/Users/luigi/Desktop/Axx assistant/evidence/resident-20261019/packaged-runtime.json>) | PASS 8/8: memoria propia con consulta/lectura/reinicio, reutilización procedural, render Blender, WAV SAPI, tiny ASR sobre audio sintético y error tipado por credenciales ausentes. Es evidencia del SHA 8312…, no del 90e7…. |
| [Suite final de la biblioteca](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/backend-final-python312.log>) | 72 pruebas, exit 0, Python 3.12. Incluye voz sintetizada local, sin certificar altavoz o micrófono físicos. |
| [Paquete aislado nuevo](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/verified-package-report.json>) | PASS 20/20 sobre SHA 90e7…: catálogo, límites, preparación/aprobación, herramientas locales, recetas, cancelación y recuperación. Una comprobación exige expresamente que Blender siga bloqueado. No prueba render Blender, transcripción empaquetada ni ciclo MCP del nuevo binario. |
| [Snapshot de fuentes nuevo](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/frozen-source-verification.json>) | 58 archivos; `stable:true`, sin cambios registrados durante su construcción aislada. |

El archivo [packaged-commands.json](<C:/Users/luigi/Desktop/Axx assistant/evidence/command-library-20261019/packaged-commands.json>) corresponde a un **binario intermedio distinto** (`b068…`) y terminó con `KeyError: schema`. No debe utilizarse como evidencia positiva del SHA 90e7…; su informe válido es `verified-package-report.json`.

No se ejecutó un nuevo binario ni se realizaron renders o síntesis durante esta revisión de solo lectura. Las conclusiones operativas anteriores se apoyan en los registros identificados, separando su hash y alcance.

## Cuarto adaptador propuesto para el siguiente release

Propuesta enviada al responsable antes de editar; **no implementada** por la decisión de congelar la entrega:

```text
ID local: axx.blender.fixture
Ejecutor: blender_render_fixture
Riesgo: workspace_write
Entrada: filename string obligatorio; basename .png; hasta 84 caracteres
Aprobación: true explícito, vinculada a operation_id y parámetros inmutables
Ámbito: archivo nuevo dentro del workspace autorizado de artifacts
Proceso: Blender instalado; escena fija; CPU; timeout/cancelación actuales
Verificador: PNG, IHDR 256×256, IEND, tamaño y SHA-256 existentes
```

La modificación mínima sería añadir ese ID a ADAPTERS y retirar únicamente su placeholder bloqueado, validar de nuevo el nombre/destino antes de ejecutar y parametrizar `filename` al registrar una receta Blender. Deben conservarse la confirmación por operación, los 7.562 documentales deshabilitados y los rechazos de bypass legacy. No se propone aceptar rutas de ejecutable, scripts, escenas, comandos libres ni aprobación por texto/voz.

Coste estimado comunicado: 8–15 minutos de implementación y comprobaciones, sin dependencias nuevas, descargas ni pagos. Es una estimación de trabajo pendiente, no un compromiso de ejecución en segundo plano.

### Pruebas necesarias antes de adoptar la biblioteca

1. Cuarto adaptador visible y habilitado; documentos importados siguen deshabilitados. Actualizar los conteos esperados: cuatro adaptadores locales habilitados; ningún documental habilitado.
2. Rechazo de ejecución sin aprobación, aprobación no booleana, parámetros extra, rutas, scripts y nombres no permitidos; aprobación vinculada a entradas e identificador.
3. Render real mediante el backend empaquetado nuevo; verificar PNG y registrar aplicación, versión, hash y evidencia. Repetir el mismo identificador debe recuperar el resultado sin reescribir.
4. Cancelación de un render activo y estado final correcto; no afirmar que se revirtió un efecto ya completado.
5. Guardar receta desde el render comprobado, reiniciar y prepararla con nombre nuevo; confirmar y verificar un segundo PNG. Mantener bloqueados los bypass antiguos.
6. Repetir SAPI, ASR y escritura/consulta/lectura/reinicio de ai-memory en el paquete nuevo, adaptando únicamente el transporte de acciones a la nueva política.
7. Comprobar la interfaz y la instalación de ese conjunto exacto de HTML, shell y backend. No combinar binarios, recursos y recibos de dos compilaciones concurrentes.

La instalación del snapshot residente y la solución del caché vacío quedan bajo el responsable de la entrega. Este informe no declara que esa instalación posterior ya haya terminado.
