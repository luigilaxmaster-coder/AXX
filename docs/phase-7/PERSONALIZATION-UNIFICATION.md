# Fase 7 · Personalizar AXX (Incremento 4)

Capturas: `screenshots/after-personalize-*`, `after-appearance-*`, `after-sound-*`, `after-agent-*`.

## Entrada única
Nueva función `personalize` («Personalizar AXX») en el catálogo, en lugar de las tres tarjetas separadas «Apariencia», «Sonidos» y «Personalizar agente». Esas funciones siguen existiendo en `Axx.FEATURES`: el buscador del catálogo las encuentra y `openFeature('appearance' | 'sound' | 'agent')` funciona igual (comandos, menú del chat y suites lo usan).

Una barra de cinco pestañas (`nav.p7-tabs`, `role=tablist`, flechas ←/→) acompaña a las cuatro vistas y el título del panel pasa a ser «Personalizar AXX».

| Pestaña | Vista que se muestra | Propietario de los datos | Controles |
|---|---|---|---|
| Forma y materiales | `view-appearance` (sin modificar) | identidad/estudio en `Axx.html` | formas, paletas, tamaño, luz y superficie, estilos guardados, cámara, vista previa `appearance-apply` / `appearance-restore` |
| Interfaz y colores | `view-personalize` | `interface-theme.js` (`axx.interface.theme`, `axx.interface.customization`); residente (`axx.resident.panel-pos`) | tema claro/oscuro, colores, tipografía, tamaño, widgets; `dock-placement`, `dock-position-reset`, `reset-desktop-layout`, `reset-layout` |
| Movimiento y presencia | `view-personalize` | identidad (`id20-motion`), ajustes (`reduced-motion`, `static-mode`), `anticipation.js` | carácter y expresividad, reacciones; menos movimiento; accesos a «Presencia y autonomía» y al laboratorio |
| Sonidos y respuesta | `view-sound` (sin modificar) | motor de sonido en `Axx.html` | perfil, volumen, categorías, muestras, mezcla |
| Personalidad e instrucciones | `view-agent` (sin modificar) | `agent-profile.js` → `/axx-api/chat/profile` | nombre, rol, contexto, instrucciones, tono, comandos preferidos |

## Sin copias de datos
- No se crea ningún almacén, clave ni endpoint nuevo. No se clona ningún control.
- **Movidos de forma permanente** a `view-personalize`: `#id20-motion` (sus estilos no dependen de la vista), el control del dock y los tres botones de recuperar posiciones.
- **Compartidos** entre «Sistema y datos» y «Personalizar AXX»: `#axx-interface-theme`, `reduced-motion` y `static-mode`. Son un único nodo que se coloca en la vista que está abierta; un comentario `p7-home` guarda su sitio original. Motivo: `scripts/test-installed-appearance.cjs` (aceptación nativa) abre `settings` y usa ahí el tema; ese contrato se conserva.
- «Sistema y datos» termina con el grupo «Personalización»: tema + botón «Personalizar AXX» + los accesos antiguos al estudio y al agente.

## Cambios en `Axx.html` (script inline, dos líneas)
- `GROUPS.assist.ids`: `'agent'` → `'personalize'`; se retiran `'appearance'` y `'sound'` de la lista (no del registro de funciones).
- `LABELS`: se añade `personalize: 'Personalizar AXX'`.

La función se registra en `Axx.FEATURES` desde `phase7-ui.js`.

## Cierre de anchuras y Forma · Codex
- Las cinco pestañas comparten durante la visita la clave de layout de la entrada;
  salir restaura la independencia de cada vista. Se conservan todos sus tamaños
  guardados. Las dimensiones por defecto consultan esa misma clave, sin fabricar
  ni persistir valores al navegar. Arrastre y resize explícitos conservan el dueño
  existente y se guardan para la entrada activa.
- Forma y materiales mueve los mismos nodos a Vista previa, Forma, Materiales e
  iluminación y Opciones avanzadas. Guardar cambios/Descartar prueba permanece
  visible fuera del scroll. Geometría, shaders, cámara y valores no se modifican.
- Pruebas: medidas distintas preguardadas, cinco pestañas, igualdad de RAM y
  localStorage tras navegar, arrastre/resize real del navegador, recarga y
  restauración de la vista independiente. Layout comprobado en cada vista,
  incluida Forma, a ancho normal y 380 px.

## Pruebas
`phase7-ui-harness.cjs test`: cinco pestañas con los controles de su propietario visibles, flechas, nodo único del tema en ambas entradas, persistencia de tema/tipografía/tamaño de widget a través de `interface-theme.js`.
