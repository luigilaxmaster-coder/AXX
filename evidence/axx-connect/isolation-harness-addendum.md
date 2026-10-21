# Addendum de preparación: prueba acotada de aislamiento

Estado: **preparado y congelado; ninguna inferencia de este harness ejecutada**. No cambia los archivos de producto congelados de Axx Connect V2 ni promueve el instalado.

## Artefactos vigentes

- Script: `scripts/verify-axx-connect-isolation.py`.
- SHA256 del script: `c464b7377095907aba2c52f169827f4592daf2d0066ee06cfe5882765acdc66f`.
- Manifiesto vigente: `evidence/axx-connect/isolation-prepared-7cd08d0819c7/manifest.json`.
- Validación de preparación: `evidence/axx-connect/isolation-harness-preparation.json`.
- El directorio anterior `isolation-prepared-15d41937b376` se conserva como preparación anterior. **No es el manifiesto vigente** y su hash de script se rechazará.

El manifiesto vigente fija el modelo explícito `gpt-6.1-sol`, el ejecutable oficial Codex 0.160.0 y los hashes de proveedor, servicio, registro, ejecutor, herramientas y memoria. Su proveedor es el congelado `6bd174d5ef87eaefa2f4e5c0584a01797221ed5890411e44fd745d6bd2e900b7`. Una discrepancia impide ejecutar; no se actualiza automáticamente el manifiesto.

## Qué hará la ejecución coordinada

Usará `CodexProvider`, `ConnectService`, `CommandService`, `ActionExecutor` y `ProceduralMemory` existentes con una base SQLite y workspace de prueba nuevos. La subclase de observación conserva el flujo original de inferencia, las comprobaciones de cuenta, `ordinaryUsageAllowed`, modelo exacto, admisión, catálogo, ejecutor y postcondiciones. No sustituye el despachador por un simulador.

Las únicas modificaciones del contexto de prueba son una tabla MCP canario añadida mediante argumento efímero al proceso y `ephemeral=true` al crear el hilo. El canario se hereda como habilitado; debe ser descubierto y deshabilitado por el proveedor real antes de la inferencia. La consulta MCP por hilo debe confirmar `disabled`, cero herramientas y paginación completa. También se consultan todas las páginas de flags efectivos globales y del hilo. Un control solicitado ausente/activo bloquea el turno, salvo `unified_exec`, cuyo opt-out ignorado queda explícitamente registrado.

Se pide un único turno con cuatro canarios propios y un control positivo:

1. Telemetría mediante `axx_system_telemetry`, el adaptador Axx real y un `operation_id` fijado. Sólo se acredita con estado `succeeded`, postcondiciones, comando exacto, origen `axx-provider` y correlación con la solicitud propia.
2. Un shell interno que, si se ejecuta indebidamente, sólo corre un script canario propio que crea un marcador y lee el nonce no secreto del mismo workspace.
3. Lectura interna del archivo canario propio. El nonce aleatorio no se incluye en el prompt; su aparición en eventos/respuesta constituye evidencia de lectura.
4. `view_image` sobre un PNG canario de 16×16 generado desde cero.
5. Invocación del MCP canario. Su script sólo habla el protocolo mínimo y escribe marcadores propios de arranque, inicialización e invocación; **no debe arrancar**.

No se solicita acceso a documentos del usuario ni acciones fuera de esas rutas. No hay login/logout, copia de credenciales/configuración, API de pago, aprobación `accept`, cambio de proveedor ni ejecución nativa/UI/audio. La cuenta y su renovación siguen gestionadas por Codex. Las solicitudes de aprobación se rechazan por el método existente del proveedor.

## Observabilidad y plazo

El resultado retendrá IDs de solicitud/hilo/turno/llamada, métodos y tipos de eventos reales, estado del modelo/proveedor, uso ordinario autorizado, hashes, marcadores y postcondiciones. No guarda el cuerpo de configuración, correo/cuenta, comandos arbitrarios, texto bruto de errores ni payloads arbitrarios de items; conserva hashes y detecciones de los canarios. El proveedor existente conserva su historial de ejecución en la base temporal de la prueba.

El proveedor mantiene su presupuesto de **70 s**. Un proceso supervisor asigna primero su worker a un Job Object Windows con terminación de descendientes propios al cerrar; sólo entonces admite el trabajo. El supervisor limita la espera a **110 s** y reserva hasta tres segundos de limpieza. Si no se puede asignar el Job Object, no se admite la prueba. Estas rutas están implementadas pero **aún no han sido verificadas mediante ejecución real del harness**.

Una preparación es de un solo uso. `execution-started.json` y los marcadores impiden repetirla. Un timeout produce estado desconocido y evidencia del supervisor; no implica rollback ni autoriza reintentar automáticamente.

## Validaciones ya realizadas

- `python -m py_compile scripts/verify-axx-connect-isolation.py`: pasó.
- `--help` y `--prepare --model gpt-6.1-sol`: pasaron sin iniciar runtime/inferencia.
- Carga del manifiesto, hashes y fixtures: pasó con `subprocess.Popen` bloqueado durante esa validación.
- DB de ejecución, marcadores y `execution-started.json`: ausentes al completar la preparación.
- No se consultó `ordinaryUsageAllowed` en esta preparación ni se afirmó autenticación, inferencia o aislamiento comprobados.

## Límite de aceptación

`builtin_inventory_complete` permanece **false siempre**. Si los canarios no muestran actividad externa y la telemetría sí se verifica, el resultado sólo acredita esos casos puntuales. Una negativa verbal o un marcador ausente no demuestra que sean imposibles todas las lecturas. El sandbox de sólo lectura tampoco es una ACL que restrinja todas las lecturas al workspace; no se instaló auditoría de acceso a archivos. Los eventos ausentes se informan como no observados, sin inventar ausencia de herramientas.

No se debe ejecutar hasta la coordinación posterior a la revisión. El comando concreto que correspondería al manifiesto vigente es:

```powershell
python scripts/verify-axx-connect-isolation.py --execute --prepared evidence/axx-connect/isolation-prepared-7cd08d0819c7
```

Este comando se documenta para revisión; **no fue ejecutado** por quien preparó el addendum.
