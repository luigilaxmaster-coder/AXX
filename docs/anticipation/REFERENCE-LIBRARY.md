# Biblioteca documental de razonamiento

Se incorporó explícitamente `AXX_BIBLIOTECA_RAZONAMIENTO.zip`, recibido del usuario,
con SHA-256 `a47e1de71f0a142b4a89d1ab1bcab5d81dc2925bad14946ee94f5934bbd9cc26`.
Su revisión declarada es 2026-10-29. El manifiesto interno contiene diez archivos;
se comprobaron sus diez hashes y el CRC del ZIP. Esto acredita integridad del
paquete recibido, no autenticidad, vigencia o compatibilidad de las fuentes externas.

La biblioteca existente conserva sus 7.566 procedimientos y añade 28 referencias:
nueve Markdown del paquete, dieciséis entradas del catálogo de fuentes y tres
documentos históricos aportados por separado. Todas quedan como
`DOCUMENTED_NOT_EXECUTED`. Los nombres incluyen la revisión del paquete mediante
su hash; una importación idéntica es idempotente y una revisión distinta no
sobrescribe registros anteriores.

Cada ficha conserva tipo de conocimiento, hash del archivo, revisión declarada,
procedencia y limitaciones. Los textos originales, catálogo, manifiesto y ZIP
recibido permanecen como miembros inertes de `resources/procedure-library.zip`.
Los extractos de consulta están acotados para reutilizar la recuperación actual
de hasta tres procedimientos pertinentes. El encargo dirigido al integrador se
conserva como referencia no confiable; no se convierte en política del asistente.

La integración no instala frameworks, modelos, scripts ni adaptadores. Los enlaces
a CoALA, ReAct, Reflexion, Voyager y las demás fuentes son documentación propuesta;
su presencia no prueba comportamiento de Axx ni acredita ejecución en Windows.

Los documentos históricos conservan sus bytes y hashes originales, con nombre de
archivo y revisión declarada; los metadatos no incluyen rutas privadas del usuario:

| Documento | Revisión | SHA-256 |
|---|---|---|
| AXX_ANALISIS_PROMPTS_Y_PLAN_DE_INTEGRACION (1).md | 2026-10-29 | baf3a6be9b9992a3fe3b5827e7bf163415ad2a18222147a9afd7e2e730bb17b8 |
| 2026-10-22-axx-integracion-modular.md | 2026-10-22 | 93ce0ec3334b6d7e7edd76b8333c05a85a4411cb359609526bc2616237fe79cf |
| AXX_DOCUMENTACION_MAESTRA.md | 2026-10-23 | d281235f0729b4dbdc0d308185d08a482e3b110e210a658a2ff856ea55aa8441 |

Sus bases de código y propuestas pueden estar desactualizadas: el compositor de
instrucciones y varios adaptadores descritos como pendientes ya existen. Los
límites históricos de workflows y el catálogo de 619 acciones propuestas no
modifican los contratos ni habilitan comandos del runtime actual. Se revisaron
patrones de credenciales, claves privadas, correos y rutas personales sin encontrar
coincidencias en estos tres archivos; esa revisión no certifica las fuentes enlazadas.

## Incorporación reproducible

Desde la raíz del repositorio, con el ZIP recibido en una ruta local explícita:

```powershell
python scripts/import_procedure_folder.py "C:\ruta\AXX_BIBLIOTECA_RAZONAMIENTO.zip" resources/procedure-library.zip build/reasoning-reference-import.json --reference-package
python -m unittest backend.tests.test_reference_library backend.tests.test_procedure_integration -v
```

El importador valida nombres, límites, manifiesto completo y hashes antes de tocar
la biblioteca. Conserva los registros existentes y reemplaza el archivo mediante
una escritura temporal seguida de sustitución atómica. El modo habitual de
importación de JSONL mantiene su contrato anterior.
Los documentos históricos se seleccionan individualmente con
`--historical-reference "C:\ruta\documento.md"`; no se recorren otras carpetas.

## De documentación a ejecución

La recuperación existente de `ActionLearning` incorpora fragmentos como datos de
referencia. `ProcedureLibrary` nunca habilita un documento como comando. Para un
procedimiento ejecutable se reutiliza `CapabilityWorkshop`: propuesta `workflow`
con herramientas registradas, revisión de su digest, plan de ensayo, recibos reales
del ejecutor y activación versionada en `SkillMemory`. Si falta un adaptador, la
documentación permanece no ejecutable.

El ejemplo de archivo generado utiliza las capacidades ya disponibles:
`axx.artifact.write`, `axx.file.sha256` y el recorrido de anticipación. El hash
esperado procede del recibo de generación; se compara con una lectura posterior
del archivo y se revalida su identidad. Calcular un hash por sí solo no acredita
contenido correcto, calidad visual o utilidad. Los permisos y M15 mantienen sus
condiciones habituales.

Para revertir esta incorporación se restaura la versión anterior del archivo de
recursos desde Git. La importación no cambia datos personales, emparejamientos,
credenciales, permisos ni recetas verificadas de la instalación.
