# 15 — Repositorios, componentes, licencias y criterios de adopción

## 15.1 Clasificación

**Integrar código** solo si license, transitive deps y arquitectura compatibles; **adaptar ideas** cuando el framework es demasiado distinto; **interoperar** cuando aplicación/licencia obliga a separación; **no integrar** si peso/riesgo supera beneficio. MIT/Apache del repositorio no cubren por sí mismos fotos, packs, modelos convertidos, TTS, datasets o servicios comerciales. Cada asset tiene propia procedencia.

| Repo | Licencia declarada / estado (cuando verificado) | Aporta | Decisión |
|---|---|---|---|
| `obra/superpowers` | MIT | methodology/skills/TDD/review | Adaptar a SkillMemory/ActionLearning |
| `cathrynlavery/diagram-design` | MIT | 51 estilos, SVG HTML, scripts | Incorporar patrones, parser/QA selectivos |
| `Kai-Jungsthoefel/SOMA` | GPL-3.0 | CadQuery/OCCT, STEP, DXF, FEM | No copiar a AXX MIT sin revisión GPL; worker/interop |
| `zeative/motion-educator` | MIT en código raíz | timeline deterministic y films | Adaptar worker/timeline, revisar GSAP/audio |
| `openvinotoolkit/openvino` | Apache-2.0 | inferencia Intel | proveedor opcional probado |
| `acher249/codevember-2026` | MIT en proyecto | shaders y PBD, Three/WebGPU | técnicas seleccionadas + licencia assets |
| `cobanov/pixelart-gaussiansplat` | MIT código, ciertos modelos excluidos | splats, surfels, estilos pixel | renderer opcional sin modelos excluidos |
| `codepawl/viz3d` | MIT, archivado | lecciones 3D | referencia sucesora `creator-generalist` |
| `codepawl/asset-gate` | MIT code | GLB, dimensiones, LOD, licencia, MCP | adapter catalog con licencia por asset |
| `sloemo01/diorama` | MIT | procedural diorama, QA, pixel/toon | render mode opcional |
| `milind-soni/OpenMausBot` | Apache-2.0 | bots, harness, event fan-in, broker | adoptar conceptos, no runtime paralelo |
| `CopilotKit/OpenDots` | MIT, alpha | Spaces, runs, HITL, AG-UI | patrones UX, no Intelligence obligatorio |
| `CopilotKit/OpenBot` | verificar licencia/version antes de importar | plataforma agentes más mantenida | referencia adicional |
| `trycua/cua` | MIT | computer use drivers/VM/backend | adapter opcional tras prueba Windows |
| `alstonmendonca/openMouse` | MIT, alpha | Windows multi-pointer experimental | investigación, no base de independencia |
| `microsoft/winappCli` | MIT, public preview | UI Automation/sandbox/SDK Windows | referencia e integración selectiva |
| `microsoft/monaco-editor` | MIT | editor WebView | editor Code Studio Lite |
| `TypeFox/monaco-languageclient` | MIT | LSP client | Code Studio LSP |
| `microsoft/vscode-languageserver-node` | MIT | LSP tooling | servidores/adaptadores |
| `tree-sitter/tree-sitter` | MIT | parser incremental | indexador codebase |
| `microsoft/debug-adapter-protocol` | verificar archivos individuales | especificación DAP | protocolo, adaptadores aparte |
| `OpenHands/software-agent-sdk` | MIT | agentes de código/entornos | referencia y posible SDK worker |
| `OpenHands/OpenHands` | MIT | app/computadoras | referencia de integración y UX |
| `Aider-AI/aider` | Apache-2.0 | git diffs/test/lint/repomap | técnicas de Code Studio |
| `anomalyco/opencode` | MIT | agent CLI + modelos | motor opcional bajo policy |
| `eclipse-theia/theia` | EPL-2.0 | IDE extensible/Theia AI | evaluar como Code Studio Pro separado |
| `continuedev/continue` | Apache-2.0, README indica read-only | agent coding | referencia histórica, NO dependency nueva |
| `microsoft/playwright` | Apache-2.0 | navegador/pruebas | browser worker/test |
| `browser-use/browser-use` | MIT | browser agents | estudio/adapter opcional |

**Advertencia de fuentes:** las licencias declaradas de la tabla se basan en inspección GitHub en esta investigación o en la revisión previa; deben confirmarse nuevamente en el SHA exacto importado. El manifiesto `records/upstream-lock.json` distingue commits verificados y upstreams pendientes. No atribuir licencia global a media externa.

## 15.2 Directrices por upstream

**Asset Gate:** endpoint MCP HTTP alojado y stdio local; `search_assets/get_asset/list_sources/find_elsewhere`, generación alojada opcional. Registrar `license`, `credit_line`, size en metros solo cuando fuente lo conozca, decoders, SHAs de binario descargado; Quixel/Fab solo enlaces, no redistribución. No confundir índice de assets con biblioteca descargada al instalador.

**OpenMausBot:** su harness usa registro de drivers y EventBus; su default de permisos puede diferir del AXX. Extraer conceptos de routing/team/approvals, no clonar su servidor Electron ni presuponer acceso completo por defecto.

**OpenDots:** AG-UI y CopilotKit Intelligence son dependencias configuradas para sus conversaciones; AXX mantendrá su ChatStore y provider router, tomando patrones de HITL, Spaces y agent computers. OpenBot es referencia para auditoría y permisos por bot, no dependencia obligatoria.

**Cua/Mouse:** Windows multiinput es parcialmente experimental. Cua background por acción debe verificarse sobre aplicación y versión reales; `openMouse` no ofrece segundo teclado y foco completos en misma sesión Windows. La independencia robusta es VM/navegador separados o APIs, no pintar punteros.

**SOMA:** GPL puede introducir obligaciones si hay distribución de código derivado/combinado. No copiar `python/soma/build.py` ni `drawing.py` al árbol MIT sin revisión legal; para geometría preferir contratos propios y componentes con licencias evaluadas, o invocar app instalada separada bajo sus términos. Los modelos CAD generados tienen información de origen y precisión; no son ingeniería certificada automáticamente.

**Diorama/Codevember:** tres.js versiones/requisitos WebGPU pueden diferir. Evitar importar demos React enteras al renderer de AXX; separar bundle/contexts y adaptar shaders selectivos. QA de per-entity freeze/timeline sí se puede reproducir. Fuentes de texturas/fotos deben auditarse individualmente.

## 15.3 Cadena de custodia de código y assets

Por cada dependencia/archivo importado guardar: upstream repo, URL/commit/ref, path/sha256, licencia verificada, copyright/avisos, dependencias transitorias, propósito, superficie de permisos, tests, versión, razón de adopción y procedencia de assets. Verificar vulnerabilidades y SBOM. No seguir branch `main` dinámicamente en builds de publicación: usar lock con commit exacto y digest.

## 15.4 Fuentes primarias de AXX

- <https://github.com/luigilaxmaster-coder/AXX/blob/main/AGENTS.md>
- <https://github.com/luigilaxmaster-coder/AXX/blob/main/docs/UNIFIED-EXECUTION.md>
- <https://github.com/luigilaxmaster-coder/AXX/blob/main/docs/CHAT-WORKSPACE.md>
- <https://github.com/luigilaxmaster-coder/AXX/blob/main/docs/MAGIC-PEN-DESKTOP.md>
- <https://github.com/luigilaxmaster-coder/AXX/blob/main/docs/mobile/COMPATIBILITY-PROTOCOL.md>
- <https://github.com/luigilaxmaster-coder/AXX/blob/main/docs/RELEASING.md>

**Conclusión de adopción:** este inventario es una lista de fuentes útiles, no un mandato para instalar paquetes globales. Primero integrar comportamientos y contratos que puedan verificarse con el AXX real, y luego solo dependencias necesarias.
