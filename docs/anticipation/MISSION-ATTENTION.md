# Atención por misión

Esta unidad amplía M10 sobre las misiones y superficies existentes. Cada entrega Windows necesita sus propios recibos; la aceptación de 0.22.30 y del APK 0.2.11 no acredita esta implementación.

## Estado y exposición

`AnticipationService.status` añade `mission_attention`. Cada grupo conserva la identidad de misión, tarea, proyecto, revisión y hash del plan. Su estado procede del plan durable y de los recibos actuales, antes de filtrar las sugerencias individuales. Un hijo antiguo pendiente de aprobación no restaura una decisión que la misión ya superó.

| Categoría | Evidencia necesaria |
| --- | --- |
| `done` | `ActionLearning._mission` acredita los pasos y el contrato final completos. |
| `decision` | Aprobación, pregunta o revisión concretas pendientes. |
| `problem` | Fallo, bloqueo o resultado incierto actuales. |
| `progress` | Trabajo, dependencia o capacidad pendiente, pausa o cancelación voluntaria. |

La proyección no ejecuta comandos, inspecciona nuevamente archivos ni consulta un modelo. Describe resultados durables; no certifica que un archivo o una aplicación externos permanezcan sin cambios. Los verificadores y permisos existentes vuelven a aplicarse al preparar o ejecutar una acción.

La tarjeta y Actividad muestran un grupo por misión. Las actualizaciones de progreso no crean otra interrupción. Consultar una misión manualmente no consume presupuesto. Una misión sin candidato proactivo vigente conserva su consulta manual y no obtiene una alerta por existir.

## Recibos de atención

Se conserva `/axx-api/anticipation/feedback` y el cuerpo legacy `{suggestion_id, action}`. La extensión `action: shown` admite una clave de atención del servidor y estas fases:

- `claim`: reserva una interrupción dentro de la transacción SQLite. Sólo la primera admisión permite una narración nueva.
- `presented`: declara que la interfaz presentó el grupo admitido. Repetirla no vuelve a cobrar.
- `response`: reconoce una respuesta solicitada ya renderizada y guardada. No consume presupuesto proactivo; si existía un cargo, lo conserva.

`claim` y `presented` requieren el representante vigente. `response` admite la identidad de misión para reconocer una respuesta sin sugerencias hijas. El servidor recompone el grupo, su clave, origen y versión; el cliente no aporta permisos ni decide la categoría autorizada.

`response_digest` identifica el mensaje original del snapshot del plan mediante SHA-256 UTF-8. El cliente lo compara antes de reconocer una respuesta, además del estado, revisión y hash. No se calcula sobre el resumen truncado ni sustituye la clave del servidor. La respuesta visible puede añadir los recibos del mismo plan. El reconocimiento no demuestra que el humano leyera o considerara útil el resultado.

El presupuesto cuenta cargos de admisión grupal y exposiciones legacy dentro de la misma ventana. Tres hijos no son tres cargos. Una respuesta perdida conserva la reserva: no demuestra presentación y no autoriza repetir efectos. Reiniciar, cambiar de perfil u olvidar una conversación no devuelve presupuesto consumido.

## Descartar y suprimir

Los controles del grupo usan `{mission_id, action, attention_key}` con `dismiss`, `suppress` o `restore`. El servidor verifica la versión antes de modificar el estado de atención.

Descartar afecta a esa clave completa y sobrevive al reinicio; no rota silenciosamente al siguiente hijo. Una decisión nueva puede tener otra clave. «No volver a avisar de esta misión» conserva una supresión de esa misión entre revisiones. Su restauración se ofrece en la lista manual existente. No modifica supresiones de otras rutinas, resultados técnicos, utilidad, grants ni recibos de efectos.

Una admisión anterior no mantiene elegible una tarjeta después de caducidad, descarte, pérdida de consentimiento o invalidación. El grupo manual conserva únicamente el estado que aún resulte válido.

## Perfiles y memoria

Discreto conserva respuestas solicitadas y consulta manual. Copiloto y Full respetan sus modos efectivos, horarios, silencios y límites actuales. Una tarjeta o respuesta no concede ejecución. Durante dictado, llamadas, interacción incompatible o una superficie oculta se difiere la presentación; no se inventa una exposición.

La voz de respuestas solicitadas mantiene `voiceRead` y su solicitud explícita de voz. Los avisos proactivos sólo narran una admisión nueva autorizada. Actividad no añade otra narración, abre una ventana ni cambia el foco.

Las cachés y recibos conservan `memory_scope`, `memory_context_id` y `memory_dependencies` originales. Estas dependencias son distintas del contexto ambiental por proyecto. El servidor las revalida al proyectar y reconocer atención. El cliente rechaza tokens propios antiguos y referencias que conoce revocadas; una dependencia válida recibida del servidor no exige abrir antes su chat de origen.

Olvidar una tarea retira también los grupos derivados y las respuestas pendientes. El cargo conserva sólo su encabezado opaco durante la ventana presupuestaria, sin texto, plan o procedencia reutilizable. La memoria independiente y los journals de efectos permanecen. No se activa el envío de observaciones a proveedores ni se amplían grants Full.

## Verificación y entrega

Las pruebas usan SQLite, archivos temporales reales, transporte HTTP autenticado y navegador con entrada controlada. Separan agrupación, cargo, presentación, comprensión humana y resultado técnico. Las carreras de dos servicios deben admitir como máximo un cargo, incluso mezclando una tarjeta legacy y un grupo.

Pruebas focales:

```powershell
python -m unittest backend.tests.test_mission_attention backend.tests.test_anticipation_http -q
node 1.AXX/scripts/test-mission-attention.cjs
node 1.AXX/scripts/test-mission-attention-integration.cjs
node 1.AXX/scripts/test-anticipation.cjs
node 1.AXX/scripts/test-task-memory.cjs
```

Estas comprobaciones no acreditan utilidad humana, todos los gestos del escritorio, audio físico o una instalación. La entrega exige el gate conjunto sobre la fuente final, sus CI y los recibos de build, instalación y aceptación nativa correspondientes. Un rollback debe conservar cargos y usar una base compatible; un binario antiguo que ignore estos recibos no es una reversión segura de la política de atención.
