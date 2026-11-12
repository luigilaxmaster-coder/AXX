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

## Etapa 2 · versión 0.22.47 y build oficial (fuente `bb15abb25f9f7c9c3f05c9ed5efee1eb35db40fe`)

Commits de esta etapa, en orden: `b962e26f` versión 0.22.47 (`release.py sync`,
notas `docs/releases/0.22.47.md`; `release.json` sigue en 0.22.46 hasta publicar),
`1cb87ce3` empaquetado del worker, `7b9b6ce9` ruta corta opcional, `bb15abb2`
compilación sin junction.

**Hallazgo de entrega:** `tauri.conf.json` y `build-windows.ps1` de producción no
empaquetaban `axx-dictation-asr.exe` (solo las configuraciones de candidata), de modo
que un instalador oficial habría mostrado el dictado sin su motor. Cambios aditivos:

- `tauri.conf.json`: recursos en forma de mapa, con el worker y las licencias de Handy/transcribe.cpp.
- `build-windows.ps1`: `cargo test` y `cargo build --release --locked` del worker; fuentes y licencias entran en `source_hashes`; el worker es el artefacto 4 (los índices 0-2 no cambian). `-WorkerTargetDirectory` opcional para checkouts profundos.
- `verify-installed-files.py` y `release.py`: verifican el worker y sus licencias instalados cuando el recibo declara sus fuentes; los recibos antiguos siguen siendo válidos. 34 PASS en `test_release.py` + `test_verify_installed_files.py` (2 tests nuevos).
- `transcribe-cpp-sys` compila a través de una junction `%LOCALAPPDATA%\tcs\<hash>`; con este MSBuild el chequeo del compilador de CMake falla (MSB1009) también con rutas cortas. Quitar `LOCALAPPDATA`/`TEMP` solo en los comandos cargo del worker lo evita (aislado: la misma compilación funciona en 2 min).

| Comprobación | Resultado |
| --- | --- |
| `release.py check` | PASS (v0.22.47) |
| Gate PC/Android sobre `bb15abb` (`build/companion-validation.json`) | PASS: 15 contratos, 113 servicio (1 omitida), 58 navegador, 8 selector |
| `build-windows.ps1` (`build/release-current/build-result.json`) | 6 pasos con salida 0; `source_tree_clean=true`; commit `bb15abb2…` |
| Rust host `cargo test --lib` | 27 PASS, 2 ignoradas |
| Worker ASR `cargo test --release` | PASS (dentro del build) |

| Artefacto | Bytes | SHA-256 |
| --- | --- | --- |
| `Axx_0.22.47_x64-setup.exe` | 202564324 | `6B8ABD2EC6990DE652963AE46534CC129C7234F90D85E28CB66B9D2ACB46F6C3` |
| `Axx.exe` (host) | 15721472 | `50C9251F0D56B8422D34E22A74C1ADC5B9175711927093DB410C2FB93BD416E4` |
| `axx-backend.exe` | 23239942 | `A2FF6C04F6272435969EE6D627991659675E1522A8CF620C74DB4EE5CD8FACC2` |
| `axx-dictation-asr.exe` | 3707392 | `688A9A5206D366F30582404EE7729FFFB53C3BDEE808916BB3FE1D3EFDE5367E` |

El worker y las licencias de dictado aparecen en `src-tauri/target/release/resources` con el
mismo hash. El contenido del instalador solo se comprobará al instalarlo
(`verify-installed-files.py`); aún no se ha ejecutado.

## Estado de la entrega: NO publicada, NO instalada

Bloqueos de release (no se fuerza nada, el AXX personal no se ha tocado; la instalación
personal registra 0.22.42 en el registro de Windows y 0.22.46 en `Axx.exe`, sin proceso Axx activo):

1. **Pruebas físicas del dictado** (voz humana, Bloc de notas y navegador, sin envío automático,
   cambio de campo, pausa/reanudación/cancelación, cierre del micrófono, convivencia con chat y
   comandos, reinicio, sesión prolongada y con música). No se han hecho ni se declaran aprobadas.
2. **Aceptación nativa WebView2 de la identidad productiva:** los scripts existentes son privados
   de la candidata `com.axx.integration678` (`build/integration/` del worktree de Codex) y no se
   reutilizan sin adaptarlos; instalar la identidad productiva en un directorio de prueba
   sobrescribiría el registro de desinstalación del AXX personal.
3. **Copia de seguridad, preservación de datos y rollback** antes de `install-verified-windows.ps1`
   (cierra Axx e instala sobre `%LOCALAPPDATA%\Programs\Axx`); el recibo `installed-runtime.json`
   no existe, por lo que `release.py publish` (también `--dry-run`) no puede ejecutarse.
4. `main` no se integra: la publicación exige `main` limpio y sincronizado tras los puntos anteriores.

Siguiente paso: pruebas físicas sobre la candidata ya instalada
(`C:\Users\luigi\.codex\worktrees\axx-phase-7-finish\axx2\build\integration\installed`, mismo
código funcional) o sobre esta versión tras hacer copia de seguridad. Con la aprobación del
dictado: copia de seguridad → cierre de Axx → `install-verified-windows.ps1` → aceptación
nativa → `release.py publish --dry-run` → merge a `main` → publicación.
