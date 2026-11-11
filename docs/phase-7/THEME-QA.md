# Fase 7 · Temas claro y oscuro (Incremento 5)

Autorización del cambio visual: petición del usuario de la Fase 7 («preservar casi íntegramente el modo claro, corregir selecciones y controles poco visibles, mejorar sustancialmente el modo oscuro»). Este documento es la revisión de regresión que exige `docs/mobile/COMPATIBILITY-PROTOCOL.md`.

**No se editó ningún archivo protegido por `mobile/design-baseline.json`** (`Axx.html#inline-styles`, `interface-theme.css`, `chat-workspace.css`, `transfer.css`): todas las reglas están en el archivo nuevo `1.AXX/scripts/phase7-ui.css`, cargado al final. Los hashes no se han refrescado.

## Medición
`node 1.AXX/scripts/phase7-ui-harness.cjs contrast` (añadir `P7_VERBOSE=1` para el detalle). Compone cada color sobre sus ancestros reales y aplica WCAG: texto 4.5:1 (3:1 si es grande), borde de campos 3:1, botones rotulados 1.5:1.

| Tema | Vista | Antes: texto / contorno | Después: texto / contorno |
|---|---|---|---|
| Claro | Sistema y datos | 0 / 156 | 0 / 0 |
| Claro | IA y proveedores | 0 / 26 | 0 / 0 |
| Claro | Forma, Sonidos, Personalidad, Laboratorio, Interfaz | 0 / 14–42 | 0 / 0 |
| Claro | Voces | 24 / 6 | ver nota |
| Oscuro | Sistema y datos | 0 / 159 | 0 / 0 |
| Oscuro | IA y proveedores | 0 / 26 | 0 / 0 |
| Oscuro | resto de vistas de la fase | 0 / 14–42 | 0 / 0 |
| Oscuro | Chat | 3 / 18 | 0 / 1 |

Causa común: `--line` (8 % en claro, 9 % en oscuro) se usaba también como contorno de controles → ≈ 1.2:1.

Nota sobre Voces (claro): el medidor no ve fondos con degradado, así que sigue contando como fallo el texto claro sobre las tarjetas oscuras de esa vista. La comprobación es visual: `screenshots/after-voices-light-full.png`.

## Claro (identidad conservada)
Sin cambios de superficie, tinta, acento ni tipografía. Solo:
- Contorno de botones: tinta al 26 % (antes 8 %). Contorno de campos y selectores: tinta al 56 % (≥ 3:1).
- Seleccionado (`aria-selected`, `.active`, `aria-pressed`, forma elegida): fondo de acento al 13 % (antes 5 %), borde de acento al 75 %, peso 600.
- Foco: anillo sólido de 2 px en el color de acento (antes 3 px al 45 %).
- Casillas y radios de 18 px con `accent-color`; deslizadores con `accent-color`.
- Pulsado (`:active`) y deshabilitado (opacidad .55, cursor) definidos.

## Oscuro
- Superficies con más separación: `--surface-subtle #2a2a2f`, `--surface-raised #35353b`, `--field #19191c`, `--button #38383e` / hover `#46464d`. Fondo `#202023` y tinta `#ededf1` sin cambios (son los valores por defecto del selector de colores).
- Separadores `--line #ffffff26`; texto secundario `#c3c3cc`, terciario `#a6a6b0`.
- `color-scheme: dark` en panel, catálogo y menú contextual: menús desplegables, casillas y barras de scroll nativas pasan a oscuro. `scrollbar-color` visible.
- Los mismos contornos, seleccionado, foco, pulsado y deshabilitado que en claro, derivados de `--ink`/`--accent`, así que siguen los colores personalizados por el usuario.

## Defectos de Fase 6 (solo color, sin rediseño)
- **Voces (claro)**: la vista conserva sus tarjetas oscuras en ambos temas, pero el tema claro les imponía tinta oscura (título «Tu voz, a tu manera.» a 1.05:1). Ahora el texto dentro de esas tarjetas es claro y los rótulos de sección usan `--secondary`.
- **Chat (oscuro)**: etiqueta de modo (2.18:1), «Configurar control del PC» (1.32:1) e iconos de ayuda pasan a tokens legibles; el hilo actual usa `#005fc7` (blanco a 5.3:1, antes 4.32:1); borde de los campos del navegador de chats.

## Fuera de alcance, sin tocar
- Chat en claro: 16 contornos por debajo de 3:1 (lanzadores y campos del navegador de chats). No se cambió para no alterar el chat claro aprobado.
- Chat en oscuro: el selector `#cw-mode` (1.14:1) no tiene borde propio.
- Exterior del avatar, órbita, dock y materiales 3D: sin cambios.

## Capturas
`screenshots/before-*` y `screenshots/after-*` (`-fold` = panel real; `-full` = vista completa en claro).
