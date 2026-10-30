# Referencias documentales y habilidades comprobadas

Esta unidad enlaza la biblioteca importada con el planificador y el taller existentes. Es un incremento de fuente posterior al instalador R3 0.22.30; no certifica el aprendizaje semántico general por demostración de aplicaciones ni una instalación nueva.

## Recorrido

`documento como referencia → propuesta parametrizada → revisión exacta → ensayo aprobado → recibos del ejecutor → habilidad → nueva revisión con otras entradas`.

En Comandos, una ficha documental puede abrirse mediante **Usar como referencia**. La selección sólo prepara el formulario del taller. Crear una propuesta, aprobar su definición, ejecutar la prueba y activar la capacidad siguen siendo decisiones separadas. El formulario permite quitar la referencia de un borrador nuevo; una revisión de una capacidad existente conserva su linaje.

La identidad resuelta por `ProcedureLibrary` contiene `document_id`, `record_sha256`, `member_sha256` y `revision`. El servicio vuelve a leer el ZIP actual y comprueba índice, receta, documento, rutas, procedencia declarada, duplicados y límites. Las referencias importadas usan el hash canónico de su receta; se conserva el algoritmo original del catálogo antiguo. Una identidad enviada por el cliente debe coincidir con los bytes actuales. La biblioteca sigue marcada `DOCUMENTED_NOT_EXECUTED` y nunca concede ejecución.

El texto documental entra como dato no confiable, con un máximo combinado de tres referencias y 3500 bytes de referencias por prompt. La identidad persistida procede del resolver, no de la respuesta del modelo. El linaje admite hasta 24 referencias para las composiciones existentes y se conserva aunque el texto enviado sea más corto. Superar el límite produce un rechazo, no una pérdida silenciosa de dependencias.

## Aprobación y continuidad

Los nuevos planes tienen `approval_version=2`: el hash incluye el candidato parametrizado y las referencias documentales, además de los pasos y dependencias anteriores. Se valida el candidato antes de finalizar la revisión. Cambiar esos datos después invalida la aprobación.

Los planes históricos conservan su hash anterior. Cuando contienen un candidato que no estaba sellado, pueden conservar el recorrido de sus pasos aprobados y sus recibos, pero no publicar silenciosamente una nueva habilidad parametrizada; el resultado indica que el aprendizaje requiere revisión. No se inventa procedencia documental para habilidades históricas ya publicadas.

El linaje continúa por composición, configuración, reparación, revalidación, comandos recordados, revisiones del taller, rollback y publicación. El digest del taller incluye las referencias cuando existen; el digest antiguo sin ese campo permanece igual. Una revisión restaurada vuelve a ser propuesta y conserva las fuentes heredadas.

La biblioteca se revalida antes de inferencia, aprobación, despacho, activación y reutilización. Esto incluye el uso directo de transformaciones ya presentes en el catálogo, sin depender de actualizar primero su lista. Los recibos de comandos conservan sus referencias para impedir que recordar una operación pierda su procedencia. La evidencia y las comprobaciones de efectos del único ejecutor siguen siendo obligatorias.

Las referencias documentales son distintas de `memory_dependencies`: no sustituyen la tarea, generación y contexto de M9. Olvidar una sesión sigue bloqueando sus derivados. Cambiar de chat durante una espera impide mostrar la respuesta en el chat nuevo o enviar una continuación con otro token; se conserva el borrador humano.

## Verificación y límites

Las pruebas usan ZIP y SQLite temporales, servidores HTTP loopback, transporte de modelo controlado y archivos reales de ensayo. El recorrido de comparación usa primero dos binarios iguales; después reutiliza la habilidad con otro par distinto, verifica `equal=False`, los SHA-256 esperados y que los cuatro originales permanecen intactos. La reutilización por ID con parámetros nuevos no llama al modelo. También se comprueban referencias alteradas, candidatos modificados, revisión y rollback, callbacks retenidos y conservación de recibos.

```powershell
python -m unittest backend.tests.test_document_references backend.tests.test_document_skill_learning backend.tests.test_workshop_document_provenance backend.tests.test_document_reference_http -q
node 1.AXX/scripts/test-document-provenance.cjs
python scripts/validate_companion.py --output build/companion-validation.json
```

La coherencia de hashes no acredita autoría ni vigencia externa del documento. El ensayo acotado de archivos no acredita exportación semántica en aplicaciones, proveedor externo, voz ni control físico del escritorio. No amplía permisos Full, activa el envío de contexto observado, introduce otro ejecutor ni deshace efectos ya iniciados. Los archivos, recibos, credenciales y emparejamientos existentes se conservan.
