# Entrega Windows: Axx 0.21.3

- Fecha: 23 de octubre de 2026.
- Instalación: `%LOCALAPPDATA%\Programs\Axx\Axx.exe`.
- Fuente funcional: `8fd67de`, sobre las actualizaciones remotas `afaf301` (0.21.2).
- Recibos locales: `build/release-0.21.3-verified/build-result.json`, `installed-files.json`, `installed-runtime.json` y `acceptance/`.
- Instalador: `Axx_0.21.3_x64-setup.exe`, 212.974.752 bytes.
- SHA-256 del instalador: `45b3471dbb48b09982f62f8cef253fc0a7f4e033f52c8b1c4621d7989c8cdf93`.
- SHA-256 del backend instalado: `336791abfb817fbb23baa53a58bc285fafc450f2d4536ec50cd056408eb5cb32`.
- SHA-256 del EXE instalado: `2972ab51ebc4715acd4ebd4055aa7ee26ee932be7a6c74d5f5ef9327e5020e13`. Se verificó la diferencia de tres bytes del marcador NSIS de Tauri respecto al EXE de build.
- Instalación y arranque: PASS; registro, archivos, backend autenticado, superficie visible y HTTP 401 a una petición sin token comprobados.

## Aceptación desde la app instalada

La prueba usa el WebView del EXE instalado y su IPC nativo, sin sustituir el backend. CDP se habilita temporalmente en loopback; la instalación final arranca sin esa opción.

- **P1:** dueño único de entrada y origen `axx_automation` observados. Un evento de mouse externo sin etiqueta de Axx revocó la concesión y dejó teclas/botones liberados. Es entrada sintetizada de Windows; queda pendiente la concurrencia con una persona usando hardware físico.
- **Foco del Explorador:** carpeta, ubicación Shell y foreground comprobados; ventana minimizada restaurada y enfocada; identidad de ventana cerrada rechazada.
- **P2:** escritura en documentos nuevos de Notepad con aprobación en la interfaz instalada y comprobación SHA-256/longitud. La pérdida de foco bloqueó la escritura. Repetir operation_id conservó el recibo sin repetir el efecto.
- **P3:** guardado del procedimiento desde la interfaz, variación de título/texto y ejecución sobre otro documento con un control UIA distinto, aprobación vigente y cero llamadas de modelo.
- **UIA lento real:** una fixture WPF demoró SetValue 12 segundos. Axx agotó el plazo en 8,2 segundos, conservó `unknown`, bloqueó el duplicado y reconcilió por lectura el efecto tardío. El proveedor registró exactamente una escritura. Dos ejecuciones pasaron.
- **Estabilidad:** se reprodujo `0xc0000409` con stdout/stderr del lanzador cerrados. Tras cambiar el logger a archivo, el mismo escenario sobrevivió a toda la aceptación. Recibos: `closed-stream-launch.json` y `native-crash-reproduction.json`.
- **Interfaz:** controles y superficie 3D capturados desde el WebView nativo; cero excepciones de página. Identidad visual y preferencias conservadas.

## Regresión y reproducción

- Python: **295 PASS**; Rust: **15 PASS**, un helper interno ignorado.
- Interfaz de comandos: **20 contratos PASS**; lector de ventanas y procedimientos con backend empaquetado: **PASS**. La planificación de esas pruebas utiliza un proveedor de modelo de prueba; no acredita inferencia de un proveedor real.
- `node scripts/test-installed-application-control.cjs build/installed-application-control`
- `node scripts/test-installed-uia-timeout.cjs build/installed-application-control`

Estos scripts requieren el host instalado con CDP temporal en `127.0.0.1:9224`, Python y el runtime Playwright utilizado por las pruebas del repositorio. El segundo compila una fixture WPF con .NET Framework de Windows. Usan documentos/carpetas de prueba y no cierran pestañas personales de Notepad. Relanzar normalmente al terminar para retirar CDP.

## Límites y publicación

La aceptación corresponde a estas acciones de Notepad, Explorador y al proveedor UIA de prueba. Otras aplicaciones, privilegios elevados y controles sin ValuePattern necesitan pruebas propias. Cancelar no revierte efectos ya recibidos por un proveedor externo: se conservan como inciertos. Wake word, dispositivos externos y pruebas físicas de Android quedan fuera de esta entrega. Android conserva su versión.

El estado y hash de la descarga pública se mantienen en `release.json` y README mediante `scripts/release.py publish`, después de comprobar el asset en GitHub. Ver [alcance de control](docs/CONTROL-DE-APLICACIONES.md) y [notas de versión](docs/releases/0.21.3.md).
