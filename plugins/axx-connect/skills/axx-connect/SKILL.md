---
name: axx-connect
description: "Usa Axx Connect cuando el usuario solicite consultar Axx o ejecutar sus herramientas y módulos existentes en su computadora Windows."
---

Usa las herramientas MCP de Axx Connect para operar el asistente existente.

1. Consulta `axx_status`. Distingue autenticación del modelo, servidor MCP y ejecutor local. Una configuración o una instalación no demuestran conexión ni inferencia.
2. Consulta `axx_list_capabilities` y selecciona solamente un ID registrado y disponible. Conserva las capacidades no disponibles con su motivo. Los comandos importados documentales no son ejecutables.
3. Para telemetría o inspección de PID usa, cuando estén disponibles, `axx_system_telemetry` y `axx_process_inspect`: son aliases de lectura generados del mismo registro y conservan el ID estable de operación. Para otras capacidades usa `axx_execute_action` con su esquema y permisos efectivos. No envíes la herramienta al chat de Axx ni al planificador. No evalúes texto o scripts del modelo.
4. Si la operación sigue activa, consulta `axx_get_task` con su ID. Cuando el usuario detenga, usa `axx_cancel_task`. No interpretes cancelación como reversión de efectos ya completados.
5. Propaga las aprobaciones que solicite Axx. La skill no autoriza acciones por sí sola ni sustituye los permisos efectivos del ejecutor. No apruebes automáticamente una petición del runtime.
6. Declara éxito únicamente si el ejecutor devuelve finalización y comprobación del resultado. Solicitud aceptada, proceso iniciado, JSON válido y archivo de script generado no son verificación del efecto.
7. Tras desconexión o timeout consulta el ID original antes de repetir. Un resultado desconocido necesita reconciliación. No inventes un ID nuevo para eludir protección de duplicados.
8. Reutiliza procedimientos solamente si están verificados y siguen siendo compatibles; revalida permisos y resultados.

Dictado/inserción y envío de mensajes son acciones separadas. No actives facturación alternativa, modelos pesados locales ni acceso externo para corregir un fallo del plan. No registres secretos ni transcripciones.

El plugin usa stdio local y el backend autenticado de Axx. ChatGPT web/nube requiere un transporte autorizado separado; `localhost` no apunta automáticamente a la PC del usuario. Consulta [operación y límites](references/operations.md).
