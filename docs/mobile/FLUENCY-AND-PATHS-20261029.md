# Android 0.2.9 · Movimiento y carpetas

## Corrección de movimiento

La cámara compartida llegaba en snapshots y se asignaba de golpe. El teléfono ahora aplica esa corrección progresivamente entre fotogramas, por el camino angular más corto, mientras conserva la rotación que ya estaba en curso. El primer estado se aplica directamente. Girar con el dedo/teclado o restablecer la cámara cancela la corrección pendiente; movimiento reducido conserva la aplicación inmediata.

Resolución, supersampling, mallas, shaders, materiales, luces, gotas y calidad permanecen iguales. No cambia el renderer extraído del PC ni se introduce otro modelo de geometría. La caché de gotas de 0.2.8 y sus 81 comparaciones exactas permanecen. La prueba nueva exige ausencia de salto inmediato, convergencia, giro corto alrededor de 2π, rechazo de cámaras no finitas y prioridad del gesto directo/movimiento reducido.

Se ensayó también cachear atributos WebGL con VAO: 15,9 frente a 16,1 ms por dibujo, sin diferencias de píxeles. Se descartó porque no demostró mejora. Esta entrega no afirma un aumento de FPS derivado de esa variante.

## Ruta configurada para otro enlace

Se reprodujo en Windows: existían cuatro enlaces llamados SM-A217M. La carpeta elegida estaba autorizada para otro enlace; el perfil obtenido directamente del Samsung actual no tenía lectura ni carpetas. Se aplicó manualmente la carpeta que el usuario ya había elegido al ID real de ese teléfono. Se conservaron los otros tres enlaces y sus permisos; el producto no migra ni copia permisos automáticamente.

En el teléfono, Archivos muestra el sufijo de su ID y la ayuda de permisos indica qué enlace debe elegirse en Windows. «Comprobar carpetas» vuelve a consultar permisos y carga las carpetas sin olvidar/recrear el enlace. El primer snapshot tampoco se anuncia como un cambio de PC. Las búsquedas y transferencias conservan su vinculación a la identidad TLS y al ID autorizado.

Prueba física previa a esta APK: navegar a Downloads, seleccionar un archivo propio de prueba de 9.600 bytes y traerlo al Samsung; SHA-256 `40b0dd3c586d50e196a786b5f5bebe39832871bf0673987c28f496b8c70fb520`, con persistencia nativa `received`. No se usaron documentos privados para esa comprobación. La selección inequívoca de enlaces en Windows se coordina con su responsable de entrega y se acredita por separado.

## Medición prolongada

Preparada: 20 minutos con animación y 10 minutos con la imagen quieta como referencia, misma pantalla y calidad. El registro nativo debe indicar ausencia real de USB/AC/carga inalámbrica; no se usa `dumpsys battery unplug`, simulación de batería ni reinicio de sus estadísticas. Se registran carga restante, contador de carga, temperatura de batería y estado/sensores térmicos, junto con tiempos de dibujo y visibilidad del WebView.

El contador Android expresa microamperios-hora; la diferencia se convierte a mAh. El consumo observado corresponde al teléfono completo, incluidos pantalla, red y tareas de fondo, y no permite atribuirlo íntegramente a Axx. [BatteryManager](https://developer.android.com/reference/android/os/BatteryManager#BATTERY_PROPERTY_CHARGE_COUNTER).

La prueba se detiene si Android informa estado térmico severo o superior. Se conserva el dato real; no se manipulan umbrales ni el estado térmico. [Niveles térmicos Android](https://source.android.com/docs/core/power/thermal-mitigation).

Una sesión oculta, bloqueada, reconectada a corriente o incompleta no acredita el tramo previsto. Los resultados de temperatura, batería, rendimiento e instalación se añadirán cuando termine el ensayo; no se presuponen por compilar o aprobar tests.
