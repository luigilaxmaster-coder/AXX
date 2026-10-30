# Android 0.2.8 · Rendimiento conservando la imagen

29 de octubre de 2026. Android **0.2.8-companion / versionCode 29**; Windows mantiene su versión independiente.

## Cambio y conservación visual

El perfil del Samsung SM-A217M identificó cálculo repetido de geometría esférica en las gotas. Se conservan en memoria los 759 vértices base Float32 originales (9.108 bytes por renderer que use gotas). El primer uso calcula una esfera; los siguientes reutilizan sus muestras. Antes se calculaban 2.277 muestras por fotograma. Las tres gotas siguen calculando su posición, movimiento y radio en cada dibujo, con las mismas operaciones y conversión final a Float32.

No cambian resolución de canvas/raster, supersampling, mallas, número de gotas, shaders, iluminación, materiales, animación ni interfaz. La geometría y el resto del renderer siguen extrayéndose del escritorio. No se cambia el ejecutor ni el transporte de sincronización. El modo de compatibilidad conserva su recorrido original.

La huella protegida del adaptador GPU se actualiza mediante esta revisión autorizada de rendimiento, respaldada por comparación de imagen; no para ocultar una modificación visual. Las otras nueve superficies protegidas permanecen intactas.

## Medición física del candidato

Prueba controlada en el WebView real del Samsung, calidad `balanced`, canvas **544 × 544**, raster **1088 × 1088**, 16.128 triángulos de malla. Se alternaron seis rondas con 18 dibujos por variante; se comparó la mediana de las medianas. No se modificaron los ajustes guardados del personaje para esta medición.

| Forma | Recorrido anterior | Con caché | Reducción del tiempo |
| --- | --- | --- | --- |
| 8 | 19,5 ms | 15,1 ms | 22,6 % |
| 11 | 19,7 ms | 15,2 ms | 22,8 % |

Los tres acabados dieron **cero bytes RGBA distintos** antes/después en ambas formas. Los tiempos y muestras están en [performance-20261029.json](evidence/performance-20261029.json). Esta medición de dibujo no promete una tasa sostenida de FPS ni cuantifica batería, temperatura o todos los teléfonos.

## Regresión incorporada al protocolo

La suite de personalización compara el recorrido original heredado y el optimizado sobre el mismo renderer: las 24 formas, las nueve paletas distribuidas entre ellas, tres acabados, estados idle/thinking y las vistas de diagnóstico de la forma 11. Son **81 comparaciones exactas de píxeles**. Comprueba también que la esfera se calcula una sola vez, que el segundo uso no vuelve a generarla y que calidad/adaptación no bajan. La prueba existente de CPU fallback se conserva.

```powershell
node mobile/build.mjs
.venv/Scripts/python -m unittest mobile.tests.test_personalization -q
.venv/Scripts/python scripts/validate_companion.py --output build/mobile-0.2.8/companion-validation.json
```

El gate conjunto incluye estas regresiones y mantiene los 120 escenarios de pantalla y las doce referencias de apariencia. Una comparación de píxeles no sustituye la firma, instalación ni aceptación física de la nueva APK; esos resultados se registran por separado.

## APK instalada y aceptación física

El gate integrado pasó: 10 pruebas de contrato, 92 de servicio (una omitida) y 36 de navegador, incluyendo las 81 comparaciones exactas, los 120 escenarios y las doce referencias previas. Android compiló; se verificaron identidad `com.axx.mobile`, código 29, firma idéntica a 0.2.7, integridad ZIP y los 20 archivos web empaquetados.

Se actualizó el Samsung en sitio, después de guardar y comprobar una copia privada. El SHA-256 leído del APK instalado coincide con **`7b1008f856aa9c2b1cb93f0dce63ebe8c107382d7cbe4c305425fed6769fbb93`**. El enlace, tema, acento, tamaño de texto, preferencia de movimiento, borrador y apariencia se conservaron. Tras reiniciar la app móvil reconectó con la misma identidad y siguió presentando la apariencia del PC. La consulta móvil `axx.system.telemetry` terminó `succeeded` con `postconditions_passed=true`. GPU activa, cero fallos de renderer registrados.

La comparación alternada repetida con el código **realmente instalado**, sin inyectar el candidato, dio **18,2 → 15,1 ms por dibujo** (17,0 % menos), con la misma resolución/malla/calidad y cero bytes RGBA distintos en los tres acabados. El recorrido de referencia es el heredado del renderer original. Los tiempos dependen de carga y temperatura; las mediciones de candidato e instalado se mantienen separadas en sus informes.

[Recibo físico y muestras de la APK instalada](evidence/performance-installed-028-20261029.json). Los datos privados de respaldo permanecen en `build/mobile-0.2.8/` y no se publican. El APK es un artefacto local de prueba. No se repitieron QR óptico, audio ni gestos remotos completos; no se midió autonomía, temperatura sostenida ni FPS prolongados. No se instaló ni reinició Windows para esta entrega exclusivamente Android.
