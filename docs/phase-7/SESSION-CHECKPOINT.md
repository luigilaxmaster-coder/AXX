# Fase 7 · Checkpoint de sesión

> Leer junto con `AGENTS.md` al reanudar. No resetear el árbol. No repetir lo ya verificado.

## Estado Git
- Worktree: `C:\Users\luigi\Desktop\axx2\.claude\worktrees\axx-phase-7-ui-09978b` (independiente; no es el árbol de Codex).
- Rama: `claude/axx-phase-7-ui` (creada en esta sesión; la rama `claude/axx-phase-7-ui-09978b` que traía el worktree queda intacta en `dfe3d5a`).
- Commit base: `a750362` (informes Fase 6). Código validado Fase 6: `4f4e18b`. `4f4e18b` es ancestro de `a750362` (verificado). La diferencia entre ambos es solo `docs/phase-6/*` y el fixture `1.AXX/scripts/test-providers.cjs`.
- `main` = `dfe3d5a`, 12 commits por detrás de `a750362`, 0 por delante. No se ha tocado.
- HEAD verificado: ver «Incrementos» (último commit listado).

## Objetivo
Reorganizar el INTERIOR de Sistema y datos, IA y proveedores y Personalizar AXX; conservar el tema claro, corregir controles poco visibles y mejorar el oscuro. Sin push, sin publicar, sin instalar, sin tocar main, voz/ASR, Rust ni Python.

## Decisión de arquitectura (vigente)
Las tres vistas se componen en ejecución: ~14 módulos inyectan tarjetas en `#view-settings`. Por eso la fase es una **capa de presentación nueva** que se carga la última y **mueve** nodos existentes (nunca los clona ni recrea), de modo que handlers, IDs y persistencia quedan intactos:
- `1.AXX/scripts/phase7-ui.js` — reagrupa nodos.
- `1.AXX/scripts/phase7-ui.css` — componentes y correcciones de tema.
- `1.AXX/Axx.html` — solo dos etiquetas (`<link>` y `<script>`) al final. No se editan los estilos inline protegidos por `mobile/design-baseline.json`.

## Incrementos
| # | Incremento | Estado | Commit |
|---|---|---|---|
| 1 | Auditoría, inventario, baseline | en curso | — |
| 2 | Sistema y datos | pendiente | — |
| 3 | IA y proveedores | pendiente | — |
| 4 | Personalizar AXX | pendiente | — |
| 5 | Temas claro/oscuro | pendiente | — |
| 6 | Pruebas, capturas, handoff | pendiente | — |

## Archivos modificados (acumulado)
- nuevo `1.AXX/scripts/phase7-ui-harness.cjs` (arnés: inventario, capturas, pruebas)
- nuevo `1.AXX/scripts/phase7-control-baseline.json` (IDs previos a la fase, por vista)
- nuevo `docs/phase-7/*`

## Últimas pruebas
- Inventario en ejecución: 0 errores de página; IDs estables entre dos ejecuciones.
- Baseline de suites existentes: lanzado en segundo plano (ver `REGRESSION-RESULTS.md` cuando termine).

## Errores pendientes
- Ninguno propio. Fallos preexistentes: por clasificar con el baseline.

## Dependencias de Codex
- Ninguna bloqueante. No se toca `native-voice.js`, ASR, audio, micrófono, atajos ni contratos de voz. Ver `CODEX-HANDOFF.md`.

## Próxima operación concreta
Crear `phase7-ui.js`/`phase7-ui.css`, enlazarlos en `Axx.html` y agrupar `#view-settings`.

## Comandos para retomar (desde la raíz del worktree)
```bash
git status -sb && git rev-parse --short HEAD && git log --oneline a750362..HEAD
node 1.AXX/scripts/phase7-ui-harness.cjs test                 # contratos de la fase
node 1.AXX/scripts/phase7-ui-harness.cjs shots docs/phase-7/screenshots after
node 1.AXX/scripts/test-desktop-frontend.cjs                  # contrato de frontend existente
python scripts/validate_companion.py --output build/companion-validation.json   # gate PC/móvil
```
