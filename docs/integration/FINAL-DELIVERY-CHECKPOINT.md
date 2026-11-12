# AXX · checkpoint de entrega final

Fecha: 2026-11-12. Rama de trabajo: `claude/axx-final-unified-release`
(worktree `axx-final-unified-release-17f0e9`). Revisión propia de Claude.

## Etapa 0 · estado real verificado

| Referencia | SHA completo |
| --- | --- |
| `main` local y `origin/main` (v0.22.46 publicada) | `dfe3d5a27e2830eb7cf1cb3a2aa0707d4e117dc4` |
| Integración 6+7+8, base de esta rama | `4ed8fc476082e1d53aef8462aa1fd21cf09f9e80` |
| Claude Fase 7, último diseño (no modificada) | `1dcc89aa5c6963c388ec97dde27c07c4b0313c73` |
| Fase 6 (`claude/axx-phase-6`) | `a750362` |

- `dfe3d5a` es ancestro de `4ed8fc4`; la rama nueva avanzó por fast-forward
  (sin merge ni commits propios previos). Ninguna rama de Claude ni de Codex
  fue modificada ni borrada.
- Última versión de escritorio publicada en GitHub: **0.22.46**
  (`gh release list`). La siguiente disponible es **0.22.47**.

## Etapa 1 · reconciliación de `1dcc89a` con la integración

Comparación de `phase7-ui.js`, `phase7-ui.css`, `phase7-ui-harness.cjs` y
`Axx.html` entre `1dcc89a` y `4ed8fc4`:

| Área | Resultado | Decisión |
| --- | --- | --- |
| Agrupación interior de Forma y materiales | Código idéntico en ambas ramas | Conservar la integración |
| Contornos del chat claro (1 px interior, foco de 2 px) | CSS idéntico; la integración añade solo reglas del grupo de dictado | Conservar la integración |
| Anchuras y posiciones de Personalizar AXX | `1dcc89a` guarda en RAM el tamaño visible (`panelPositions['panel:'+entry]`) al cambiar de pestaña. La integración (`234ffa8` + `Axx.html`) usa la clave de layout efectiva y **no escribe nada** al navegar. | Conservar la integración: su test exige que ni `localStorage` ni `panelPositions` cambien, y añade un test de layouts guardados distintos, redimensión, arrastre y recarga |
| Navegación, scroll y persistencia | La integración prueba además `appearance` sin desbordamiento horizontal (en `1dcc89a` estaba excluida por 19 px) | Conservar la integración |

**No se aplicó ningún cambio de código de `1dcc89a`**: la integración contiene
todos sus ajustes con comprobaciones más estrictas. Solo quedaron fuera las
capturas de `docs/phase-7/screenshots` de esa rama (no se mezclan: describen
una versión sin el panel de dictado) y su fragmento de caché en RAM, que
contradice el contrato de la integración. Handy, ASR, WASAPI, atajos, chat,
permisos, backend, Android/Telegram y el renderizador del avatar no se tocaron.

## Etapa 1 · validación (fuente `4ed8fc4`, sin cambios de código)

Registros en `build/final/` (local, no versionado).

| Comprobación | Resultado |
| --- | --- |
| Harness de diseño Fase 7 (`phase7-ui-harness.cjs test`) | PASS, todas las comprobaciones |
| Dictado JS: engine, global-runtime, dictation-runtime | PASS (3/3) |
| UI: desktop-frontend, chat-usability, chat-groups, chat-workspace, composer-tools, command-library, sound-runtime, computer-use, quick-reply, mission-attention-integration, document-provenance, browser-runtime, tendril-geometry, magic-pen | PASS (14/14) |
| Python: actions 41, connect 130 (1 omitida), inference 166, memory 2, mobile 112 (1 omitida) | PASS |
| Python `backend/tests` subconjunto chat/memoria/comandos/MCP/Telegram/ASR/dictado/proveedores/Fase 6 | 440 PASS, 1 omitida, 1 FAIL intermitente (ver nota) |
| Los cinco fallos históricos (tools-interaction L75, providers L148, skills ENOENT, capability-workshop, goal-cycle) | Siguen fallando con la misma firma que el baseline; ninguna regresión nueva |

Notas honestas:

- Primera pasada de varias suites falló por entorno (Chromium de Playwright
  1234 ausente en un worktree nuevo; suites en paralelo con los tests Python y
  timeouts). Con `AXX_TEST_CHROMIUM` apuntando al headless shell 1248 y sin
  carga concurrente, pasan; no se modificó ningún test.
- `test_command_library::test_pre_dispatch_rejection_...` falló una vez bajo
  carga y pasa aislado y con el archivo completo (17 PASS). No se atribuye a
  este cambio porque no hay cambios de código; queda anotada como intermitente.
- `pytest backend` de una vez falla en la colección por dos `test_task_memory.py`
  homónimos (artefacto de pytest, no de código). `backend/tests` completa se
  interrumpió tras más de 20 min sin salida; se usó el subconjunto relevante.
- Rust: `cargo test --lib` exige `resources/axx-backend.exe`, que solo existe
  tras la compilación del backend; se ejecuta en la etapa de build.
- Gate PC/Android: el último PASS conocido (15/113/58/8) es de `bb52322`. Se
  vuelve a ejecutar sobre la fuente final de la versión nueva.
