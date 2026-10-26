# Taller de capacidades de Axx

El taller permite convertir un objetivo en una propuesta de capacidad, revisarla,
comprobar sus efectos y guardar una versión reutilizable. Usa el proveedor y el
modelo seleccionados en Axx. No instala otro proveedor ni habilita facturación.

## Tipos de propuesta

| Tipo | Resultado | Ejecución |
| --- | --- | --- |
| Flujo de comandos | Una composición de uno a ocho comandos registrados, con parámetros tipados | Solo mediante `CommandService` y `ActionExecutor`, después de revisión y aprobación |
| Transformación Python pura | Función `run(inputs)`, esquemas y casos esperados | Intérprete AST acotado; pruebas, aprobación por digest y registro explícito. Sin I/O ni Python general |
| Propuesta de código | Código y notas de integración exportables en Markdown | No se importa, instala ni ejecuta desde el taller |

Axx puede proponer mejoras de una capacidad anterior. Cada mejora crea una revisión
nueva. No puede concederse permisos ni alterar la política del backend. El código
puro activable y sus límites se explican en [GENERATED-COMMANDS.md](GENERATED-COMMANDS.md).
Para incorporar un adaptador con acceso al sistema sigue
[COMMAND-EXTENSIONS.md](COMMAND-EXTENSIONS.md) y el proceso de revisión, pruebas y
entrega del proyecto.

## Uso desde la aplicación

1. Abre **Comandos → Taller de capacidades** o escribe `/capacidad` en el chat.
2. Describe el objetivo y elige procedimiento, transformación pura o propuesta de integración.
3. Revisa el contenido generado, los parámetros de muestra, destinos y riesgos.
4. Confirma la revisión. La confirmación queda ligada al número de revisión y a su
   SHA256; modificar el contenido invalida esa aprobación.
5. Para un flujo, prepara la validación. Se abre la tarjeta de comandos habitual,
   asociada al chat de origen. Aprueba sus pasos concretos para ejecutarlos.
6. Regresa al taller y activa la revisión cuando todos los pasos tengan recibos
   comprobados. La capacidad aparecerá en la memoria de acciones aprendidas.
7. Pulsa **Usar capacidad** para preparar otra ejecución con parámetros
   nuevos. Sus destinos, precondiciones y política se comprueban nuevamente.

**Revisar**, **ejecutar la muestra** y **activar** son acciones distintas. La revisión
de una definición no equivale a autorizar cada ejecución posterior. Un resultado
incierto conserva su identidad y sus efectos parciales; no se vuelve a ejecutar
automáticamente ni se convierte en evidencia de éxito.

## Qué significa cada estado

| Estado | Evidencia |
| --- | --- |
| `draft` | Definición sin aprobar ni activar; sus pruebas puras pueden haberse ejecutado |
| `reviewed` | Confirmación humana ligada a revisión y digest |
| `active` | Flujo con muestra y recibos reales en `SkillMemory`, o transformación con pruebas pasadas, aprobación exacta y herramienta registrada |
| `superseded` | Otra revisión reemplazó esta versión activa |
| `revoked` | Deshabilitada; no se pueden preparar ejecuciones con versiones históricas |

`validation.status = static_validated` comprueba estructura, tipos, comandos y
parámetros de muestra. No acredita interacción física ni éxito en otras aplicaciones,
ventanas, cuentas o equipos. En un `workflow`, `runtime_verified` se establece al activar usando
el plan vinculado y los recibos persistidos tanto del servicio de comandos como del
ejecutor. La evidencia corresponde a esa muestra concreta. Una transformación usa
`self_tests_passed` ligado a su digest y aprobación; su activación registra una
herramienta en el catálogo dinámico. No publica un flujo en `SkillMemory` ni
acredita efectos sobre aplicaciones.

## Formato declarativo de un workflow

```json
{
  "kind": "workflow",
  "title": "Consultar estado local",
  "objective": "Consultar el sistema antes de continuar el trabajo",
  "schema": {
    "type": "object",
    "properties": {},
    "required": []
  },
  "templates": [
    { "command_id": "axx.system.telemetry", "inputs": {} }
  ],
  "sample_inputs": {}
}
```

Las plantillas pueden usar `{{parametro}}`. Cada parámetro debe estar declarado en
`schema.properties`; admite `string`, `integer`, `number` y `boolean`. El tipo debe
coincidir con el contrato del comando. `sample_inputs` completa una muestra concreta
que el usuario puede revisar. Los nombres de comandos siempre son IDs literales.

Los comandos shell y los selectores UIA efímeros quedan fuera de los flujos del
taller. Los adaptadores de aplicación admitidos vuelven a resolver sus objetivos
cuando se ejecutan. Una capacidad nunca toma coordenadas guardadas como identidad.

## Persistencia, versiones y cancelación

- Tablas `capability_heads`, `capability_revisions` y `capability_events` en la base
  local que ya utiliza `ActionLearning`; no hay un catálogo ejecutor paralelo.
- La definición y el digest de cada revisión son inmutables. La aprobación, el plan
  vinculado y la evidencia se conservan separados de la definición.
- Para un `workflow`, publicar y cambiar el estado activo comparte la transacción
  SQLite que crea su versión y evidencia en `SkillMemory`. Una transformación
  persiste su revisión activa y actualiza el registro dinámico; al reiniciar se
  reconstruye desde las revisiones aprobadas.
- Revocar deshabilita la versión activa y solicita cancelación de planes pendientes
  vinculados. Un efecto ya ejecutado no se deshace; un efecto en curso conserva sus
  recibos y requiere comprobar su estado real.
- Restaurar una revisión anterior crea un borrador nuevo. Requiere otra revisión y
  validación antes de reemplazar la versión activa; no hereda aprobaciones.
- Solo se genera una propuesta a la vez. Cada solicitud hace una inferencia con el
  límite de tiempo del adaptador existente. Al cerrar, se cancela la inferencia y se
  descartan respuestas tardías. No hay un bucle autónomo de autoedición del programa.
- Los registros técnicos contienen IDs, revisión y evento. No registran el texto de
  los mensajes, el código propuesto ni las credenciales del proveedor.

## Integración técnica

`CapabilityWorkshop(learning)` comparte conexión y bloqueo con `ActionLearning`.
Debe cerrarse antes de cerrar el servicio de aprendizaje. La integración HTTP local
expone el taller por los mismos controles de acceso que el resto de Axx.

| Método Python | Función |
| --- | --- |
| `catalog()` / `list(limit=100)` / `get(id)` | Contratos disponibles, borradores y revisiones |
| `create(definition, project_id='')` | Guardar una definición validada estáticamente |
| `generate(goal, model, provider_name, selection_mode, kind, ...)` | Solicitar una propuesta al proveedor configurado |
| `revise(id, revision, digest, definition)` | Crear revisión con control de concurrencia |
| `approve(id, revision, digest, confirmed=True)` | Confirmar la definición exacta |
| `validate(id, revision, digest)` | Validar contratos del flujo o ejecutar los casos de prueba puros |
| `prepare_validation(id, revision, digest, conversation_id)` | Crear o recuperar el plan de muestra de un workflow, sin ejecutarlo |
| `activate(id, revision, digest)` | Publicar el workflow con recibos en `SkillMemory`, o registrar la transformación probada y aprobada |
| `revoke(id, revision, digest)` | Deshabilitar y cancelar planes vinculados |
| `rollback(id, revision, digest, target_revision)` | Recuperar una definición anterior como nuevo borrador |
| `export(id, revision=None)` | Devolver contenido para descarga; no escribir ni ejecutar archivos |

`ActionLearning` comprueba la disponibilidad del taller al vincular y ejecutar sus
habilidades, incluidos planes compuestos y referencias a versiones anteriores. Una
validación del taller no se guarda automáticamente como una habilidad por otra ruta.
Las correcciones de capacidades gestionadas deben pasar por una nueva revisión del
taller.

## Validación del módulo

```powershell
python -m unittest backend.tests.test_capability_workshop -v
python -m unittest backend.tests.test_capability_workshop_http -v
```

La suite comprueba JSON mal formado, campos de permisos inventados, tipos, revisión
obsoleta, persistencia, aprobación, validación ligada al chat, recibos del ejecutor,
revocación, versiones históricas, restauración, cierre y propuestas de código.
Las pruebas locales no sustituyen la aceptación visual ni la prueba de Windows del
instalador que se publique.
