# Fase 7 · Handoff para Codex (dictado global / Handy)

Rama `claude/axx-phase-7-ui`, base `a750362`. Sin push, sin publicación, sin instalación. `main` intacto.

## Archivos compartidos modificados
Solo `1.AXX/Axx.html`, 6 líneas:

| Línea | Cambio |
|---|---|
| 1663–1665 | Rótulos de las pestañas de `view-ai`: «Modelo local», «Cuenta ChatGPT», «Por API · Otro proveedor con clave». Mismos `id`, `data-ai-mode`, `aria-controls`. |
| 12905 | `LABELS`: añade `personalize: 'Personalizar AXX'`. |
| 12910 | `GROUPS.assist.ids`: `'agent'` → `'personalize'`; salen `'appearance'` y `'sound'` de la lista del catálogo. |
| 20099 | Al final: `<link rel="stylesheet" href="scripts/phase7-ui.css"><script src="scripts/phase7-ui.js"></script>`. |

Si Codex toca esas líneas, el conflicto se resuelve conservando ambas partes; `phase7-ui.js` debe seguir siendo el **último** script.

## Archivos nuevos (propiedad de esta fase)
`1.AXX/scripts/phase7-ui.js`, `phase7-ui.css`, `phase7-ui-harness.cjs`, `phase7-control-baseline.json`, `docs/phase-7/*`.

## No modificado
`native-voice.js`, `native-speech-stream.js`, `voice-audio.js`, `voice-conversation.js`, `voice-phrases.js`, `remote-voice.js`, `native-voice-fallback.draft.js`, ASR, servicios de audio, coordinador de micrófono, atajos, contratos de voz, `src-tauri/` (Rust), `backend/` (Python), `providers.js`, `interface-theme.*`.

Lo único relacionado con voz es **solo CSS de color**: texto de `#view-voices` en tema claro y `#cu-open`/etiquetas del chat en oscuro. La tarjeta `#axx-remote-voice` y el interruptor `#voice-autosend` solo cambiaron de contenedor (mismo nodo, mismo handler).

## Cómo integrar el nuevo apartado de dictado sin otro rediseño
1. **Tarjeta en Sistema y datos**: añadir un `<section class="setup-card" id="…">` con un `<strong>` de título a `#view-settings` (como hacen hoy los demás módulos). `phase7-ui.js` la recoge sola en «Conexiones e integraciones» como plegable (o tal cual si tiene un único botón). Llamar a `card.scrollIntoView()` abre su plegable.
2. **Vista propia**: registrar la función en `Axx.FEATURES` y crear `section.panel-view#view-<id>`. Componentes disponibles con solo usar las clases:
   - `section.p7-group > header > h3 + p`, cuerpo `div.p7-body`.
   - `div.p7-row > div.p7-copy (strong + small) + div.p7-actions` — variantes `p7-danger`, `p7-caution`, `p7-stack`.
   - `button.p7-main` (una acción principal por grupo), `details.p7-more` / `details.p7-fold` (divulgación progresiva), `nav.p7-nav` (saltos), `nav.p7-tabs[role=tablist]`.
   - Los contornos, foco, seleccionado, deshabilitado y el tema oscuro se aplican solos dentro de `#panel`.
3. **Atajo de dictado**: `labelOf('shortcut')` vive en «Windows e inicio»; un control nuevo de atajo puede añadirse a `#p7-windows .p7-body`.
4. Tokens: usar `--surface`, `--surface-subtle`, `--line`, `--ink`, `--secondary`, `--accent`, `--danger`, y para contornos `--p7-button-line` / `--p7-field-line`.

## Contratos que debe respetar un módulo nuevo
- No depender de que un control sea hijo directo de `#view-settings` o `#view-ai`: ahora están dentro de `.p7-group`.
- `#axx-interface-theme`, `#reduced-motion` y `#static-mode` cambian de vista según cuál esté abierta (un comentario `p7-home` marca su sitio).
- Añadir los ids nuevos a las pruebas propias; `phase7-control-baseline.json` solo protege los ids anteriores a la fase.

## Dependencias de Codex
Ninguna. La fase no espera nada del trabajo de dictado.
