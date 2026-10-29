# Android 0.2.7 · Corrección de los 24 casos de pantalla

29 de octubre de 2026. Android independiente: **0.2.7-companion / versionCode 28**. Desktop conserva 0.22.26 y el API v1; no se modifica su ejecutor, datos ni apariencia.

## Corrección

- Las etiquetas de navegación pueden refluir dentro del ancho del botón, conservando fuente, texto y centrado. Se incluye el espacio de sus insets originales de 2 px para no introducir saltos de línea en tamaños que ya funcionaban.
- El área del personaje puede ceder altura antes de desplazar las acciones fuera del contenido. Su mínimo deja espacio para los controles de lanzamiento, incluso con texto grande.
- En ventanas de poca altura se aprovecha el espacio vertical de la portada y la flecha decorativa de sincronización sigue la altura del texto. La entrada a chat queda por encima de la navegación.
- El indicador decorativo de la entrada a chat se centra sin que una fila de grid desborde su círculo con texto aumentado. No se reduce el tamaño del texto ni se eliminan controles.

El personaje sigue usando la misma geometría y material del PC. Los colores, radios, fondos, texto, permisos y funciones se conservan.

## Regresiones obligatorias

El contrato promueve las diez ventanas del estudio y sus cruces completos a la matriz de entrega: claro/negro, texto 100/170/200 %, DPR 1/3 y teclado de 299 puntos. **120 de 120 escenarios pasan; cero incidencias de las comprobadas.**

`mobile/tests/fixtures/screen-failures-20261029.json` conserva los identificadores de los 24 casos originales. El test comprueba que todos siguen incluidos en la matriz obligatoria, exige 120 casos y falla ante cualquier incidencia. La entrada a chat se comprueba contra el comienzo de la navegación, no solo contra el borde inferior de la pantalla, para detectar también solapamientos.

El resultado completo corregido está en [screen-matrix-20261029-fixed.json](evidence/screen-matrix-20261029-fixed.json). El [informe inicial](SCREEN-STUDY-20261029.md) y su archivo de fallos se mantienen como históricos.

## Conservación del diseño aprobado

Antes de modificar el CSS se capturaron doce referencias de 339/390/440 píxeles CSS, texto 100/170 % y ambos temas, usando fixtures explícitos. Se conservaron en `mobile/tests/fixtures/approved-portrait-layout.json`.

La comparación local anterior/posterior de cabecera, marca, escenario del personaje, ajustes, entrada a chat y navegación obtuvo:

- **0 px de variación geométrica máxima** en las doce referencias.
- **Cero cambios** en tamaño de fuente, colores, fondos o radios de esos elementos.

El test queda incorporado al gate. Permite hasta 1 píxel CSS de tolerancia geométrica para pequeñas diferencias de métricas del navegador; exige igualdad de las propiedades de estilo. No se regeneraron las referencias después del cambio para ocultar diferencias.

Solo se actualizó la huella del CSS móvil en la baseline, con esta revisión y la petición explícita de corregir los casos sin rediseñar. Las demás superficies protegidas permanecen intactas.

## Reproducción

```powershell
python -m unittest mobile.tests.test_screen_contract -q
python -m mobile.tests.test_screen_contract --study --output build/screen-matrix-fixed.json
python scripts/validate_companion.py --output build/companion-validation.json
```

La última orden es obligatoria antes de publicar una entrega de Desktop. Los cambios exclusivos de Android conservan la versión Windows existente; no requieren reemplazar su instalador publicado con otros bytes.

## Compilación y controles de entrega

El gate local pasó con 10 pruebas de contrato, 92 de servicio móvil (una omitida) y 35 de interfaz, incluida la matriz completa y las referencias anteriores. Android 0.2.7/code 28 compiló correctamente. Se comprobó integridad ZIP, identidad `com.axx.mobile`, firma coincidente con la APK anterior y coincidencia exacta de los 20 archivos web empaquetados con sus fuentes validadas.

APK SHA-256: `0a9f384b3848b047e27e4176f46c332bf0c576f4d3e81c951a11d28d754c4a9e`.

Los recibos de fuente/APK y las capturas de revisión se guardan en `build/mobile-0.2.7/` y `build/screen-fixes/`. La compilación es un artefacto local de prueba, no una publicación en una tienda.

## Límites de aceptación

Estas comprobaciones usan Chromium y transporte nativo simulado de forma explícita. No acreditan los sensores, safe areas, postura de bisagra, sistema de archivos, teclado físico o rendimiento de todos los teléfonos. No se instaló la APK: el teléfono no estaba conectado y la aceptación física seguía aplazada. Esta corrección no cambia la aceptación física previa ni declara una build iOS.
