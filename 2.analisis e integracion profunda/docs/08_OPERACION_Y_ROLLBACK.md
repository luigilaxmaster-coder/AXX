# 08 — Operación, diagnóstico y rollback

## Arranque normal

Cargar configuración aprobada, validar versión/esquema, resolver directorio y secretos, abrir estado y consultar elegibilidad. No llamar APIs para 'saludar' ni hacer probes en cada arranque. Estado local debe funcionar aunque no haya internet. Empezar con router flag off hasta terminar pruebas de integración; activación solo en configuración local autorizada.

Mantener logs estructurados con fecha, request_id, etapa, nombre lógico de proveedor, intento, duración, status/error y versión de configuración. El baseline solo tiene logs de texto y métricas agregadas: la correlación es trabajo del adaptador. No grabar mensajes, respuestas completas, tool arguments, ruta de documentos personales ni claves. Rotación propuesta: 5 ficheros de 1 MiB y 7 días como máximo, adoptando límites más estrictos del proyecto si los hay.

## Diagnóstico

| Síntoma | Interpretación | Acción |
|---|---|---|
| missing_key | Backend no ve la variable o almacén | Corregir en proceso padre; reiniciar solo backend necesario |
| disabled/free_not_confirmed | Entrada no aprobada | Revisar validación y tier, no activar a ciegas |
| cooldown | Pausa local pendiente | Esperar o corregir causa; reset no restaura cuota remota |
| local_quota_exhausted | Contador local por día UTC alcanzado | Esperar cambio UTC o ajustar política justificada; no borrar DB |
| ready pero llamada falla | Elegibilidad no equivale a salud | Comprobar status oficial, endpoint, modelo y consola |
| INVALID_REQUEST | Cuerpo/formato incompatible | Corregir entrada; no rotar proveedores |
| STATE_UNAVAILABLE | Reserva/DB falla | Detener envío, comprobar ruta/permisos/lock |
| DEADLINE_EXCEEDED | Host agotó tiempo de pared | Terminar worker; mostrar reintento manual, no asumir acción deshecha |
| NO_PROVIDER_AVAILABLE | Ninguna fila pudo completar | Mostrar causa local disponible; no inventar saldo de cuenta |

El baseline permite `python router.py --config <config> --state <db> --status` y `--reset-cooldown <name>`. Ejecutar con argumentos separados desde host. No exponer reset a texto libre del modelo.

## Copia y migraciones

Antes de modificar schema, cerrar conexiones/worker o usar API SQLite backup sobre una conexión estable; no copiar solo el fichero .db mientras hay escritura/WAL activo. Guardar backup y hash en directorio privado, sin secretos adicionales. Registrar versión de esquema con migración idempotente; incremento 1 debe poder conservar tablas existentes.

No borrar usage para recuperar una conexión. Si migración falla: no enviar nuevas peticiones; restaurar versión compatible de código y snapshot, dejando el estado fallido aparte para diagnóstico. Nunca restaurar una copia antigua de cuotas para aparentar consumo menor. Tras rollback de DB, mantener un registro conservador de intentos posteriores al snapshot o bloquear hasta reconciliar.

## Rollback de integración

1. Cancelar solicitudes en vuelo y recoger procesos del router por handle.
2. Desactivar api_router_enabled en configuración del host; no editar credenciales ni historial.
3. Restaurar build/código previo desde el punto guardado de T0. Si no hay ruta previa de IA válida, mostrar IA no disponible; no habilitar otra de pago.
4. Conservar SQLite/configuración y logs sanitizados; no realizar downgrade destructivo de esquema.
5. Probar chat anterior o estado de indisponibilidad honesto, atajos, posición y módulos actuales.
6. Registrar causa, versión anterior/nueva, pruebas y si hubo efectos externos cuyo resultado falta reconciliar.

No utilizar git reset --hard sobre cambios ajenos ni desinstalar otros runtimes del usuario. Las claves comprometidas se revocan en el proveedor por un flujo explícito, no se copian a un backup de diagnóstico.

## Política de tareas y acciones

Una solicitud fallida no genera por defecto una tarea en segundo plano. El usuario recibe resultado o error. Si se implementa cola del documento 10, solo tareas expresamente diferibles. Reintentar texto remoto puede consumir cuota adicional; repetir acciones externas requiere idempotencia y verificación de estado real.

## Mantenimiento del catálogo

Revisión manual o automatización expresamente configurada por el usuario; este paquete no programa tareas. Nuevo snapshot se valida y compara, manteniendo versión anterior. Cambios de URLs, precios, términos o modelos no se aplican a runtime automáticamente. La configuración activa solo cambia después de pruebas de capacidad y revisión local.
