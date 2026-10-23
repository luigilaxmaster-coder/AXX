# Magic Pen sobre el escritorio

Abre el menú circular del muñeco y pulsa **Magic Pen**. La aplicación que estabas
usando permanece visible y sigue cambiando; no se abre el antiguo panel de captura.

- **Rectángulo, punto y lazo:** selecciona directamente sobre la pantalla.
  Al soltar, Axx captura ese momento sin sus controles ni su tinta y pide una
  explicación al proveedor de visión disponible. El lazo se cierra al soltar.
- **Todo:** selecciona toda la pantalla en la que está Axx.
- **Pluma y marcador:** dibuja sobre las aplicaciones. La flecha del widget
  explica la zona de las marcas; puedes escribir o dictar una pregunta.
- **Usar escritorio** (cursor): permite pulsar las aplicaciones debajo sin
  cerrar Magic Pen. Pulsa un selector o marcador para volver a dibujar.
- **Deshacer, rehacer y borrador** conservan la tinta editable. El borrador
  elimina trazos completos.
- **Guardar e historial:** exporta el original o la copia anotada a PNG con
  comprobación de integridad. No reemplaza archivos existentes.
- **Listo / Escape:** cierra los controles y devuelve la interacción normal.
  Una respuesta tardía no vuelve a abrir el widget.

El widget aparece junto a la selección y permanece dentro del área visible.
Puedes ocultarlo con × para marcar esa zona. Mueve Axx a otra pantalla antes
de abrir Magic Pen para trabajar allí.

## Qué significa tiempo real

La selección y la tinta están superpuestas al escritorio vivo. Axx captura al
terminar cada selección, o al pedir una explicación de las marcas. No analiza
vídeo continuamente ni manda capturas en segundo plano. La explicación se
refiere a ese instante; selecciona de nuevo si el contenido cambia.

La visión depende del proveedor que tengas configurado en Axx. En otra PC debes
configurar tu propia conexión; el instalador no incluye credenciales ni modelos
personales. Si falta capacidad o el proveedor falla, el widget muestra el error
real. La selección, la tinta y la exportación son locales.

## Verificación reproducible

- `node 1.AXX/scripts/test-magic-pen.cjs`: punteros reales en navegador con
  captura e inferencia simuladas en el límite nativo. Comprueba captura fresca,
  ausencia del panel/fondo congelado, coordenadas físicas, lazo, tinta editable,
  widget, entrada transparente, exportación, Escape y fallos de captura.
- `node 1.AXX/scripts/test-tools-interaction.cjs`: menú, navegación, arrastre,
  paneles, escalado y recuperación del muñeco.
- `python -m unittest backend.tests.test_magic_pen backend.tests.test_magic_pen_http -v`:
  integridad del original, captura asociada a cada pregunta, tinta excluida
  del análisis y exportación sin reemplazo.
- `cargo test --manifest-path src-tauri/Cargo.toml`: coordenadas nativas,
  entrada transparente, transporte privado y ciclo de vida.
- Compilación e instalación según [RELEASING.md](RELEASING.md). Los recibos de
  instalación y las pruebas de interfaz son verificaciones distintas.
