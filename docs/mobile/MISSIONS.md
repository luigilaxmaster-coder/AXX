# Una misión entre PC y teléfono

Implementación de fuente en integración. Requiere una entrega Windows y un APK
con esta interfaz; la aceptación de Windows 0.22.30/0.22.31 o Android 0.2.11 no
acredita este recorrido nuevo. No modifica sus versiones ni el diseño protegido.

## Uso

Con historial compartido y permiso Work vigentes, Acciones muestra «Misiones de
la PC». Abrir una fila conserva el identificador original, proyecto, revisión y
hash. El teléfono consulta la misión; no crea otro plan ni otro ejecutor.

El editor muestra el objetivo completo y su destino. Una corrección necesita
texto humano y revisión explícita del JSON, incluidos los criterios que declaran
la ruta final. Editar sólo una etiqueta no cambia los pasos. Cambiar el borrador
invalida la revisión; el sondeo no lo sobrescribe.

«Preparar en la misma misión» vuelve a consultar las referencias exactas antes
de enviar. La PC prepara el sufijo pendiente, conserva recibos completados y
presupuesto acumulado, y retira la aprobación anterior. Preparado no significa
ejecutado. Continuar requiere el hash vigente y la autoridad de la PC, mediante
sus aprobaciones o permisos previos que sigan cubriendo el plan concreto.

Al perder una respuesta se conserva el ID de envío y su PC original. Consultar
el recibo no repite la reparación. También se puede consultar ese recibo cuando
la PC cambia a otro chat compartido, sin trasladarlo al editor actual. Cambiar
de PC/certificado impide usar el seguimiento con el enlace nuevo. «Olvidar
seguimiento» es una decisión local explícita; no cancela nada en la PC.

## Contrato aditivo

La capacidad opcional `mission_continuity` se anuncia cuando se comparte el
historial. Se mantienen las rutas y respuestas existentes de `/v1/tasks` y Work.
Las rutas nuevas requieren el permiso `tools.control` vigente y el contexto
original de una conversación conocida:

| Ruta | Función |
| --- | --- |
| `GET /v1/work/missions` | Lista las misiones de la conversación compartida. |
| `GET /v1/work/mission?operation_id=…` | Consulta la misión original y su contrato actual. |
| `POST /v1/work/mission-correct` | Admite una corrección revisada, sin ejecutar efectos. |
| `GET /v1/work/mission-correction?command_id=…` | Reconcilia el recibo de ese teléfono y envío. |

El POST contiene exactamente `command_id`, `operation_id`, `conversation_id`,
`plan_hash`, `goal_revision`, `text`, `goal_spec`, `memory_scope` y
`memory_context_id`. No acepta proveedor, modelo, dispositivo, grant o aprobación
aportados por el teléfono. Las llamadas nativas fijan el device ID y fingerprint
esperados antes de salir; la credencial TLS no se copia al código de la interfaz.

El gateway deriva un `correction_id` distinto por dispositivo/envío y reutiliza
el journal `mobile_commands`. La primera admisión guarda atómicamente los
encabezados de vínculo antes de llamar al backend. No copia el texto ni el
objetivo al recibo móvil. Repetir ID y payload consulta lo existente; cambiar el
payload con el mismo ID se rechaza.

`ActionLearning.repair` recibe `correction_id`, hash/revisión esperados y la
restricción de dispositivo comunicada por el host. El token local del host sigue
siendo la autoridad; ese origen declarado no constituye una credencial ni un
permiso nuevo. El contrato anterior de repair se conserva sin estos campos.

La admisión compara el snapshot durable en SQLite antes de inferir. El marcador
de propietario y el snapshot esperado impiden que un trabajador tardío reescriba
otra corrección, cancelación u olvido. Dos conexiones independientes compiten
por una sola admisión. La nueva revisión exige su hash exacto al ejecutar o
reanudar; no hereda una aprobación ligada sólo al ID.

El journal del plan conserva hasta 32 recibos de corrección; al alcanzar el
límite rechaza nuevas admisiones sin borrar IDs. Sólo una preparación
`awaiting_approval` completa registra hash/revisión de resultado. Fallo, pausa,
cancelación o interrupción no acreditan preparación. Un hash nuevo ajeno no
demuestra que la corrección de este teléfono haya sido aceptada.

## Memoria y permisos

Cada espera conserva la tarea, generación, contexto opaco y dependencias
originales. Nunca se captura una referencia nueva para rehabilitar un plan viejo.
Olvidar una fuente retira sus derivados y finaliza un recibo pendiente en el
mismo escritor que retira el plan. La proyección olvidada devuelve sólo
encabezados seguros, también para los recibos nuevos.

El permiso móvil se revalida durante la preparación y antes de publicar su
resultado. Revocarlo no concede ni retira por sí solo la autoridad independiente
del usuario de la PC para revisar posteriormente un plan ya preparado. El
presupuesto existente no se reinicia para reparar. Los recursos explícitos,
ensayos de revalidación y planes de Taller conservan sus restricciones actuales.

## Verificación

```powershell
python -m unittest backend.tests.test_mission_corrections backend.mobile.tests.test_missions backend.tests.test_mobile_mission_flow -q
node mobile/tests/test-mission-continuity.cjs
node mobile/build.mjs
python -m unittest mobile.tests.test_mission_continuity_ui -q
```

Las pruebas usan SQLite, HTTP/TLS y archivos temporales reales. Los modelos son
fixtures deterministas declaradas. El ensayo integrado corta respuestas tras
preparar y tras el efecto final, consulta los mismos IDs y comprueba recibos,
contador del ejecutor y SHA-256 independiente. Las pruebas de interfaz usan un
DOM y transporte controlados. Los casos de navegador recorren Actividad, la
revisión del objetivo, la pérdida de respuesta y el texto ampliado con teclado;
no acreditan APK, teclado físico, voz ni dispositivos reales. La entrega exige
gate conjunto, APK/hash/firma, actualización
en sitio y aceptación física por separado.
