# Axx 20 · Estabilidad, identidad y conversación

## Alcance

Se extrae y modifica Axx 19. Los doce identificadores originales de forma permanecen estables. No se reemplazan las herramientas ni se introducen otro modelo, motor de voz o proveedor musical. No se exige WebGL para renderizar la presencia.

La revisión corrige autoridades de preferencias, amplía la geometría/movimiento, depura el recorrido de retorno y simplifica la conversación. Es una revisión transversal de esos mecanismos y una regresión de herramientas; no una certificación de ausencia de fallos en todas las integraciones futuras.

## Causas reproducidas

`docs/v20/baseline-probe.json` registra una forma 3 guardada que pasaba a 6 durante éxito y a 8 durante concentración. La tabla STATE_FORM se imponía después de aplicar preferencias. También registra regreso con profundidad 1 y Herramientas visible; Home18 volvía a mostrar la cápsula cada fotograma.

Se encontró un segundo almacén de superficie en Experience que podía aplicar parámetros antiguos después de restaurar Studio. En navegación, las cabeceras trataban `summary` como una zona arrastrable: pulsar un menú no lo abría. Al volver a la base, un movimiento de solo dos píxeles despertaba el control como arrastre, de modo que su clic siguiente actuaba sobre una tarea en lugar de revelar la cápsula.

## Archivos principales

| Archivo | Responsabilidad en la revisión |
|---|---|
| src/core/model.ts | Settings keepForm/actionMorph/motionStyle; identidad normalizada; catálogo 24. |
| src/core/motion.ts | Seis perfiles paramétricos; buffer reutilizado de ondas. |
| src/render/software-core.ts | Nuevas superficies, transición de 24 pesos, caché de base y resolve2x exacto. |
| src/render/software-renderer.ts | Resolución de forma y controles temporales; cámara; reacciones; ahorro de operaciones sin reducir fidelidad. |
| src/ui/app.ts | Forma persistida frente a estado; persistStudio20 canónico; etiqueta de herramienta. |
| src/ui/experience.ts | Previsualizar/aplicar/descartar; respeto del almacén canónico. |
| src/ui/home18.ts | Retorno con paso 0; primer toque; umbral de arrastre y cancelación. |
| src/ui/action11.ts | Control corporal existente; vista previa separada; encaje de chat/apariencia. |
| src/ui/action-windows.ts / organic.ts | Exclusión de menús del gesto de mover; mismas ventanas reales. |
| src/ui/stability20.ts / .css | Preferencias, estilos guardados, miniaturas, chat mínimo y roadmap futuro. |
| src/ui/shape-thumbs20.ts | Miniaturas generadas por el renderer, solo para el selector. |
| src/ui/companion.ts / dictation13.ts / symbiosis.ts | Integraciones de identidad, borrador/scroll y acabado, sin duplicar ejecutores. |

## Autoridad de identidad

La configuración guardada representa la identidad. El estado de tarea no escribe en ella. `identityForm20` resuelve: vista previa explícita → forma guardada si keepForm → forma del estado cuando el usuario permite adaptación. Las muestras del laboratorio pueden mostrar otra forma sin guardarla.

`actionMorph` es independiente: conserva la capacidad histórica de hacer el propio cuerpo un botón volumétrico de pausa/reproducción/números. Desactivarlo conserva la figura sin anular el control de tareas. Al aparcar, se limpian los símbolos transitorios y se restaura la forma guardada.

`axx-studio-v2` es la autoridad de superficie/cámara; la superficie antigua de Experience solo se usa para migrar cuando falta el almacén canónico. Aplicar confirma forma, paleta y superficie; descartar restaura el conjunto. No se restaura una mezcla de dos revisiones distintas.

Las claves de notas, tareas, voz, música, dimensiones y base no se cambian. `axx.presets20` añade hasta ocho presets validados. El respaldo añade `identity20` con versión, estudio/cámara y presets. No incluye audio, transcripciones ni secretos. Un estilo solo se guarda después de confirmar la apariencia. Los valores importados se validan y acotan.

El tamaño visible puede limitarse temporalmente para una órbita o un chat de teléfono; la preferencia manual no se modifica. Esta separación no depende de comprimir texto mediante transform:scale.

## Geometría y movimiento

Las formas 12–23 tienen fórmulas volumétricas propias. Las formas tubulares tienen profundidad real; los huecos se resuelven como superficie, no como una máscara PNG. ShapeTransition tiene 24 pesos y redirige a la última selección. Las muestras de reacción duran aproximadamente 1,4 segundos, se interrumpen y no ejecutan herramientas.

La malla estándar sigue siendo 112×72 segmentos (16.128 triángulos), el material LUT bilineal 512×512 y el raster por dimensión el doble de la salida. No se reducen esos valores para compensar una máquina lenta. El usuario conserva Eco/movimiento reducido/estático como elecciones, no degradación silenciosa.

## Optimización preservando el fotograma

`SoftwareShapeCache20` reutiliza la parte independiente del tiempo de la superficie, con un máximo de ocho entradas. Las formas dependientes del tiempo conservan su ruta original. Se mantiene el orden de redondeo Float32 de las curvas tubulares para evitar diferencias. Las pruebas comparan salida directa y caché en todas las formas.

`resolve2x` acelera píxeles opacos sin cambiar el cálculo del borde premultiplicado. El test incluye alfa fraccionaria, no solo áreas opacas. Se reutiliza el buffer de ondas y se elimina la degradación automática `adaptive`.

El límite de planificación de Balanced/High permite refrescos hasta 60; esto es un destino del programador, NO un FPS obtenido. El benchmark aislado compara 48 dibujos calientes de dos instancias nuevas e idénticas a 430×430. Guarda los PNG y comprueba todos los bytes RGBA. Véase VALIDACION.md.

## Chat mínimo y entrada

No se clonan ni el compositor ni el historial. Los nodos existentes se trasladan dentro del menú. El encabezado original conserva el asa de arrastre; los botones, summary, details y campos no lo disparan. La captura de selección y la aprobación del dictado siguen en su propio componente.

El textarea tiene autoaltura acotada y borrador independiente de la solicitud pendiente. Opciones de modelo/conexión, medidas, nueva conversación y exportación permanecen accesibles. El desplazamiento conserva el contexto del lector. Los comandos son los del ejecutor anterior; no se interpreta una cadena HTML como marcado.

## Regreso y prioridades

Home18.home repliega con FlowDock.step=0. Su bucle no puede forzar Herramientas visible. Al tocar aparcado: despierta y revela solo la cápsula. Un gesto tiene que superar siete píxeles para ser arrastre; pointercancel, lostpointercapture y blur limpian el seguimiento del gesto. El retorno no cancela tiempo/música local/grabación; se mantiene la política explícita de detener entrada de micrófono/traducción.

## Construir y verificar

```sh
npm install
npm run build
npm test
node scripts/server20.mjs
python -m pip install playwright
python scripts/identity20-browser.py
python scripts/chat20-browser.py
python scripts/jitter20.py
python scripts/layout20-browser.py
python scripts/polish20.py
python scripts/capture20.py
```

El build genera Axx.html, Axx-20.html y dist/index.html idénticos. Los scripts usan `/usr/bin/chromium`, `set_content` y Map de almacenamiento, porque la navegación directa estuvo bloqueada en el entorno de entrega. Para probar un PC, usar el navegador instalado, `page.goto` al servidor y almacenamiento real, sin simulaciones de permisos/voz. No alterar políticas para eludir un bloqueo.

Las regresiones actuales comienzan por `regression20-`; ejecutan el HTML 20, aunque conserven el nombre del escenario 19. Sus ayudantes pueden detener el renderer y usar un ticker de prueba para aislar tareas. No presentar sus tiempos como rendimiento gráfico.

`benchmark20.py` necesita la base original Axx-19.html junto al workspace para comparar. Ese archivo se conserva en el entorno de trabajo y no se distribuye como ejecutable principal; obtenerlo del ZIP anterior y comprobar su hash de VALIDACION.md. No cambiar preferencias de producción desde el benchmark.

## Referencias técnicas

Consultadas el 18 de octubre de 2026:
- https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
- https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame

Las reglas de identidad, límites, medidas y reacciones son decisiones del proyecto. La documentación de API no garantiza la ejecución en Windows ni rendimiento de 60 FPS.
