# Fase 7 · Resultados de regresión (Incremento 6)

Fecha: 2026-11-11. Árbol: `claude/axx-phase-7-ui`. Baseline: checkout limpio de `a750362` ejecutado en la misma máquina, con el mismo navegador (`AXX_TEST_CHROMIUM` → `chromium_headless_shell-1248`).

Alcance: pruebas de contrato en navegador con host nativo simulado y el gate de compatibilidad. **No** es aceptación nativa en Windows: no se construyó ni instaló ningún candidato (restricción de la fase).

## Contratos de la fase
`node 1.AXX/scripts/phase7-ui-harness.cjs test` → **todas pasan**.

| Área | Comprobación |
|---|---|
| General | sin errores de página al arrancar ni tras interactuar |
| General | cada id de control anterior a la fase existe exactamente una vez (`phase7-control-baseline.json`) |
| General | en las 7 vistas ningún control queda inalcanzable (visible o dentro de un plegable que se puede abrir) |
| Sistema y datos | orden de grupos; `clear-data` en fila destructiva; `import-all` marcado; `backup-all` en Copias |
| Sistema y datos | `scrollIntoView` de una tarjeta abre su plegable; handlers existentes siguen disparando |
| IA | la configuración sola nunca aparece como verificada; una prueba fallida mantiene «sin comprobar» |
| IA | «Probar conexión» ejecuta la sonda del propietario; coste y capacidades visibles; cada opción muestra solo sus controles; FreeLLMAPI solo con su plataforma |
| Personalizar | 5 pestañas con los controles de su propietario; flechas; nodo único del tema en ambas entradas; persistencia de tema, tipografía y tamaño de widget |
| Teclado | Tab alcanza los controles y el anillo de foco es visible en claro y oscuro |
| Diseño | sin scroll horizontal al ancho por defecto y con panel de 380 px (Sistema, IA, Interfaz, Personalidad, Sonidos) |

`node 1.AXX/scripts/phase7-ui-harness.cjs contrast` → 0 fallos de texto y contorno en las 7 vistas de la fase, en claro y oscuro (detalle en `THEME-QA.md`).

## Suites existentes: baseline frente a Fase 7
| Suite | Baseline | Fase 7 | Nota |
|---|---|---|---|
| `test-desktop-frontend` | pasa | pasa | |
| `test-anticipation` | pasa | pasa | |
| `test-mobile-pairing` | pasa | pasa | |
| `test-mission-attention-integration` | pasa | pasa | |
| `test-document-provenance` | pasa | pasa | |
| `test-chat-usability` | pasa | pasa | |
| `test-sound-runtime` | pasa | pasa | |
| `test-composer-tools` | pasa | pasa | |
| `test-command-library` | pasa | pasa | |
| `test-browser-runtime` | pasa | pasa | |
| `test-computer-use` | pasa | pasa | falló durante el desarrollo (ver abajo) |
| `test-quick-reply` | pasa | pasa | |
| `test-tools-interaction` | **falla** L75 | **falla** L75 | preexistente: el catálogo muestra el rótulo «Chat» y la prueba espera texto vacío |
| `test-providers` | **falla** L148 | **falla** L148 | preexistente (Fase 6): «La memoria de esta conversación cambió» |
| `test-skills` | **falla** | **falla** | preexistente: necesita `dist/axx-backend.exe` |
| `test-capability-workshop` | **falla** L16 | **falla** L16 | preexistente: timeout |
| `test-goal-cycle` | **falla** L23 | **falla** L23 | preexistente: timeout |

Ninguna suite cambia de resultado. Sin `AXX_TEST_CHROMIUM`, `test-providers` falla antes, al no encontrar el Chromium 1234 que tiene fijado: es un fallo de entorno, también preexistente.

## Gate de compatibilidad PC/móvil
`python scripts/validate_companion.py --output build/companion-validation.json` sobre el árbol final → **PASS** (contract 15, renderer_build, backend 112 con 1 omitida, browser 58, selector de archivos 8). El recibo queda en `build/` (ignorado por Git) y corresponde a este árbol; `release.py publish` no se ejecutó.

La ejecución del gate sobre el baseline se hizo en paralelo con otras suites y dio 3 fallos de backend; no se repitió en solitario, así que no se usa como comparación.

## Regresiones propias detectadas y corregidas durante la fase
1. «Probar conexión» quedaba deshabilitado tras una sonda fallida (la acción de `providers.js` restauraba el estado que yo había fijado). Corregido: el botón ya no se deshabilita al delegar.
2. La sonda real no se usaba si `providers.js` no había cargado aún las conexiones. Corregido: se pulsa antes su «Actualizar conexiones».
3. `test-providers` L78: la tarjeta de estado empujaba el formulario bajo el pliegue. Corregido: al elegir una opción, sus controles suben al inicio.
4. `test-computer-use` L66: el botón «Configurar Computer Use» quedaba dentro de un plegable cerrado. Corregido: una tarjeta con un solo control no se pliega.

## No verificado
- WebView2 empaquetado, DPI reales de Windows y atajos globales (requiere candidato instalado).
- `scripts/test-installed-appearance.cjs` (necesita instalación). Su contrato se replica en el arnés.
- Android/teléfono físico: `mobile/` no cambia.
- El desbordamiento horizontal de 19 px de «Forma y materiales» es anterior a la fase y no se tocó.
