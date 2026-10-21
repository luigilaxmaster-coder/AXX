# Estado de entrega: Axx Connect V2 + UI V2.1

Fecha: 20 de octubre de 2026. **Fuentes implementadas y verificadas; activación de la instalación combinada pendiente.** No se declara aceptación Windows completa.

## Implementación y alcance comprobado

- Proveedor Codex App Server 0.160.0, autenticación ChatGPT gestionada por el runtime oficial, modelo exacto, uso incluido exigido y sin fallback a API de pago u Ollama. Axx no copia las credenciales de Codex.
- Puente MCP con SDK 1.30.0 y plugin privado instalado `axx-connect@axx-local` 0.1.2. Usa el mismo CommandService/ActionExecutor mediante el backend privado existente; no inicia un segundo ejecutor para aparentar conexión.
- Registro compartido, tareas durables/idempotentes, permisos existentes, resultados con postcondiciones, reanudación y procedimientos verificados. El inventario de capacidades distingue adaptadores conectados, superficies bloqueadas y catálogo documental sin ejecutor.
- UI incorporada al Axx existente. Modelo seleccionado explícitamente, autenticación e inferencia separadas, desconexión sólo local persistida, botón Detener y estado del ejecutor independiente. Esc sólo afecta interfaz/seguimiento; no cancela tareas. La variante nativa C3 del integrador separa sus eventos y conserva cancelación explícita por dueño.
- Presupuesto de ejecución de 70 segundos; UI con plazo monotónico de 75 segundos desde el envío y rechazo de respuestas tardías. Admisión sincronizada con la cuenta y transporte acotado. Los efectos ya consumados no se anuncian como revertidos.

Desde Axx, la interfaz completa y sus handlers se comprobaron mediante navegador/IPC controlado; esto no certifica WebView2 instalado, voz física ni captura real. Desde Codex se comprobó previamente una llamada real plugin→MCP→ejecutor→respuesta; sus hashes son anteriores a la revisión final del proveedor.

La revisión final del proveedor `6bd174d5…2e900b7` sí inició el proceso oficial, leyó una sesión autenticada y siete modelos, y cerró sólo su hijo. Esa comprobación no envió turn/start ni login/logout: `inference_verified:false`. Las pruebas reales anteriores de inferencia, streaming, telemetría, traducción e interrupción permanecen como evidencia de sus revisiones exactas.

## Pruebas actuales

| Suite | Resultado | Evidencia |
|---|---:|---|
| Proveedor final E | 66 aprobadas; 1 real opt-in omitida | provider-revision-e-tests.txt/result.json |
| Servicio y ejecutor | 21 aprobadas | core-revision2-final.log/result.json |
| HTTP privado | 2 aprobadas | http-revision2-final.log |
| MCP stdio real | 1 aprobada | mcp-revision2-final.log |
| UI V2.1 | 33 comprobaciones; 0 excepciones | ui-connect-tests-revision21.log |
| Regresión frontend final | 18 comprobaciones; 0 excepciones | frontend-revision21-final.log |

Total: **141 pruebas/comprobaciones aprobadas y una omitida**. No se presentan como 141 pruebas físicas. La captura `ui-connect-settings-controlled-revision21.png` tiene metadata con los hashes de HTML, producto y tests; muestra motor desconectado. El HTML probado conserva versión fuente 0.20.0, 24 formas y 9 paletas.

Los fallos anteriores se conservaron: ejecución combinada Python con access violation, seguida de 44 pruebas previas aprobadas en procesos aislados; y el fallo de clasificación de timeout del proveedor corregido antes de E. Consulte validation.md para el alcance histórico.

## Entregas inmutables para integración

1. `axx-connect-source-review-v2.zip`: 47 archivos, fuentes y recibos, parche incremental V1→V2 reconstruido/verificado. SHA256 `50a801e89eb319fc1b6ac43080c19a026f345d4b2060dc24567802ca6971e964`.
2. `axx-connect-ui-review-v21.zip`: sólo JS Connect y su prueba, aplicable después de V2. SHA256 `2f89088e9f9a7c0763a5f5cc2ab5e1f17b93d0b6afd328770095aa914db6c970`.
3. Plugin instalable independiente: `dist/axx-connect-0.1.2.zip`, SHA256 `47b46d7c327ec5004ab1db047975dc97f093db8d8b45b9e9e4f36546c43c11a5`.

Fuentes finales: proveedor `6bd174d5ef87eaefa2f4e5c0584a01797221ed5890411e44fd745d6bd2e900b7`; servicio `c2a8af7f5be9a68c262d23766f18f9e728ffd0d6d4e2cd65317b478d4bc2eb6d`; JS `0ab6ecda5db22ea7f8160c5f5beb92e5849a402c8fb1c4b7cb5b5f7a230fe6c3`.

El chat autorizado «Verifica AXX por fases» recibió ambos paquetes y mantiene la propiedad de C3/Rust, mezcla por hunks, compilación, instalación y aceptación nativa. Este chat no sustituyó ni reinició esa instalación. Los paquetes son revisión de fuentes; no son un instalador nativo nuevo.

## Puertas abiertas y causa exacta

1. **Aislamiento integral del runtime.** App Server y dynamicTools son experimentales. El esquema 0.160.0 no expone inventario completo de herramientas internas. Diagnósticos reales por hilo verificaron 18 restricciones de features desactivadas y un MCP canario deshabilitado; `unified_exec=false` se ignora y no se usa como frontera. Esto no demuestra una lista exclusiva de herramientas Axx ni impide formalmente toda lectura externa. `builtin_inventory_complete:false` permanece explícito.
2. **Ensayo real de canarios.** `scripts/verify-axx-connect-isolation.py` y el manifiesto `isolation-prepared-7cd08d0819c7/manifest.json` están preparados, revisados estáticamente y sin ejecutar inferencia. El addendum documenta un único turno con canarios propios y telemetría real, cuenta gestionada sin copiar auth/config, presupuesto 70/110 s, sin accept ni compras. La ejecución se dejó pendiente de coordinación; sus controles de proceso todavía no se presentan como probados en runtime.
3. **Versión nativa combinada.** Falta aceptación de la integración instalada con atajos, dueños de tareas, UI, micrófono, pantalla y altavoces reales. Sus fuentes C3 contienen cambios propios que no deben sobrescribirse copiando HTML/Rust completos.
4. **ChatGPT web/nube.** No se acreditaron túnel, credencial runtime ni asociación de workspace. Instalar el plugin local Codex no registra automáticamente el equipo en ChatGPT web. La elegibilidad SIWC privada tampoco se presume a partir de la suscripción.

## Inicio, actualización, detener y quitar

Después de disponer de una release Axx compatible y validada, iniciar Axx y abrir Conectar IA→Axx Connect; seleccionar explícitamente modelo y pulsar Verificar conexión. No lanzar otro backend sobre datos alternativos para simular que el instalado es compatible.

Desde la raíz del proyecto, el flujo fuente usa:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-axx-connect.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/diagnose-axx-connect.ps1
```

Actualizar: verificar cambios y repetir el instalador con el mismo marketplace. Si cambia el contenido del plugin, incrementar su versión antes de reinstalar; no editar el cache del host. Para backend empaquetado, usar el modo Packaged sólo cuando su --help incluya --mcp-server. La compilación se delega al procedimiento existente mediante build-axx-connect.ps1; no se ejecutó aquí.

Detener solicita cancelar la tarea identificada; Esc sólo cierra UI/seguimiento. Desconectar Axx conserva las credenciales compartidas y bloquea nuevas inferencias hasta reconexión explícita.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall-axx-connect.ps1
```

Desinstalar el plugin conserva Axx, archivos, recetas y sesión Codex. El rollback acotado está en docs/axx-connect/recovery.md; no restaurar todo el árbol ni una base de estado anterior sobre trabajo posterior.
