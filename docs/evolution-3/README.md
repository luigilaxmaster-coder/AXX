# AXX Evolution 3.0 — Paquete maestro de ingeniería

**Estado:** especificación de implementación, no software instalado. **Fecha de corte:** 2026-11-21. **Idioma:** español. **Propietario del proyecto:** autor humano de AXX. **Repositorio:** <https://github.com/luigilaxmaster-coder/AXX>.

> **REGLA PRINCIPAL:** ampliar AXX sin sustituir sus chat, CommandService, ActionExecutor, memoria, router de inferencia, sistema de voz, avatar ni Magic Pen. Todo cambio es aditivo, reversible, medible y aprobado por pruebas.

## Alcance

Esta documentación une tres planes sucesivos en **un único backlog**:

1. **AXX Evolution / Magic Pen:** Superpowers, Diagram Design, CAD preciso, Motion Educator, viz3d/creator-generalist, Codevember, OpenVINO, Gaussian Splat, Asset Gate y Diorama.
2. **AXX Agent Workspace:** personalización exhaustiva de agentes, conversión de chats existentes, equipos multiagente, handoffs, memoria por alcance, permisos y continuidad.
3. **AXX Independent Workspaces + Code Studio:** ejecución en segundo plano sin interferir con usuario, mouse virtual comprobable, navegadores aislados, entornos virtuales, edición profesional de código, Git, LSP, DAP, tests y verificación.

No se ha editado el código de AXX, lanzado sus tests nativos ni instalado nada durante la preparación de este paquete. Los contratos nuevos son **propuestas versionadas** que se deben integrar y probar, nunca descripciones de endpoints ya disponibles.

## Documentos: leer en este orden

| Archivo | Objetivo |
|---|---|
| `docs/00_BASELINE_Y_REGLAS.md` | Hechos comprobados, fuentes, autoridad y prohibiciones de regresión |
| `docs/01_REQUISITOS_PRODUCTO.md` | Requisitos, historias, modos, UX y criterios no funcionales |
| `docs/02_ARQUITECTURA_OBJETIVO.md` | Componentes, fronteras, dependencias, datos y diagramas |
| `docs/03_AGENT_DESIGNER_CHAT.md` | Personalización y transformación de chats sin pérdida |
| `docs/04_ORQUESTACION_MULTIAGENTE.md` | TaskGraph, eventos, handoffs, autonomía y recovery |
| `docs/05_SEGURIDAD_Y_PERMISOS.md` | Amenazas, controles, secretos, scopes, aprobaciones |
| `docs/06_COMPUTER_USE_SEGUNDO_PLANO.md` | Mouse propio, UIA/Cua, aislamiento, limitaciones Windows |
| `docs/07_CODE_STUDIO.md` | Editor profesional, LSP/DAP, Git, parches y tests |
| `docs/08_MAGIC_PEN_Y_ASSETS.md` | Evolución 2D/3D, CAD, simulación, assets y fidelidad |
| `docs/09_DATOS_Y_MIGRACIONES.md` | Datos SQLite y migración segura |
| `docs/10_API_Y_EVENTOS.md` | HTTP, SSE, auth, errores y contratos de eventos |
| `docs/11_RENDIMIENTO_Y_INFRAESTRUCTURA.md` | Política de recursos, nube y workers |
| `docs/12_PRUEBAS_Y_ACEPTACION.md` | Pruebas por módulo y matriz de no regresión |
| `docs/13_FASES_Y_GATES.md` | Orden dependiente y entregas verificables |
| `docs/14_DESPLIEGUE_Y_ROLLBACK.md` | Conservación, backups, publicación y reversión |
| `docs/15_REFERENCIAS_Y_LICENCIAS.md` | Inventario upstream, compatibilidad y adopción |
| `docs/16_PROMPT_MAESTRO_CODEX.md` | Instrucción ejecutable para equipos de agentes |
| `docs/17_DECISIONES_Y_RIESGOS.md` | ADRs, alternativas rechazadas y decisiones pendientes |
| `docs/18_CONTRATOS_DE_INTERACCION.md` | Casos de uso de extremo a extremo, UX y errores |
| `docs/19_MAPA_DE_CAMBIOS_POR_ARCHIVO.md` | Acoplamiento concreto a ficheros actuales y nuevos módulos |
| `docs/20_PLAN_DE_PRS.md` | Descomposición granular en 20 PRs con dependencias y gates |
| `schemas/*.json` | Ejemplos de JSON Schema (Draft 2020-12) para nuevas entidades |
| `sql/001_agent_foundation.sql` | DDL propuesto de foundation; **no ejecutar en producción antes de revisión** |
| `qa/acceptance-matrix.csv` | Matriz rastreable, implementable como pruebas |
| `qa/PHASE_GATE_TEMPLATE.md` | Acta estándar de cierre de fase |
| `records/ADR_TEMPLATE.md` | Plantilla para decisiones arquitectónicas |
| `records/upstream-lock.json` | Revisiones upstream comprobadas y pendientes de fijación |

## Orden de adopción

**No saltar fases.** Fases 0–7: modernización y aceptación de Magic Pen. Fase 8: perfiles de agente sobre chats existentes. Fase 9: Code Studio Core. Fase 10: workspaces en segundo plano. Fase 11: orquestación multiagente. Fase 12: Code Studio Pro y más integraciones. Fase 13: automatizaciones y transferencia entre dispositivos. Cada fase requiere los gates de `13_FASES_Y_GATES.md`.

### Semántica de estado

- **ACTUAL/VERIFICADO-EN-FUENTE:** observado en la rama publicada; no prueba instalado/funcionando en PC.
- **PROPUESTO:** contrato o componente que no forma parte aún de la fuente revisada.
- **NO VALIDADO EN WINDOWS:** dependerá de pruebas en el equipo real y permisos del usuario.
- **GATE:** requisito binario para habilitar, fusionar o publicar.
- **BLOQUEO:** no se puede asumir éxito o degradar permisos para continuar.

## Cómo entregar este paquete a Codex/Antigravity

1. Extraer el ZIP **en el repositorio de trabajo o junto a él**, idealmente bajo `docs/evolution-3/` **en una rama aislada**; conservar `main` intacta.
2. Leer primero `AGENTS.md`, `docs/RELEASING.md`, `docs/mobile/COMPATIBILITY-PROTOCOL.md` de **la copia actual** de AXX. Ante discrepancia, el repositorio prevalece sobre este paquete.
3. Comparar commit, tests y archivos presentes contra `00_BASELINE_Y_REGLAS.md`. No implementar con rutas supuestas.
4. Ejecutar `docs/16_PROMPT_MAESTRO_CODEX.md` **fase por fase**; cada cambio conserva recibos y matriz de aceptación.
5. Versionar la documentación junto al código y registrar los cambios de contrato en `docs/17_DECISIONES_Y_RIESGOS.md`.

## Invariantes irrenunciables

**I-01** No segundo ejecutor con efectos en host. **I-02** No ampliar permisos al delegar. **I-03** No repetir efecto `unknown`. **I-04** No alterar formas/material/voz/tentáculos sin autorización visual. **I-05** No romper `/v1`, pairing o Android. **I-06** No borrar historial/borradores/credenciales. **I-07** No afirmar una simulación como CAD exacto. **I-08** No ejecutar código generado en host como sandbox. **I-09** No fallback oculto de proveedores. **I-10** No confundir un cursor decorativo con entrada independiente. **I-11** No publicar con validaciones fallidas o incompletas. **I-12** No tocar configuraciones ajenas de otra rama o sesión.

## Entregables exigidos por cada fase

Inventario de cambios, manifiesto de licencias, migración arriba/abajo, tests positivos y negativos, evidencias Windows cuando corresponda, `AGENTS.md` y compatibilidad respetados, reporte PASS/FAIL/BLOCKED/SKIPPED, plan de rollback, diffs revisados y documentación actualizada. Una prueba simulada no certifica funcionalidad instalada.
