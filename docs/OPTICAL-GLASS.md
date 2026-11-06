# Optical Glass — integración aditiva en AXX

Base revisada: AXX 0.22.46, rama de función; no es una nueva interfaz ni un ejecutable publicado.

## Alcance

- Se incorpora el acabado optativo `opticalglass` en el selector **actual** de Apariencia → Acabados. Obsidian Chrome, Prism Edge y Smoke Chrome permanecen sin modificaciones en su implementación.
- `1.AXX/scripts/optical-glass.js` transforma solo la tabla de luz del renderer `SoftwareRenderer` cuando `finish === 'opticalglass'`. Reutiliza los reflejos originales del Chroma y calcula bordes, dispersión e índice óptico aproximado.
- `OrganicTendrils` comparte la tabla del avatar por el mecanismo original `material(lut, renderer.lutKey)`. No se editan trayectorias, raíces, radios, conexiones, animaciones o hit-testing; los tentáculos reciben los nuevos colores y reflejos al cambiar de acabado.
- Los parámetros ópticos se guardan aparte en `localStorage` (`axx-optical-glass-v1`): transmisión, IOR, espesor visual, pulido, iridiscencia, intensidad del borde, saturación, exposición y color personalizado. La selección del acabado sigue usando la persistencia original de AXX, con vista previa, Aplicar y Restaurar.
- Se conservan las 24 formas, nueve paletas, posiciones y tamaños de panel, Morph Reach, voz, comandos, modelos, acciones, capturas, tareas, automatización, permisos y contratos nativos.

## Comportamiento y limitaciones

Es una **aproximación visual**, no ray-tracing físico. El rasterizador original fija la máscara alfa a 255 para conservar hit-testing, raíces de los tentáculos y clics del usuario; por eso la transparencia del material se representa principalmente mediante luminancia/reflexión y no se vuelve una ventana físicamente refractiva. No se incorpora WebGL ni un overlay superpuesto. Los otros tres materiales mantienen su código original.

## Verificación de código

```bash
node --check 1.AXX/scripts/optical-glass.js
node scripts/test-optical-glass.cjs
node scripts/test-tendril-geometry.cjs
python scripts/validate_companion.py --output build/companion-validation.json
```

Antes de integrar a `main` y distribuir, cumplir el protocolo `AGENTS.md` y `docs/mobile/COMPATIBILITY-PROTOCOL.md`: prueba visual de las 24 formas, cambios de 9 paletas, 3 materiales antiguos, Optical Glass en estado y movimiento, tentáculos largos/cortos, persistencia y restauración, colocación nativa WebView2, costes de LUT y las pruebas nativas de tentáculos. La actualización Windows necesita compilación, instalación y recibos propios. Sin esas pruebas, esta rama no demuestra instalación ni funcionamiento nativo.

## Reversión

Elegir **Obsidian Chrome** restaura el sombreado previo en tiempo real. Revertir esta rama elimina el módulo y la cuarta opción sin modificar los IDs de forma ni los datos de conexión.
