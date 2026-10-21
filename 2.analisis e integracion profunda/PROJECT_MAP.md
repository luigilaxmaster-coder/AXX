# Mapa del proyecto real Axx

Inspeccionado el 19-10-2026 en Windows 11 x64. Este mapa describe código presente; la aceptación del instalador y sus límites se registran en `DELIVERY_STATUS.md`.

| Componente | Ruta y responsabilidad comprobadas |
|---|---|
| Proyecto canónico | `C:\Users\luigi\Desktop\Axx assistant`. No contiene repositorio Git; no hay rama/commit que atribuir a esta entrega. |
| Interfaz original | `1.AXX/Axx.html`: renderer líquido original, 24 formas, 9 paletas, `Axx.App`, `Companion`, `BrainClient`, `ResidentDesktop`, `DesktopRuntime`. |
| Entrada instalada | `%LOCALAPPDATA%\Programs\Axx\Axx.exe`; acceso `%USERPROFILE%\Desktop\Axx.lnk`. Verificar hashes/versiones en el informe de instalación. `INICIAR-AXX.cmd` busca el ejecutable, sin iniciar un servidor de demostración. |
| Conversación | `BrainClient.connect` y transporte `Axx.backendRequest` en el HTML. Catálogo utilizable exige `ready_locally`; inferencia verificada exige una respuesta final válida. |
| IPC | `src-tauri/src/lib.rs`: `backend_request`, rutas/métodos/tamaños validados y token conservado en Rust; el frontend no recibe el bearer. |
| Servicio | `backend/server.py`, HTTP loopback privado en puerto efímero. UUID de instancia y comprobación autenticada de disponibilidad; origen de navegador rechazado. |
| Router y cancelación | `backend/inference/router.py`, `adapter.py`, `process_manager.py`: trabajador del mismo ejecutable, plazo total, cuota compartida, cooldown, cancelación y árbol de procesos propio. |
| Credenciales | El router resuelve exclusivamente las variables `api_key_env` configuradas en el proceso. No se ha implementado aquí un almacén DPAPI de credenciales. Ninguna clave se copió de otras aplicaciones. |
| Herramientas | `backend/actions/executor.py`, `tools.py`: operaciones persistidas y artefactos confinados a `%LOCALAPPDATA%\Axx\artifacts`. Un lanzamiento de aplicación se registra como `dispatched`, sin prueba ficticia de control universal. |
| CLI-Anything | `backend/actions/cli_blender.py` y `vendor/cli_anything_blender`: generador upstream fijado y Blender local real. La capacidad admitida es una escena acotada, no scripts arbitrarios. |
| Memoria procedural | `backend/memory/procedural_memory.py`: SQLite autoritativo, receta basada en operación verificada y reutilización parametrizada. `ai_memory_adapter.py` inicia el servicio oficial propio autenticado y comprueba escritura/lectura. |
| Voz | `backend/speech/windows_tts.py`, `offline_asr.py`; cliente `1.AXX/scripts/native-voice.js`. SAPI y tiny CPU locales. Captura de micrófono/reproducción audible requieren su aceptación física. |
| Ventana Windows | `src-tauri/src/resident.rs`: geometría compacta/ancla global, DPI, bandeja, disponibilidad del primer dibujo y seguimiento del escritorio mediante API pública. `lib.rs`: máscara alfa, sondeo de cursor, atajos y Job Object. |
| Persistencia | `%LOCALAPPDATA%\Axx`: `providers.json`, `state.db`, `native-window.json`, `artifacts`, `ai-memory`. La autoridad original de apariencia sigue siendo `axx-studio-v2` en el perfil WebView. |
| Recursos y compilación | `src-tauri/tauri.conf.json`, Cargo y `axx-backend.spec`. `scripts/build-windows.ps1` comprueba hashes, empaqueta runtime/modelo, crea NSIS y rechaza deriva de fuente. |
| Pruebas | Backend: `python -m unittest discover -s backend -p 'test_*.py' -v`. Frontend: `node 1.AXX/scripts/test-desktop-frontend.cjs`. Rust: `cargo test --manifest-path src-tauri/Cargo.toml --lib`. Aceptación congelada: `backend/tests/verify_resident_packaged.py`. |
| Rollback | `%LOCALAPPDATA%\Axx\backups\delivery-20261019-175611` y `backups\resident-20261019`: fuentes, SQLite consistente, configuración y copia instalada previas. No se han borrado datos del usuario. |

El baseline bajo `baseline/axx-api-router` permanece como referencia original; las correcciones activas están en `backend`. El manifiesto original se conserva como evidencia histórica, sin regenerarlo para ocultar cambios documentales.

No declarar completas las puertas del producto a partir de pruebas controladas. Las comprobaciones del sidecar, de Chromium, del host y del hardware son evidencias distintas. Hey Axx e integraciones futuras continúan **FUTURO · NO ACTIVO**.
