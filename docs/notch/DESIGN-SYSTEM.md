# AXX Notch Design System (`AXX Identity Accent`)

> Evolución vigente: [Project Obsidian — diseño y chat directo](OBSIDIAN-DESIGN-AND-DIRECT-CHAT.md). El propietario rechazó el símbolo SVG genérico: la identidad del notch usa un retrato del personaje real. El shell y las preferencias se han refinado; los valores históricos siguientes describen Phase II, no todos los tokens actuales.

## 1. Anatomy
- **Top Seam:** Flush with monitor `workArea.y` (top edge), `border-top-left-radius: 0`, `border-top-right-radius: 0`, bottom corners continuously rounded (`14px` compact → `22px` expanded).
- **Shell:** `#090c12` high-contrast base (`rgba(10, 14, 21, 0.94)` with subtle inner border derived from active `Axx.PALETTES[palette].colors[1]` at low alpha). Supports opaque fallback and Windows High Contrast (`forced-colors: active`).
- **Status Spine:** Abstract SVG/geometric AXX Identity Mark tinted by active palette stops + semantic attention dot (`idle`, `active`, `progress`, `completed`, `approval`, `error`, `offline`).
- **Leading Lane:** Primary active activity icon, title, and deterministic progress ring/bar (or indeterminate pulse when source has no deterministic fraction).
- **Trailing Lane:** Secondary indicator / overflow count (`+N`) / real-time metric (e.g. `MM:SS` remaining) / quick action button (`>= 24x24` CSS px, `>= 30x30` in peek/expanded).
- **Expansion Body (`peek` / `expanded`):** Revealed below the persistent top header using clipped layout transition without reflowing per frame. Includes pull-down/escape grip to return to `FREE`.

## 2. DIP Layout Tokens (Clamped to Monitor Work Area)
- `compact`: width `clamp(184, contentWidth, min(360, workWidth * 0.24))`, height `clamp(30, round(32 * uiScale), 40)`
- `ambient`: width `clamp(168, contentWidth, min(320, workWidth * 0.22))`, height `clamp(28, round(30 * uiScale), 36)`
- `peek`: width `clamp(260, contentWidth, min(440, workWidth * 0.36))`, height `clamp(56, contentHeight, 96)`
- `expanded`: width `clamp(340, contentWidth, min(680, workWidth * 0.58))`, height `clamp(190, contentHeight, min(520, workHeight * 0.48))`
- `stage` (top bar anchor): compact header stays anchored at top seam while `#panel` opens cleanly at `y >= notchHeight + 16` DIP.

## 3. Typography & Accessibility
- Font stack: `var(--interface-font, "Segoe UI Variable", "Segoe UI", system-ui, sans-serif)`
- Roles: `status` (`13px` weight 600), `body` (`13px` weight 400), `label` (`12px` weight 500), `micro` (`11px` non-critical metadata only — never for errors/approvals).
- Minimum interactive target: `24x24` CSS px in compact, `32x32`–`44x44` CSS px in peek/expanded.
- Full keyboard traversal (`Tab`, `Shift+Tab`, `Enter`, `Space`, `Esc`, arrow keys in Orbit rail), visible `2px` focus ring, `aria-live="polite"` for status changes, `prefers-reduced-motion` bypasses bounce and reduces to short crossfade/instant geometry.
