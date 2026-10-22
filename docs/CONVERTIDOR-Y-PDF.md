# Convertidor y PDF de Axx — fase inicial

## Integración comprobada

Axx Desktop usa `1.AXX/Axx.html` para la órbita, el catálogo y el panel persistente/redimensionable; `1.AXX/scripts/converter.js` añade la vista dentro de ese panel. El mismo puente Tauri (`backend_request` en `src-tauri/src/lib.rs`) lleva peticiones autenticadas al servicio Python (`backend/server.py`). `backend/converter.py` crea trabajos y resultados bajo el directorio privado de artefactos de Axx. El historial lee manifiestos JSON de salidas completadas. No se conecta a la IA para ejecutar operaciones.

La acción rápida **Convertidor** aparece junto a Dictar y Grabar; también se encuentra en el catálogo y se abre con «abre el convertidor» en el comando local. El panel conserva el sistema existente de posición, tamaño, foco y preferencias. Dictar, Grabar, Chat y Magic Pen no cambian de implementación.

## Capacidades por dirección

| Entrada → salida | Motor y requisitos | Estado | Opciones | Conserva / transforma | Validación |
|---|---|---|---|---|---|
| PNG → JPEG | Pillow 12.1.1 en el equipo de desarrollo; Pillow en el paquete | Implementada local | Fondo hexadecimal, calidad 20–100 | Dimensiones y orientación efectiva; compone alpha; JPEG tiene pérdida | Decodificación, formato, dimensiones y SHA-256 de salida |
| JPEG → PNG | Pillow | Implementada local | Sin opciones iniciales | Dimensiones, orientación efectiva, ICC si existe; no recupera detalle | Decodificación, formato, dimensiones y SHA-256 |
| PDF + PDF → PDF | pypdf 6.1.3 | Implementada local | Orden de selección | Páginas y tamaños físicos; no reconstruye marcadores o metadatos globales | Reapertura, número y cajas de páginas, SHA-256 |
| PDF → PDF (extraer páginas) | pypdf 6.1.3 | Implementada local | Rangos 1-based, sin duplicados | Orden solicitado y tamaños físicos; no reconstruye marcadores o metadatos globales | Rangos previos, reapertura, número y cajas de páginas, SHA-256 |
| DWG/DXF ↔ DWG/DXF, DWG → PDF | AutoCAD 2025 detectado | Pendiente de implementación | Ninguna habilitada | Sin afirmaciones de conservación | No verificada |
| RVT → PDF/DWG/IFC/SKP | Revit 2024, 2026 y 2027 detectados | Pendiente de implementación | Ninguna habilitada | Sin afirmaciones de conservación | No verificada |
| SKP/Layout → CAD/PDF/3D | SketchUp y LayOut 2023 detectados | Pendiente de implementación | Ninguna habilitada | Sin afirmaciones de conservación | No verificada |
| PDF vectorial → CAD, IFC → visualización y demás rutas del catálogo | Adaptadores aún no integrados | Pendiente de implementación | Ninguna habilitada | No se promete reconstrucción exacta | No verificada |

La detección de aplicaciones se hizo mediante entradas de desinstalación de Windows y existencia de `acad.exe`, `Revit.exe`, `SketchUp.exe` y `LayOut.exe`. No demuestra licencias, automatización, complementos de exportación ni compatibilidad de versiones. Las rutas CAD/BIM quedan deshabilitadas hasta probar lectura, escritura, unidades, geometría y salida con cada aplicación.

## Contrato y límites de la fase

El panel acepta 1–10 entradas; cada archivo puede ocupar hasta 30 MB, con un máximo de 60 MB por trabajo. Los envía al backend local en fragmentos de 256 KiB por el puente privado de Axx. El backend comprueba tamaño, orden de fragmentos, firma y decodificación real antes de ofrecer una operación. PNG/JPEG admiten un fotograma y hasta 40 millones de píxeles. PDF admite hasta 1000 páginas, rechaza cifrado y documentos con AcroForm, incluidos los formularios y firmas que registra ese catálogo. No se ejecutan contenidos incrustados.

Cada trabajo usa una carpeta nueva con identificador aleatorio. La conversión ocurre en `output.tmp`; se reabre y verifica antes de moverla a un nombre final. El manifiesto incluye hashes de entradas y salida, tamaño y propiedades verificadas. Las copias de entrada se eliminan al terminar o cancelar. Los originales seleccionados no se escriben. Dos conversiones pueden ejecutarse a la vez; una tercera recibe un error explícito. La cancelación se comprueba entre páginas y antes de publicar. En operaciones sin porcentaje del motor, la interfaz muestra la etapa y el tiempo transcurrido. Tras un cierre inesperado, Axx limpia los temporales e indica el trabajo interrumpido en Historial; el usuario debe volver a seleccionar las entradas. Los resultados ya publicados permanecen disponibles.

La validación PDF es estructural: número y cajas de página. **Aún no incluye comparación visual ni comprobación de fuentes, recursos o renderizado.** Los PDF protegidos, los formularios y las firmas requieren una ruta posterior específica. El panel no ofrece OCR, PDF/A, censura, Office, audio, vídeo ni conversión CAD/BIM.

## Construcción y comprobaciones

```powershell
python -m pip install -r requirements-converter.txt
python -m unittest backend.tests.test_converter -v
python 1.AXX/scripts/test-converter-ui.py
npm run build:windows
python -u scripts/verify_converter_packaged.py
```

`npm run build:windows` exige que Pillow y pypdf estén instalados en el Python elegido. pypdf se distribuye bajo BSD-3-Clause; su aviso está en `src-tauri/resources/license-notices/pypdf/LICENSE`. Debido a builds concurrentes en el árbol compartido, se congeló el frontend y `src-tauri` en `build/converter-package-snapshot-20261022`; allí terminó el instalador Axx 0.20.10. Sus hashes están en `evidence/converter-20261022/isolated-build.json`. El backend congelado produjo un JPEG y un PDF combinado reales en la prueba de paquete. El panel se probó en navegador con el puente simulado; falta un recorrido manual del panel dentro del `.exe`/instalador. Los tests actuales usan archivos pequeños generados para la prueba; no prueban todavía PDF firmado, fuentes complejas, documentos grandes ni salida visual.
