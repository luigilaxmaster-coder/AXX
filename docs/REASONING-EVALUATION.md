# Evaluación reproducible de los contratos de razonamiento

El ejecutor reutiliza trece regresiones existentes sobre autoridad, documentos,
procedencia, vigencia de lecciones, aprendizaje verificado, olvido y recuperación. No añade otro
planificador ni instala un evaluador. Son pruebas de desarrollo ya expuestas,
con proveedores simulados y archivos/SQLite temporales; no constituyen un holdout.

Desde la raíz de la copia de trabajo:

```powershell
python -B -m unittest discover -s scripts -p test_evaluate_reasoning.py -v
python -B scripts/evaluate_reasoning.py --output build/reasoning-evaluation.json
```

Cada invariante identifica sus pruebas, alcance, estado y duración. El informe
registra el commit y un SHA-256 de los archivos Python del backend y del ejecutor.
Si esos archivos cambian durante la ejecución, el resultado queda incompleto.
No se incluyen trazas, texto de las pruebas, documentos ni credenciales.

`contract_result: passed` significa que las regresiones seleccionadas pasaron.
El resultado general sigue siendo `partial`: cumplimiento del modelo real,
aceptación del binario Windows, audio físico, conectores y holdout aparecen como
`not_run`. Un caso omitido nunca se convierte en aprobado. El código de salida
es 0 para las regresiones aprobadas, 1 para fallos/incompletos y 2 para errores
de entrada o de captura. Ese 0 no certifica la entrega completa ni E01–E28.

Para comparar una copia anterior con la actual, conservar su informe:

```powershell
python -B scripts/evaluate_reasoning.py --output build/reasoning-candidate.json --baseline build/reasoning-baseline.json
```

La comparación exige el mismo hash de código de pruebas y evaluador, inventario, clasificación de datos y
entorno. Señala cambios de resultado, no mejoras porcentuales de inteligencia.
Las duraciones son del test offline; no son latencia de inferencia, voz ni efecto
físico. Cambiar proveedor, recursos o condiciones requiere otra comparación
explícita con ensayos reales, junto con los recibos de ejecución correspondientes.

## Medición de instrucciones durante la sesión

`Axx.promptContracts.timingSummary()` resume hasta 128 muestras en memoria con
p50/p95 por rango más próximo (`nearest_rank`). Separa modo, versión/hash del
contrato, selección solicitada, ruta/modelo reportados y resultado. Una identidad
no confirmada permanece `null`; no permite atribuir tiempos a un modelo efectivo.
La caché desaparece al cerrar la aplicación y no guarda texto, audio, claves ni
documentos. `lastTiming` conserva su contrato anterior.

Primer texto no equivale a primer audio ni a objetivo verificado. Estas métricas
no calculan el tiempo desde el fin del habla: esa medida requiere correlacionar
captura, turno y reproducción real. Tampoco acreditan una mejora de latencia sin
muestras comparables de ambas versiones.

```powershell
node scripts/test-prompt-contracts.cjs
node scripts/test-prompt-timings.cjs
```

La CI ejecuta las guardas del evaluador, los contratos de métricas y la evaluación
acotada. El resultado parcial conserva explícitamente la aceptación no ejecutada.
