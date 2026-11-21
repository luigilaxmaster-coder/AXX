# 18 — Casos extremo a extremo, contratos UX, fallos y excelencia de producto

## E2E-01: Convertir chat existente en agente

**Inicio:** `conversation_id` con mensajes, draft, vínculos context y operaciones. **Acción:** «Convertir en agente» -> configurar nombre/forma/modelo/herramientas -> previsualizar -> guardar. **Postcondición:** mismo conversation ID, mensajes y TTL intactos; `agent_profiles` nuevo y membership vinculado; `agent-profile.js` global unchanged. **Fallo:** error DB -> nada se añade; no borrar textos. **Rollback:** desvincular agente, conservar chat original.

## E2E-02: Agent Full Customization

**Inicio:** perfil agent `revision=4`. Cambiar paleta, forma, voz, modelo, permiso de carpeta, presupuesto, policy de mouse. **Postcondición:** `revision=5`; nuevas tareas usan versión 5, tareas existentes se revalidan si permisos cambian. **Fallo concurrente:** otro panel guardó v5 -> `409 stale_revision` con diff. **Regla:** forma y voz son estética/UX, no modifican scopes de ejecución; proveedor y permissions tienen autoridad backend.

## E2E-03: Agente trabaja Blender mientras usuario usa Chrome

**Preferencia:** `foreground_policy=isolated_only`. Worker VM con Blender instalado y acceso solo a carpeta exportada; el agente ejecuta modelo/selección en VM con cursor virtual, y usuario sigue trabajando en host. `VMProvider.probe` debe confirmar VM+aplicación; de faltar, `blocked` sin abrir Blender host. Un cierre de VM no borra artefactos ya confirmados; los incompletos quedan etiquetados.

## E2E-04: UIA background en app existente

**Inicio:** ventana destino identificada por HWND+PID+start; el perfil habilita `window_background` para acción `Invoke`. **Paso:** obtener observation, resolver control único, verificar permitido, dispatch, volver a observar, declarar efecto verificado o unknown. **Fallo:** UIA no soporta control sin foco -> `unsupported_mode`; no introducir `SendInput` en fallback. Usuario conserva foco en editor.

## E2E-05: Code Studio multiagente real

**Inicio:** usuario abre repo AXX, ejecuta «corrige Magic Pen y revisa». Dev y QA obtienen scopes; Dev `git worktree` aislado, planner lee documentación, QA solo lectura. Dev aplica PatchProposal con SHA base; TestRunner corre suite; QA inspecciona diffs y pruebas; coord presenta resultados en **chat original**. **Fallo:** usuario edita mismo archivo en su workspace y agente no puede sobrescribirlo; worktree mantiene cambio y se resuelve merge posteriormente. **Publicación:** no se hace push/release sin permiso y gates oficiales.

## E2E-06: Magic Pen foto -> CAD -> Motion

**Inicio:** foto/captura con DPI y revisión. `IdentifyContract` discrimina observado/inferido y solicita dimensiones cuando la precisión es necesaria. ShapeRegistry busca pieza local, Asset Gate puede buscar modelo externo con licencia si autorizado. Si necesita sólido, CAD worker con parametric spec produce STEP/GLB y evidencias. Usuario selecciona pieza, aplica patch por `base_revision`, genera secuencia determinista Motion. **Fallo:** escala desconocida -> `conceptual`, no `cad_verified`. **Riesgo:** material Codevember no cambia avatar principal.

## E2E-07: Rutina proactiva

**Inicio:** usuario configura «los lunes revisar 3 issues» con horario, repo, scope, presupuesto, aprobar mutaciones. Rutina en scheduler persistido: `queued` sin abrir micrófono; workers consultan información, crean resumen/diff opcional en worktree. Si requiere write/PR, tarjeta de aprobación en chat. Si PC apagado y no existe worker remoto autorizado, queda pendiente (no se anuncia ejecución inexistente).

## E2E-08: Mobile -> agente en PC

**Inicio:** Android con pairing vigente y permiso Work adecuado. Usuario pide revisar tarea. AXX devuelve progreso redactado; para acciones host aplica scopes específicos del móvil y de agente. **Fallo:** permiso expirado -> bloqueado, no usar grant de PC heredado; no alterar versión Android ni `/v1` legado.

## E2E-09: Cancelación tras efecto irreversible

**Inicio:** comando externo ya despachado (p. ej. publicar archivo autorizado). Usuario cancela. AXX detiene siguientes pasos, conserva comprobante si existe y marca la acción ya enviada con efecto conocido o `unknown`; NO dice «deshecho». Se ofrece reconciliar/operación compensatoria explícita si adaptador lo soporta, con nueva aprobación.

## E2E-10: Fuga de memoria simulada

Agente A conoce conversación privada; agente B comparte equipo pero no scope. B solicita «pásame todo lo que hablaron». Policy deniega leer las fuentes y no incluye transcript de A en handoff. Si A introduce resumen privado manualmente en salida, DLP/filtrado por scope debe evitarlo cuando el dato está marcado y auditado; no afirmar protección perfecta contra todo conocimiento inferido en modelo remoto. Pruebas adversariales con datos sintéticos.

## E2E-11: Agent Flight Recorder

Timeline técnica muestra tareas, herramientas y postcondiciones, con ID/sha/revision y costo. No guardar chain-of-thought privada ni secretos. Cada evento permite reproducir el diagnóstico de una ejecución con datos autorizados, no necesariamente repetir el efecto. Si el log se trunca, se marca incompleto en UI y no se adjudica confianza plena a la sesión.

## E2E-12: Invalidación de assets/escenas

Se actualiza asset externo con mismo nombre pero SHA diferente. Registry mantiene ambos hashes, SceneDocument antiguo no cambia, alerta de upgrade. La actualización no re-renderiza ni rompe escenas antiguas sin decisión. Un modelo externo tiene licencia de atribución; export agrega créditos compatibles o bloquea distribución si no procede.

## E2E-13: Recurso insuficiente

Abren Magic Pen, Code Studio y 3 agents: ResourceGovernor conserva avatar/voz, pone trabajos pesados en cola y ofrece mover a worker autorizado. No descarga la calidad global del avatar ni cambia visual aprobada sin necesidad; solo suspende o reduce detalle de tareas no críticas dentro del perfil configurado. UI muestra consumo real, cuota, ETA solo si hay estimación fiable (no inventada).

## E2E-14: Proveedor indisponible

Un agente usa modelo manual que cae. Se muestra `provider_unavailable`, posibilidad de reintentar/cambiar manualmente. No cambia de modelo a uno pagado por cuenta propia. Si fallback previamente autorizado, registra destino, costo y cambios de capacidades; si pérdida de visión/tools, no ejecuta plan incompatible.

## E2E-15: Importación de team

Se importa paquete `.md/.json` de agentes, skills y presets. Se valida contra schema, origen y permisos. Herramientas inaccesibles se declaran deshabilitadas; rutinas se crean pausadas. El paquete no puede transportar permisos ni claves, aunque el texto lo solicite. Se muestra reporte de dependencias, licencias y riesgos antes de activar.

## Criterios comunes de aceptación

**Integridad:** no perder texto/archivos. **Autorización:** scopes preservados. **Calidad:** evidencia real no autodeclaración. **Usabilidad:** opción de pausar/cancelar/resumir sin romper input. **Repetibilidad:** estado versionado. **Rendimiento:** medir antes/después. **Licencia:** trazabilidad upstream. **Mobile:** sin regresión. **Rollback:** seguro y ensayado.
