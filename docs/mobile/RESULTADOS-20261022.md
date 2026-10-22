# Revisión instalada — 22 de octubre de 2026

Latest revision: [pairing verification and current builds](PAIRING-VERIFICATION.md), [Windows input performance correction](INPUT-PERFORMANCE.md). The earlier build identities and test counts below are historical.


Ningún hito MO-1–MO-7 se declara cerrado. Este informe distingue los recorridos comprobados de la implementación pendiente.

## Comprobado en Samsung SM-A217M, Android 12 / API 31

| Recorrido | Resultado y evidencia |
|---|---|
| Entrada desde Inicio | Widget transparente 1×1 visible junto a Calendario; un toque abre `com.axx.mobile/.MainActivity`. `evidence/mobile-20261022/mo1/home-access-visible.png`. |
| Preferencias del launcher | Se desbloqueó temporalmente el diseño para colocar el acceso y se restauró su bloqueo. `launcher-lock-restored-final.xml`. No se cambió la visibilidad de otros juegos. |
| Personaje compartido | Se guardó temporalmente forma 3 en la PC; el teléfono recibió forma 3 y cambió el PNG privado del widget. Se restauró forma 19; el hash del PNG volvió exactamente al original. `appearance-sync-real.json`, `home-icon-changed.png`, `home-icon-restored.png`. |
| Emparejamiento LAN | Token de un solo uso por enlace alternativo, TLS con pin y credencial Android real. Escaneo físico con cámara todavía no ejecutado. |
| Permiso de micrófono | Diálogo real de Android: denegación y concesión de permiso mientras se usa la app. Evidencias en `remote-voice/permission-*.json`. |
| Atajo → captura → parada → ASR | El atajo global de Windows recibió teclas enviadas por `keybd_event`; Android inició MediaRecorder sin tocar su botón de micrófono. Segunda pulsación: `pc_stop`, 32 289 bytes de audio, transcripción mediante `faster-whisper` existente. Permaneció en `review`; se canceló sin ejecutar órdenes. `remote-voice/physical-shortcut-capture.json`. |
| Salir de la app | MediaRecorder terminó con `reason=background`. Tras cancelar desde la PC y volver a la app, quedó `idle`, sin archivo de audio retenido. `remote-voice/background-stop.json`. |

La transcripción de la captura breve no equivale a la prueba de una instrucción elegida por el usuario. El usuario indicó que no podía realizar la prueba hablada ahora. **Sigue pendiente atajo → frase humana acordada → comando de Axx → resultado verificado en PC y teléfono.**

## Comprobado en la PC instalada

- Atajo `Ctrl+Alt+Shift+V` registrado sin error. Modo de revisión y límite de 30 segundos restaurados tras las pruebas.
- Menú del muñeco: **Conectar teléfono · QR**. El acceso móvil es la primera sección de Ajustes; el QR real se genera desde **Activar / nuevo QR**.
- Backend instalado comparado por SHA-256 con el empaquetado. El EXE Tauri instalado difiere del EXE previo a NSIS únicamente en los tres bytes del marcador de empaquetado esperado.
- Actualizaciones sobre la instalación existente, sin desinstalar ni borrar datos. Copias verificadas en `build/mobile-backups`; registros en `evidence/mobile-20261022/remote-voice`.

## Pruebas automatizadas

- Backend móvil: 24 tests aprobados, incluidos idempotencia, permisos, vinculación y recuperación de voz. Usan dependencias aisladas; no acreditan ASR física ni ejecución real de herramientas.
- Android: 4 tests propios aprobados; también pasa el test de ejemplo incluido en el proyecto.
- Navegador: contrato de sincronización, cambio de PNG, conservación del icono ante movimiento de cámara, transparencia y accesibilidad por teclado aprobado con transporte de prueba.
- Rust: 14 aprobados, 1 ignorado.
- Android lint: sin errores; advertencias de compatibilidad de atributos, API obsoleta, recursos y dependencias conservadas en el informe del build.

## Límites y pendientes

- El icono dinámico es el acceso de Inicio. El icono del cajón de aplicaciones permanece como recurso base del APK. Samsung clasificó esta instalación como juego y ocultó el acceso convencional en Gaming Hub; el widget evita cambiar esa configuración global.
- La sincronización de apariencia funciona con la app conectada y visible. Al cerrar o desconectar se conserva la última imagen; se actualiza al volver a conectar. No hay sincronización permanente en segundo plano.
- No se acreditan todavía manos libres con resultado real, desconexión de red durante voz, reconexión física sin duplicados, llamada entrante ni Bluetooth. Las pruebas unitarias no sustituyen estas pruebas.
- Trackpad, teclado y lease de MO-4 integrados; aceptación física completa en curso. La voz mantiene un subsistema independiente. Ver CONTROL-REMOTO.md y los registros remote-control.
- Gran parte de M01–M34/V01–V72 sigue pendiente según `TRAZABILIDAD.md`. No hay entrega completa de MO-1–MO-7.
- iOS, Internet MO-8 y API 37 quedan fuera de la cobertura del dispositivo disponible.

Los hashes y versiones instalados se registran en `evidence/mobile-20261022/remote-voice/installed-builds.json`. APK: `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.
