# Axx 0.20.4 · movimiento residente del frontend

Implementación congelada exclusivamente en `build/resident-release-0.20.3/1.AXX`. El directorio conserva su nombre histórico; el host prepara la versión 0.20.4. No se compiló ni instaló desde esta tarea. El canónico `1.AXX/Axx.html` permanece intacto.

| Fuente | SHA-256 |
|---|---|
| Snapshot `Axx.html` | `EBB78A1B865EE818A4A2DD432839E6BE7304ADFCA58326880695C5B501722554` |
| Snapshot `scripts/native-voice.js`, sin cambios | `E61076C5081F8C442C054097731A7A15A25A1817E8035C6DAABEDB7594537555` |
| Snapshot `scripts/test-desktop-frontend.cjs` | `6FB6E3E66DCC8C18F8A494F28F875E58CB2A10E8892E861AD2C0A04FD9599697` |
| Canónico `1.AXX/Axx.html`, sin cambios | `5BB9DEEE92DB19509BE4F5DD61880E83A1DF5A180C7D7DA997B48D2BCE678682` |

Se conservan las 24 formas, nueve paletas, la malla y el material originales. `ResidentMotion` añade respiración, balanceo y atención amortiguada al puntero mediante los resortes existentes. Su pose solo modifica la proyección y el centro dentro del canvas transparente: no cambia la cámara guardada, no escribe `axx-studio-v2` y no solicita geometría nativa en cada cuadro. La máscara de entrada se obtiene de los píxeles actuales del renderer.

Movimiento vivo y paseo están habilitados por defecto por instrucción humana. El host controla el desplazamiento físico, limitado a unos 64 píxeles CSS del ancla manual. El frontend envía `desktop_activity {active, follow, roam, reducedMotion, pinned}` y recibe `axx-motion` con velocidad CSS. La prueba física del desplazamiento corresponde al host; una respuesta IPC no demuestra que Windows haya movido la ventana.

Los controles están en Ajustes: `#resident-motion-alive`, `#resident-motion-roam`, `#resident-motion-pin`; `#resident-motion-status` explica las pausas. Se guardan bajo `axx.resident-motion-v1` y se incluyen en el layout del mecanismo existente de identidad, sin sustituir su forma/material/cámara. Esc deshabilita el paseo. Movimiento reducido del sistema, modo estático y ajustes de animación suspenden la animación adicional y el viaje. El pin detiene el desplazamiento y conserva la respiración.

Las pausas cubren panel/dock abierto, foco editable visible, arrastre, solicitudes de chat, operaciones propias, captura de audio, permisos de dictado, ASR pendiente, TTS pendiente/reproducción y temporizador activo. Se consultan los campos reales `nativeVoice.activeCapture`, sesiones, lectores y reproducción; no se activa el micrófono ni escucha permanente.

## Validación controlada

Baseline previo: suite de 16 contratos, exit 0. Con el renderer final se ejecutó y pasó la aserción de encuadre de las 24 formas: escala 1, desplazamientos de 6 px, yaw 0,09 rad, pitch 0,06 rad, escala temporal 1,008; todas conservaron un borde alpha. Esta comprobación pasó antes de corregir únicamente la sincronización del harness y no se repitió, por instrucción del integrador. No certifica todas las combinaciones posibles de escala/cámara elegidas por el usuario.

Validación final posterior: **19/19 contratos restantes**, exit 0, `uncaught: []`. Se ejecutó el archivo de pruebas mediante `Module._compile`, omitiendo en memoria solamente el bloque del barrido de formas ya comprobado. El archivo guardado conserva ese bloque para futuras ejecuciones completas. No se presenta esta ejecución como una única suite 20/20.

Aserciones relevantes que pasaron:

- El arranque pinta únicamente el canvas líquido, con alpha cero fuera de él, sin controles permanentes y con ventana compacta; funciona con RAF suspendido y backend pendiente.
- Abrir/cerrar el chat adapta el layout; el drag emite una sola llamada nativa tras siete píxeles y no abre herramientas al soltar.
- El movimiento cambia los píxeles renderizados, mantiene máscara utilizable, responde a la dirección del puntero y conserva exactamente cámara y `axx-studio-v2`; no emite `desktop_layout` por paso de animación.
- Panel y texto hacen volver la pose autónoma al reposo. Captura/permisos, ASR, TTS y trabajo propio producen `active:true`; vuelve a `false` al quedar libre.
- La preferencia de movimiento reducido de Windows detiene renderer/viaje y muestra el motivo. Pin, animación y paseo se guardan aparte; Esc desactiva el paseo y permite reactivarlo desde Ajustes.
- Permanecen los contratos anteriores de proveedores sin credencial, chat/cancelación, acciones, recetas, memoria, cuadernos, WAV y ASR sin envío automático.

El harness difunde los eventos a todos sus listeners, como Tauri, y usa un reloj de sondeo independiente de RAF para comprobar el arranque oculto. Los estados de servicios y respuestas backend de esta suite son fixtures IPC; el WAV es un fixture PCM decodificado. **No son prueba nativa física**, de micrófono, de altavoz ni de desplazamiento entre monitores. El integrador debe observar el binario instalado, el click-through, el paseo y sus pausas sobre aplicaciones reales. No se midió FPS físico ni se garantiza una tasa de cuadros.

Respaldo: `%LOCALAPPDATA%/Axx/backups/resident-20261019/liveness-0.20.4/Axx-before-liveness.html`, hash base `1CC9A0E4F2B54C9B3012226B39E832882B266EF2BCBAB9B3302B7C1FA592AD45`. Revisión propia del frontend; integración del contrato coordinada con el responsable nativo.
