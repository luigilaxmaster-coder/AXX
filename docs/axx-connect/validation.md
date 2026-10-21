# Validación y límites de la entrega

Fecha local: 20 de octubre de 2026. Entorno real: Windows 11 Home 26200, Acer Spin SP314-55N, i7-1255U, 16 GB RAM, Iris Xe. Python 3.12.10, Node 24.14.1, Cargo 1.96.0. App Server fijado a Codex CLI 0.160.0; SDK MCP 1.30.0; plugin privado 0.1.2.

## Evidencia real

- `evidence/axx-connect/provider-inference-live.json`: cuenta ChatGPT gestionada, inferencia en gpt-6.1-sol, streaming, ejecutor de telemetría y respuesta final. No se leyeron archivos de autenticación ni se copiaron tokens.
- `http-provider-live.json`: HTTP autenticado real, herramienta y evidencia, rechazo sin bearer y reintento del turno sin duplicación.
- `provider-final-live.json`: traducción adversarial sin herramientas, interrupción real y reanudación del mismo hilo. Las huellas indican la revisión exacta probada.
- `provider-latest-live.json`: petición real pequeña después de los primeros controles de cuenta, coste, modelo y pertenencia de acciones. Precede a la revisión 2 de desconexión local, presupuesto total, admisión sincronizada y transporte acotado. No certifica esas fuentes nuevas ni el binario combinado.
- `live-integration-result.json` y el directorio `live-a1be182234`: cliente Codex CLI real → plugin instalado → servidor MCP → ejecutor Axx real → telemetría con postcondiciones → respuesta `AXX_CONNECT_HOST_OK`. Datos de prueba aislados; no equivale a controlar la UI instalada 0.22.0.
- `installed-plugin-host-diagnostic.json`: host real descubre siete herramientas sin inferencia y sin errores de herramientas.
- `provider-readonly-v2-result.json`: proveedor final SHA256 `6bd174d5…2e900b7` inicia el proceso oficial 0.160.0, lee siete modelos y una cuenta autenticada, y cierra sólo su hijo. No envió turn/start ni RPC de login/logout; `inference_verified:false`. Demuestra transporte real de esa revisión, sin atribuirle inferencia ni aislamiento completo.
- `runtime-inventory-readonly-result.json`, `-hardened-result.json` y `-extended-result.json`: procesos reales aislados sin credenciales ni inferencia. Inventario MCP por hilo con canario deshabilitado; 18 opt-outs efectivos desactivados globalmente y por hilo. `unified_exec=false` es ignorado por 0.160.0 y no se usa como frontera. El protocolo no proporciona inventario integral de herramientas internas. Alcance y reproducción en `runtime-inventory-investigation.md`.
- Pruebas de servicio: archivos reales con SHA256, SQLite, reinicios, recetas verificadas, aprobación y pertenencia de cancelaciones. No sustituyen pruebas físicas de micrófono/pantalla/altavoces.

## Criterios de aceptación

| Criterio | Resultado y alcance |
|---|---|
| 1. MCP inicia y descubre | Real: SDK y host Codex instalado. |
| 2. Entradas incorrectas | Validadores, HTTP privado y MCP: aprobados. |
| 3. Comandos representativos | Ejecutor real: telemetría, procesos, archivo/SHA256; UI mediante contrato controlado. |
| 4. Inferencia autenticada | Real, modelo exacto gpt-6.1-sol, sin API de pago alternativa. |
| 5. Streaming/finalización/error | Streaming real; errores/límites también cubiertos por controles offline. |
| 6. Herramienta desde Axx | UI completa con IPC controlado y puente HTTP real en pruebas separadas. Falta aceptación nativa combinada. |
| 7. Llamada desde plugin | Real en Codex CLI y ejecutor fuente aislado. ChatGPT web/nube pendiente. |
| 8. Cancelación | Interrupción real App Server; carreras de acciones/efectos consumados con controles deterministas. |
| 9. Dependencia ausente | UI ausente en servidor real y handler ausente en navegador controlado; no falso conectado. |
| 10. Revocación/expiración | Casos controlados, sin revocar la cuenta real del usuario para probarlos. |
| 11. Límite/coste | Uso incluido real informado; límites/permiso ausente comprobados offline. UNKNOWN de coste bloquea el turno. |
| 12. Reinicio | SQLite y UI recargada controlados; hilo oficial reanudado realmente. Reinicio nativo instalado pendiente. |
| 13. Sin efectos duplicados | Reintento MCP real, IDs estables, archivos reales y rechazo de colisiones. |
| 14. Sin recursión | Registro cerrado, origen/profundidad, callbacks y pruebas de rechazo. No se llama al planificador desde MCP. |
| 15. Procedimiento | Receta promovida sólo desde evidencia, persistida y reutilizada con versión/entorno/permisos revalidados. |
| 16. No regresión | 44 pruebas previas por módulos; UI completa, identidad, paneles y dictado sin envío mediante contrato. Hotkeys y aceptación visual nativa pendientes del stage combinado. |

## Resultados controlados

Los logs iniciales `provider-unit-tests.txt`, `core-tests.log`, `mcp-tests.log`, `http-isolation-tests.log`, `ui-connect-tests.log` y `frontend-regression.log` conservan sus resultados históricos y alcance. La revisión 2 agrega `provider-revision-e-tests.txt` (66 offline aprobadas, 1 real opt-in omitida), `ui-connect-tests-revision2-final.log` (28 comprobaciones), `core-revision2-final.log` (21 pruebas), `http-revision2-final.log` (2), `mcp-revision2-final.log` (1) y `frontend-revision2-final.log` (18). Son 136 pruebas/comprobaciones aprobadas y una omitida; las categorías no se presentan como 136 pruebas físicas. Revisiones C/D preceden al transporte/admisión definitivos.

`provider-revision-e-pre-fix-tests.txt` conserva una ejecución anterior con fallo de clasificación BUSY frente a DEADLINE_EXCEEDED al esperar un bloqueo. La corrección y los casos adicionales pasaron en la ejecución final de 67 tests; no se borró el intento fallido.

La UI comprueba selección explícita sin sustitución de modelo, badge vinculado al modelo exacto, desconexión local, Esc sin cancelar tareas, Detener/AbortSignal con ID propio, ACK/consultas colgados, cancelación de confirmaciones tardías y conservación de texto parcial. Las pruebas del plazo UI aceleran exclusivamente sus timers largos; no son una medición física de 75 segundos. Servicio y HTTP usan SQLite, archivos y ejecutor reales con límites del proveedor controlados.

Las pruebas de navegador usan el HTML completo y handlers reales con IPC controlado; no certifican WebView2 instalado ni hardware. La captura `ui-connect-settings-controlled-revision2.png` muestra esa UI con motor desconectado y tiene metadata explícita; no se generó un vídeo simulado.

Una ejecución combinada previa de la regresión Python terminó en access violation (`-1073741819`) mientras se ejecutaban pruebas simultáneas; se conservó `backend-regression.log`. La causa no se atribuye sin evidencia. Las cinco suites se ejecutaron después en procesos separados con faulthandler: 44 pruebas, todos los códigos de salida 0, en `backend-regression-isolated.json` y `*.final.log`.

## Puertas pendientes

1. Integrar por hunks con `build/phased-ux-20261020`, compilar e instalar la versión combinada y observar UI/atajos/voz/pantalla reales. Otro chat autorizado mantiene esa instalación; esta entrega no la sustituyó ni reinició. Su variante C3 separa `axx-ui-escape` del Cancelar explícito `axx-cancel`; conservar esa separación y los dueños de cada herramienta al combinar HTML/Rust. La raíz conserva Rust anterior y no acredita por sí sola la nueva semántica nativa.
2. App Server y herramientas dinámicas son experimentales. La consulta de inventario MCP del proveedor agotó su plazo: `runtime_inventory_verified:false`. Configuración restrictiva y callbacks cerrados no se anuncian como demostración de un inventario vacío ni como confinamiento de todas las herramientas internas. La inferencia/dev y el control del ejecutor no cierran esta puerta. Activar acciones en la instalación combinada requiere evidencia efectiva de aislamiento adicional.
3. ChatGPT web requiere un túnel/endpoint autorizado con identidad, credencial runtime y asociación workspace; no se acreditaron esos recursos ni se abrió un servidor público.
4. Once superficies implementadas aún exigen selector, permiso, verificador o separación adicional. El inventario generado `capabilities.json` las conserva con causa concreta. Los 7.562 registros documentales siguen sin adaptador y no se habilitan automáticamente.

Los modelos de prueba no son un indicador de producción. Las tablas adicionales de Connect, el paquete privado y sus pruebas son revisables; la aceptación de la aplicación instalada sigue separada.
