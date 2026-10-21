# Axx instalada: 0.22.5

Recuperación adicional el 21 de octubre: se reprodujo un cierre del backend causado por una entrada inválida en la configuración heredada de proveedores. Se aisló únicamente esa entrada, se conservaron las otras dos y se guardó el original cifrado con DPAPI del usuario. No se modificaron binarios ni el almacén cifrado de perfiles. La misma instalación arrancó con backend disponible en 9,96 segundos; dos activaciones de Herramientas recibieron confirmación nativa, layout y foco, sin nuevo pánico. Identidad, ajustes y cámara guardada se conservaron. Axx quedó abierto con Herramientas.

Recibo actual: [recuperación de configuración y apertura](</C:/Users/luigi/Desktop/Axx assistant/build/completion-0.22.6-20261021/evidence/current-installed/recovery-delivery.json>). La protección de arranque y las dos correcciones adicionales están en el [candidato 0.22.6](</C:/Users/luigi/Desktop/Axx assistant/build/completion-0.22.6-20261021/CANDIDATE-STATUS.md>), **sin compilar ni instalar**, pendiente de la autorización adicional ya solicitada. No se certifican micrófono, arrastres físicos ni autenticación/inferencia remota por estas observaciones.

Entrega instalada el 20 de octubre de 2026. Axx quedó abierto con Herramientas desplegado. Ejecutable: `C:\Users\luigi\AppData\Local\Programs\Axx\Axx.exe`. Accesos habituales: Axx en el escritorio, **Alt+Shift+T** y **Herramientas** en la bandeja.

La apertura fallaba por un pánico del registro de fern al fallar la salida estándar y su respaldo stderr. La versión 0.22.5 utiliza únicamente el archivo de registro de la aplicación. Conserva los trabajadores nativos, el orden de cerrar/abrir paneles y la pausa de seguimiento junto a los controles. El muñeco, las formas, materiales y el perfil existente se conservan.

Después de finalizar el proceso instalador se activó la aplicación instalada dos veces: ambas aperturas recibieron confirmación nativa, ampliación del layout y foco del panel. El proceso permaneció vivo y el registro de pánicos no cambió respecto a antes de instalar. Axx Connect respondió desde la misma instancia del backend. La cámara guardada, el giro continuo, la inclinación, el estudio y los ajustes coincidieron con la copia previa; el ángulo de animación en curso cambia mientras está activo el giro continuo.

La fuente exacta de esta entrega está en [build/recovery-0.22.5-20261020](</C:/Users/luigi/Desktop/Axx assistant/build/recovery-0.22.5-20261020>). Para continuar el desarrollo use esa fuente y su recibo; las copias anteriores se conservan como historial y recuperación. No reconstruir una versión antigua tomando solamente la raíz histórica.

- [Recibo de entrega](</C:/Users/luigi/Desktop/Axx assistant/build/recovery-0.22.5-20261020/evidence/native-recovery-delivery/delivery.json>)
- [Aperturas verificadas](</C:/Users/luigi/Desktop/Axx assistant/build/recovery-0.22.5-20261020/evidence/native-recovery-delivery/install/tools-activation.json>)
- [Conservación de ajustes](</C:/Users/luigi/Desktop/Axx assistant/build/recovery-0.22.5-20261020/evidence/native-recovery-delivery/install/visual-preservation-canonical.json>)
- [Instalador entregado](</C:/Users/luigi/Desktop/Axx assistant/build/recovery-0.22.5-20261020/src-tauri/target/release/bundle/nsis/Axx_0.22.5_x64-setup.exe>)

Instalador SHA256: `A5B34774D89F1E1BC093E8441FBB191B612E5919F071C91BC0E9A6D01F62BC42`. Fuentes selladas: 331 entradas, manifiesto `0CA5F78F0414346089B1AEB99DF9ABCCD480AA38398F9E66EBA7EE00C52A30A0`.

Alcance: reparación instalada y apertura observada mediante activación del EXE, eventos y layout. Los arrastres físicos, micrófono y proveedores con credenciales remotas requieren validación separada; esta entrega no los certifica. No se hicieron nuevas llamadas de inferencia ni pagos. El backend se reutilizó byte a byte con su cadena de recibos; las comprobaciones anteriores de MCP, ASR y Ollama conservan su alcance original. La comparación estricta inicial de cámara se conserva en la evidencia y se explica en el recibo; no se alteraron preferencias para obtener un resultado favorable.
