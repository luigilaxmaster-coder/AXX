# Fase 7 · Auditoría UI e inventario (Incremento 1)

Base: `a750362`. Método: `node 1.AXX/scripts/phase7-ui-harness.cjs inventory` (Chromium + host nativo simulado, panel real de 680×720). Evidencia: `screenshots/before-*`.

## Hallazgo principal
Las vistas no son estáticas: **14 módulos inyectan tarjetas en `#view-settings` al arrancar** (`prepend`/`append`), sin orden común.

| Vista | Controles | Alto de scroll (573 px útiles) | Problema |
|---|---|---|---|
| `view-settings` | 269 (240 ids) | 7 738 px ≈ 13 pantallas | 37 bloques de primer nivel sin jerarquía; integraciones antes que ajustes; «Borrar datos locales» junto a «Exportar datos» con el mismo aspecto; copia/importación mezcladas con «Traer al cursor» |
| `view-ai` | 71 (103 ids) | 2 916 px | «Modelo en uso» se oculta en la pestaña API; estado, coste y capacidades repartidos; formulario completo abierto por defecto |
| `view-appearance` | 69 | 2 921 px | forma, paletas, luz, movimiento, estilos y cámara en una sola lista |
| `view-agent` | 12 | 1 216 px | correcto; aislado del resto de la personalización |
| `view-sound` | 34 | 1 499 px | correcto; aislado |
| `view-lab` | 22 | 1 077 px | muestras; no es configuración |

## Propietarios de cada bloque de `view-settings`
| Bloque | Propietario | Destino en Fase 7 |
|---|---|---|
| Dock, calidad, movimiento reducido, estático, estado, Windows, datos, copia, diagnóstico | `Axx.html` (estático) | grupos 1–4 |
| `#axx-interface-theme` (tema, colores, tipografía, widgets) | `interface-theme.js` | Personalizar AXX |
| «Personalizar agente…» | `agent-profile.js` | Personalizar AXX |
| `#resident-studio`, `#reset-layout` | `Axx.html` (residente) | Personalizar AXX |
| `#anticipation-settings` | `anticipation.js` | Conexiones |
| Computer Use | `computer-use.js` | Conexiones |
| `#axx-mobile`, `#axx-remote-control`, `#axx-mobile-work-approval`, `#axx-remote-voice` | `mobile-gateway.js`, `remote-control.js`, `mobile-work-approval.js`, `remote-voice.js` | Conexiones (contenido sin modificar) |
| `#mcp-connections`, `#mcp-settings-shortcut` | `mcp-connections.js` | Conexiones |
| `#application-catalog`, `#telegram-panel`, `#desktop-runtime` | `application-catalog.js`, `telegram-panel.js`, `Axx.html` | Conexiones / Rendimiento |

## Tokens de tema (`interface-theme.css`, protegido)
- Claro: `--line:#00000015` (borde de botones ≈ 8 % → contorno casi invisible), `--accent-soft:#007aff0d` (selección al 5 %).
- Oscuro: superficies `#202023 / #28282c / #303034` (pasos de 3–4 % de luminosidad), `--line:#ffffff16`.
- Foco: anillo de 3 px al 45 % del acento.

Se corrigen en el Incremento 5 desde `phase7-ui.css`, sin editar el archivo protegido.

## Contratos existentes que condicionan el diseño
- `test-providers.cjs` L76–80: en la pestaña API `.ai-current` no es visible, `.provider-overview` mide < 150 px, `#provider-saved` queda sobre el pliegue y `#provider-advanced` está abierto.
- Varios módulos hacen `card.scrollIntoView()` sobre su tarjeta de ajustes (MCP, teléfono, Telegram, aplicaciones).
- Las suites abren las vistas con `Axx.companion.openFeature(id)`.

## Baseline de pruebas
Ver `REGRESSION-RESULTS.md`.
