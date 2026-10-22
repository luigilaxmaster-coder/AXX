# Revisión de la entrega de escritorio — 22 de octubre de 2026

Versión 0.20.10, rama `codex/magic-pen-h1`. Esta revisión reúne los cambios locales de escritorio y distingue código, comprobaciones automatizadas y pruebas nativas anteriores. No certifica ausencia de lag en cualquier equipo o carga.

## Cambios incluidos

- **Magic Pen MP-H1:** una entrada en el menú circular; captura con exclusión temporal de Axx; selección por punto, rectángulo y lazo; tinta, borrador, deshacer/rehacer; consulta de la selección mediante el proveedor visual disponible; historial y exportación PNG verificada. Las credenciales y la configuración personal permanecen fuera de Git. No se implementa un motor OCR dedicado ni fases posteriores.
- **Paneles:** diseño compartido grafito/lavanda sin filtros de fondo, menú circular transparente y superficie nativa estable. El arrastre tiene un único controlador; el muñeco se mueve localmente durante el gesto y comunica la posición al soltar. Se conservan identidad, datos y atajos existentes.
- **Acciones existentes en la copia de trabajo:** resolución de solicitudes de escritorio, inventario de aplicaciones, lectura SHA256 y biblioteca documental. Los procedimientos importados no se convierten en código ejecutable; los planes del modelo requieren revisión y aprobación antes de sus efectos y sólo se guardan como aprendidos tras verificarse.
- **Convertidor existente en la copia de trabajo:** PNG/JPEG y unión/extracción de páginas PDF, límites de entrada, verificación del resultado y aviso de capacidades ausentes. Incluye pypdf y su licencia.
- **Empaquetado:** versión coherente en los manifiestos y finales LF para conservar los hashes de los recursos de voz. La revisión añadió los archivos ZIP al inventario de fuentes del build: un cambio en la biblioteca documental ahora invalida la reutilización del backend.

## Comprobaciones realizadas antes del push

| Comando | Resultado |
| --- | --- |
| `python -m unittest discover -s backend/tests -p 'test_*.py'` | 99 pruebas aprobadas. Avisos de cierre de HTTPError en pruebas; sin fallos. |
| `cargo test --manifest-path src-tauri/Cargo.toml --lib` | 14 aprobadas; 1 auxiliar ignorada deliberadamente. |
| `node 1.AXX/scripts/test-magic-pen.cjs` | Contrato de interfaz aprobado. |
| `node 1.AXX/scripts/test-action-learning.cjs` | HTML completo y backend congelado: escritura, SHA256, aprobación y repetición aprendida comprobados; respuesta del modelo controlada. |
| `node 1.AXX/scripts/test-internal-actions.cjs` | 6 comprobaciones aprobadas; IPC y micrófono controlados. |
| `python 1.AXX/scripts/test-converter-ui.py` | Navegación, entrada y resultado aprobados con puente simulado. |
| `python -u scripts/verify_converter_packaged.py` | Backend congelado produjo y reabrió JPEG 2×2 y PDF de dos páginas. |
| `node 1.AXX/scripts/test-tools-interaction.cjs` | 8 comprobaciones aprobadas en dos repeticiones finales, sin excepciones JavaScript. |
| Parser de PowerShell e inventario de build | Sintaxis válida; `procedure-library.zip` incluido. |
| Revisión de archivos preparados | Sin patrones de claves privadas/API detectados, sin archivos superiores a 90 MiB. No sustituye una auditoría de seguridad exhaustiva. |

Una primera ejecución de interacción, mientras se ejecutaban otras suites, falló en la posición de Magic Pen al soltar el panel. Dos repeticiones posteriores pasaron. Se amplió el diagnóstico de la aserción; no se atribuye una causa ni se presenta como corregido ese fallo intermitente. La muestra de reposo final observó una consulta de estado en 600 ms.

## Evidencia nativa y paquetes

Las pruebas nativas anteriores de 0.20.10 recorrieron 31 vistas: apertura/cierre sin desplazamiento del muñeco ni fotogramas donde un panel lo cubriera en la muestra. El arrastre nativo registró el desplazamiento solicitado de −70, −45. Se conservan resultados estructurados en `evidence/review-20261022/`; se excluyen las capturas privadas y las copias de fuentes de trabajo.

El instalador existente `dist/Axx_0.20.10_convertidor-20261022_x64-setup.exe` tiene 247334589 bytes y SHA256 `D44AA4E96B15BBD7792BF1A0C71800866BFF17E634BFB3479EA1DFB926F261D7`. El frontend principal y los archivos Rust de residencia de su snapshot coinciden por hash con los revisados. El backend congelado comprobado tiene SHA256 `C729DF6F124F1681C9C503FAB92B3A51D3C4E701CA91AFB09E918E68BBCAA96D`. Los ajustes de diagnóstico de pruebas y del inventario del build hechos durante esta revisión no se han vuelto a empaquetar. Los instaladores no se suben a Git.

El acceso habitual continúa siendo `INICIAR-AXX.cmd`, que abre el ejecutable instalado. Las pruebas nativas de apertura desde ese acceso constan en las evidencias locales de las entregas anteriores; esta revisión para Git no vuelve a controlar el escritorio.

## Pendientes y exclusiones

- Prueba física de llamada mediante `Alt+Shift+A`: la sesión anterior se detuvo por Escape del usuario antes de completarla. La conexión del atajo existe, pero no se declara validada esa llamada.
- DPI mixtos, lápiz físico y rendimiento sostenido con otras aplicaciones: pendientes.
- OCR dedicado: no disponible. La visión depende de un proveedor configurado localmente y no se incluyen credenciales.
- Investigar el fallo intermitente de la prueba de arrastre bajo concurrencia.
- El prototipo `mobile/` y sus scripts estaban sin seguimiento y pertenecen a otro trabajo. Se conservan localmente; no se publica su entrada `npm run mobile` en este commit.
- Las capturas privadas, binarios, archivos temporales y snapshots se conservan localmente fuera del commit.

Los logs completos de esta revisión quedan en `build/push-review-20261022/`; el índice anterior y el diff local se respaldaron allí antes de preparar el commit. `staged-source-hashes.json` registra el inventario preparado inicialmente, antes de los ajustes finales del script de build y del test.
