# 07 — AXX Code Studio: editor integrado, agentes, Git, LSP y debugger

## 7.1 Alcance y estrategia

AXX debe poder comprender, editar, probar, depurar, revisar y versionar código propio o de un proyecto aprobado. En su evolución inicial **no** construirá una bifurcación completa de VS Code. Elegir `Monaco Editor` (MIT) para el área de edición, `monaco-languageclient` y servidores LSP para IDE semántico, `tree-sitter` para parsing estructural, Git worktree para aislamiento, `Debug Adapter Protocol` con adaptadores instalados para depurar, y un `PatchEngine` propio ligado a CommandService. `Eclipse Theia` queda como alternativa Pro bajo demanda si las características avanzadas superan el coste de integrar componentes individualmente.

### Referencias

- `microsoft/monaco-editor`: edición basada en navegador. **Extensiones de VS Code no son plug-and-play** en Monaco.
- `TypeFox/monaco-languageclient`: comunicación editor <-> LSP.
- `microsoft/vscode-languageserver-node`: implementación/infraestructura LSP.
- `tree-sitter/tree-sitter`: parsing incremental y gramáticas versionadas.
- `microsoft/debug-adapter-protocol`: contrato DAP, sin depuradores universales incluidos.
- `OpenHands/software-agent-sdk`: agentes de software con herramientas filesystem/terminal/workspace y runs.
- `Aider-AI/aider`: repomap, edición incremental, Git, tests, lint.
- `anomalyco/opencode`: planes/agent build, motor opcional de agente CLI; no darle acceso paralelo directo al host sin adaptar permisos.
- `eclipse-theia/theia`: IDE extensible y Theia AI, condicionado a peso y licencias.
- `continuedev/continue`: referencia histórica; repo declara sin mantenimiento activo, no usar como dependencia principal.

## 7.2 UI y workflows

UI principal: Explorador de archivos, Monaco editor con tabs, explorador de símbolos, búsqueda global, minimapa opcional, diff, panel Problems, terminal controlada, Git (branches/diff/commit/review), tests, debugger, preview, Activity y conversación contextual con agente. Paneles se pueden sacar desde avatar y mover/guardar posición; no reemplazar UI radial de AXX. El IDE no se inicia al arrancar app; lazy load con control de RAM/WebGL.

Flows: `abrir repo` -> `escoger carpeta autorizada` -> `indexar` -> `análisis` -> `proponer patch` -> `mostrar diff` -> `aplicar a worktree` -> `lint/tests` -> `solicitar revisión` -> `integrar`, o flujo interactivo humano guardando directamente archivos propios con confirmación de conflicto.

### Modos de agente Code Studio

`plan` = read-only y análisis; `edit` = patch limitado a worktree; `test` = ejecutar herramientas aprobadas en worker; `review` = comprobación independentemente de generación; `merge` = requerir gate de integración. No aplicar los permisos permisivos del CLI externo directamente a host.

## 7.3 Editor Monaco

- Cargar monaco desde bundle fijo local, sin CDN ni `eval` de contenido remoto.
- No abrir archivos binarios como texto; detectar BOM/UTF-8/UTF-16, fin de línea CRLF/LF, tamaño y exclusiones.
- Soportar archivo grande mediante modo solo lectura/degradado; avisar claramente de truncamiento.
- Documento con `file_version`, dirty flag, `original_sha256`, etag, encoding, line endings.
- Autosave manual/optional, protegida con CAS y verificación de disco. `Save conflict`: diff 3-vías/descartar/copia nueva, nunca pisar el archivo en silencio.
- CSP restrictiva; editor y terminal nunca comparten credenciales crudas. Bloquear HTML emitido en diagnósticos como scripts.

## 7.4 Language Server Protocol

`LanguageServerManager`: `discover` -> `authorize` -> `spawn with workspace root` -> `initialize capabilities` -> `didOpen/change/save` -> diagnostics/completion/definition/references/rename -> `shutdown`. Múltiples workspaces deben crear sesiones separadas. Un servidor de lenguaje es código ejecutable de terceros: requerir instalación autorizada, hash/version, `cwd` permitido y no crear LSP arbitrarios desde archivos del repo sin revisión.

Inicialmente soportar sintaxis de Python, JS/TS, Rust, JSON y HTML/CSS, con nivel de servicio reportado: sintaxis básica disponible, LSP instalado, LSP probado, depuración disponible por lenguaje. No afirmar funcionamiento completo de todos los lenguajes.

## 7.5 Code Intelligence

Parser incremental Tree-sitter para símbolos/imports/estructuras, combinado con `ripgrep` o búsqueda equivalente y mapa de dependencia. Capa semántica del IDE busca referencias mediante LSP cuando disponible; el AST no sustituye tipos ni compilación. `RepositoryMap` indexa dentro de raíces autorizadas y respeta `.gitignore`, excludes, archivos demasiado grandes, patrones de secreto y política de contenido. Índice `path, commit, sha256, language, definitions, refs, last_analysed`, con invalidación por FS watcher y fallback rescan limitado. No enviar repo completo al proveedor sin scope/permiso.

## 7.6 Git y worktrees

- `GitWorkspaceService` reconoce `.git`, commits, HEAD, status, upstream, branch lock y submódulos, y no modifica `.gitconfig` global.
- Crear `git worktree add -b axx/agent/<id>/<task> <path> <base>` después de comprobar conflictos de rama/path y espacio disponible.
- Cada agente de escritura usa worktree distinto; el usuario conserva su directorio principal intacto.
- Tests y builds se ejecutan en el worktree del agente. Integra solo mediante revisión de diff, verificaciones de artefactos y autorización.
- Branches, cambios y archivos no rastreados de usuario nunca se descartan sin confirmación. Evitar `git reset --hard`, `git clean -fd`, force push o rebase destructivo.
- Merge/adopción: rebase/merge en integración controlada con detección de conflictos, pruebas repetidas, autoría Git conforme `AGENTS.md`.
- El `AgentChangeSet` guarda hash antes/después, archivos afectados, diff por hunks, línea/base_ref, tests, violaciones de scope y approve receipt.

## 7.7 Patch Engine: contrato

`PatchProposal` es dato no ejecutable; `PatchEngine` valida `workspace_id`, `path`, `base_sha256`, codificación, `expected_hunks`, ausencia de traversal/reparse, conteo de archivos, tamaño, texto propuesto y cambios concurrentes. Aplica patch mediante temporal + fsync + rename donde sea aplicable y registra recibo, sin abrir transacción larga durante I/O. Devolver resultado claro `applied`, `conflict`, `permission_denied`, `stale_revision`, `unsupported_encoding`, `partial_failure`.

Ejemplo de patch en `schemas/code-changeset.schema.json`. No aceptar inyecciones del modelo que alteren schema, tests o rutas de trabajo sin revisión. Archivos generados no se marcan automáticamente confiables por estar dentro del worktree.

## 7.8 Terminal, tests, sandbox

**Distinción fundamental:** `backend/actions/process_runner.py` ya permite ejecución revisada de `.exe` en `cwd`, con Job Object y límites, pero declara que **no es sandbox ni generador de código**. Para que el agente ejecute scripts arbitrarios necesitará un `CodeWorker` con aislamiento real según riesgo, o un proceso de construcción aprobado y limitado. Whitelist de ejecutables de toolchain y argumentos tipados, no shell libre inherente al perfil.

`TestRunner` produce `test_id, command_ref, env_fingerprint, timeout, exit_code, stdout_hash, stderr_hash, test_counts, artifact_refs, verification_scope`. Un 0 exit solo verifica la orden, no que toda app esté correcta. `FailureClassifier` permite replanificar después de error de compilador/linter con máximo de intentos y diff controlado. Deploy y cambios en nube requerirán autorizaciones separadas.

## 7.9 Debug Adapter Protocol

`DebugAdapterManager` selecciona el adaptador disponible para lenguaje, crea sesión, mapea `sourceReference`, breakpoints, pila, variables, step in/out y stop. No exponer listeners DAP a red pública. Debug de procesos de usuario fuera del worktree necesita autorización. Evaluaciones en debugger pueden ejecutar código: policy explícita; no permitir `evaluate` de una cadena LLM sin revisión de riesgo.

## 7.10 AI context y aprendizaje

El agente puede usar selección de líneas, logs, AST, LSP, tests, documentación y conversación. Sus resultados generan conocimiento referenciado por SHA/revisión y scope. Al cambiar un archivo se invalidan recomendaciones obsoletas. Superpowers define checks de plan/TDD/review; SkillMemory persiste procedimientos demostrados. Prompts y herramientas pueden proponer arreglos, pero un passing test **es evidencia específica**, no garantía de calidad universal.

## 7.11 Extensión con Magic Pen

Seleccionar función -> dibujar flecha -> pedir explicación -> Scene Document/Diagram Studio muestra arquitectura. Seleccionar UI en pantalla -> localiza componente de código por trazabilidad registrada (si existe) -> propone cambio en worktree -> preview/diff -> pruebas. Sin índice fiable no fingir correspondencia screenshot -> archivo. Generación visual de un componente no implica código de producción sin tests.

## 7.12 Pruebas obligatorias

- Guardar en UTF-8 CRLF conserva finales; conflicto si usuario modifica archivo fuera; preview no es commit.
- Dos worktrees escriben misma ruta semántica en branches distintas sin pisar local; merge detecta conflicto.
- LSP tarda, se cuelga o muere; Monaco continúa con modo sintaxis y mensaje de error.
- Un `README.md` malicioso no obtiene ejecución ni secret tools.
- DAP reinicia, breakpoints siguen ligados al proyecto correcto, eval desautorizado bloqueado.
- Terminal no ejecuta path no permitido, interrumpe proceso árbol al cancelar, no confunde 0 exit con prueba de app.
- Git push y PR exigen grant externo; generar diff local no publica.
- Instalador Windows abre Code Studio, edita y recarga archivo real, detecta cambio de ruta, mantiene avatar fluido y micrófono usable.
