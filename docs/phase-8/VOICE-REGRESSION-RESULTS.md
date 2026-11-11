# Validaciones · Fase 8

Base: a750362; 4f4e18b es ancestro. La rama original 9b4ed53 no tiene esa
ascendencia. Sus cambios locales de voz se dejaron intactos. Revisión propia.

Baseline antes de editar: Python ASR/speech 27 OK; test-dictation-runtime PASS
con Chrome instalado; Rust 21 OK/1 helper ignorado. El primer intento de browser
no encontró Chromium del runtime Node; se usó AXX_TEST_CHROMIUM. No se borró test.

Resultado de esta fase (exit 0 salvo los intentos fallidos documentados):
- Python test_asr_http + test_speech_text + test_dictation_models: 32 OK.
- Node test-dictation-engine: PCM/WAV, VAD, segmentación, límites, foco/diccionario,
  perfiles literal/código, validación de preferencias y parser de atajo.
- Node test-global-dictation-runtime: opt-in/OFF, stream único, captura durante
  decode, foco antiguo pendiente, no comandos/envío, prioridades, pausa/Escape,
  limpieza y final manual que permite la siguiente activación. Audio sintético.
- test-dictation-runtime: regresiones existentes y controles en la vista de voz;
  dictado del chat conserva borrador sin envío, leases y cancelación.
- test-chat-groups (9), test-chat-workspace y test-tendril-geometry: PASS.
- Rust lib: 26 OK/2 opt-in; una es el helper anterior y otra la prueba interactiva.
  La prueba interactiva se ejecutó aparte: 1 OK en controles Win32 reales.
- Sidecar release: 1 self-test y compilación real OK. No acredita modelos.
- Gate PC/móvil: PASS; contrato 15, servicio 112 (1 omitida previa), navegador 58,
  selector 8, renderer y diseño protegido. build/phase8/companion-validation-final.json.
- Backend PyInstaller: PASS, QR empaquetado PASS, bundle verificado; sin pesos.

Hallazgos corregidos durante implementación: serde no rechazaba campos extra en
variantes unitarias (cambio a variantes struct); fixture UIA enfocaba antes de
procesar activación (enfoque desde su message loop); cancelación del dictado global
ahora comparte la barrera ASR antes de ceder captura; hold/toggle finalizan manual
sin perder la frase ni impedir la siguiente activación.

No ejecutado: micrófono/altavoz físicos, aplicaciones de terceros, bloqueo real,
UAC real, Android físico, Telegram real, corpus dominicano y Magic Pen con modelo.
Las pruebas de geometría no sustituyen aceptación visual nativa completa.

Separación adicional: auto-rearme de órdenes bloqueado durante dictado armado; conversación/lectura tienen prioridad incluso entre turnos, sin capturar TTS. Atajos se registran tras comprobar el chord de órdenes; una colisión previa deshabilita el nuevo, conserva el existente y ofrece reconfigurar. Pruebas cubren espera durante conversación, hold sin teclas pegadas, cesión del micrófono visual y posterior rearme de órdenes.

Prueba nativa de fixture: dos intentos previos no obtuvieron ValuePattern al activar la ventana. Se corrigió la sincronización del fixture con su message loop, se espera foco válido y se comprueban HWND/PID propios antes de escribir; no se suavizó el guard. La repetición final pasó.

WebView2 candidato: arranque/backendReady/ventana visible PASS con perfil aislado; se observó avatar y acciones rápidas. Clic del helper falló dos veces con `point (1508, 728) is over ChatGPT.exe ... not target window AxxPhase8.exe`, incluso tras reactivar. No hubo clic exitoso ni validación nativa de los controles nuevos. No se automatizó la UI de Codex; quedó como ventana subyacente.

Cierre: gate final repetido PASS, protocolo sidecar ante modelo ausente PASS sin inferencia simulada. Timeout de AudioContext suspendido libera el stream (fixture); al armar dictado se cancela la captura de órdenes anterior antes de nuevas frases. Estado real vuelve a ARMED si el foco cambia durante apertura del audio.

Diagnóstico definitivo del fixture: Windows no siempre cedía foreground al proceso lanzado en segundo plano. El fixture ahora lo exige y espera activación; la ejecución final se activó con Computer Use y pasó (28.12 s incluidos en espera). Esto sustituye la interpretación incompleta de los intentos iniciales como solo sincronización de mensajes. No certifica foco universal ni micrófono físico.

WebView2 final por diagnóstico CDP de solo lectura: hash del módulo servido idéntico a fuente, OFF sin micrófono, atajo registrado, 8 modelos vía IPC del backend empaquetado. PASS. El harness esperó navegación, habilitó Page y esperó una respuesta GET válida del backend; los sondeos iniciales de arranque no se cuentan como fallos de producto ni como validación de voz. El clic nativo transparente continúa BLOCKED.
