# Taller de capacidades de Axx

El taller permite convertir un objetivo en una propuesta de capacidad, revisarla,
comprobar sus efectos y guardar una versión reutilizable. Usa el proveedor y el
modelo seleccionados en Axx. No instala otro proveedor ni habilita facturación.

## Dos tipos de propuesta

| Tipo | Resultado | Ejecución |
| --- | --- | --- |
| Flujo de comandos | Una composición de uno a ocho comandos registrados, con parámetros tipados | Solo mediante `CommandService` y `ActionExecutor`, después de revisión y aprobación |
| Propuesta de código | Código y notas de integración exportables en Markdown | No se importa, instala ni ejecuta desde el taller |

Axx puede proponer mejoras de una capacidad anterior. Cada mejora crea una revisión
nueva. No puede concederse permisos, alterar la política del backend ni ejecutar
código que haya generado. Para incorporar un adaptador nuevo al programa sigue
[COMMAND-EXTENSIONS.md](COMMAND-EXTENSIONS.md) y el proceso de revisión, pruebas y
entrega del proyecto.

## Uso desde la aplicación

1. Abre **Comandos → Taller de capacidades** o escribe `/capacidad` en el chat.
2. Describe el objetivo y elige **Flujo de comandos** o **Propuesta de código**.
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
| `draft` | Definición guardada; no aprobada ni ejecutada |
| `reviewed` | Confirmación humana ligada a revisión y digest |
| `active` | Muestra ejecutada con postcondiciones y recibos reales; versión publicada en `SkillMemory` |
| `superseded` | Otra revisión reemplazó esta versión activa |
| `revoked` | Deshabilitada; no se pueden preparar ejecuciones con versiones históricas |

`validation.status = static_validated` comprueba estructura, tipos, comandos y
parámetros de muestra. No acredita interacción física ni éxito en otras aplicaciones,
ventanas, cuentas o equipos. `runtime_verified` solo se establece al activar usando
el plan vinculado y los recibos persistidos tanto del servicio de comandos como del
ejecutor. La evidencia corresponde a esa muestra concreta.

## Formato declarativo

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
- Publicar una versión y cambiar el estado activo ocurre en la misma transacción
  SQLite que crea la versión y su evidencia en `SkillMemory`.
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
| `prepare_validation(id, revision, digest, conversation_id)` | Crear o recuperar el plan de muestra, sin ejecutarlo |
| `activate(id, revision, digest)` | Verificar recibos y publicar en `SkillMemory` |
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
