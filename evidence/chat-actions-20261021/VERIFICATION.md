# Chat con acciones y reparación de Dictar — 2026-10-21

## Cambios

- `backend/actions/desktop.py`: acciones tipadas para abrir sitios/aplicaciones y búsquedas; ejecución explícita de PowerShell con salida acotada, entorno filtrado, tiempo máximo y cancelación.
- `backend/actions/tools.py`, `backend/actions/executor.py`, `backend/commands.py`: catálogo, validación, aprobación vinculada al script y cancelación por operación.
- `1.AXX/scripts/command-library.js`: las órdenes admitidas se resuelven antes que la bandeja antigua que capturaba cualquier «abre…»; el chat muestra el resultado real y la salida de PowerShell.
- `backend/server.py`, `1.AXX/scripts/native-voice.js`: detener síntesis/transcripción ya no cancela comandos pendientes ni otras acciones. Información de dictado local actualizada.
- `1.AXX/Axx.html`: instrucciones de capacidades corregidas; tocar Axx en Dictar inicia/pausa la captura, estado de finalización correcto, una autoridad de colocación nativa y paneles de dictado/destino separados. El control de herramientas queda fuera de los botones de dictado.
- `docs/COMANDOS-DESDE-CHAT.md`: instrucciones de uso y límites de ejecución.

## Diagnóstico reproducido

1. Las órdenes de apertura no tenían adaptador y la instrucción del modelo negaba toda ejecución.
2. En la interfaz completa, la bandeja de recursos interceptaba «abre YouTube» antes del nuevo resolvedor.
3. La lectura de mensajes llamaba a cancelar todas las acciones, anulando la aprobación de PowerShell.
4. El clic nativo sobre Axx abría el menú en modo Dictar; el menú oculta la tarjeta de voz. Los paneles de dictado y destino se superponían completamente (128.000 píxeles cuadrados en la prueba).

## Verificación

Todos los comandos siguientes terminaron con código 0 después de las correcciones:

- `python -m unittest backend.tests.test_command_library backend.tests.test_commands_http backend.tests.test_desktop_commands backend.tests.test_server_smoke -q`: 33 pruebas.
- `node 1.AXX/scripts/test-command-library.cjs`: 19 contratos de interfaz y cancelación.
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: 18 contratos generales; identidad, selección de modelo y herramientas conservadas.
- `node 1.AXX/scripts/test-chat-usability.cjs`: 7 pruebas de escritura, lectura y desplazamiento.
- `node 1.AXX/scripts/test-dictation-runtime.cjs`: interfaz completa, geometría estable, paneles sin solapamiento, toque del avatar, captura compartida, finalización y colocación sin envío. Micrófono/recorder sintéticos.
- `node 1.AXX/scripts/test-desktop-commands.cjs`: interfaz completa conectada por HTTP autenticado al backend compilado; entrega real de YouTube a Windows, aprobación de PowerShell, salida real en el chat y transcripción local real con Whisper de audio generado. Resultado detallado en `e2e.json`.
- `git diff --check`: limpio.
- PyInstaller y Tauri: logs de compilación en este directorio. Hashes y lanzamiento en `build-receipt.json`.

Las pruebas de PowerShell incluyen salida Unicode, errores, cancelación de un proceso realmente iniciado, límite de tiempo/salida, aislamiento de variables sensibles y prevención de ejecución por voz o por la ruta antigua sin aprobación.

## Alcance de la evidencia

El backend compilado y sus acciones Windows son reales. La prueba automatizada del HTML utiliza un puente IPC de prueba a HTTP; no equivale a una inspección manual de WebView2. Windows aceptó la apertura de YouTube; no se verificó visualmente la carga de la página. Whisper transcribió exactamente «Hello. This is a local dictation test.» desde audio de prueba; no se midió el micrófono físico del usuario.

Revisión propia. Cambios sin commit; se conservaron las modificaciones ajenas y las reparaciones anteriores de proveedores, chat, sonidos y herramientas.
