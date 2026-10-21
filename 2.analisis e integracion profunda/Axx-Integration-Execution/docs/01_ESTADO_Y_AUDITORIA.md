# 01 — Estado técnico y auditoría del baseline

## Evidencia inspeccionada

Se materializó la versión persistente 1 de `Axx-API-Router.zip`, se leyó `router.py` y se ejecutó de nuevo su suite de 20 pruebas el 2026-10-19. El código incluido en `baseline` se conserva sin modificaciones en esta entrega. La evidencia completa está en `evidence/baseline-tests.txt`.

Se consultó GitHub mediante el conector para fijar `free-llm-api-hub` al commit `90e4f43865e7fd1724c5f74227ba106ae01122cd`. Ese catálogo y su MCP son fuentes de descubrimiento; no forman parte del runtime del baseline. Véase 12.

## Lo que ya hace el baseline

Selección por prioridad del array, categoría y capacidades declaradas; consulta de variables de entorno; envío de chat JSON por HTTPS; failover secuencial; pausas persistidas en SQLite; límite diario de intentos por nombre; métricas acumuladas; restricciones por etiqueta sensible; límite de salida y de bytes serializados; CLI de chat, estado y reset de pausa. No necesita paquetes Python externos. Solo transporta respuestas completas, `stream=false`.

## Correcciones obligatorias antes de distribuir la integración

| ID | Hallazgo en el código | Riesgo práctico | Corrección y prueba requerida |
|---|---|---|---|
| H01 | El timeout de urllib es de socket, no un deadline total; el CLI lee stdin entero antes de validar tamaño | Proceso bloqueado por respuesta lenta o consumo excesivo al leer entrada | Adaptador con deadline de pared, captura limitada y cancelación; stdin limitado a tope+1 antes de parsear; probar fuente lenta y JSON sobredimensionado |
| H02 | Validación incompleta de tipos, mensajes, roles, valores finitos y respuestas | Tracebacks, NaN, respuesta vacía aceptada, tool_calls malformados | Validador estricto de config/request/response; errores JSON estables; pruebas de null, listas inesperadas, NaN/Infinity y truncamiento |
| H03 | `Retry-After` puede aceptar valores no finitos; fecha sin zona puede generar error | Pausas imposibles o fallo de status() | Aceptar números finitos o fecha consciente de zona; inválidos a 0; saturar pausa a 24 h; prueba inf/NaN/fecha inválida |
| H04 | Cada nombre de entrada tiene cuota y pausa independientes | Dos modelos de la misma cuenta pueden seguir golpeando un límite compartido | Primer release: una entrada por cuenta; incremento 2 añade quota_scope_id en 10. No afirmar cuotas independientes por modelo |
| H05 | Solo se comprueba que message sea un objeto | Una respuesta sin contenido ni herramienta válida cuenta como éxito | Validar assistant, texto o tool_calls válidos; rechazar elecciones vacías y finish_reason=length incompleto para acciones |
| H06 | Config sin enabled se considera activada, y las capabilities son declaraciones | Se activa una fila incompleta o mal verificada | En configuración de despliegue exigir enabled explícito; bloquear IDs de plantilla y capabilities sin evidencia vigente |
| H07 | Todas las cabeceras 403 se interpretan como pausa de credenciales; no se distinguen moderación, región o permisos | Reenvío a otros destinos de una solicitud que debería detenerse | Documentar clasificación conservadora; adaptador de proveedor por implementar. 403 desconocido: detener en el release endurecido. Mantener 401/402 como failover configurable sin pagos |
| H08 | No hay cancelación, correlación, empaquetado ni puente con Axx | Axx puede mostrar respuestas atrasadas o dejar procesos huérfanos | Worker cancelable, request_id, ignorar resultados después de cancelación, prueba en binario Windows |
| H09 | Estado 'ready' es solo local y métricas no tienen fecha/modelo/config | Puede aparentar salud remota y mezclar mediciones | UI 'elegible localmente'; mantener nombre estable por modelo/config o versionarlo; no mostrar saldo remoto inventado |
| H10 | Errores del transporte inyectado fuera de UpstreamError y fallos de SQLite no tienen una política integral | Finalización brusca o reenvío duplicado | Normalización de errores en frontera, fail closed si reserva SQLite falla, no reenviar tras efecto externo desconocido |

Los 20 tests cubren el contrato local básico, no estas diez áreas de endurecimiento completas. La documentación previa llamó al paquete 'sistema creado'; eso significa baseline local, no release listo para instalar en Axx.

## Lo que no existe todavía

Adaptador al backend real de Axx; eventos de progreso por intento; almacenamiento nativo de secretos; detección automática de datos sensibles; prueba remota de capacidades; cuota remota por cuenta; memoria procedural; cola; streaming; servidor HTTP; STT/TTS; ejecutor Windows; instalación en el Acer. No añadir etiquetas DONE por haber escrito una especificación.

## Orden de resolución

H01, H02, H03, H05, H06, H07 y H10: endurecimiento del router/adaptador, antes del chat live. H08: integración y empaquetado, antes de release. H04: restricción inicial a una entrada por cuenta y arquitectura preparada para incremento 2. H09: copy de UI y nombres de configuración en incremento 1. Cada hallazgo se cierra con un test/evidencia concreto.
