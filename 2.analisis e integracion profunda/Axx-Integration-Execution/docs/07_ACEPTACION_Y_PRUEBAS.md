# 07 — Aceptación, evidencias y definición de terminado

## Gates de integración

Los gates son criterios técnicos de salida, no peticiones rutinarias de permiso al usuario. PASS requiere evidencia; BLOCKED no se trata como PASS.

| Gate | Criterio | Evidencia mínima |
|---|---|---|
| G0 | Repo y stack reales inventariados, baseline capturado | PROJECT_MAP con rutas/símbolos y comandos existentes |
| G1 | Baseline endurecido y contrato estable | Suite de regresión, nuevos tests H01–H10 aplicables y salidas |
| G2 | Adaptador cancelable y seguro | Deadline, límites, secretos, IPC y rutas con espacios probados |
| G3 | Integrado en conversación existente | Flujo desde UI, respuesta única y estados reales |
| G4 | Dos proveedores reales aptos | Validación por cuenta/modelo y éxito individual live |
| G5 | Recuperación y no duplicación | 429 simulado en flujo integrado, Esc, reinicio, rollback |
| G6 | Build/instalador Windows verificado | Prueba del binario y no regresión de Axx en equipo destino |

RELEASE_READY exige G0–G6 PASS. Si faltan cuentas o Windows, entregar código/documentación con G4/G6 BLOCKED y motivo preciso. Las pruebas de esta entrega no cumplen G3/G4/G6.

## Matriz de escenarios obligatorios

| ID | Escenario | Resultado esperado | Nivel |
|---|---|---|---|
| A01 | A responde | Una respuesta de A, intentos 1 | Unit + integración |
| A02 | A=429, B válido | B responde, A pausado, historial idéntico | Unit + UI con fallo inyectado |
| A03 | A=503 o timeout | B si queda deadline y no hubo efectos | Unit + integración |
| A04 | A=400/422 | Detener, no enviar a B | Unit |
| A05 | A=403 sin clasificación | Detener por política, no reenviar | Unit endurecido |
| A06 | Ninguno elegible | Error NO_PROVIDER_AVAILABLE, sin bucle | Unit + UI |
| A07 | Clave ausente | Omitir fila y mostrar missing_key | Unit |
| A08 | Capacidad visión requerida | Nunca elegir modelo text-only | Unit |
| A09 | tools/tool_choice malformado | Rechazo previo a red | Unit endurecido |
| A10 | Salida message vacío o JSON inválido | No declarar éxito; política de respaldo | Unit endurecido |
| A11 | Esc durante red/failover | CANCELLED único, sin B posterior, sin UI tardía | Integración + Windows |
| A12 | Respuesta lenta indefinida | Deadline de pared aplicado; worker recogido | Integración |
| A13 | Reinicio | Cuotas/pausas sobreviven, sin repetir acción | Integración |
| A14 | SQLite ocupado/no escribible | Fallo manejado, sin envío si no hubo reserva | Unit + integración |
| A15 | JSON sobredimensionado/NaN/config null | Error estable sin traceback ni exceso de captura | Unit |
| A16 | Rutas con espacios/cwd distinto | Binario encuentra recursos y datos | Windows |
| A17 | Dos peticiones misma conversación | Segunda BUSY; no se mezclan respuestas | Integración |
| A18 | Solicitud sensible/local_only | Solo destino autorizado o bloqueo; nada a otro | Unit + integración |
| A19 | Mismo operation_id ya ejecutado | Devolver resultado guardado, no repetir efecto | Ejecutador local si existe |
| A20 | Claves/logs/frontend | Ninguna exposición del secreto de prueba | Inspección + test |
| A21 | Flag off / rollback | Vuelve ruta previa sin borrar historial/DB | Integración |
| A22 | Cuenta/modelo real | Smoke live separado en A y B | Live |
| A23 | UI y módulos | Radial, atajos, Dictar, grabar, música y persistencia conservados | Windows/manual |
| A24 | Cuota compartida | Dos entradas misma cuenta bloqueadas en incremento 1 | Integración |

## Cómo provocar fallos sin consumir cuotas

Usar transporte inyectado del router en tests, o un modo de fallo de desarrollo aislado del artefacto release. Hacer que A produzca UpstreamError(429,retry_after=120) y B devuelva respuesta sintética. No llamar cientos de veces a un servicio para forzar límites. Registrar 'simulado' en la evidencia. Desactivar A prueba inelegibilidad, no un error HTTP real.

Probar herramientas con una función inocua que escriba un contador temporal bajo carpeta de tests; dos ejecuciones del mismo operation_id deben dejar contador=1. No usar enviar email, borrar archivos o hacer pagos como smoke test.

## Evidencia y privacidad

Cada test/regresión: ID, versión del código, comando, exit, resultado, hora UTC, plataforma y fichero de salida. Live: proveedor/modelo real, capacidad, status, fecha y metadatos sanitizados. No conservar Authorization, claves, prompts privados o contenido de pantalla personal. Si se necesitan capturas de UI para QA, usarlas localmente y no publicarlas sin autorización.

Métricas de referencia por medir en equipo destino: coste de arranque del worker, RSS del módulo, latencia por intento, duración de cancelación y carga con 2 conversaciones. No fijar un número de rendimiento como si estuviera medido. La aceptación funcional de deadline es 70 s máximo de espera del host; el cierre de recursos tiene presupuesto de limpieza separado de hasta 5 s y debe medirse.

## Informe final del ejecutor

DELIVERY_STATUS debe separar: DOCUMENTADO, IMPLEMENTADO, PROBADO_OFFLINE, PROBADO_LIVE, PROBADO_WINDOWS. Incluir fallos previos, fallos nuevos, pruebas no ejecutadas, bloqueos y artefactos. Para marcar un hallazgo cerrado, citar el test que lo cubre; una captura de terminal verde no sustituye las salidas completas.
