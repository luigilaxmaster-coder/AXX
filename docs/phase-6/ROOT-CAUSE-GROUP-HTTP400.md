# P0-01 · HTTP 400 después de crear o asignar un grupo — causa raíz

Base: `9e5850c` (código empaquetado `b99d8bd`), rama de trabajo `claude/axx-phase-6`. Evidencia privada en `build/phase6/` (no se publica).

## Reproducción y cuerpo exacto

Ruta real: botón **Crear grupo** de `1.AXX/scripts/chat-workspace.js` → backend real (HTTP + SQLite). Sin tocar datos de usuario (fixture `backend.tests.chat_http_fixture`, base temporal).

Petición rechazada (sin datos sensibles; identificadores truncados):

```
POST /axx-api/chat/save          { id:<chat>, messages:[…], draft:"Borrador A", attachment:null,
                                   memory_scope:{task_id:<chat>, generation:0},
                                   memory_context_id:<connect_id ANTERIOR> }
→ 400  {"error":{"code":"INVALID_REQUEST","message":"El contexto de la conversación cambió; descarta el resultado anterior"}}
```

Secuencia observada con el backend real (`create → save → group → update(group_id) → get → save`):

| Paso | Resultado |
|---|---|
| `chat/create` | 200, `connect_id` = `2cb26c69…`, generación 0 |
| `chat/save` (contexto actual) | 200 |
| `chat/group` {title} | 200 |
| `chat/update` {group_id} (token actual) | 200 — **el servidor rota `connect_id`** → `7510eb82…`; `group_id` persistido |
| `chat/save` con el contexto anterior | **400** (cuerpo de arriba) |
| `chat/save` con el contexto nuevo | 200 |

La prueba de regresión nueva (`scripts/test-chat-groups.cjs`) reproduce lo mismo pulsando los botones reales: sobre `9e5850c` termina con `timeout` de la UI y un único rechazo `POST /axx-api/chat/save → 400` con ese mensaje (`build/phase6/groups-before.log`). La prueba antigua `scripts/test-chat-workspace.cjs` fallaba en su línea 34 con el mismo cuerpo (ya fallaba en Fase 5; Codex la registró como A05 sin atribuirla a esta causa).

## Causa raíz demostrada (tres eslabones)

1. **Servidor (correcto, intencional).** `backend/chat_store.py:553-554` genera un `connect_id` nuevo cuando `group_id` cambia; `group_delete` (`:566`), las notas de contexto de grupo (`:609`, `:621`) y el perfil del agente (`:619-621`) también lo rotan. Una escritura con la identidad anterior se rechaza (`task_memory.assert_context`): protege contra resultados obsoletos.
2. **Cliente (defecto).** Los manejadores `cw-group.onchange`, `cw-create-group` y `cw-group-delete` llamaban a `select(id)` después de mutar. `select()` ejecuta **primero** `flush()` (`chat-workspace.js:154`), que guarda el *snapshot* del contexto anterior. El servidor lo rechaza con 400, `select()` lanza antes de `applyRow(row)` y la UI **nunca adopta** la identidad nueva: queda con el grupo y el contexto anteriores y muestra el error.
3. **Siguiente solicitud (misma familia).** Si el contexto rota sin que el cliente lo adopte (grupo, nota de grupo en otro hilo, perfil), `c.send` capturaba el token viejo; `brain.chat` llamaba a `refreshActiveContext()`, que adopta la fila y ejecuta `invalidateMemory`, el cual **aborta la propia solicitud nueva** (`AbortError: La memoria de esta conversación cambió`). Reproducido con `scripts/test-chat-workspace.cjs` línea 44 una vez corregido el primer eslabón.

Descartado con evidencia: no es el selector de grupo, ni un fallo de persistencia (el servidor guarda `group_id`), ni la serialización del payload (el cuerpo es válido; el rechazo es semántico), ni el proveedor/modelo (no interviene en `chat/save`).

## Corrección (origen, no el mensaje)

`1.AXX/scripts/chat-workspace.js`:

- `rotate(mutate)`: guarda el estado pendiente **antes** (contexto aún válido), marca `rotating` (un snapshot del contexto antiguo no se escribe: `snapshot()` devuelve `null` y `flush()` se omite), ejecuta la mutación, **adopta** el contexto nuevo con `syncContext()` y recién entonces rehabilita el guardado. Si la mutación falla, el error se propaga (sin reintento) y no se adopta nada.
- `syncContext()`: compara el contexto/generación del servidor con el del cliente; si cambió, `applyRow(row, true)` (conserva el borrador tecleado, cancela solicitudes en vuelo por `invalidateMemory`).
- `select()` llama a `syncContext()` antes de `flush()`; `c.send` y `brain.chat` lo llaman antes de capturar el token (una solicitud **nueva** parte del contexto actual; solo una rotación **durante** la solicitud la aborta).
- Los tres manejadores de grupo usan `rotate`.

No se modificó el servidor: el rechazo de escrituras obsoletas sigue siendo estricto (la prueba lo exige).

## Comportamiento verificado

Crear grupo ✔ · asignar chat existente ✔ · selector y cabecera muestran el grupo al instante ✔ · el chat usa el contexto actualizado (nota de grupo en la petición) ✔ · el chat de otro grupo no ve esa nota ✔ · filtro por grupo sin mezclar conversaciones ✔ · asignar con guardado pendiente (borrador teclado durante el cambio) ✔ · rotación externa + `select()` ✔ · mutación rechazada se muestra y no cambia el contexto ✔ · borrar grupo adopta el contexto ✔ · un guardado con el contexto anterior sigue dando 400 ✔ · tras reiniciar (página nueva sobre la misma base) las asignaciones persisten ✔. Detalle en `FIXES-AND-TESTS.md`.

Pendiente (no se afirma): aceptación física en el WebView2 empaquetado de la candidata nueva.
