# Grabar un área del escritorio

En Axx para Windows, abre **Grabar pantalla** y pulsa el icono circular de grabación. Arrastra sobre el escritorio para seleccionar un rectángulo. Puedes arrastrar en cualquier dirección; **Esc** cancela la selección.

El halo rodea exactamente el área seleccionada, deja pasar los clics y cambia a ámbar al pausar. El halo y la ventana de Axx se excluyen de la captura. Toca el cuerpo de Axx o el botón de pausa para pausar/continuar; pulsa el cuadrado para finalizar. El vídeo continúa si cierras el panel de herramientas.

El MP4 se escribe directamente en `%LOCALAPPDATA%/Axx/artifacts/recordings`. Al terminar se comprueba que pueda decodificarse y aparecen los botones para abrir el vídeo y su carpeta. No hace falta guardar una segunda copia ni transferir el vídeo completo por el puente del navegador.

## Opciones y límites

- Compresión ligera, equilibrada o con máximo detalle; 15, 30 o 60 fps solicitados. El rendimiento real depende del área y del equipo.
- Cuenta previa de 0, 3 o 5 segundos; duración máxima configurable hasta 30 minutos activos. Las pausas no cuentan.
- Límite de 4 GB y área entre 16 × 16 y 7680 × 4320 píxeles. El codificador redondea dimensiones impares un píxel hacia abajo.
- **Esta modalidad nativa no graba sonido del sistema ni micrófono.**
- Requiere Windows con soporte de exclusión de ventanas de captura (Windows 10 2004 o posterior). El contenido protegido de otras aplicaciones puede aparecer negro.
- Ante un error de codificación se muestra el fallo y se conserva el archivo parcial que exista; no se presenta como vídeo completado.

La prueba de escritorio se ejecuta sobre una ventana de color creada por el propio test. Coordenadas negativas tienen cobertura unitaria; aún falta validar físicamente pantallas múltiples con escalas distintas y sesiones largas de grabación.
