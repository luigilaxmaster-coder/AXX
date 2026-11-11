# Validación de distribución

Código candidato: `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`. Rama local: `codex/axx-phase-5`. Fecha: 10 de noviembre de 2026, America/Santo_Domingo. Evidencia privada en `build/phase5/`; no se publica con los informes.

Resultado: **PASS de construcción e integridad; NOT_READY para publicación**. Paquetes privados en `build/phase5/packages/`. No se publicaron ni sustituyeron assets existentes.

## Identidad de fuente y recursos

El build estándar `windows-final/build-result.json` fija el commit `b99d8bd4855e3d516bdcdc4653a4eba314b0dd63`, árbol limpio al construir, 273 entradas de fuente y hashes de ejecutable/backend/instalador. `package-validation.json` vuelve a comprobar esos 273 hashes y los **2095 archivos** del backend efectivamente instalado en la candidata paralela. No hay modificación Python runtime entre el backend construido y el que se reutilizó con --SkipBackend; la reutilización comprobó huella de fuente y manifiesto onedir completo.

El overlay `parallel.conf.json` cambia sólo productName, identifier, mainBinaryName y compresión NSIS a zlib. Su SHA-256 es `6b69143b5dfdd090aa808a4792ae2e5bb532f866fdeff1c2ed9210be7fcf70ba`. El build estándar usa la configuración de producto original y LZMA. Son artefactos diferentes construidos desde el mismo código; la aceptación en el host acredita el paquete **paralelo**, no una instalación limpia del estándar con la identidad de producción.

La versión PE y los metadatos de ambos instaladores son 0.22.46 / 0.22.46.0, x64, currentUser. Es una candidata privada identificada por commit en el nombre. No es una nueva release publicada. Antes de publicar bytes distintos se requiere una nueva versión mediante `python scripts/release.py sync --version X.Y.Z`, reconstrucción y recibos nuevos. No se debe reemplazar el asset publicado 0.22.46.

PyInstaller incluye Python y dependencias onedir, PyAV, OCR, MCP y licencias/notices. El manifiesto y la exploración de nombres no encontraron account.dpapi, sesiones, providers.json, state.db, pesos model.bin ni muestras de voz en los recursos distribuidos. Esto no es un escaneo forense de secretos por contenido. No se incluyeron perfiles de prueba, capturas, grabaciones ni memoria de usuario. Office, Blender, modelos OCR/ASR/TTS opcionales y Ollama son dependencias externas o privadas; no se prometen incluidas. WebView2 está instalado en este equipo; NSIS usa downloadBootstrapper si falta: instalación completamente offline no acreditada.

## Paquetes y SHA-256

| Archivo | Bytes | SHA-256 |
|---|---|---|
| `Axx-0.22.46-phase5-b99d8bd-standard-windows.exe` | 201523268 | `ad89a76a7543c6423c1d0260c859493ecd94f263dc87f4b1e6e9ed7e656c924f` |
| `Axx-0.22.46-phase5-b99d8bd-parallel-windows.exe` | 278157677 | `7efc6f24cf36795afd27bdd3f5b75b03f4c6da59c562d5cd52436f7f8e3ed887` |
| `Axx-Android-0.2.14-code35-phase5-b99d8bd-debug.apk` | 11710523 | `7260d9ec53a278cce1748ad7ec0d71566a705aa940d71390188953eb6cfdb2a9` |
| `Axx-Android-0.2.14-code35-phase5-b99d8bd-UNSIGNED.apk` | 9814673 | `7d659969e0576401f49e4d410b07fc0e5849701f3dc528fc5cb74cccc13d7a8a` |

`SHA256SUMS.txt` permite comprobar los archivos preparados. El APK debug lleva certificado Android Debug SHA-256 `d1ae05895e7e8f43e8e7007028b3a27f84e802c309be13a4be04563e7c5361a8`. El APK UNSIGNED requiere firma del propietario. Los hashes permanecieron iguales al repetir Gradle desde el commit congelado; 214 tareas, 1 ejecutada, 213 up-to-date, 85 s. Se verificaron manifest/versiones y firma debug con aapt/apksigner. Los dos APK contienen los 22 recursos públicos esperados del renderer actual.

Se descargó un JDK 21 Temurin verificado por SHA-256 a build/phase5/jdk, sin instalación global ni cambio persistente de PATH; procedencia y hash en jdk-download.json. Fuente oficial: [Adoptium](https://adoptium.net/installation/archives). NPM raíz informó cero vulnerabilidades; mobile reportó seis moderadas en herramientas CLI/dev, sin altas/críticas. No se cambió el lock para ocultarlas ni se infiere que el runtime esté libre de vulnerabilidades.

## Ciclo del instalador en entorno aislado

| Prueba | Estado | Duración | Preservación |
|---|---|---|---|
| same_version_update_preserves_settings_models_memory | PASS | 13.922 s | 6 archivos |
| isolated_uninstall_preserves_user_data | PASS | 2.531 s | 6 archivos |
| reinstall_recovers_same_user_data | PASS | 11.422 s | 6 archivos |

Se comprobaron SHA-256 de providers.json, state.db (configuración/memoria/chats) y cuatro archivos del modelo ASR privado después de cada etapa. Tras reinstalar, se arrancó realmente el ejecutable, se recuperó el borrador `AXX_PHASE5_PERSISTENT_DRAFT` y se verificaron temas/configuraciones: `reinstalled-native.json`. El intento previo de actualizar con el proceso abierto retornó **2**, sin cambiar el backend: `running-update-denial.json` (2.194 s). No se evaluó un salto entre dos versiones de release distintas; se probó reinstalación/actualización de la misma candidata.

El Axx personal siguió activo y su hash/registro no cambiaron. La instalación paralela de prueba queda disponible bajo build/phase5 y cerrada. El lanzador `packages/Start-Phase5-Acceptance.ps1` verifica el hash del ejecutable y aplica el perfil aislado. Sin esas variables, el backend aún usa la ruta Axx habitual: **no abrir directamente el ejecutable paralelo ni usar el instalador estándar en el host**. El lanzador no levanta el proveedor de inferencia; el Ollama de prueba :11485 fue detenido. Para continuar chat se debe configurar un proveedor local autorizado en el perfil aislado o volver a levantar ese servicio de prueba. No copiar credenciales personales.

## Intentos descartados y pendientes

La primera compilación fue rechazada al cambiar la fuente durante el build y su instalador se movió a `rejected/source-change-rejected-706c192.exe`. Nunca se instaló/aceptó como candidata. El commit inicial de aislamiento tenía un escape inválido del nombre Windows; se corrigió y se probó con un mutex real antes de la construcción definitiva. La fuente congelada correcta es b99d8bd.

Pendientes: instalador estándar en Windows limpio con identidad de producción; firma/SmartScreen y escenario sin WebView2; migración entre versiones distintas; APK firmado de release, actualización/instalación física Android. No hay aprobación de producción ni prueba de recuperación ante corte eléctrico a mitad de instalación.
