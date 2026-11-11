# Análisis del aviso «Wait for gate B to finish: exit code 4»

## Qué fue

Un aviso de tarea en segundo plano de la sesión de revisión de la Fase 3 (tarea `byngmmzu9`, estado `failed`, código 4). No era el gate: era **mi propio comando de espera**, que lanzó el arnés para esperar el recibo del gate de la copia B (`9fe55a2`) y luego imprimir un resumen.

## Evidencia (no se asume; se contrasta)

| Fuente | Contenido |
|---|---|
| Salida de la propia tarea `byngmmzu9` | Antes de la línea `[exited with code 4]` aparece el final del gate B: `Ran 8 tests … OK`, `PASS: paired compatibility receipt saved to …gate-B.json`, `exit=0` |
| `run-B-gate.log` (log del gate B) | Termina en `PASS: paired compatibility receipt saved` y `exit=0` |
| `gate-B.json` (recibo) | `result: PASS`; pasos `contract`, `renderer_build`, `backend_tests`, `browser_tests` con `exit_code 0` |
| Cuenta del propio gate B | 15 contrato · 111 backend (1 omitida) · 58 navegador · 8 selector |

## Causa del código 4

El comando de espera tenía un bucle de hasta 300 s (20 × 15 s) y encadenaba, tras el bucle, un `tail`, un `grep -n "gate A raw summary"` **sin operando de archivo** y un script Python con un `heredoc`. Superó el límite de 400 s del tool de la sesión y fue movido a segundo plano; el código 4 es el de esa cola de diagnóstico (terminada fuera de plazo), **no** el de `validate_companion.py`. Comprobado: `grep` sin archivo devuelve 1 de inmediato en este entorno, de modo que el `grep` huérfano por sí solo no explica el 4; lo que consta es que el código 4 pertenece al envoltorio y que ningún paso del gate devolvió distinto de 0. No se puede atribuir el valor exacto a una línea concreta del envoltorio; sí se descarta el gate como origen.

## Conclusión

**No hubo fallo del gate B.** El aviso fue un fallo del comando de espera (mi arnés de diagnóstico), con el gate en PASS en tres fuentes independientes. No se declara aprobado por eso, sino porque el gate se **repitió** en esta fase:

| Repetición | Resultado |
|---|---|
| Gate PC/móvil en `f07f1ba` (fase 6, solo, sin concurrencia) | PASS: 15 / 112 (1 omitida) / 58 / 8 |
| Gate PC/móvil sobre `4f4e18b` (barrido final, ver `FINAL-RELEASE-GATE.md`) | véase `build/phase6/final/summary.txt` y `PHASE6-REGRESSION-RESULTS.md` |

## Lección aplicada

Un gate lento bajo carga concurrente es sensible al tiempo (en la Fase 3 el gate A falló una vez un test de avatar al ejecutar dos gates a la vez y pasó solo; Fase 5 registró el mismo patrón). En esta fase los gates se ejecutaron **uno a uno** y los comandos de espera usan sondeo corto con límite.
