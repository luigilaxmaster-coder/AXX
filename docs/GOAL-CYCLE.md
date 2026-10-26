# Objetivos conservados y construcción de capacidades

La tarea conserva su petición original, contrato de resultado y revisión en `learning_plans`, junto con los pasos y recibos existentes. El modelo propone un plan o una carencia concreta; una redacción nueva no registra por sí sola otra herramienta.

## Recorrido integrado

1. El planificador recibe los comandos actuales, incluidos MCP y transformaciones activas, con sus contratos.
2. Puede devolver `goal_spec` junto al plan. Contiene intención, objetos y fuentes de referencia, destino, filtros, parámetros, condiciones de conservación y comprobaciones de texto final. Metadatos omitidos quedan vacíos; no se inventan selecciones ni identidades nativas.
3. Una `capability_request` describe una transformación pura o una propuesta de integración. La tarea queda en `waiting_capability`, vinculada al ID, revisión y digest del candidato; no se transforma en otra conversación ni se ejecutan efectos.
4. El Taller genera el candidato y ejecuta las pruebas puras existentes. Una generación rechazada admite un reintento explícito con el diagnóstico, sin cambiar el resultado pedido. Las pruebas del candidato no certifican el objetivo completo.
5. La revisión y activación conservan las puertas del Taller. Al activar, la interfaz retoma el objetivo original y presenta el plan concreto para su aprobación. El recuperador también puede preparar esa continuación; nunca aprueba ni ejecuta efectos por sí solo.
6. El planificador vuelve a consultar el catálogo activo. Los pasos conservan ActionExecutor, journal, bindings tipados, cancelación y comprobaciones por operación.
7. Los archivos de texto declarados en `goal_spec.checks` se leen con el comprobador estable de SHA-256 y se comparan con el contenido esperado fijado antes de construir el candidato. Si difieren, el objetivo falla aunque cada herramienta haya devuelto éxito. Los archivos y pasos completados se conservan.

El código generado sólo recibe sus entradas, no el contrato ni la evidencia del evaluador. El intérprete mantiene sus límites de instrucciones, tiempo y tamaño; no ejecuta Python mediante `exec`, imports, red, procesos o archivos. La revisión de código no concede permisos adicionales.

## Continuidad y versiones

El contrato forma parte de la huella del plan aprobado. Una continuación tras construir no puede debilitarlo. Las correcciones explícitas admitidas por la API requieren texto y la revisión vigente, conservan el contrato anterior e invalidan la preparación previa. Los efectos inciertos conservan la conciliación existente.

Un candidato sustituido no se enlaza silenciosamente. `learning/bind-capability` admite una versión exacta ya activa de la misma familia, proyecto y clase, sólo mientras la tarea espera y no tiene pasos despachados. El Taller utiliza ese enlace al activar una revisión reparada.

Las transformaciones activas son descubribles mediante el registro actual y `axx_list_capabilities`; su ejecución usa `axx_execute_action` y el mismo CommandService. No se instala otro servidor ni se reemplaza AnythingMCP.

Codex utiliza un propósito `planning` separado de la generación de capacidades, sin herramientas directas ni recuperación de hilos de chat. Conserva modelo y proveedor exactos, cancelación, `allow_paid=false` y ausencia de fallback. El plazo IPC de planificación admite la inferencia del objetivo y la construcción inicial consecutivas.

## Validación y cobertura

Se ejecutaron pruebas de contrato del objetivo, transformación, Taller, proveedor y recuperación, además del recorrido UI → HTTP autenticado → intérprete → ejecutor → archivo. El modelo de estas pruebas de interfaz es determinista; los efectos de archivo y sus comprobadores son reales.

Una prueba adicional con el proveedor Codex real y `gpt-6.1-sol` construyó una función de normalización de códigos, ejecutó sus pruebas, retomó el mismo objetivo y creó `codigos-a.txt`. Una segunda redacción, otro lote y `codigos-b.txt` reutilizaron el mismo ID de herramienta. Ambos contenidos y hashes se comprobaron independientemente. Los recibos privados están en `build/goal-cycle-live/attempt3/`.

Esta entrega cubre composición, transformaciones puras, vínculo duradero, revisión, continuación y comprobación exacta de texto. Los escenarios NOV-01–NOV-03, NOV-08 y NOV-12 tienen pruebas concretas de esas rutas. Reinicio, cancelación y sustitución de candidato tienen pruebas de contrato; no equivalen a aceptación física de todas las aplicaciones.

## Límites actuales

- La generación de APIs o adaptadores nuevos produce propuestas para integración; no importa código arbitrario ni acredita una API sugerida por el modelo.
- La revisión explícita del candidato y la aprobación del plan se conservan. La generación y las pruebas puras sí están conectadas automáticamente a la tarea.
- Los comprobadores nuevos cubren texto UTF-8 exacto dentro de artifacts. Selecciones CAD, dimensiones nativas, Excel, imágenes y calidad visual requieren verificadores y aceptación específicos.
- Las referencias descriptivas del contrato no sustituyen las observaciones nativas frescas ni autorizan coordenadas inventadas.
- La planificación conserva el presupuesto existente de dos inferencias; construir la función tiene su propia inferencia y un único reintento explícito si la generación se rechaza antes de crear un candidato.
- El catálogo de 200 casos, los 60 escenarios avanzados y los restantes NOV siguen siendo especificaciones salvo la cobertura identificada arriba.
