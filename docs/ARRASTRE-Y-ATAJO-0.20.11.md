# Axx 0.20.11 — arrastre libre y estado del atajo

## Correcciones

- El muñeco puede moverse cerca de los bordes aunque esté encogido. El margen ya no depende del tamaño de su lienzo transparente; sólo conserva 12 píxeles para poder recuperarlo con el puntero.
- Una consulta de geometría iniciada antes de arrastrar se descarta si llega tarde. Ya no puede pintar brevemente la posición anterior.
- Mientras Windows confirma la nueva posición del muñeco, el cálculo de distribución espera esa confirmación.
- Los paneles respetan el borde durante el gesto, en vez de sobrepasarlo y saltar al soltar. Sus posiciones guardadas convierten correctamente píxeles físicos y coordenadas de interfaz.
- El atajo existente sigue siendo `Alt+Shift+A`; no se cambiaron las teclas ni la identidad, los proveedores, las herramientas o los datos personales.

## Regresión automatizada

Se reprodujeron tres fallos antes de cambiar el código: el panel salía del área disponible, una respuesta antigua pintaba la posición anterior y el muñeco pequeño no podía llegar a `(40, 40)`, quedándose en `(92, 92)`.

Después de corregirlos, pasaron 12 comprobaciones de interacción, incluidas posición cerca de la esquina, respuesta tardía, arrastre a escala 150 %, navegación, redimensionado y menú transparente. Esta escala se simula en la prueba; no equivale a validar monitores físicos con DPI mixtos.

- `node 1.AXX/scripts/test-tools-interaction.cjs`: 12 comprobaciones aprobadas, sin excepciones JavaScript.
- `node 1.AXX/scripts/test-magic-pen.cjs`: aprobado.
- `node 1.AXX/scripts/test-native-capture.cjs`: aprobado.
- `node 1.AXX/scripts/test-dictation-runtime.cjs`: aprobado.
- `python -m unittest discover -s backend/tests -p 'test_*.py'`: 99 pruebas aprobadas; avisos de limpieza de HTTPError en las pruebas.
- `cargo test --manifest-path src-tauri/Cargo.toml`: 29 pruebas aprobadas; un auxiliar ignorado deliberadamente.

Los resultados de antes y después se guardan en `evidence/drag-shortcut-20261022/`. Los logs completos y el recibo de compilación quedan en `build/drag-shortcut-20261022/`.

## Verificación nativa y paquete

Compilación completa con `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1 -EvidenceDirectory build/drag-shortcut-20261022/build`: backend PyInstaller y paquete NSIS terminados con código 0. La comprobación y extracción con 7-Zip pasaron. El backend extraído volvió a convertir y reabrir JPEG/PDF correctamente.

El instalador `Axx_0.20.11_x64-setup.exe` tiene 247335144 bytes y SHA256 `4104765597B6248BB285B51E655C59C6F3F066F3BBBE51782DF86266A1D6611C`. Se instaló localmente con salida 0; el ejecutable instalado coincide con el extraído del paquete. La única diferencia entre el ejecutable compilado y el empaquetado son los tres bytes del marcador de Tauri `UNK` → `NSS`.

Se abrió la versión instalada desde `INICIAR-AXX.cmd`. El registro del atajo devolvió `shortcutError: null`. Sin embargo, **no se declara aprobada la prueba física de arrastre ni del atajo en 0.20.11**: Computer Use rechazó coordenadas sobre la ventana transparente y después la interacción con la ventana externa. El usuario pidió publicar manteniendo esa prueba pendiente. Las pruebas automatizadas del movimiento sí pasaron.

[Descargar la versión de prueba 0.20.11](https://github.com/luigilaxmaster-coder/AXX/releases/tag/v0.20.11).

## Límites

La prueba en otra PC, los monitores físicos con DPI mixtos y el lápiz físico requieren comprobación en ese hardware. La posición se limita al área de trabajo del monitor actual. El instalador necesita Internet si falta WebView2 y no tiene firma digital. Las consultas visuales siguen necesitando un proveedor configurado con visión.
