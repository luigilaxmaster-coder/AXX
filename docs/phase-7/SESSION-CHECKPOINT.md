# Fase 7 · Checkpoint de sesión

> Leer junto con `AGENTS.md` al reanudar. No resetear el árbol. No repetir lo ya verificado.

## Estado Git
- Worktree: `C:\Users\luigi\Desktop\axx2\.claude\worktrees\axx-phase-7-ui-09978b` (independiente; no es el árbol de Codex).
- Rama: `claude/axx-phase-7-ui`. La rama `claude/axx-phase-7-ui-09978b` con la que nació el worktree sigue intacta en `dfe3d5a`.
- Commit base: `a750362` (informes Fase 6). Código validado Fase 6: `4f4e18b`, ancestro de `a750362` (verificado; la diferencia es `docs/phase-6/*` y el fixture de `test-providers.cjs`).
- `main` = `dfe3d5a` (12 commits por detrás de la base). No se ha tocado. Sin push, sin publicación, sin instalación.
- HEAD: el último commit de `git log --oneline a750362..HEAD`. Debe haber 5 o más commits de la fase y el árbol limpio (salvo `build/`, ignorado).
- Los commits no llevan trailer `Co-authored-by` (regla de la skill ponytail del proyecto); se retiró de los dos primeros con `git filter-branch` antes de cualquier push.

## Objetivo
Reorganizar el INTERIOR de Sistema y datos, IA y proveedores y Personalizar AXX; conservar el tema claro, corregir controles poco visibles y mejorar el oscuro.

## Arquitectura (vigente)
Capa de presentación que se carga la última y **mueve** nodos existentes (nunca los clona): `1.AXX/scripts/phase7-ui.js` + `phase7-ui.css`. `Axx.html` cambia en 6 líneas (ver `CODEX-HANDOFF.md`). Ningún archivo protegido por `mobile/design-baseline.json` se edita.

## Incrementos
| # | Incremento | Estado | Documento |
|---|---|---|---|
| 1 | Auditoría, inventario, baseline | hecho | `UI-AUDIT.md` |
| 2 | Sistema y datos | hecho | `SYSTEM-DATA-REDESIGN.md` |
| 3 | IA y proveedores | hecho | `AI-PROVIDERS-REDESIGN.md` |
| 4 | Personalizar AXX | hecho | `PERSONALIZATION-UNIFICATION.md` |
| 5 | Temas claro/oscuro | hecho | `THEME-QA.md` |
| 6 | Pruebas, capturas, handoff | hecho | `REGRESSION-RESULTS.md`, `CODEX-HANDOFF.md` |

## Archivos de la fase
- nuevos: `1.AXX/scripts/phase7-ui.js`, `phase7-ui.css`, `phase7-ui-harness.cjs`, `phase7-control-baseline.json`, `docs/phase-7/*`
- modificado: `1.AXX/Axx.html` (6 líneas)

## Últimas pruebas
Ver `REGRESSION-RESULTS.md` (fecha 2026-11-11).

## Pendiente / no verificado
- Aceptación nativa en WebView2 empaquetado (no se construyó ni instaló candidato: restricción de la fase).
- `scripts/test-installed-appearance.cjs` necesita una instalación; su contrato (tema visible en `settings`) se cubre con una prueba equivalente en el arnés.
- Teléfono/Android: sin cambios en `mobile/`; solo se ejecutó el gate de compatibilidad.
- El panel cambia de tamaño entre pestañas de Personalizar AXX (anchos por vista preexistentes).

## Dependencias de Codex
Ninguna. Ver `CODEX-HANDOFF.md`.

## Próxima operación concreta
Revisión del usuario. Después, y solo si lo pide: construir un candidato aislado (como en Fase 6) y ejecutar la aceptación nativa.

## Comandos para retomar (desde la raíz del worktree, Git Bash)
```bash
git status -sb && git rev-parse --short HEAD && git log --oneline a750362..HEAD
export AXX_TEST_CHROMIUM="$LOCALAPPDATA/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe"
node 1.AXX/scripts/phase7-ui-harness.cjs test                                   # contratos de la fase
node 1.AXX/scripts/phase7-ui-harness.cjs contrast                               # contraste claro/oscuro
P7_EXTRA=voices,chat node 1.AXX/scripts/phase7-ui-harness.cjs shots docs/phase-7/screenshots after
node 1.AXX/scripts/test-desktop-frontend.cjs && node 1.AXX/scripts/test-providers.cjs
python scripts/validate_companion.py --output build/companion-validation.json   # gate PC/móvil
```
