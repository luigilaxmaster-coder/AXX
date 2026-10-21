# Recuperación y rollback

## Error, límite o desconexión

1. Conserva request_id y operation_id; consulta historial/estado antes de reenviar una operación con efectos.
2. Distingue motor desconectado de ejecutor no disponible. Axx cerrado, descriptor ausente o UI sin heartbeat no se corrigen cambiando de modelo.
3. Reconecta el proveedor desde Axx. Si Codex solicita login, usa su flujo oficial. No introduzcas tokens en manifest, chat, consola visible o archivos de configuración.
4. Un resultado `unknown` tras timeout/reinicio requiere inspeccionar el efecto. El mismo ID no debe ejecutar otra vez; sólo prepara una nueva operación cuando se haya reconciliado.
5. Para un límite de uso, espera el restablecimiento indicado por el runtime. No se activa API de pago, recarga ni fallback local.

Detener y el AbortSignal de la solicitud propia solicitan interrumpir ese turno y cancelar sus acciones pendientes. Esc sólo cierra la interfaz o detiene el seguimiento: la tarea continúa. La cancelación conserva los efectos que alcanzaron a terminar; no elimina archivos creados ni restaura preferencias consumadas.

Cada ejecución dispone de un presupuesto global de 70 segundos desde su admisión, incluidos arranque, cuenta, cuota, modelo, hilo y turno. Las llamadas comparten el plazo restante. La UI consulta durante un máximo de 75 segundos y solicita cancelación con el mismo request_id al agotarlo. Un efecto no reconciliado permanece `unknown`, con el texto parcial conservado; no se repite automáticamente. La limpieza puede emplear hasta 3 segundos adicionales para solicitar interrupt.

Desconectar Axx persiste una exclusión local y cierra sólo su proceso propio. No revoca ni cierra la sesión compartida de Codex. Diagnóstico y nuevas solicitudes respetan ese estado después de reiniciar; Reconectar Axx o iniciar sesión son decisiones explícitas para reactivar la conexión.

## Runtime o instalación ausentes

Ejecuta `scripts/diagnose-axx-connect.ps1`; su salida nunca incluye bearer ni tokens. Si falta runtime fuente, repite `install-axx-connect.ps1`. Si el backend empaquetado no acepta `--mcp-server`, instala una release compatible mediante el procedimiento de entrega existente. No lances otra instancia con una base de estado alternativa para simular que el Axx instalado ya funciona.

La configuración bootstrap sin secretos está en `%LOCALAPPDATA%/Axx/connect/runtime.json`. El descriptor `endpoint.dpapi` es efímero, protegido por Windows y sólo lo publica la instancia activa. No lo copies a otro usuario/equipo.

## Rollback acotado

1. Detén las ejecuciones y consulta posibles efectos antes de cerrar el runtime propio.
2. Desinstala `axx-connect@axx-local` con el script; conserva los datos del usuario.
3. Si necesitas revertir fuentes, usa las copias de `evidence/axx-connect/baseline-*` y el inventario de archivos afectados. No restaures todo el árbol: puede contener trabajo ajeno simultáneo.
4. No sobrescribas `state.db` con un backup anterior sin decisión explícita: perderías tareas posteriores. Las tablas Connect son adicionales; pueden permanecer inactivas tras revertir el código.
5. El instalador guarda `runtime.json.before-install` al reemplazar bootstrap existente. Restaurarlo revierte sólo la selección del runtime; no cambia credenciales Codex ni recetas.

No hay repositorio Git inicializado en la raíz examinada. Por ello no se ofrecen comandos git reset/clean ni un commit ficticio como rollback.
