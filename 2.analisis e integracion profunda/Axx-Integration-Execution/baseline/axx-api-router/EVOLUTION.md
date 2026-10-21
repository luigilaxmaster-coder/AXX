# Qué se puede hacer con Axx y esta capa

## Implementado y probado localmente

- Selección secuencial por prioridad, capacidad y categoría de tarea.
- Cambio ante cuotas, credenciales rechazadas y fallos temporales.
- Pausas y contadores diarios persistentes, límites de intentos y salida.
- Diagnóstico sin consumir API: estado, métricas, pausa restante y consumo local.
- Restricción de solicitudes etiquetadas como sensibles a destinos explícitamente autorizados.
- Demostración reproducible sin claves ni conexión, además de 20 pruebas automáticas.

## Aplicaciones posibles, según modelo y herramientas de Axx

| Función | Modelo | Trabajo adicional necesario |
|---|---|---|
| Chat y redacción | Texto | Interfaz e historial de Axx |
| Resumir documentos | Texto | Lectura/extracción, fragmentación y referencias |
| Traducir dictado sin enviarlo | Texto + STT separado | Captura de voz, transcripción e inserción en campo elegido |
| Comprender una captura | Visión | Captura autorizada, reducción de tamaño y envío explícito |
| Abrir apps y ordenar archivos | Herramientas | Ejecutor local, validación de argumentos y comprobación del resultado |
| Ayudar a programar | Código/texto | Acceso acotado al proyecto, revisión y pruebas |
| Reutilizar acciones aprendidas | Modelo solo para casos nuevos | Registro procedural local, parámetros, precondiciones y verificación |

Estas aplicaciones no están implementadas en este paquete. El router facilita elegir y conectar la inferencia.

## Mejoras siguientes, en orden de utilidad

1. **Integración real en Axx.** Sustituir su llamada actual al modelo por este módulo y probar dos cuentas por separado. Preservar animaciones, chat, disposición radial, atajos y memoria existentes. Esto exige el código real de Axx.
2. **Memoria procedural verificable.** Guardar recetas que funcionaron, con versión, entorno, argumentos, precondiciones y resultado esperado. Reutilizar solo si siguen siendo válidas; si la verificación falla, detener o replanificar. No guardar pasos inventados ni contraseñas.
3. **Adaptadores de cuotas reales.** Leer APIs oficiales de saldo/cuota cuando existan, con caché breve; distinguir agotamiento diario de limitación por minuto. Hace falta verificar el contrato de cada proveedor y probarlo con credenciales. No inferir saldo a partir de los contadores locales.
4. **Cola persistente opcional.** Guardar tareas que puedan esperar cuando todas las APIs estén agotadas; volver a intentar a partir del próximo momento elegible, con caducidad, cancelación y límite de intentos. Para mensajes interactivos, mostrar el bloqueo inmediatamente.
5. **Pruebas de capacidad por modelo.** Ensayos mínimos de visión, JSON, herramientas y contexto. Guardar fecha y resultado; invalidarlos al cambiar modelo. No ejecutar acciones reales durante esos ensayos.
6. **Memoria de documentos con recuperación.** Buscar fragmentos locales antes de llamar al modelo, con citas y límites de contexto. Evitar reenviar archivos enteros en cada turno.
7. **Panel en el cuerpo de Axx.** Mostrar proveedor activo, tarea, intentos y estado utilizando el diseño existente. Los datos ya pueden obtenerse de `status()`; la interfaz visual aún no está implementada.

## Decisiones críticas

- No consultar varios modelos para toda pregunta: consume más cuotas y agrega demora. Reservar una segunda evaluación para tareas que la justifiquen.
- No usar caché indiscriminada: una respuesta sobre datos actuales o estado del PC puede quedar obsoleta. Cachear solo operaciones deterministas y con invalidación definida.
- No confundir respuesta correcta con ejecución correcta: confirmar el estado real de archivos/apps después de una acción.
- No prometer autonomía continua gratis: cuotas, internet y disponibilidad siguen siendo dependencias.
- No usar cualquier nuevo destino descubierto automáticamente. Revisar proveedor, términos, capacidades y tratamiento de datos antes de activarlo.

## Equipo

La arquitectura mantiene inferencia remota y estado local en SQLite. Es apropiada en principio para el Acer i7 de 11.ª generación con 16 GB que indicaste. No se ejecutaron mediciones en ese equipo y no se incluye un motor local de modelos grandes.
