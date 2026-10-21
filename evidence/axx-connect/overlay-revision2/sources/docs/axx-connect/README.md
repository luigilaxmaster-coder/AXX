# Axx Connect

Integración privada local para el Axx existente. Conserva el personaje 3D, distribución radial, paneles, persistencia y módulos originales. No instala un modelo generativo local ni convierte una sesión Codex en servicio para terceros.

## Estado de entrega

La implementación y las pruebas de fuentes se distinguen de la versión nativa instalada. No actualizar ni reiniciar una aplicación que esté siendo trabajada desde otro chat. El paquete de plugin se instaló con el CLI oficial 0.160.0 como `axx-connect@axx-local`; la instalación no prueba una llamada desde el cliente ni una operación física. El ejecutable Axx debe contener esta versión del backend antes de poder servir las herramientas.

Se observó inferencia real mediante el proveedor Codex con `gpt-6.1-sol`, streaming, herramienta `axx.system.telemetry`, resultado local verificado y respuesta final: [evidencia de inferencia](../../evidence/axx-connect/provider-inference-live.json). Esa prueba usa el proveedor de fuentes, no constituye aceptación visual del Axx instalado.

La línea base está en [inventario previo](../../evidence/axx-connect/inventory-baseline.md). Los resultados actuales deben consultarse en los archivos de `evidence/axx-connect`; la presencia de un archivo de configuración no es una prueba de conexión.

## Inicio y uso

1. Inicia la versión de Axx que incluya Connect. Abre Conectar IA y el panel Axx Connect.
2. Consulta estado del motor y ejecutor por separado. Si Codex necesita autenticación, usa el flujo oficial que abre el runtime. Axx no recibe ni copia sus tokens.
3. Selecciona explícitamente un modelo del catálogo y pulsa Verificar conexión. Seleccionar no inicia inferencia; un modelo vacío o ausente detiene la prueba sin cambiar la preferencia guardada. El catálogo no acredita acceso. Escribe una orden pequeña en la barra principal; el texto dictado permanece separado de su envío.
4. Desde un host local compatible, activa Axx Connect y solicita primero estado/capacidades. Usa un ID de operación estable para cada acción y consulta su evidencia.
5. Pulsa Detener para solicitar cancelar la tarea activa. Esc sólo cierra la interfaz o detiene el seguimiento; la tarea continúa. Los cambios ya consumados no se revierten automáticamente.

Operación MCP: `axx_status` → `axx_list_capabilities` → `axx_execute_action` → `axx_get_task`. `axx_cancel_task` pide detener la operación identificada. Las escrituras conservan las aprobaciones existentes de Axx.

Las consultas concretas de sistema/PID ofrecen además `axx_system_telemetry` y `axx_process_inspect`, aliases de lectura generados del mismo registro. Su metadata describe sus efectos reales y conserva la misma idempotencia; no se cambia la política de aprobación del host.

## Instalación fuente

Desde la raíz del proyecto en PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-axx-connect.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/diagnose-axx-connect.ps1
```

Requisitos: Windows, Python 3.11+ y Codex oficial con comandos de plugins. El script crea/reutiliza `.venv-axx-connect`, instala `mcp==1.30.0` desde `requirements-axx-connect.txt`, registra el marketplace del proyecto y conserva el resto de plugins. Si hay varias instalaciones Codex, indica `-CodexExecutable` con la ruta de la instalación examinada; el proveedor de Axx exige 0.160.0. No actualiza Codex ni cambia planes automáticamente.

Diagnóstico de proceso MCP real, con una consulta de estado autenticada y una operación local de lectura opcional:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/diagnose-axx-connect.ps1 -Probe -ExecuteTelemetry
```

El flag `-Probe` necesita que Axx Connect esté sirviendo en la instancia de Axx. No cambia identidad, música, micrófono, pantalla ni archivos del usuario. La telemetría escribe únicamente el historial local de la operación.

Para inspeccionar el plugin instalado sin inferencia: `.venv-axx-connect/Scripts/python.exe scripts/diagnose-axx-plugin-host.py`. Consulta App Server `mcpServerStatus/list` con plazo de 45 segundos, sin crear turno de modelo y sin reescribir configuración. En una prueba aislada, `--data-dir` selecciona una instancia de prueba mediante la variable permitida por el manifest Codex.

## Instalación empaquetada

El backend empaquetado debe aceptar `--mcp-server`; el instalador comprueba su `--help` antes de seleccionarlo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-axx-connect.ps1 -RuntimeMode Packaged
```

El runtime de release usa el backend de Axx y no requiere otro Python. `scripts/build-axx-connect.ps1` prepara un entorno de compilación con las dependencias nativas existentes y el SDK MCP fijado, y llama al script original `build-windows.ps1` con ese Python. Compilar/instalar y verificar esa release es una puerta independiente de tener fuentes correctas. Esta entrega no recompiló ni sustituyó la instalación nativa administrada por el otro chat.

## Actualizar, detener y quitar

- Actualizar fuente: conserva las fuentes, ejecuta pruebas y repite el instalador con el mismo marketplace. Si cambia el plugin incrementa su versión en ambos manifiestos antes de reinstalar; no edites el cache de Codex.
- Empaquetar ZIP privado: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/package-axx-connect.ps1`. Incluye manifiestos ocultos y verifica referencias/hashes. El ZIP no incluye Python, credenciales ni un ejecutor paralelo.
- Detener: el botón solicita cancelar la ejecución identificada; Esc sólo afecta a interfaz/seguimiento. Salir de Axx cierra su runtime propio. Cerrar el proceso MCP del plugin no implica revertir tareas previamente despachadas.
- Quitar plugin: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/uninstall-axx-connect.ps1`. `-RemoveMarketplace` quita además sólo `axx-local`. Conserva datos, recetas, archivos y login Codex. No borra ni desinstala Axx.

**Desconectar Axx** conserva la sesión compartida de Codex y bloquea localmente nuevos turnos hasta una reconexión explícita. Reconectar no selecciona un modelo ni inicia inferencia automáticamente.

Repetir el instalador con la misma versión y los mismos componentes reutiliza la instalación activa. Un contenido distinto bajo la misma versión se rechaza con diagnóstico: incrementa versión y reinstala en una ventana de mantenimiento. La instalación no sobrescribe un cache en uso.

## Documentos

- [Arquitectura y fronteras](architecture.md).
- [Autenticación, suscripción y acceso desde web](authentication.md).
- [Recuperación y rollback](recovery.md).
- [Capacidades y pendientes](capabilities.md).
- [Validación y puertas pendientes](validation.md).
