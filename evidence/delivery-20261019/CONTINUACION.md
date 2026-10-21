# Continuación de entrega Axx Windows 0.20.1

Estado al detenerse: el usuario pulsó Esc físico y Computer Use ordenó detener el trabajo y no volver a utilizar sus herramientas durante este turno. No se ha construido ni instalado el instalador final 0.20.1. No confundir los instaladores 0.20.0 preexistentes con esta entrega.

## Entorno y protección

- Proyecto canónico: C:\Users\luigi\Desktop\Axx assistant. No existe repositorio Git en esta carpeta.
- Windows 11 Home x64, versión 10.0.26200, usuario laptop-9cjbqb83\luigi.
- Python3.12.10, Node24.14.1, Rust/Cargo1.96.0. CLI local @tauri-apps/cli2.12.3 fijada en package-lock.json.
- Copia de fuentes, hashes, configuraciones y SQLite mediante backup consistente: C:\Users\luigi\AppData\Local\Axx\backups\delivery-20261019-175611.
- Se respaldó también la instalación0.20.0 y su registro de desinstalación. No se desinstaló ni sustituyó esa instalación.
- Datos existentes: %LOCALAPPDATA%\Axx; perfil WebView existente: %LOCALAPPDATA%\com.axx.desktop.

## Implementación presente

- Host Tauri: proxy IPC privado, token en host, puerto dinámico, identidad de instancia autenticada, backend empaquetado, creación suspendida y Job Object retenido, cierre del árbol propio, escape explícito permitido para aplicaciones iniciadas por el usuario; instancia única; Alt+Mayús+A/doble A modificada/Esc; mapa alfa64x64 y controles, DPI, geometría persistida, arrastre/paneles/set_topmost.
- Frontend: transporte único backend_request, sin token ni puerto4173, cancelación correlacionada y descarte de resultado tardío; controles reales de archivos, telemetría y recetas en Ajustes; persistencia canónica. Root añadió CSS de transparencia nativa después del primer release compilado: necesita recompilación. Root añadió botón #desktop-blender y llamada de Esc a /axx-api/actions/cancel.
- Backend: servidor privado con autenticación/origen/tamaños limitados; trabajador congelado por solicitud; límite de pared70s y cierre acotado, escritura de stdin concurrente cancelable; cuota compartida implícita por scope, JSON estricto, rechazo401/política sin fallback, límites7MiB upstream/8MiB wrapper; SQLite/migración; acciones idempotentes confinadas a artifacts; recetas parametrizadas, historial de versiones y rechazo de operation_id con entradas distintas.
- ai-memory real3.1.1: adaptador autenticado y proceso propio, puerto aleatorio, embeddings none, lectura de confirmación completa, autoridad de ejecución SQLite. Binario oficial ya copiado a src-tauri/resources/ai-memory.exe y licencia al lado. Fuente del release52020da90131a5afea70a114a01e44a8e67b44f3; diferente del commit documental de auditoría. SHA256 exe C2BA1391A763E3D68E2B1CB10677F428934D1F54DDF066103C6A9DBEA372DC11.
- CLI-Anything: módulos originales fijados34f519533bc175d2fe287ab8316b0dd99bb9cc43 en vendor/cli_anything_blender con licencia/procedencia. backend/actions/cli_blender.py usa generador original y Blender4.5.5LTS realmente instalado, salidaPNG256x256, controles de timeout/cancelación/archivo/hash. Worker backend estaba terminando registro y /actions/cancel; inspeccionar esas fuentes antes del build.
- Empaquetado: axx-backend.spec actualizado con runtime Python, defaults sin secretos, módulos CLI-Anything y licencias. scripts/build-windows.ps1 genera backend + NSIS, verifica deriva de fuentes y hashes. Recursos Tauri incluyen ambos ejecutables y licencia. INICIAR-AXX.cmd abre exe instalado, no servidor Python.
- Configuración local respaldada: OpenRouter cambiado a ruta documentada openrouter/free; Gemini2.0Flash retirado deshabilitado. Ninguna credencial disponible en variables process/user/machine previstas. No se ejecutó inferencia remota. No se tomaron claves privadas de Ollama u otras aplicaciones.

## Evidencia ejecutada, no extrapolar

- Manifiesto original31/31 coincidente antes de cambios; no regenerado. Baseline original20 pruebas con19 errores teardown WinError32 por SQLite abierto. scripts/verify-baseline-windows.py ejecuta las mismas20 aserciones sin tocar baseline y cierra sus recursos:20/20PASS.
- Backend última suite completa confirmada41/41, antes del último registro/cancel de Blender; se requiere repetir por esos cambios nuevos. Log backend-tests.log; fallo intermedio de construcción de prueba conservado backend-tests-intermediate.log.
- Rust cargo check exit0; cargo test --lib7PASS/0FAIL +1 helper ignored invocado internamente por prueba de separación de Job. Logs native-check.log/native-tests.log.
- Frontend controlado con fixtures7/7 y0errores no capturados después de CSStransparente/botónBlender; frontend-contract.log. No equivale a app instalada.
- Primer PyInstaller anterior a últimos cambios: PASS; scripts/verify-packaged-backend.py pasó6 comprobaciones reales, archivo nuevo y receta tras reiniciar; packaged-backend-initial.json. Debe reconstruirse con cambios finales.
- ai-memory servidor oficial7/7 y adaptador real5/5, con reinicio real, lectura/búsqueda y segundo archivo distinto. Evidencias build/deps/ai-memory/acceptance-6e0433b286/real-ai-memory-acceptance.json y build/deps/ai-memory/axx-adapter-acceptance-cc730edcb2/real-axx-adapter-acceptance.json.
- CLI-Anything/Blender4pruebas dirigidasPASS incluyendo render/cancel reales. evidence/delivery-20261019/cli-anything-blender-tests.log y cli-anything-blender-render.json. PNG real %LOCALAPPDATA%\Axx\artifacts\cli-anything-delivery-evidence.png, SHA2566CC5923073475B27099493ED108F34DB3798FB10C6DE217D5355A5E3BB2EC48B.
- `npx --no-install tauri build --no-bundle` terminó exit0,2m09s, exe src-tauri/target/release/Axx.exe. Es un build INTERMEDIO anterior a CSStransparente y recursos/funciones finales; recompilar. Log native-release-compile.log.
- Preflight nativo abrió ventana propia observada con @oai/sky (tituloAxx, WebViewtauri.localhost/Axx.html, cuerpo líquido/paneles reales), sin Chrome y con PATH limitado a Windows. No fue prueba instalada. Lanzado desde %LOCALAPPDATA%\Axx\native-preflight-0.20.1\Axx.exe, PID4208 al crearlo; datos aislados %LOCALAPPDATA%\Axx\native-preflight-data. Puede seguir abierto; usuario interactuó con Ayuda y después Esc físico detuvo ComputerUse. No afirmar cierre probado ni matar otros procesos por nombre.

## Siguiente acción exacta

1. Respetar parada de ComputerUse en el turno que la recibió. Continuar al recibir nueva instrucción del usuario. No reiniciar auditoría.
2. Revisar última implementación de /actions/cancel y registroBlender; repetir `python -m unittest discover -s backend -p "test_*.py" -v` y pruebas pertinentes si algo cambia. Verificar spec pathex/hiddenimports/datas contra vendor existente.
3. Cerrar solo ventana de ensayo propia de forma controlada tras reautorizar nueva interacción; observar procesos descendientes. Evitar pruebas sobre documentos del usuario.
4. Ejecutar `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1`. Logs pyinstaller-build.log/tauri-nsis-build.log y build-result.json. No publicar mientras sourcehashes deriven.
5. Probar frozen final desde otra carpeta con ai-memory.exe junto a axx-backend.exe. scripts/verify-packaged-backend.py ya existe; ampliarlo para comprobar status.memory.available y procesoowned cuando se pruebe copia de recursos completa.
6. Instalación de prueba separada usando NSIS admitido `/S /UPDATE /NS /D=<ruta prueba>`; template NSIS ya revisado: UPDATE evita desinstalar la0.20.0 del usuario, NS evita cambiar accesos de prueba. Respaldos de registro existentes. Separar datos mediante LOCALAPPDATA del proceso en ensayo. Validar actualización/desinstalación solo del destino de prueba y restaurar registro con instalación final.
7. Instalar final en %LOCALAPPDATA%\Programs\Axx mediante actualización autorizada que preserve datos, verificar accesos existentes Escritorio\Axx.lnk y menúInicio\Axx.lnk al exe correcto.
8. App instalada: ventana/transparencia/alpha clickthrough/control/foco/atajos desde otra aplicación; acción creada desde UI; guardarreceta/reiniciar/nuevaentrada/segundoarchivo; ai-memoryreal; Blenderreal; chat error real de credencial; Esc; persistencia/cierre/reapertura; dejar finalabierta sin tarea de prueba.
9. Multimedia continúa pendiente de validación: WebViewSpeechRecognition/dictado e inserciónexterna no empaquetados como ASR; traducción sin credencial/browsetranslator no comprobada; voz real, música, captura/permisos, temporizador9→1 y MorphReach requieren prueba instalada. No confundir deshabilitar honestamente con completar. HeyAxx/IAI/BitNet/invisible_dots/móviles permanecen FUTURO.
10. Actualizar DELIVERY_STATUS.md y mapa real existentes con estados verificados, rutas/hash/tamaños/version/exits, evidencias y bloqueos. No entregar instaladores0.20.0 como resultado nuevo.

No hay publicación ni facturación, modelos grandes descargados, hooksglobales instalados o inicioautomático activado. No se ha completado la entrega solicitada.
