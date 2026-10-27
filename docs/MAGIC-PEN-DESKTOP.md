# Magic Pen: selección, tinta y análisis en directo

## Uso

Abra **Magic Pen** desde las herramientas del avatar. La barra permanece sobre
el escritorio; el resto de las herramientas conserva su panel independiente.

La barra principal ofrece **Seleccionar**, **Dibujar**, **Usar escritorio**,
**Deshacer** y **Listo**. **Más herramientas** reúne las variantes de selección,
marcador, borrador, puntero, color, grosor, rehacer y análisis en directo.
Se abre también con el teclado; al elegir una variante se cierra y conserva el
foco en su acceso. Durante un análisis, **Detener** permanece en la barra principal.
Las transiciones respetan la preferencia de reducir movimiento del sistema.

- **Rectángulo, punto y lazo:** marque el detalle que desea explicar.
- **Todo:** selecciona la pantalla actual. **Usar escritorio** permite pulsar las
  aplicaciones debajo; un selector vuelve a activar la superficie de dibujo.
- **Pluma y marcador:** dibuje directamente sobre la pantalla. La tinta aparece
  durante el movimiento del puntero y se conserva como trazos editables.
- **Deshacer, rehacer y borrador:** conservan la tinta editable; el borrador
  elimina trazos completos.
- **En directo:** analiza la región marcada al terminar la selección o tras una
  pausa de la tinta. Puede seguir marcando mientras llega la explicación.
- **Preguntar:** envía la pregunta escrita o dictada sobre la selección actual.
- **Detener:** cancela el análisis pendiente. **Listo / Escape** cierra la
  herramienta, cancela su trabajo y libera la entrada del escritorio.
- **Guardar e historial:** exporta original o anotación a PNG; las capturas
  anteriores se muestran en una previsualización propia, separada del escritorio.

La respuesta del modelo necesita una petición al proveedor; no es vídeo continuo
ni texto transmitido token a token. La actualización se inicia por los gestos del
usuario. No hay un temporizador que capture toda la pantalla periódicamente.

## Evidencia y proveedor

Cada análisis se vincula a una captura inmutable, su revisión y la geometría de
selección. La captura nativa excluye temporalmente las ventanas de Axx para que
la tinta y sus controles no tapen el contenido analizado. El backend recorta la
región; en un lazo, enmascara lo que queda fuera. La imagen enviada se limita a
1280 × 1280 píxeles. El original íntegro queda local para edición/exportación.

En modo manual se respeta la conexión y el modelo seleccionados en **API**. La
ruta necesita la capacidad `vision`; si no está configurada, se muestra el motivo
y no se cambia silenciosamente a otra conexión. La autorización de cuota y las
restricciones del router siguen vigentes (`allow_paid: false`).

La lista de modelos para visión ofrece **Usar en visión**: esta elección queda
guardada aparte y conserva el modelo de texto del chat. Una selección de texto
no basta para habilitar el análisis de imágenes.

Para esta entrega se comprobó la ruta existente `axxx3` / `gemma4:31b` con una
imagen de prueba sin datos personales. Se añadió únicamente `vision` a las
capacidades declaradas de esa conexión después de consultar la
[documentación del modelo en Ollama](https://ollama.com/library/gemma4%3A31b-cloud).
La respuesta real reconoció el número 4279 y la posición de un rectángulo azul.
Esto prueba interpretación visual de esa ruta; no certifica independientemente
la identidad del modelo upstream ni una latencia universal.

## Ejecución y cancelación

Se reutilizan `MagicPenService`, el adaptador de inferencia y la captura Tauri.
Las respuestas no ejecutan comandos ni crean herramientas. El texto de la imagen
se trata como contenido a explicar.

| Operación POST | Entrada | Resultado |
|---|---|---|
| `/axx-api/pen/start` | Captura, revisión, pregunta, ruta, `request_id` | Trabajo con identidad disponible al iniciar |
| `/axx-api/pen/query` | `id` de captura, `query_id` | Estado persistido y respuesta o error |
| `/axx-api/pen/cancel` | `id` de captura, `query_id` | Cancelación del trabajo y del adaptador |
| `/axx-api/pen/get` | `id` de captura | Documento y previsualización para historial |

Los IDs de petición constan de 32 caracteres hexadecimales. Repetir la misma
petición no duplica el análisis; reutilizar su ID con otro contenido se rechaza.
El estado terminal se conserva. Una respuesta tardía no puede reemplazar una
cancelación ni aparecer bajo otra selección.

La interfaz separa captura, guardado y análisis. Agrupa movimientos de tinta con
`requestAnimationFrame`, aplaza el análisis hasta la pausa y conserva solamente
la selección más reciente pendiente. El backend limita la concurrencia de Magic
Pen y el adaptador mantiene sus límites globales. Cambiar de herramienta,
cerrar o cambiar la geometría de pantalla invalida las referencias que corresponda.

La enumeración y captura usan coordenadas físicas bajo un contexto DPI por hilo
`PER_MONITOR_AWARE_V2`, restaurado al terminar incluso si ocurre un error. Esto
evita el desfase entre Tauri y Python en pantallas con escalas distintas. La
grabación de área reutiliza el mismo contexto durante la captura de vídeo.

## Pruebas y reproducción

```powershell
python -m unittest backend.tests.test_magic_pen backend.tests.test_magic_pen_http -v
node 1.AXX/scripts/test-magic-pen.cjs
node scripts/test-installed-magic-pen.cjs
```

La primera capa prueba geometría, persistencia, idempotencia, cancelación,
revisiones y permisos HTTP. El contrato de navegador usa punteros reales con
captura/inferencia simuladas y no equivale a aceptación de Windows.

La prueba instalada usa el EXE y el backend empaquetados: abre una ventana
descartable con contenido conocido, la selecciona, captura mediante IPC nativo y
pregunta al proveedor real. Los recibos y capturas permanecen privados en
`build/chat-0.21.4/magic-pen/`. Se comprueban además historial, temas, cancelación
y recuperación; los resultados concretos se registran en `CURRENT-DELIVERY.md`.

Las pantallas protegidas o inaccesibles pueden impedir una captura. Una selección
antigua no se reutiliza como prueba de la pantalla actual. La configuración del
proveedor y la geometría se vuelven a comprobar al iniciar otra operación.
