# Fase 7 · Sistema y datos (Incremento 2)

Capturas: `screenshots/before-settings-light-full.png` → `screenshots/after-settings-light-full.png` (7 738 px → ≈ 3 660 px de scroll).

## Estructura
Barra de secciones fija (Windows · Datos · Copias · Rendimiento · Conexiones) y cinco grupos:

| Grupo | Acción principal | Contenido (ids existentes) | Divulgación progresiva |
|---|---|---|---|
| **Windows e inicio** | `summon-settings` | `native-warning`, `always-top`, `autostart`, `shortcut`; fila «Traer AXX»: `summon-settings`, `recenter`, `reset-position`; fila «Presentar y ocultar»: `presentation`, `hide-avatar`, `quit-native` | «Dock y distribución de ventanas»: `dock-placement`, ayuda, `dock-position-reset`, `reset-desktop-layout` |
| **Datos y almacenamiento** | `export-data` | fila «Exportar mis datos»; fila destructiva «Borrar datos locales» (`clear-data`) | — |
| **Copias de seguridad** | `backup-all` | «Crear copia completa» (`backup-all`); «Restaurar desde una copia · reemplaza datos» (`import-all`, `import-file`) | — |
| **Rendimiento y diagnóstico** | — | `quality`, `reduced-motion`, `static-mode`, `show-label`, `compat-info` (`download-diagnostics`) | `toggle-diagnostics` → `diagnostics`; «Windows · acciones y memoria» (`desktop-runtime`) |
| **Conexiones e integraciones** | — | `mcp-settings-shortcut` | un plegable por tarjeta: Presencia y autonomía, Computer Use, teléfono (3), MCP, Aplicaciones, Telegram, micrófono remoto |

El tema, la distribución de paneles y el acceso al agente salen de esta vista hacia «Personalizar AXX» (Incremento 4).

## Borrar / restaurar inequívocos
- `clear-data`: fila con borde y texto en `--danger` y la descripción «Pide confirmación y no se puede deshacer». El `confirm()` original no cambia.
- `import-all`: título con la marca «· reemplaza datos». El `confirm()` de `importBackup` no cambia.
- `export-data` y `backup-all` llaman al mismo `backup()`; se conservan los dos ids porque otros módulos pulsan `backup-all`.

## Qué NO cambia
Ningún handler, id, valor guardado ni permiso. Los nodos se **mueven** (`append`), no se clonan. Los títulos `.section-title` antiguos quedan ocultos (`hidden`), no eliminados. Las tarjetas de otros módulos conservan su contenido íntegro dentro del plegable; su método `scrollIntoView` abre el plegable, de modo que «Conexiones MCP», «Conectar teléfono» o el comando «abre conexiones MCP» siguen llevando a su tarjeta. Una tarjeta que un módulo futuro añada a `#view-settings` cae en «Conexiones» automáticamente.

## Pruebas
`phase7-ui-harness.cjs test`: orden de grupos, fila destructiva, plegable que se abre al hacer scroll, handlers vivos, ningún control inalcanzable. Suites existentes: ver `REGRESSION-RESULTS.md`.
