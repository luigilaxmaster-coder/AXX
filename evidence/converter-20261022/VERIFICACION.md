# Verificación de Convertidor y PDF — 22 de octubre de 2026

- `python -m unittest backend.tests.test_converter backend.tests.test_server_smoke -v`: 12 pruebas aprobadas.
- `python 1.AXX/scripts/test-converter-ui.py`: acción radial, panel, selección, envío de fragmentos y resultado con puente simulado aprobados; sin errores de página.
- La misma prueba de interfaz pasó sobre `build/converter-package-snapshot-20261022/1.AXX`, que es el frontend incluido en el instalador final.
- `python -u scripts/verify_converter_packaged.py`: el `axx-backend.exe` congelado produjo un JPEG 2×2 y un PDF combinado de dos páginas; ambos se reabrieron.
- `scripts/build-windows.ps1 -EvidenceDirectory evidence\converter-20261022`: el backend final se empaquetó con PyInstaller y superó la prueba de JPEG/PDF; los intentos de NSIS en el árbol compartido coincidieron con otro build y cambios de fuentes.
- Se congelaron `1.AXX`, `src-tauri` y el backend verificado en `build/converter-package-snapshot-20261022`. Desde esa copia, `tauri build --bundles nsis` compiló y generó el instalador Axx 0.20.10 sin conflictos. Los hashes están en `isolated-build.json`.
- Instalador final: SHA-256 `D44AA4E96B15BBD7792BF1A0C71800866BFF17E634BFB3479EA1DFB926F261D7`.
- Copia de entrega: `dist/Axx_0.20.10_convertidor-20261022_x64-setup.exe`, 247.334.589 bytes; hash idéntico al instalador de la copia congelada.

El instalador corresponde a una copia congelada del árbol compartido con cambios locales de otras funciones, no al commit aislado de `codex/converter-pdf`. Los artefactos en `src-tauri/target/release` del árbol compartido pueden pertenecer a builds concurrentes. Falta el recorrido manual del panel en la aplicación nativa y la comparación visual de páginas PDF.
