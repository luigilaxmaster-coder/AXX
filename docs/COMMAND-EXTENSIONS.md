# Personalización y comandos de Axx

## Personalizar sin cambiar código

En **Personalizar agente** se guardan nombre, rol, contexto, instrucciones y una
lista de hasta 20 IDs de comandos preferidos. El tono conserva las preferencias
existentes. El perfil se envía al proveedor elegido al comenzar una respuesta y
se conserva localmente hasta cambiarlo o restablecerlo. No concede permisos ni
convierte la respuesta del modelo en una ejecución.

En **Comandos** se puede buscar por nombre o ID, recorrer todas las páginas del
catálogo, consultar disponibilidad, completar parámetros y revisar resultados.
Una entrada documental bloqueada describe una posibilidad; no demuestra que
exista un adaptador ejecutable. Preguntar solicita aprobación incluso para una
acción segura; Auto seguro sigue las reglas del backend.

## Añadir un comando mediante código

El punto de partida es un adaptador existente, por ejemplo
`ADAPTERS['axx.system.telemetry']` en `backend/commands.py`. No hay un segundo
ejecutor ni un editor que evalúe texto importado como código.

1. Definir un ID estable, título, descripción, riesgo, alias exactos y argumentos
   tipados en `ADAPTERS`. Usar límites y `required`; nunca aceptar campos sobrantes.
2. Reutilizar una herramienta registrada cuando su contrato ya corresponda al
   trabajo. Para una herramienta nueva, implementar el mismo contrato que las
   clases de `backend/actions/tools.py`, incluyendo validación, cancelación y
   comprobación del resultado, y registrarla en el ejecutor existente.
3. Revisar la traducción de parámetros en `CommandService`: un descriptor por sí
   solo no conecta un nuevo tipo de entrada con su herramienta. Mantener destino,
   origen, riesgo y postcondiciones en el registro de la operación.
4. Añadir pruebas al catálogo y al ejecutor: parámetros inválidos, permisos,
   cancelación, timeout, resultado incierto y reintentos sin efectos duplicados.
5. Comprobar el caso real en Windows. Hasta entonces, indicar la disponibilidad
   con precisión; una prueba de contrato no es validación de la aplicación destino.
6. Reconstruir e instalar según `docs/RELEASING.md`. El catálogo del ejecutable
   instalado no cambia al editar solamente el checkout.

Ejemplo de uso de un ID existente desde el chat:

```text
/comando axx.process.inspect {"pid":1234}
```

El PID es ilustrativo: hay que sustituirlo por un proceso observado. La petición
se prepara, se aplica el modo del chat, y solo se declara terminada con evidencia.

Los scripts PowerShell/CMD escritos explícitamente siguen su ruta separada de
revisión y aprobación. El perfil del agente y los documentos MD no autorizan su
ejecución. Las muestras personales de voz, credenciales y estado local no forman
parte del código publicado ni del instalador.

## Descubrir capacidades de una aplicación

El trabajo de Antigravity se integró como observación UIA y propuestas tipadas.
El nombre interno `cli_anything` identifica este adaptador local; no instala el
runtime de HKUDS/CLI-Anything ni afirma compatibilidad universal.

1. Usa `axx.desktop.list_windows` y selecciona el HWND y PID exactos.
2. Ejecuta `axx.desktop.cli_anything.scan` con `window_id` hexadecimal y `pid`.
   Devuelve hasta 1.000 controles con patrones, estado y selectores observados;
   no exporta valores de campos ni texto del documento. Una ventana puede no
   exponer controles, responder tarde o requerir permisos adicionales.
3. Solo `inspect`, `read`, `focus` y `type` se traducen a adaptadores existentes.
   `type` exige un `control_id` único, visible y editable; `read` mantiene su
   aprobación de contenido. No hay clic por coordenadas ni atajos inferidos.
4. `POST /axx-api/cli-anything/prepare` recibe `target`, `command`, `args` y
   opcionalmente `conversation_id`. Devuelve una preparación del CommandService;
   utiliza el modo guardado del chat y las rutas normales de aprobar/cancelar.
   No acepta `approved` ni ejecuta efectos por sí misma.

Para desarrollo local:

```powershell
python scripts/cli_anything.py --json list
python scripts/cli_anything.py scan 0x1234
python scripts/cli_anything.py prepare 0x1234 focus
```

Sustituye `0x1234` por el HWND observado. El último comando imprime una propuesta;
no cambia el foco. Los botones descubiertos necesitan un adaptador explícito con
postcondición y aceptación Windows antes de convertirse en acciones habilitadas.

## Catálogo por ventana y procedimientos reutilizables

`python scripts/cli_anything.py commands 0x1234` y
`GET /axx-api/cli-anything/commands?target=0x1234` devuelven una observación
actual con contratos del registro. Un patrón UIA observado no habilita una
acción nueva. No se ejecutan nombres inferidos, coordenadas ni selectores
guardados de una ventana anterior.

La memoria es `ActionLearning` sobre la base existente de Axx:

- `POST /axx-api/learning/remember` promueve un recibo verificado compatible.
- `GET /axx-api/learning/actions` enumera procedimientos y sus evidencias.
- `POST /axx-api/learning/compose` combina IDs/versiones de habilidades
  guardadas con parámetros tipados. Prepara un plan revisable; no lo ejecuta.
- `/axx-api/cli-anything/commands/develop` es una entrada de composición al
  mismo servicio: `name`, `parts` y opcionalmente `operation_id`, `project_id`.
  Cada parte tiene `id`, `version` e `inputs`; no admite código, riesgo declarado
  por el cliente ni pasos arbitrarios.
- `GET /axx-api/cli-anything/history?limit=50` consulta el registro existente.
  No hay una segunda base de efectos ni cifras de aceleración simuladas.
- `/axx-api/cli-anything/execute` rechaza ejecución directa. Usa la operación
  preparada y las rutas de aprobación, cancelación y recuperación de comandos.

Las repeticiones verificadas reutilizan el procedimiento sin una inferencia
nueva cuando sus parámetros están completos. Siempre vuelven a resolver el
destino y sus controles, y comprueban la postcondición.

## Comandos recibidos desde Axx Mobile

El teléfono necesita permiso **Work** explícito. Una orden exacta del catálogo
se prepara con el ID real y el modo persistido del chat de origen. En Preguntar
aparece una tarjeta para aprobar en la PC; Auto seguro se aplica en el backend.
El gateway nunca crea una aprobación. Los IDs de operación son estables para
evitar repetir una petición. Un resultado incierto se comunica como incierto.
Las órdenes sin coincidencia exacta no se ejecutan ni se convierten en scripts.
