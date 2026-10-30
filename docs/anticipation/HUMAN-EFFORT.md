# Coste humano por resultado útil

M12 necesita observaciones humanas, además de los recibos técnicos. El evaluador
existente admite un archivo explícito de episodios manual/Axx. Calcula un informe
descriptivo; no ejecuta tareas, modelos, aplicaciones ni las regresiones de
razonamiento al usar esta opción. No cambia permisos o memoria del asistente.

```powershell
python scripts/evaluate_reasoning.py --human-episodes build/evaluation/human-episodes.json --output build/evaluation/human-effort.json
```

El archivo de entrada y el resultado son privados. No se deben adjuntar a una
publicación como estado de ejecución. La salida no puede reemplazar la entrada,
incluido un enlace duro al mismo archivo. El lector limita la entrada a 1 MiB.
La fuente y el evaluador quedan sellados; un cambio de fuente durante el cálculo
impide escribir el resultado. `--baseline` pertenece al evaluador de regresiones
y no se combina con episodios humanos.

## Protocolo antes de medir

Definir la familia, dificultad, estado inicial, variantes equivalentes y el
criterio de aceptación antes de observar los resultados. Registrar el hash del
protocolo, su revisión y el universo de pares elegibles. No reducir ese universo
para ocultar un intento fallido, una abstención, abandono o medición ausente.
Alternar o registrar el orden manual/Axx en el protocolo para poder revisar
efectos de aprendizaje. No reutilizar el artefacto del primer brazo.

Cada archivo corresponde a una persona y un reloj común. Los intervalos usan
milisegundos enteros desde el mismo origen, incluyendo ambos brazos y todos los
pares. Si cambia el reloj, usar otro archivo y conservar el anterior. El registro
es explícito: el evaluador no detecta atención humana, inactividad ni trabajo en
otras aplicaciones. Un temporizador dejado activo durante una espera distorsiona
la medición; debe revisarlo quien observa.

Contar trabajo manual, preparación, supervisión, corrección, deshacer,
interrupciones y recuperación. Incluir reintentos y preparaciones descartadas en
el episodio, aunque al final se alcance el objetivo. No usar duración del
ejecutor, latencia del modelo o tiempo total transcurrido como tiempo humano.
Los intervalos solapados se rechazan para revisar su atribución.

## Contrato de datos, versión 1

Los objetos admiten exactamente los campos indicados. IDs opacos usan letras
ASCII, dígitos, `_`, `.`, `:` o `-`, comienzan por letra/dígito y tienen como
máximo 128 caracteres. No introducir nombres personales, conversaciones, rutas,
documentos, audio ni instrucciones en esos identificadores.

| Objeto | Campos |
| --- | --- |
| Dataset | `schema_version: 1`, `dataset_id`, `dataset_revision`, `partition`, `measurement_basis`, `protocol_sha256`, `eligible_pairs`, `pairs` |
| Par | `id`, `family`, `project`, `period`, `contract_sha256`, `equivalent`, `manual`, `axx` |
| Episodio | `outcome`, `result_verified`, `result_receipt_sha256`, `useful`, `measurement_complete`, `intervals`, `corrections`, `undos`, `interruptions`, `preparations` |
| Intervalo | `activity`, `start_ms`, `end_ms` |
| Preparación | `id`, `state` |

- `partition`: `development` o `holdout`. La etiqueta no demuestra independencia.
- `measurement_basis`: `self_reported_intervals`, `observer_recorded_intervals`
  o `fixture`. Los fixtures nunca generan diferencia humana elegible.
- `equivalent`: revisión humana booleana del par según el protocolo. No es una
  equivalencia deducida del nombre de la tarea ni una certificación automática.
- `manual`/`axx`: un episodio o `null` si falta. `eligible_pairs` incluye los
  pares todavía ausentes; se admiten hasta 500 pares registrados por archivo.
- `outcome`: `completed`, `failed`, `abandoned`, `abstained` o `incomplete`.
- `result_verified`: declaración booleana del observador. Si es verdadera requiere
  `result_receipt_sha256` de 64 caracteres hexadecimales minúsculos. Si es falsa,
  esa referencia puede ser `null`. El programa no consulta el contenido del recibo.
- `useful`: confirmación humana `true`/`false`, o `null` si se desconoce. La
  verificación técnica no sustituye esta respuesta.
- `measurement_complete`: `false` conserva los intervalos conocidos como cota
  inferior; no convierte lo no medido en cero.
- `activity`: `manual_work`, `preparation`, `supervision`, `correction`, `undo`,
  `interruption` o `recovery`. Cada intervalo exige `end_ms > start_ms >= 0`.
- `corrections`, `undos`, `interruptions`: listas de IDs de eventos conocidos.
  Repetir una referencia no crea otro evento.
- `preparations.state`: `used`, `obsolete` o `pending`. Repetir el mismo ID/estado
  no aumenta el denominador; estados contradictorios necesitan conciliación.

`family`, `project` y `period` permanecen en cada fila para segmentar el informe.
El hash de contrato identifica el criterio de resultado revisado para ese par;
el hash del protocolo identifica sus condiciones de comparación.

## Interpretación

La diferencia es **tiempo humano manual − tiempo humano con Axx**. Puede ser
negativa. Sólo se calcula para pares declarados equivalentes, con medición
completa, resultado completado/verificado declarado y utilidad confirmada en
ambos brazos. Una referencia SHA no demuestra por sí sola ninguna de esas
afirmaciones; la salida lo identifica como evidencia aportada no inspeccionada.

El agregado de pares completos muestra su propio denominador y no representa
automáticamente todo el universo. Por separado, el coste global conserva el
tiempo de episodios fallidos o abandonados. El coste por resultado útil incluye
ese trabajo desperdiciado; queda `null` si falta tiempo o no hay resultados
útiles declarados. Nunca actuar no acredita ahorro.

El porcentaje de preparaciones obsoletas declara numerador/denominador. Si hay
preparaciones pendientes, conserva esos conteos y deja el porcentaje sin
resolver. Los eventos se cuentan por referencias únicas.

`result: descriptive`, `independent_holdout_verified: false` y
`physical_acceptance_verified: false` son límites deliberados. Faltan todavía
recogida de observaciones humanas reales, revisión de sus recibos, comparabilidad
independiente y un holdout nuevo. Estas funciones no completan por sí solas M12,
no calibran el ranking de intención y no certifican un dispositivo o modelo.

## Pruebas

```powershell
python -m unittest backend.tests.test_effort_evaluation -q
python -m unittest discover -s scripts -p test_evaluate_reasoning.py -q
```

Los datos de prueba son declaraciones sintéticas. Cubren costes omitidos,
diferencias negativas, observaciones incompletas, fallos, obsolescencia,
referencias repetidas, solapamientos, ausencia de utilidad, límites de entrada,
conservación del archivo original y cambios de fuente durante la evaluación.
