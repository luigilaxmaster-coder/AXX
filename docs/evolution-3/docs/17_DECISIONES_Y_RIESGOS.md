# 17 — Decisiones arquitectónicas (ADR) y registro de riesgos

## ADR-001: Chat con agente, no app de bots paralela

**Aceptada como propuesta.** Reutilizar `chat_store.py` y `chat-workspace.js` + memberships N:N. Alternativa descartada: importar OpenMausBot/OpenDots UI y servidor completos. Motivo: duplicación de contexto, permisos, ejecutores, voz y renderizadores.

## ADR-002: Único ejecutor de efectos

**Obligatoria por baseline.** CommandService/ActionExecutor permanece autoridad del host. Alternativa descartada: cada agente ejecuta shell/UIA directamente. Motivo: journal, grants, deduplicación, recuperación y compatibilidad.

## ADR-003: Mouse independiente mediante entornos, no cursores falsos

**Decisión de diseño.** Workspaces directos, navegador, UIA, VM/remote; overlay cursor opcional. Alternativa descartada: depender de openMouse/hooks globales como garantía; Windows comparte foco de teclado. Estados per-action capability, no «background universal».

## ADR-004: Monaco Lite antes de Theia Pro

**Decisión de implementación.** Añadir Monaco lazy-loaded para editor local; LSP/DAP/Tree-sitter graduales. Theia solo como opción Pro bajo demanda tras medir tamaño, licencia, RAM y extensión. Evitar segundo IDE residente pesado.

## ADR-005: Code edits en worktree con CAS

**Decisión de implementación.** Agente modifica branch/worktree autorizado, revisa diff y tests, integración controlada. Evita interferir en archivos sin guardar del usuario. El worktree es aislamiento de cambios, NO sandbox para código hostil.

## ADR-006: Magic Pen primero

**Condición del propietario.** Fases 0–7 antes de Agent Workspace multiagente. Asset Gate y Diorama se incorporan a fase visual; no usar diseños de bots para rediseñar avatar.

## ADR-007: CAD exacto separado de escena conceptual

**Decisión.** SceneDocument versionado con fidelity y unidades; CAD Worker aislado; licencias SOMA revisadas. No ejecutar Python generado en host.

## ADR-008: Datos y compatibilidad

**Decisión.** SQLite aditivo, perfiles/versiones separados de ChatStore legacy, TTL chat 90 días, revocación de memorias y rutas `/v1` preservadas. Rollback prioritario por flags y build compatible, no DROP automático.

## ADR-009: Adopción selectiva upstream

**Decisión.** Usar herramientas/ideas necesarias y SHAs fijados. Copiar código solo con licencia compatible y QA. Fijar material importado por hash, autor y procedencia. No añadir todos los repos como dependencias del instalador.

## ADR-010: Programación remota/nube

**Decisión.** API/local/workers con routing explícito de datos y coste. No enviar archivo/captura privada por defecto; no auto fallback de proveedor manual. Modelos 50B/100B fuera de laptop actual salvo hardware probado.

## Registro de riesgos con mitigación

| ID | Riesgo | Severidad | Mitigación | Gate |
|---|---|---|---|---|
| R01 | Regresión avatar/tentáculos por shaders | Alta | Flags, golden images, hitmask/anchor tests | G5/G7 |
| R02 | Pérdida de chat/Connect al convertir | Crítica | Binding aditivo, backup, compat tests | G8 |
| R03 | Envío de acción duplicada por crash | Crítica | Journal, unknown stop/reconcile | Todos |
| R04 | Fuga de memoria entre bots | Crítica | Project ACL, approved context refs, negative tests | G8/G11 |
| R05 | Agente roba foco/teclado | Alta | Router, explicit policy, host leases, VM | G10 |
| R06 | Código de modelo ejecuta malware | Crítica | sandbox real/consentimiento, no `exec` host | G3/G9 |
| R07 | Datos enviados a nube sin aviso | Alta | consentimiento provider/asset/remote, logging de egress | Todos |
| R08 | LLM inventa precisión CAD | Alta | fidelity/provenance y validators | G3/G7 |
| R09 | Violación de licencias upstream | Alta | manifest+audit individual, no GPL copy | G0/G5 |
| R10 | GPU/CPU satura equipo usuario | Alta | resource governor/lazy load | G5/G10 |
| R11 | Incompatibilidad Android `/v1` | Crítica | contract tests y companion receipt | Todos |
| R12 | LSP/DAP ejecutan comandos externos | Alta | allowlist, worker y autorización | G9/G12 |
| R13 | Merge destructivo en Git | Alta | worktrees/diff/review/CI, no force | G9/G12 |
| R14 | Eventos SSE con secretos | Alta | schemas, projection, ACL, redaction | G11 |
| R15 | Detección errónea capabilities PC | Alta | probe real por app/acción/versión | G10 |
| R16 | Release declarado sin instalar | Alta | `AGENTS.md`, publish receipt/SHA | G7+ |

## Decisiones que requieren validación en entorno real

- Compatibilidad real de Cua Driver con cada app, GPU y Windows instalado.
- Disponibilidad de Windows Sandbox/Hyper-V y alternativa en homelab.
- Estado del motor avatar PC y mapping de las 24 formas con móvil.
- RAM/FPS baseline con Code Studio y shaders activados.
- Qué servidores LSP/depuradores deben empaquetarse vs instalar por proyecto.
- Licencias completas de assets, paquetes y tecnologías CAD.
- Retención de memoria y permisos predeterminados aprobados por propietario.

No convertir estos puntos en implementación afirmada sin gate/evidencia.
