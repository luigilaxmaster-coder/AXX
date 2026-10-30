# Selección explícita de recursos por proyecto

Incremento de M4 sobre el contexto y las habilidades existentes, incorporado en
Windows 0.22.32. Las pruebas de archivos, HTTP y navegador acreditan los
contratos descritos; la aceptación física específica de la selección entre
dos proyectos permanece separada de las comprobaciones generales del avatar.
No forma parte del artefacto 0.22.31.

## Recorrido

En Mis habilidades, un comparador parametrizado puede usar los documentos
actuales confirmados de dos proyectos. Cada parámetro tiene su propia selección;
dos archivos llamados `input.bin` no se distinguen por su nombre, posición en una
lista, fecha o aplicación en primer plano.

El usuario consulta cada proyecto y revisa su documento y revisión antes de
preparar. La aprobación existente presenta ambos roles, proyectos, rutas,
versiones y hashes. Preparar no ejecuta y seleccionar recursos no concede un
permiso Full. Una corrección de las fuentes necesita una propuesta y aprobación
nuevas; no actualiza el archivo bajo una aprobación anterior.

## Contrato aditivo

`POST /axx-api/learning/propose` acepta `resource_bindings` opcional fuera de
`context`, `inputs` y la definición de la habilidad:

```json
{
  "text": "skill.comparador",
  "resource_bindings": {
    "path": {"project_id": "proyecto-a", "field": "current_file", "revision": 4},
    "other_path": {"project_id": "proyecto-b", "field": "current_file", "revision": 7}
  }
}
```

El ejemplo omite los identificadores operativos y de memoria que el cliente
captura normalmente. Las revisiones ilustradas no son referencias utilizables.

Ausencia del campo conserva el recorrido anterior. Presencia, incluso `{}`,
selecciona el recorrido explícito sin recurrir al modelo. Una selección
incompleta pide datos; `null`, listas y tipos inválidos se rechazan en HTTP.
El primer adaptador admitido es una habilidad existente elegida por ID exacto,
sin inferencia, con un paso `axx.file.compare` y parámetros string requeridos
`path` y `other_path`. Sus plantillas usan esos parámetros completos. Un alias,
«otra vez», defaults o una instrucción documental no asignan los recursos.

El cliente sólo elige proyecto, campo y revisión. No puede aportar la ruta
efectiva, identidad física, SHA, generación de memoria ni permisos dentro del
selector. Un parámetro no admite simultáneamente un literal y un binding.

## Identidad y continuidad

El servidor exige un campo vigente de origen `confirmed_user` con procedencia
durable conocida y una tarea de origen ya persistida; leer no crea esa tarea.
Resuelve cada origen bajo su propio proyecto y tarea; no
relaja el aislamiento del contexto ambiental de la misión destino. Esa metadata
no demuestra por sí sola observación física ni pertenencia de un directorio a
un proyecto.

Las rutas deben ser archivos regulares locales dentro del workspace existente.
Se rechazan enlaces, recursos duplicados, identidad compartida y archivos fuera
del límite vigente. Se reutiliza el capturador M1 para guardar ruta relativa,
SHA-256, tamaño, dispositivo, inode y fecha de modificación.

`plan.resource_bindings` conserva, por rol, el selector, la tarea del origen,
su scope y dependencias M9 originales, caducidad y `input_version`. La firma de
petición incluye los selectores; la aprobación v2 incluye los bindings
resueltos. Cambiar los roles importa aunque los bytes de ambos archivos sean
iguales. Repetir el mismo ID no captura otra versión.

Antes de admitir y despachar se vuelven a comprobar los orígenes, revisión,
caducidad, memoria, identidad y bytes, además de los inputs concretos del
comando. La lease M1 de Windows niega compartir escritura y borrado y protege
los directorios hasta que termina el ejecutor. En plataformas sin esa lease no
se sustituye la protección por una lectura sin bloqueo.

Consultar un historial, reiniciar o reanudar no refresca snapshots. Cambiar un
campo invalida la revisión dependiente. Olvidar una fuente invalida también la
misión derivada y retira sus bindings utilizables, conservando archivos,
recibos y presupuesto. Las referencias documentales M3 siguen pasando sus
guardas propias.

## Verificación y alcance pendiente

Las regresiones usan SQLite y archivos temporales reales, HTTP loopback
autenticado y entrada de interfaz controlada. Deben probar dos proyectos con el
mismo basename, cero inferencias, aprobación exacta, cambio de bytes e identidad,
caducidad, olvido, reinicio, idempotencia, intercambio de roles y la carrera al
entrar en el comparador. La interfaz debe mostrar fuentes distintas y descartar
respuestas tardías tras cambiar de proyecto, selección o conversación.

```powershell
python -m unittest backend.tests.test_resource_bindings backend.tests.test_resource_binding_http -q
node 1.AXX/scripts/test-resource-bindings.cjs
```

Esto no completa la resolución semántica libre de «este/el otro», selección
observada entre aplicaciones, descubrimiento de recursos ni observación
adaptativa general de M4. El envío de observaciones a proveedores sigue cerrado.
La aceptación de versiones anteriores no acredita esta fuente; instalación,
gate conjunto y aceptación nativa permanecen separados.
