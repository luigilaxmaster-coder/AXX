# Entrega instalada: Axx 0.20.22

- Fecha: 23 de octubre de 2026.
- Ejecutable instalado: `C:\Users\luigi\AppData\Local\Programs\Axx\Axx.exe`.
- Fuente: commit `7945e59` (`feat: add verified Windows application control`).
- Instalador: `build/release-0.20.22/build-result.json`.
- Instalación y runtime: `build/release-0.20.22/installed-files.json` y `build/release-0.20.22/installed-runtime.json`.
- SHA-256 del instalador: `ef8f04f940681c78e5800045f3e59c474cbccb6b5c5e31c86ae22df445fc6f64`.
- Resultado de la instalación: PASS; versión 0.20.22 en el registro; Axx y backend instalados coinciden con sus hashes de build; host y backend iniciaron, la superficie nativa reportó visible y una solicitud sin token recibió HTTP 401.

## Aceptación de control de aplicaciones

- Notepad se abrió y Windows confirmó su ventana en primer plano. Un documento temporal nuevo expuso un control UIA `Document` con `ValuePattern`; el comando `axx.desktop.window.set_value` requirió aprobación, verificó el SHA-256 y longitud del valor leído, y una segunda operación aprobada limpió el búfer temporal.
- Explorador se abrió y su árbol UIA se observó. Windows mantuvo Notepad en primer plano y denegó la solicitud de foco de Explorador; el flujo informó `ready_for_action: false` y no envió una acción posterior.
- El árbol accesible de la aplicación instalada informa el host `Axx` visible, pero WebView no expone los controles del catálogo por UI Automation. La captura y aceptación visual nativa completa queda pendiente; no se certifica que el flujo se haya ejecutado desde la interfaz instalada.
- La cobertura es por aplicación y acción. No se afirma compatibilidad universal. La entrada física y el cursor remoto continúan bajo el propietario existente de Windows; UIA no crea un segundo flujo de `SendInput`.

Ver el alcance, verificaciones y límites en [CONTROL-DE-APLICACIONES.md](docs/CONTROL-DE-APLICACIONES.md) y [las notas 0.20.22](docs/releases/0.20.22.md).

