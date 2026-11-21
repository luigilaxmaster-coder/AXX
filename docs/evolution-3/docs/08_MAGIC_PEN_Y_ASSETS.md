# 08 — Magic Pen Evolution: diagramas, CAD, animación, materiales, assets

## 8.1 Objetivo único

Convertir Magic Pen de selección/análisis + presentación conceptual en estudio de creación **editable, reversible y trazable**, conservando su UI y captura existentes. Un solo `MagicPenService` administra sesión; nuevos motores son modos/capacidades enchufados con contratos declarativos. La evolución se completa **antes** de activar Multi-Agent de producción.

## 8.2 Matriz de 10 fuentes upstream

| Proyecto | Aporte | Integración preferente | Riesgo |
|---|---|---|---|
| `obra/superpowers` | Plan/TDD/review/skills | workflows AXX y contratos de verificación | No integrar otro ejecutor |
| `cathrynlavery/diagram-design` | 51 estilos según README, HTML/SVG y templates | Diagram Studio y render editable desde AST | SVG no equivale a editor |
| `Kai-Jungsthoefel/SOMA` | CAD CadQuery/OpenCascade, STEP, secciones, planos, FEM | worker CAD independiente con implementación compatible | GPL-3.0, código arbitrario |
| `zeative/motion-educator` | Timeline determinista, cámaras, piezas, render vídeo | Motion Studio + render worker | dependencias vídeo/audio/licencia separadas |
| `codepawl/viz3d` | lecciones 3D (archivo archivado) | referencia sucesora `codepawl/creator-generalist` | código upstream archivado |
| `acher249/codevember-2026` | shaders, interacción, fluidos, PBD, WebGPU | material/physics adapter opcional | r187/TSL vs renderer existente |
| `openvinotoolkit/openvino` | Inferencia optimizada CPU/GPU/NPU | provider worker opcional | drivers/hardware, cuantización |
| `cobanov/pixelart-gaussiansplat` | estilos splat/pixel, conversiones | renderer alternativo de dioramas | modelos terceros excluidos |
| `codepawl/asset-gate` | MCP búsqueda GLB/LOD/tamaño/licencia | Asset Registry + descubrimiento external | modelo remoto/coste, licencias por asset |
| `sloemo01/diorama` | paleta pixel/toon, escenas deterministas, QA por entidad | Diorama render mode + QA de escenas | assets externos y carga GPU |

## 8.3 Scene Document v2

Un documento versionado declara `scene_id`, `revision`, `mode` (`diagram|cad|simulation|motion|material|diorama|conceptual`), coordenadas, unidades, fuente, objetos estables, relaciones, timeline, fidelidad y `artifact_refs`. Ver `schemas/scene-document-v2.schema.json`. Cada `geometry_ref` apunta a asset externo con sha256, mime, licencia y tamaño. No encerrar STEP/GLB en un JSON gigante.

**Fidelidad:** `illustrative` (intención visual), `conceptual` (aproximación explícita), `measured` (dimensiones declaradas/medidas con procedencia) y `cad_verified` (sólidos/constraints comprobados). Imagen aislada no autoriza `cad_verified`. La precisión exige unidades y tolerancias verificadas. `observed|documented|inferred|assumed` en objetos/medidas; jamás ocultar supuestos.

## 8.4 Edición incremental

`ScenePatch` incluye `document_id`, `base_revision`, `operation_id`, `target_object_ids`, `allowed_paths`, `changes`, `constraints` y `verify`. Aplicar solo si revision vigente coincide, IDs existen y propiedades autorizadas. Incrementar revision y guardar undo/redo como parches inversos cuando reversible. Mantener original inmutable y `source_revision`. Render invalidation por objeto/timeline, no reconstrucción completa. Si cambia STEP/GLB, generar nuevo hash y refs, no sobrescribir binario histórico.

## 8.5 Diagram Studio

- Modelo semántico de nodos, puertos, edges, groups, capas y constraints.
- Layout manual y auto, selección/mover/resize/editar etiquetas/crear conexiones, snapping, undo/redo y keyboard accessibility.
- Templates SVG/HTML de `diagram-design` como **referencias de estilo**, no convertir HTML no confiable en herramienta privilegiada.
- Import/export Mermaid, draw.io, PlantUML y Excalidraw solo con parsers comprobados; preservar errores y elementos no soportados de forma visible.
- Exportar SVG/PNG/PDF con tipografías disponibles, sin cortar etiquetas. QA geométrica (colisiones, bounds, overlaps) y visual.

## 8.6 CAD Studio

`GeometryTask -> validation -> isolated CadQuery/OpenCascade worker -> STEP + GLB preview + metadata + diagnostic report -> Magic Pen viewer`. Permitir parámetros, piezas, referencias, medidas, secciones, despieces, export STEP/STL/3MF/DXF/PDF según worker/contrato disponible. No ejecutar `runpy` del modelo en backend AXX. Someter cualquier interoperabilidad/copia de SOMA a revisión de GPL-3.0. FEM requiere solver y validación independiente de material, condiciones de contorno y unidades; etiquetar `engineering-unverified` hasta certificación. En un plano arquitectónico, diferenciar medidas ingresadas y estimadas.

## 8.7 Asset Gate + registro local

Pipeline: búsqueda Shape Registry local -> query MCP `search_assets` con licencia/tamaño/animación/LOD -> `get_asset` -> validación de URL/host/licencia, `asset_source`, crédito, dims, decoders, bytes/hashes -> caché content-addressed -> reuso en escena -> QA de límites/triangulos/materiales. Favorecer assets existentes. `generate_asset` del hosted gate no es infinito/gratis; función opt-in con presupuesto/configuración y aviso de uso de servicio externo. Guardar `asset_provenance` y `redistribution_allowed` por asset; CC BY exige créditos, CC BY-SA puede exigir condiciones adicionales, Fab/Megascans no se redistribuye por ser visible en índice.

## 8.8 Motion/Simulation Studio

De Motion Educator: storyboard y timeline determinista `freeze(t)` para render a tiempos exactos, segmentos re-renderizables, subtítulos y narración TTS local/externa autorizada, export de MP4. De viz3d: simulaciones interactivas con inputs tipados, estado reproducible y controls. La física ilustrativa no es FEM ni CFD verificadas. Guardar seed, frame_rate y asset hashes. Export worker remote solo con aprobación de transferencia de datos.

## 8.9 Material + Diorama + Splat

Codevember: técnicas de raymarch, metaballs, PBD tendrils, membranas, caustics, voxel erosion y touch; aplicar selectivamente, bajo perfil y prueba A/B; jamás reemplazar directamente OrganicTendrils o su anclaje por copia incompatible. Diorama: paleta, postprocess, stroke, props y animación determinista; renderer alternativo solo para **contenido** Magic Pen. Pixelart splat: look opcional, evitar usar en CAD de precisión. Three.js WebGPU/TSL debe aislarse del renderer local, no cargar dos revisiones Three mezcladas. Preferir import lazy, test detección WebGPU y fallback WebGL2/estático.

## 8.10 QA visual y performance

Captura de referencia original (perspectiva, cámara, geometría, materiales, DPI, objetos) -> generar escena -> QA de existencia de objetos, conexiones/poses, units, color/mat -> freeze frames a timestamps -> `frames.mjs` adaptado detecta elementos congelados, offscreen, teleport y cambios bruscos -> comparación de capturas con thresholds específicos -> FPS/RAM/GPU y liberación context WebGL al cerrar.

## 8.11 Seguridad/licencias

No cargar shaders HTML modelados como script privilegiado; pipeline de assets sin links peligrosos; evitar XML externos; empaquetar solo dependencias y recursos con derechos de distribución; no incluir los assets de Kervan que README de pixelart-gaussiansplat excluye de MIT. SOMA GPL requiere decisión legal si se usa código, y las librerías de geometría tienen licencias propias. TTS y música externa requieren licencias y presupuestos. Todos los assets guardan `sha256`, `license`, `origin`, `author`, `credit`, `attribution_scope`.

## 8.12 Gates por capacidad

- Diagram: nodos editables y SVG/PDF correctos sin clips.
- CAD: tests paramétricos, dimensiones y STEP realmente validado + preview GLB congruente.
- Motion: `freeze(t)` reproducible, MP4 reproducible y timestamps.
- Asset Gate: licencia/respuesta/LOD/decoders, no auto-descarga fuera de roots.
- Diorama: frames por entidad, cámara, animación y poster robusto.
- Material: mismo estado visual AXX cuando modo desactivado; no regresiones hitmask/tentacles.
- OpenVINO: modelo local realmente detectado, benchmark comparable, mismo proveedor manual preservado.
