# 00 — Baseline comprobada y reglas de preservación

## 0.1 Autoridad de fuentes

**Repo de AXX revisado el 2026-11-21:** `luigilaxmaster-coder/AXX` en `main`, SHA `508bceabc718905db9bcf4042992d91f4c6c0705`. README: versión fuente y release publicada `0.22.52` (declaración de esa revisión). El equipo del propietario puede tener cambios locales o una instalación más reciente: verificar antes de editar.

Fuentes canónicas del propio AXX, en orden: `AGENTS.md`; `docs/mobile/COMPATIBILITY-PROTOCOL.md`; `docs/RELEASING.md`; `docs/UNIFIED-EXECUTION.md`; `docs/CHAT-WORKSPACE.md`; `docs/MAGIC-PEN-DESKTOP.md`; `docs/spatial-intelligence/IMPLEMENTATION-STATUS.md`; código y tests actuales. Este documento es una especificación complementaria; nunca anula la política del repositorio.

### Mapa verificado de responsabilidades

| Archivo/ruta existente | Responsabilidad observada | Qué **no** hacer |
|---|---|---|
| `src-tauri/src/` | Host nativo Tauri/Windows, captura, estado de superficie y entrada | Crear otra ventana de escritorio privilegiada no auditada |
| `backend/chat_store.py` | ChatStore, grupos, contexto, identidades, TTL de mensajes | Sustituir o migrar destructivamente `chat_conversations` |
| `1.AXX/scripts/chat-workspace.js` | UI actual Chats y grupos; autenticación host | Montar otra app de chat o cambiar IDs existentes |
| `1.AXX/scripts/agent-profile.js` | Perfil global, tono, herramientas preferidas | Reutilizar perfil global como almacén de todos los agentes |
| `backend/commands.py` + `backend/actions/executor.py` | Comandos tipados, permisos, efecto, comprobación | Dar herramientas directas al LLM sin CommandService |
| `backend/action_learning.py` | Procedimientos, planificación y acciones aprendidas | Duplicar la lógica de capacidades con otro motor separado |
| `backend/memory/skill_memory.py` | Skills y contexto versionado | Aceptar habilidad importada como ejecutable por sí sola |
| `backend/memory/task_memory.py` | Identidad/generación de memoria por tarea | Compartir memoria privada por un mero vínculo de bot |
| `backend/computer_use.py` | Grant/ticket y admisión efímera del control PC | Convertir el ticket en permiso persistente de agente |
| `backend/actions/desktop_input.py` | Entrada ligada a observación actual y ventana exacta | Inyectar entrada global desde un worker sin adjudicación |
| `backend/actions/browser_bridge.py` | CDP a navegador explícito en loopback | Conectar automáticamente al perfil personal predeterminado |
| `backend/actions/process_runner.py` | Ejecución revisada, Job Object, límites | Tratarlo como un sandbox de código arbitrario |
| `backend/actions/file_inspection.py` | Hash/inspección limitada | Usar scans sin scope y sin límite de tamaño |
| `backend/actions/file_workflows.py` | Descubrimiento/bundles verificados | Sobrescribir sin comprobar versión del destino |
| `backend/magic_pen.py` | Captura, visión, revisiones de Magic Pen | Reiniciar sesiones al convertir un chat en agente |
| `backend/presentation_plan.py` | Plan declarativo espacial validado | Generar/evaluar JS o Python de modelo en WebView privilegiada |
| `backend/shape_registry.py` | Catálogo de componentes técnicos | Confundir con formas visuales del avatar |
| `1.AXX/scripts/shape-library.js` | Exportación del catálogo técnico de partes | Usarlo como autoridad de formas del avatar |
| `1.AXX/scripts/spatial-scene.js` | Visor Three.js espacial | Mezclar versiones incompatibles de Three.js en el mismo contexto |
| `1.AXX/scripts/magic-pen.js` | UI captura/edición/visualización | Reemplazar controles, coordenadas o histórico existentes |
| `mobile/js/avatar-engine.js` | Catálogo móvil documentado de 24 formas y 9 paletas | Suponer correspondencia de índices con PC sin comprobar |
| `backend/inference/adapter.py` | Frontera de inferencia, cancelación, límites | Cambiar modelo/proveedor silenciosamente |

### Hechos específicos de compatibilidad

- `chat_store.py` define `chat_conversations`, `chat_messages`, `chat_groups`, `chat_context`, adjuntos, enlaces y preferencias. Mensajes y notas comunes del chat vencen a los **90 días**; la memoria de agente nueva no debe alterar ese contrato.
- `docs/CHAT-WORKSPACE.md` establece que los grupos comparten **solo notas compartidas expresamente**; los mensajes privados de otros chats no se incluyen. Se debe respetar revocación y renovación de IDs de Connect cuando cambia contexto.
- `docs/UNIFIED-EXECUTION.md` describe el circuito: `Chat/voz/Comandos/Axx Connect -> CommandService -> ActionExecutor -> adaptador -> verificador -> SQLite`. Los modos declarados incluyen `background` limitado, `foreground` y `isolated` **no disponible actualmente**. No se admite fallback entre modos.
- La ejecución persiste `running` **antes** de despachar. Tras interrupción puede quedar `unknown`; ni el mismo ID ni uno nuevo equivalente deben reemitir la mutación ciegamente. Cancelar no revierte efectos realizados.
- `backend/computer_use.py` concede entrada solo desde un grant explícito. Los procesos bloqueados, identificadores de ventana, PID y observaciones no se omiten para facilitar los nuevos agentes.
- El avatar original es una entidad de usuario. La identidad de agente nuevo es un *perfil* visual derivado del catálogo, no una sustitución del avatar aprobado. La especificación móvil enumera 24 formas/9 paletas; la compatibilidad exacta PC/móvil requiere prueba.
- OpenVINO puede ser proveedor opcional local, no sustituto automático de modelos 50B/100B ni garantía de rendimiento Iris Xe.

## 0.2 Reglas obligatorias de AGENTS.md

1. Autoría humana; no añadir `Co-authored-by` de IA, no cambiar identidad Git, no reescribir atribución.
2. En cambio de versión escritorio, sincronizar mediante `python scripts/release.py sync --version X.Y.Z`; nunca editar metadatos sueltos.
3. Seguir `docs/RELEASING.md`: build, instalar, verificar, push y publicación confirmada; un push no equivale a un lanzamiento.
4. `AGENTS.md` exige `python scripts/validate_companion.py --output build/companion-validation.json` sobre fuente integrada; el recibo correcto es requisito de publicar.
5. `/v1` tiene compatibilidad obligatoria: no retirar rutas, campos ni cambiar semántica. Versionar cambios incompatibles.
6. Mantener desktop/Android con versiones independientes, pairing/credenciales/IDs de operaciones intactos.
7. Respetar `mobile/design-baseline.json`; no refrescar hashes para hacer pasar una regresión visual. La autorización visual exige comparación y aprobación.
8. Nunca subir pesos de modelos, voces personales, claves, configuración privada ni estado runtime.

## 0.3 Inventario de no regresión (baseline obligatorio)

Ejecutar *antes* de cualquier parche y guardar: rama/SHA, estado de `git`, entorno Windows, logs, comandos, duración, stdout/stderr, capturas visuales aprobadas, datos de pruebas, latencia p50/p95 y hash de instalador verificado. No ejecutar una prueba instalada sin controlar el proceso/puerto y conservar la posibilidad de restaurar preferencias.

`git status --porcelain=v1`, `git rev-parse HEAD`, `git branch --show-current`, `python --version`, `node --version`, `rustc --version`, `cargo --version`, `pnpm --version` si procede. Las suites concretas están en `12_PRUEBAS_Y_ACEPTACION.md`; primero confirmar que las rutas aún existen.

## 0.4 Protección por área

- **Avatar/OrganicTendrils:** cámara, encuadre, contorno, materiales ópticos, hit mask, anclajes, estados, accesos radiales, memoria de posiciones, reacción a cursor, iconos y hotkeys son inmutables por defecto.
- **Magic Pen:** captura a DPI físico, lazo/rectángulo/punto, dibujo, historial, undo/redo, cancelación, metadatos de origen y proveedores elegidos intactos.
- **Voz/dictado:** ASR, VAD, TTS, interrupción, inserción de texto en apps, modelo de voz y selección de micrófono intactos.
- **Computer Use/CLI:** mismas autorizaciones, observaciones/leases, scopes, postcondiciones, idempotencia y logs.
- **Android/Telegram/Axx Connect:** scopes, identidad, rutas y privilegios conservados; no heredar permiso host por estar en el chat del agente.
- **Git y archivos:** no staging indiscriminado, no modificar `main`, no pisar trabajos de otras sesiones, no borrar archivos de usuario.

## 0.5 Fuentes vs objetivos

**Código fuente confirmado** no significa **aceptado en ejecutable real**. **Propuesta detallada** no significa **implementada**. **Librería MIT** no significa **assets de terceros libres**. **Cursor visual** no significa **múltiples cursores físicos reales**. **Contenedor** no significa **aislamiento seguro para cualquier amenaza**. Esta distinción es condición de los informes y las notas de release.
