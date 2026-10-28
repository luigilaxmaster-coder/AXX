# Entrega Windows: Axx 0.22.14

Estado del 27 de octubre de 2026. **Instalado localmente; publicación pendiente.**
La descarga confirmada de GitHub continúa en 0.22.11, según `release.json`.

| Área | Resultado | Alcance / pendiente |
| --- | --- | --- |
| Compilación | PASS, instalador de 320.444.745 bytes | Backend nuevo y fuentes congeladas; recibo privado `build/release-0.22.14/build-result.json`. |
| Instalación | PASS | Archivos, 36 avisos de licencia, registro, accesos directos, host y backend autenticado. |
| Datos del usuario | Copia verificada de 647 archivos | CRC y snapshots SQLite comprobados antes de instalar; no se publican. |
| Backend | 717 pruebas: 703 PASS, 13 omitidas, 1 error de arranque | Tras corregir el plazo, módulo de gateway 21/21 PASS. No se repitió el banco global tras el cambio acotado. |
| Interfaz | Contratos de Magic Pen, chat, respuesta rápida, dictado y voz: PASS | No equivalen a entrada física ni aceptación del nuevo binario. |
| Xxx default | Selección nativa, persistencia tras reinicio y dos reproducciones Web Audio: PASS | Los cuatro selectores conservan Sam; ambas reproducciones terminan sin vaciados del búfer. Altavoces físicos y micrófono pendientes. |
| Magic Pen | 0.22.14 instalada: 14 checks PASS | Captura e inferencia reales, tinta durante análisis, cancelación, historial, exportación, dos monitores y grabación verificada. |
| Control del PC | Correcciones de identidad, captura fresca y serialización integradas y probadas por contratos | Pendiente concesión humana manual y ensayo real de dos ventanas en 0.22.14. |
| Fotos y video | Tres capturas nativas y video nuevo de presentación, identificados como 0.22.12 | Video de 15 s, 450 frames decodificados, sin audio. Grabación de acciones de 0.22.14 pendiente. |
| Investigación | Laboratorio M01–M15 revisado, sin promoción | Currículo incompleto y M15 bloqueado; no acredita ejecución en Axx. |
| Publicación | PENDIENTE | No se ha publicado un asset 0.22.14 ni se declara su hash confirmado por GitHub. |

## Identidad del paquete local

- Instalador: `f97d8ec5617be782599ffb1134e5c4cd023a1fb8236da4efe7c25fec69e57ffd`.
- Backend: `3d0c0cbe721ce5eabee502dd4fb46764383c9a0a7d56bdbc42e3b851472b97d8`.
- EXE instalado: `f695fb77167ec22b6e058925af6a6266496ce98b928912b1fc4a595a986cbc48`.
- El verificador constató la diferencia exacta de tres bytes del marcador NSIS de Tauri.

Los recibos privados están en `build/release-0.22.14/`: `installed-files.json`,
`installed-runtime.json`, `installed-xxx-http.json` y `visual-session-block.json`.
No se publican audio, muestras, pesos, conversaciones ni credenciales.

## Interrupción de la aceptación del PC

La sesión anterior se detuvo por la URL de una ventana Chrome. Al retomar se
pudo operar Axx y completar voz y Magic Pen. WSL y los contenedores de AnythingMCP
estaban apagados: se arrancaron sin cambiar credenciales ni desactivar el gateway.
Después, la tecla Escape física detuvo Computer Use antes de preparar y autorizar
la sesión de control del PC. Esa prueba y la publicación siguen pendientes.
AnythingMCP/WSL debe mantenerse activo; su arranque tras reiniciar Windows no es
automático. Véase [MCP local](docs/MCP-LOCAL.md).

El campo genérico `recording=DEFERRED_BY_USER` del recibo original de instalación
no representa la petición vigente de video. Se conserva ese recibo sin editar;
este registro aclara que el usuario sí pidió el video y que la nueva grabación
está pendiente por el bloqueo de la herramienta. El script ya utiliza
`NOT_VERIFIED` para futuras instalaciones.

[Notas y requisitos](docs/releases/0.22.14.md) · [Procedencia de los medios](docs/images/showcase/README.md) · [Publicación verificada](docs/RELEASING.md).
