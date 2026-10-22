# Instalador de GitHub 0.20.10: verificación para otra PC

Comprobación realizada el 22 de octubre de 2026 sobre el archivo descargado desde GitHub, no sobre una copia elegida del directorio de compilación.

**Resultado: contiene los últimos cambios funcionales de escritorio y está preparado para una prueba en otra PC Windows x64.** La instalación y el comportamiento en ese segundo equipo todavía deben comprobarse allí. Sigue siendo una versión de prueba.

[Descargar instalador](https://github.com/luigilaxmaster-coder/AXX/releases/download/v0.20.10/Axx_0.20.10_x64-setup.exe) · [Versión y archivos](https://github.com/luigilaxmaster-coder/AXX/releases/tag/v0.20.10)

## Integridad y contenido

| Comprobación | Resultado |
| --- | --- |
| Archivo de GitHub | `Axx_0.20.10_x64-setup.exe`, 247334589 bytes |
| SHA256 de la descarga | `D44AA4E96B15BBD7792BF1A0C71800866BFF17E634BFB3479EA1DFB926F261D7` |
| Archivo NSIS | Prueba y extracción con 7-Zip correctas; 32 archivos |
| Ejecutables | Axx, backend y ai-memory para x86_64 |
| Backend | 38 módulos compilados coinciden con las fuentes de `main` revisadas en `168e47bc46674879e9635e7b91303494eeef5413` |
| Interfaz y código nativo | 30 archivos coinciden con el snapshot de compilación, normalizando únicamente finales de línea de texto |
| Recursos | Bibliotecas de comandos/procedimientos, configuración predeterminada y cuatro archivos del modelo Whisper comprobados |
| Dependencias incluidas | Pillow, pypdf, faster-whisper, PyAV, CTranslate2, tokenizers y ai-memory |
| Datos privados | No hay bases de datos, credenciales DPAPI ni configuración personal en el archivo del backend |

El `Axx.exe` extraído tiene SHA256 `681C347792BAC65811DD45BB0F42E46D29CEAC68CC132A9C3CB36C53EDF091C0`. Frente al ejecutable del snapshot sólo cambian tres bytes del marcador de Tauri: `UNK` pasa a `NSS` al generar NSIS. Se comprobó la igualdad del resto del archivo. El backend extraído tiene SHA256 `C729DF6F124F1681C9C503FAB92B3A51D3C4E701CA91AFB09E918E68BBCAA96D`.

Las modificaciones posteriores de README, pruebas e inventario de compilación no alteran el comportamiento del ejecutable. No fue necesario reemplazar el instalador. El prototipo móvil separado no forma parte de esta entrega de escritorio.

## Pruebas sobre el contenido descargado

- **Arranque del backend con datos nuevos:** sin depender de las credenciales o del perfil de esta PC.
- **Magic Pen:** imagen sintética, selección por punto/rectángulo/lazo, persistencia de tinta, exportaciones original/anotada reabiertas y verificadas por SHA256, original inalterado y rechazo de peticiones sin autorización. La ausencia de proveedor visual se informa como tal. Esta prueba no captura una pantalla física ni valida respuestas de un modelo de visión.
- **Convertidor:** PNG convertido a JPEG y PDF de dos páginas unidos; resultados reabiertos correctamente.
- **Acciones:** HTML completo conectado al backend extraído, aprobación antes de efectos, creación de archivo y SHA256 real, procedimiento guardado y repetido. Modelo e IPC nativo controlados por la prueba.

Comandos principales:

```powershell
gh release download v0.20.10 --repo luigilaxmaster-coder/AXX --pattern Axx_0.20.10_x64-setup.exe --dir build/release-audit-20261022/download
& 'C:\Program Files\7-Zip\7z.exe' t build/release-audit-20261022/download/Axx_0.20.10_x64-setup.exe
& 'C:\Program Files\7-Zip\7z.exe' x build/release-audit-20261022/download/Axx_0.20.10_x64-setup.exe -obuild/release-audit-20261022/extracted -y
python scripts/verify_converter_packaged.py build/release-audit-20261022/extracted/resources/axx-backend.exe
node 1.AXX/scripts/test-action-learning.cjs build/release-audit-20261022/extracted/resources/axx-backend.exe
```

Resultados estructurados: [evidence/release-audit-20261022](../evidence/release-audit-20261022). Los scripts auxiliares de comparación y Magic Pen, archivos extraídos y logs completos permanecen en `build/release-audit-20261022/`.

## Cómo probar en la otra PC

1. Descargar el `.exe` desde el enlace anterior y, si se desea, comprobarlo con `Get-FileHash .\Axx_0.20.10_x64-setup.exe -Algorithm SHA256`.
2. Ejecutarlo e instalar Axx para el usuario actual. No se necesitan Python, Node ni el repositorio.
3. Tener Internet durante la instalación si falta Microsoft Edge WebView2: el instalador usa `downloadBootstrapper`. No es un instalador completamente offline en ese caso.
4. Abrir Axx desde su acceso instalado. Probar el menú circular, mover el muñeco y abrir/cerrar los paneles.
5. Probar captura, selección, tinta y exportación en Magic Pen. Para preguntar sobre una selección, configurar en Ajustes un proveedor con visión; el instalador no incluye credenciales personales ni un modelo visual local.
6. Probar voz con permiso de micrófono y comprobar las conversiones con archivos de prueba.

El instalador **no tiene firma digital**; Windows puede mostrar un aviso de editor desconocido. La comprobación del hash identifica el archivo publicado, pero no sustituye una firma.

## Límites pendientes

La validación nativa anterior se hizo en Windows 11. No se ha ejecutado esta comprobación en una segunda PC, una máquina virtual limpia, Windows ARM ni un entorno con DPI mixtos. Siguen pendientes el atajo físico `Alt+Shift+A`, lápiz físico y la investigación del fallo intermitente al soltar un panel. No incluye OCR dedicado ni una garantía de rendimiento en todos los equipos. Las comprobaciones anteriores de 99 pruebas Python, 14 Rust y apertura/cierre de 31 vistas constan en la [revisión de entrega](REVISION-ENTREGA-20261022.md).
