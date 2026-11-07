---
name: axx-command-computer-use
description: Audita, repara o amplía comandos escritos/de voz, Computer Use visual, proveedores de visión y conexiones MCP/aplicaciones de Axx. Invócalo para tareas sobre command resolver, acciones de escritorio, browser/Spotify/YouTube, modelos locales con imagen o herramientas MCP.
---

# Integrar comandos y Computer Use de Axx

Aplica también el skill `/ponytail`: limita contexto y diff de forma disciplinada, sin omitir pasos, regresiones, permisos ni validación nativa que la tarea requiera.

## Procedimiento obligatorio

1. Lee `AGENTS.md`, `CLAUDE.md` y `CLAUDE-TAREA-COMANDOS-COMPUTER-USE-VISION.md`. Lee también `1.AXX/AGENTS.md` si tocas frontend; si una carpeta tiene instrucciones más específicas, léelas.
2. Inspecciona `git status`, ramas y diffs antes de editar. No limpies ni reviertas cambios preexistentes. Anota los archivos que ya estaban modificados y no los atribuyas a esta tarea.
3. Traza la ruta concreta que se va a cambiar: entrada de texto/voz → normalización y resolución → comando y esquema → permisos/precondiciones → `CommandService`/`ActionExecutor` → adaptador → postcondiciones/recibo → estado visible de UI. Busca todos los callers antes de cambiar una interfaz compartida.
4. Revisa las implementaciones y pruebas vigentes en `backend/actions/`, `backend/commands.py`, `backend/computer_use.py`, `backend/computer_vision.py`, `backend/inference/`, `backend/connect/`, `backend/mcp_host/` y `1.AXX/scripts/`. No uses una skill o documento como prueba de runtime.
5. Cambia la causa raíz en la capa común y añade regresiones para el caso fallido y sus bordes: negación, citas, ambigüedad, contenido literal, parámetros, cancelación y timeout después del despacho.
6. Reutiliza `CommandService`, `ActionExecutor`, `backend/computer_use.py`, el broker único de entrada, `backend/mcp_host` y los toggles por herramienta existentes. No introduzcas otro parser principal, ejecutor, inyector de entrada o lista paralela de herramientas.
7. En MCP, valida endpoint, transporte, esquema y cada herramienta. Mantén defaults apagados, secretos fuera de frontend y autorización separada de la disponibilidad técnica. Una mutación remota requiere readback independiente para considerarse comprobada.
8. En Computer Use, valida soporte real de imagen y tools por conexión/modelo; verifica los requests en esa ruta. Usa capturas autorizadas y efímeras, identidad HWND/PID/instancia actual, observación fresca, geometría/DPI y postcondición específica. Estado incierto implica detenerse y no repetir.
9. Ejecuta pruebas offline pertinentes antes de pruebas nativas. Distingue `ESPECIFICADO`, `IMPLEMENTADO_LOCAL`, `INTEGRADO_DEV` y `VALIDADO_WINDOWS`. No uses fixtures para afirmar aceptación física.
10. Entrega resumen de causa raíz, cambio, pruebas con resultado, compatibilidad por proveedor/modelo/app y límites o aceptación física pendiente.

## Fuentes del proyecto

- Comandos: `docs/COMANDOS-DESDE-CHAT.md`, `docs/VOICE-COMMAND-LANGUAGE.md`, `backend/actions/command_language.py`, `backend/commands.py`, `backend/actions/desktop.py`, `1.AXX/scripts/command-library.js`.
- Ejecución: `docs/UNIFIED-EXECUTION.md`, `backend/actions/executor.py`, `backend/actions/tools.py`.
- Computer Use y privacidad visual: `docs/COMPUTER-USE.md`, `backend/computer_use.py`, `backend/computer_vision.py`, `backend/actions/computer_tools.py`, `backend/actions/desktop_input.py`, `1.AXX/scripts/computer-use.js`.
- Proveedores/visión: `docs/PROVEEDORES-API-LOCAL.md`, `docs/PROMPT-CONTRACTS.md`, `backend/inference/`, `backend/connect/provider.py`, `1.AXX/scripts/model-profile.js`, `backend/magic_pen.py`, `1.AXX/scripts/magic-pen.js`.
- MCP: `docs/MCP-LOCAL.md`, `backend/mcp_host/`, `backend/connect/registry.py`, `backend/commands.py` y los tests de MCP.
- Extensiones y seguridad de comandos: `docs/COMMAND-EXTENSIONS.md`, `docs/GENERATED-COMMANDS.md`, `backend/actions/process_runner.py`, `backend/actions/application_tools.py`.

## Criterios no negociables

- “Modelo declara visión” no significa que Axx le envíe una imagen. “Modelo vio una imagen” no significa que pueda llamar herramientas. Prueba ambas cosas y luego una acción inocua con readback.
- Gemma 4 31B es una preferencia/candidato del propietario. Confirma ID, proveedor/runtime, memoria disponible, modalidad de entrada y tool calling; no inventes disponibilidad ni bajes un modelo automáticamente.
- Permitir abrir una app concreta no concede permiso global para shell, scripts, compras, envíos, borrados o cambios externos. Acciones de impacto requieren confirmación específica.
- Búsqueda de Spotify/YouTube y reproducción son capacidades distintas. Abrir navegador o app no prueba que la tarea se completó.
- Preserva `/v1`, pairing/credenciales/grants, identidad visual, `mobile/design-baseline.json` y evidencia local. No publiques secretos, capturas, voces ni pesos.
- No agregues trailers `Co-authored-by` de IA.
