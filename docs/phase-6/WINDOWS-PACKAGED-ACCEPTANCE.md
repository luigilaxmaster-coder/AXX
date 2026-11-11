# Aceptación nativa de Windows — candidata Fase 6

Fuente: rama `claude/axx-phase-6`, **HEAD `4f4e18bffb22096b0dec380b29630464e0fc1d09`** (árbol limpio al construir; `f07f1ba` con las correcciones es ancestro de `4f4e18b`, que solo añade informes). Fecha: 11 de noviembre de 2026. Evidencia privada y paquetes en `build/phase6/` (ignorado por git; sumas en `build/phase6/EVIDENCE-SHA256.txt`). WebView2 real, backend empaquetado real, Ollama real; no se usó el Axx personal.

## Construcción (procedimiento oficial `scripts/build-windows.ps1`)

| Artefacto | Bytes | SHA-256 |
|---|---|---|
| `packages/Axx-0.22.46-phase6-4f4e18b-standard-windows.exe` | 201 388 522 | `1dad599dd085fdab459f680b9ffc6b084466e0b6a49d90935032786ff3757359` |
| `packages/Axx-0.22.46-phase6-4f4e18b-parallel-windows.exe` | 277 962 706 | `9fbcf1227fa5d000c7c0eb469bfc1c9b9a98db60e4e5ac9e4595a5aee992ef39` |
| `AxxPhase6.exe` (host de la paralela) | — | `d5c57ac0c9f4b6ca8ddafede356fae6af01bdd7a4fafeabc1c574046f57bd4f3` |
| `axx-backend.exe` (PyInstaller) | 23 232 132 | `fbcb9777303ff414afea963127b046fb69525610238a268a896f404c4aa0a32d` |

`build-result.json`: `source_commit 4f4e18bf…`, `source_tree_clean: true`, 4 pasos con código 0 (PyInstaller, QR empaquetado, ayuda de la pasarela nativa, `tauri build --bundles nsis`). Los hashes **difieren** de los de Fase 5 (`ad89a7…`, `7efc6f…`): no se reutilizó ningún ejecutable de Fase 5. Versión interna 0.22.46 (sin cambio de versión: candidata privada, no release). La paralela solo cambia `productName/identifier/mainBinaryName` y la compresión NSIS (`build/phase6/parallel.conf.json`, mismo mecanismo que Fase 5 con identidad `com.axx.phase6`).

## Aislamiento demostrado antes de instalar

- `installer.nsi` generado: `PRODUCTNAME "Axx Phase6 Candidate"`, `MAINBINARYNAME AxxPhase6`, `BUNDLEID com.axx.phase6`, `UNINSTKEY …\Uninstall\Axx Phase6 Candidate`, `INSTALLMODE currentUser`. El Axx personal usa la clave `…\Uninstall\Axx` y `Axx.exe`: ninguna colisión de clave de registro, proceso ni mutex (el namespace nativo deriva del identificador).
- El hook NSIS (`backend-bundle.nsh`) solo opera dentro de `$INSTDIR`; se instaló con `/S /NS /D=build\phase6\installed-parallel` (carpeta explícita dentro del repo, **sin accesos directos**).
- Perfil de datos aislado por variables de entorno del proceso (`LOCALAPPDATA`, `APPDATA`, `WEBVIEW2_USER_DATA_FOLDER` bajo `build/phase6/profile`); el lanzador comprueba el hash del instalador contra `SHA256SUMS.txt`.
- Antes/después (`original-before.json` / `original-after.json`): hash de `Axx.exe` personal **idéntico**, registro **idéntico**, sin procesos `Axx` en ejecución antes ni después; al cerrar, 0 procesos `AxxPhase6`, 0 backends de la candidata y puertos 11485/11486 libres. No se copiaron credenciales ni sesiones; los modelos de Ollama se leyeron de solo lectura.

## Resultados (CDP sobre el WebView2 real, `native-A/B/C/D/E.json`, `native-A2.json`)

| Prueba | Estado | Evidencia |
|---|---|---|
| Arranque, WebView2, backend empaquetado, versión | PASS | `native_status.backendReady`, `Axx.VERSION=0.22.46`, datos bajo el perfil de fase 6 |
| **A1** Crear grupo con borrador pendiente + enviar mensaje | **PASS** | Contexto rotado y adoptado por la UI; borrador conservado; respuesta completa; **0 fallos HTTP** (`window.__fail` vacío) |
| **A2** Segunda conversación, segundo grupo, cambiar de grupo con texto pendiente, enviar | **PASS** | Sin mezcla (`grupo A: 2 chats, B: 0` tras el cambio); 0 HTTP 400 |
| **A3** Persistencia tras reinicio real del proceso | **PASS** | Ambas conversaciones siguen en el grupo; mensajes persistidos |
| **B1** «AXX, muéstrame el estado actual de CPU y memoria RAM.» (qwen2.5:7b-instruct real) | **PASS** | Ejecutor existente (`origin=axx-provider`), `succeeded`, poscondiciones, 266 ms; tarjeta: `CPU: 27.8 % (12 núcleos) · RAM: 15.2 GB de 15.7 GB (96.9 %) · Disco libre 118.41 GB`; recibo persistido en el diario |
| **B2** Sin datos locales hacia el proveedor | **PASS** | Proxy de captura: ningún cuerpo enviado al proveedor en el turno siguiente contiene CPU/RAM/disco |
| **B3–B5** Argumentos inválidos, herramienta prohibida (shell), campos de autoridad | **PASS** | «Resultado de herramienta sin confirmar. Estado blocked.»; 0 operaciones nuevas (proveedor simulado en red local, app real) |
| **B6** Escritura en `auto_safe` | **PASS** | `awaiting_approval`, sin archivo |
| **B7** Cancelación con el proveedor real en curso | **PASS con limitación** | La solicitud cancelada no creó operación; el compositor volvió a funcionar, pero las dos primeras consultas siguientes recibieron `BUSY 409` (ver abajo) |
| **B8** Herramientas apagadas / proveedor sin `tools` | **PASS** | No se ofrecen herramientas; ver observación sobre la bandeja |
| **C1/C2** Arranque en frío (ver `OLLAMA-COMPOSER-END-TO-END.md`) | **FAIL por latencia** (documentado) | Timeout a los 60 s con el modelo descargado; desglose medido |
| **D1** Caída del backend empaquetado | **PASS** | Se mató `axx-backend.exe`; eventos `lost` → `ready`; nueva instancia; la UI recupera |
| **D2** Chat tras la recuperación | PASS | Respuesta completa (el modelo 1b devolvió una llamada mal formada → «sin confirmar»; no se cuenta como ejecución) |
| Tentáculos / avatar / apariencia nativos | PASS | `test-installed-tentacles` (31 s), `tendril-quality` (60 casos), `appearance` (18 s) — ver nota de reducción de movimiento |
| MCP empaquetado | PASS | `verify-mcp-packaged.py` sobre el backend instalado: 5 comprobaciones |
| Magic Pen nativo con visión | BLOCKED | Llega hasta la visión; «el catálogo local de Codex no confirma visión»; sin proveedor visual autorizado (igual que Fase 5) |
| Auditoría de superficies (68 vistas) | 2 hallazgos de contraste | `voices` (claro) y `chat` (oscuro: `.cw-thread`, `#cu-open`); no tocan código de esta fase; sin línea base |

## Hallazgos del producto empaquetado (no ocultos)

1. **Reducción de movimiento latente.** En un perfil nuevo, si Windows informa `prefers-reduced-motion` durante el primer arranque, la app persiste `reducedMotion=true` (`Axx.html:6978`) y **desactiva los tentáculos** hasta que el usuario lo cambia. El test nativo de tentáculos falló con `links 0` por esto (`Axx.flow.reduced === true`, `matchMedia` ya era falso) y pasó (exit 0) al restablecer el ajuste del perfil de prueba. No es regresión de esta fase (sin cambios de CSS/render); sí una trampa: el flag se fija una vez y no sigue al sistema.
2. **`providers.json` con BOM tumba el backend.** Mi lanzador (PowerShell 5.1) lo escribió con BOM y el backend empaquetado terminó con `JSONDecodeError: Unexpected UTF-8 BOM` («backend exited during startup»). Error del arnés (corregido), pero el backend podría tolerar `utf-8-sig`.
3. **Cancelar no libera la capacidad de inferencia al instante.** Tras cancelar con qwen7B en CPU, las consultas inmediatas dieron `BUSY: Inference capacity is busy (HTTP 409)` durante ~16–25 s (hasta que termina la generación en curso). La UI se desbloquea; el slot no.
4. Con la casilla de herramientas apagada (valor por defecto), la bandeja de Alcance responde «No encontré «…» en la bandeja» a frases tipo «muéstrame…»; es el comportamiento anterior conservado a propósito (solo cede al chat cuando las herramientas están activas).
5. `window.__fail` registró 756 errores durante D1: son sondeos fallidos mientras el backend estaba caído (esperado).

## No ejecutado
Instalador **estándar** en Windows limpio (identidad de producción), SmartScreen/WebView2 ausente, voz con micrófono físico, Telegram de extremo a extremo, Android físico/APK, visión/Magic Pen con modelo.
