# Música del equipo — 21 octubre 2026

Implementación y revisión propia; sin revisor independiente.

## Cambios

- `src-tauri/src/system_media.rs`: servicio Windows local. GSMTC enumera sesiones, título, aplicación, estado y capacidades; Core Audio consulta el nivel de todas las salidas activas cada 50 ms y vuelve a detectar dispositivos cada 3 segundos. No captura el micrófono, no graba audio, no envía datos a APIs.
- `src-tauri/src/lib.rs` y `Cargo.toml`: registro de los dos comandos Tauri; se usan funciones adicionales de windows 0.61.3, ya presente en el proyecto.
- `1.AXX/scripts/native-music.js`: fuente predeterminada «Este equipo», selección automática/manual, controles con estado confirmado por Windows, rechazo de pulsaciones duplicadas, recuperación y decaimiento de señal antigua. La reacción visual usa amplitud medida, no un espectro/BPM inventado.
- `1.AXX/Axx.html`: fuente de equipo en panel y órbita; iconos accesibles; tocar el cuerpo en música ejecuta pausa/continuación; conserva la identidad guardada y fuentes anteriores.
- Pruebas: `test-native-music.cjs`, `test-native-music-windows.cjs`, arnés `src-tauri/examples/media_probe.rs` y actualización del servidor de fixtures existente.

## Verificación

- Baseline Rust: 11 aprobadas, 1 ignorada preexistente.
- Prueba nueva antes de implementar: fallo esperado, fuente nativa inexistente.
- Rust actual: 12 aprobadas, 1 ignorada preexistente.
- Navegador con IPC simulado: detección, pausa por toque, duplicados, selección de segunda sesión, reanudación, desaparición sin redirigir a otra app, audio sin controles, amplitud suavizada, decaimiento de señal antigua, fuente local. Cero errores JavaScript.
- **Windows real**, mismo módulo Rust que usa Tauri: sesión multimedia de una instancia aislada de Edge con audio local de prueba. Enumeración, pausa y reanudación verificadas tanto en GSMTC como en `HTMLMediaElement.paused`; cierre de sesión detectado y órdenes obsoletas rechazadas. Ver `native.json`. No se controlaron otras aplicaciones del usuario.
- Regresión: contrato completo del frontend 18 comprobaciones; chat 7; dictado (geometría, captura única, transcripción final y cancelación aislada), aprobados.
- Panel de música: el control de pausa está dentro de los límites visibles del panel sin desplazarse; comprobación geométrica y capturas revisadas.
- `tauri build --no-bundle`: exit 0. Binario final iniciado, PID 1892, ventana Axx respondiendo. SHA-256 `BE00CA6F0554D9BF2FEA554666D94C79699217C6D851C5EA9454FF240652DA98` (ver `build-result.json`). El backend de las tareas anteriores se conserva sin cambios en esta tarea.

## Límites comprobados

- Windows no devolvió salidas de audio activas durante esta sesión (`audioAvailable=false`, nivel 0); por tanto **no se certifica aún medición positiva de audio físico**. La API y la reacción visual están implementadas; se han probado reacción y silencio con valores de fixture. Servicios AudioSrv y AudioEndpointBuilder activos; ningún dispositivo de clase AudioEndpoint presente encontrado.
- El control real de transporte sí se validó con Edge. La prueba no operó físicamente el WebView de Axx; el enlace frontend/IPC se comprobó mediante fixture y compilación del binario.
- La reproducción puede pausarse si la aplicación publica controles multimedia de Windows. Sonidos de juegos, alertas u otras aplicaciones sin transporte se pueden detectar si hay salida activa, pero no pausar universalmente. No se simula «pausado» ni se silencia el equipo como sustituto oculto.
- Core Audio puede no medir audio en modo exclusivo si el dispositivo carece de medidor hardware.

## Referencias primarias

- [Sesiones multimedia globales de Windows](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager.requestasync)
- [Ejemplo de control de otras aplicaciones de Microsoft](https://devblogs.microsoft.com/oldnewthing/20231108-00/?p=108980)
- [Medición de salida Core Audio y limitación del modo exclusivo](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudiometerinformation)

Sin commit automático. Se conservan los cambios anteriores del usuario/proyecto.
