# 03 — Agent Designer y evolución de Chats y grupos

## 3.1 Principio de migración UX

El usuario pidió que cada chat pueda funcionar como un agente **sin abrir una aplicación ni un chat artificial separado**. Implementación: `conversation_id` conserva su identidad y se le añaden N enlaces `chat_agent_memberships`; el chat sigue renderizándose por `chat-workspace.js`. Cada agente puede participar en N conversaciones; su memoria no concede acceso cruzado a otros hilos.

**Prohibido:** crear una nueva colección independiente de conversaciones y trasladar mensajes a ella. El modelo será `AgentProfile (1..N) <-> ChatConversation (0..N)` mediante memberships. El perfil global actual (`agent-profile.js`) sigue controlando el AXX principal; crear un nuevo agente crea perfil separado, no actualiza global.

## 3.2 Agent Designer: tabs y campos

| Pestaña | Campos | Validación |
|---|---|---|
| Identidad | nombre, alias, descripción, rol, idioma, instrucciones | longitud, Unicode controlado, sin secretos en prompts |
| Apariencia | form_id, palette_id, material, idle_motion, tamaño, respuesta visual | 24/9 canónicos, material compatible, reduce motion |
| Inteligencia | provider_profile_ref, modelo preferido, modalidad, esfuerzo, max tokens | capability check, sin fallback oculto |
| Voz | voz existente, idioma, TTS provider, velocidad, lectura automática | conservar preferencias de micrófono del usuario |
| Memoria | fuentes, reglas de retención, usuario/proyecto/agente/chat | scopes ACL, revocación efectiva |
| Herramientas | allowlist de command IDs, MCP, browser, file/code/CAD | capacidades verificadas, permisos por efecto |
| Computadora | mode, entorno, procesos permitidos, raiz, network, política de foco | no autorizar ambiente no disponible |
| Autonomía | ask/auto_safe, triggers, budgets, horarios, timeout | defaults restrictivos, auditoría |
| Colaboración | equipos, skill roles, límites, revisores, delegaciones | scopes atenuados, ciclos prohibidos |
| Recursos | concurrencia, CPU/RAM/GPU, red, cuotas | límites host + proveedor |

**UX reversible:** preview -> aplicar -> descartar. Previews visuales no alteran preferencias canónicas. Límite inicial de inputs, validación de schema y frecuencia de autosave. La forma principal retorna tras cerrar un chat de agente.

## 3.3 Formas AXX

La implementación móvil inspeccionada enumera 24 formas: Core, Flow, Pearl, Torus, Split, Wave, Bloom, Fold, Spike, Drift, Orbit, Morph, Cushion, Trefoil, Nova, Heart, Infinity, Helix, Knot, Petal, Prism, Capsule, Crescent, Ripple; paletas Obsidian, Nebula, Ocean, Sunset, Amethyst, Emerald, Champagne, Silver, Void. **No asumir IDs equivalentes PC/móvil sin comprobar catálogo de escritorio**. `backend/shape_registry.py` y `1.AXX/scripts/shape-library.js` son **partes técnicas**, no autoritativas para el avatar.

- Crear `AvatarFormAdapter` que obtenga catálogo canónico de la instalación, versión de renderer y compatibilidad por plataforma.
- Guardar `appearance.form_id` y `form_catalog_version` o ID estable; no basar todo en índice si el catálogo puede reordenarse.
- Miniatura de agente a 128–256 px, sin activar renderer de cuerpo completo para agentes en reposo; caché invalidada por material/paleta/form/version.
- El agente activo puede aparecer como instancia visual dentro de chat o elegir una transición reversible de la presencia principal. Si hay tareas concurrentes, no multiplicar cuerpos con bucles WebGL permanentes.
- Reutilizar preferencias actuales de reducción de movimiento, hit-mask, tentáculos, control radial, Morph Reach, posiciones/arrastre. No reemplazar la textura/material aprobado.
- Una forma expresa identidad visual, no privilegios ni capacidades.

## 3.4 Flujos UX concretos

### Crear agente desde chat actual

`Chats y grupos > Este chat > Convertir a agente > Configurar > Preview > Guardar`. Validación atómica: registro agente + membership + revision de perfil. Ni `chat_messages` ni Connect IDs se modifican salvo que cambie explícitamente el contexto enviado al proveedor; esa actualización usa el mecanismo existente de renovación.

### Crear equipo

`Nuevo > Equipo`: elegir miembros existentes, responsable, propósito, modo (consulta/colaboración), presupuesto y política de delegación. Se crea un `agent_team` y membership de sus miembros en **el mismo hilo**. Agentes sin permiso de leer el proyecto solo ven el resumen explícitamente aprobado.

### Conversación con actividad por agente

Timeline muestra `agent_id`, estado, tarea, diff/artefacto, costes y solicitudes de aprobación. Estados visuales sugeridos: `idle`, `queued`, `thinking`, `acting`, `waiting_approval`, `verifying`, `completed`, `failed`, `paused`; mapear a animaciones canónicas sin cambiar su guardado permanente.

### Cambiar modelo sin perder agente

Actualizar `AgentProfile.revision` de proveedor, cerrar/adaptar sesión del proveedor y preservar hilo local como fuente de verdad. No trasladar tokens de sesión, credenciales ni suposiciones de acceso. Mostrar `unavailable` si el modelo no responde con herramientas/modalidad necesarias.

### Duplicar/compartir agente

Exportar solo JSON de configuración depurado y skills declarativos con hashes/licencias. No exportar tokens, bookmarks locales, grant IDs, conversaciones, caches, secretos, memoria personal, rutinas activas ni capacidad PC. Importación: vista previa, validación, mapeo de modelos/herramientas y estado `disabled` para integraciones no autorizadas.

## 3.5 Accesibilidad y foco

Roving tabindex en selector; etiquetas accesibles; no capturar teclas cuando editor de código está activo; compatibilidad de lectores de pantalla, escalado/DPI, modos claro/oscuro; iconos no indican estado por color solamente; cambios de perfil no rompen dictado/teclado. Las tarjetas de solicitud de permiso tienen foco y anuncios controlados, sin superposiciones que impidan acceso al botón Denegar.

## 3.6 Casos límite

- Chat archivado con agente activo: permitir ver resultados previos pero cerrar futuras ejecuciones o exigir desarchivar.
- Borrar chat vinculado: revocar bindings y rutinas dependientes, conservar perfil agente si usado en otro chat, limpiar materiales que referencian conversación expirada.
- Borrar agente en tarea activa: marcar `draining`, detener nuevas tareas, resolver acciones pendientes, ofrecer exportación de artefactos, luego desactivar perfil.
- Apagar PC: no prometer ejecución local; tarea queda en cola/reanudable o worker remoto previamente autorizado.
- Dos ventanas AXX: usar revision CAS y leases para configuración; evitar que un form antiguo sobrescriba una versión nueva.
- Desactivar micrófono o voz: no cambia capacidades de texto; no escuchar de forma automática.
- Copia de agente externo con rol «admin»: el rol en texto no cambia el nivel de autorización.

## 3.7 Aceptación

`T-AG-001` creación/edición/cancelación sin tocar perfil global; `T-AG-002` conversión de chat conserva identidad, mensajes, adjuntos, borrador y operations; `T-AG-003` 24 formas/9 paletas reales, mismas reglas de renderización; `T-AG-004` teams no filtran memoria; `T-AG-005` import/export excluye claves; `T-AG-006` cambiar proveedor no reenvía llamadas con permisos anteriores; `T-AG-007` a11y, multi-monitor y reduce-motion; `T-AG-008` borrado con grants revocados.
