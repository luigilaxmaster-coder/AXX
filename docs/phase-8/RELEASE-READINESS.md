# Preparación de entrega · NOT_READY

Fuente funcional aislada y pruebas de contrato/nativas limitadas aprobadas.
No se declara entrega instalada ni compatibilidad universal.

Versión de producto conservada: 0.22.46; Android sin cambios. La candidata tiene
productName Axx Phase8 Candidate, identifier com.axx.phase8, mainBinaryName
AxxPhase8, sin colisión de mutex con com.axx.desktop. No publicar con esta misma
versión; una entrega futura debe seguir release.py sync y todos los gates.

Backend nuevo empaquetado y verificado, worker C++ release compilado. Instalador
privado de depuración compilado (no firmado). Arranque WebView2 y backendReady
aprobados con perfil aislado. No se ejecutó el instalador ni se validó una instalación. Artefactos/recibos privados bajo build/phase8; no subir pesos,
audio, datos de perfil ni credenciales. Mantener la instalación personal intacta.

Bloqueantes de aceptación: comparación 50+ frases humanas ES/EN/Spanglish;
micrófono físico/permiso Windows; pruebas de aplicaciones,
modificadores/hold físicos, suspensión/bloqueo, 10 min y campos propietarios;
regresión visual WebView2 completa, persistencia y rollback de instalación.

Límites de implementación: ValuePattern requerido, no clipboard paste automático,
no LLM postproceso ni historial/exportación persistente. El audio no sale a chat.
WASAPI/IPC necesitan medición física bajo carga; no prometer captura sin pérdidas.
No actualizar hashes visuales para pasar gates ni fusionar la UI de Claude aquí.

## Artefactos privados finales

Código `b5bbaca0590700a5d090520ee544e558c7b34ec2`; fuente/commits locales sin push.
Installer: `build/phase8/packages/Axx-Phase8-Candidate-0.22.46-debug.exe`.
Compilación debug de ~673 MiB, no paquete de producción ni evidencia de firma.

| Artefacto | Bytes | SHA256 |
| --- | --- | --- |
| installer | 705885567 | `43e6bdccb760944170e9135b9f78d8b22e023c2963f2ff9027695e4de7a566b7` |
| host | 22047744 | `4fe438e66fc88cdaa668429195f6c8779860e8d4434136ba65d827b91b19ba8d` |
| backend | 23239917 | `0bf2df0b0ad930ce115fd05bb25374dcc81ff06e57fdd03c4a6952b85d236eaa` |
| native_asr | 3707392 | `25a02ac3a766aa7d0056c61f2578be2fd922e11b9e045a5aa46925b1da04d54b` |

Recibos: `build/phase8/artifacts.json`, `package-final/backend-bundle.json`,
`native-final-result.json`, `native-fixture-native-audio.log`, `rust-native-audio-final.log`,
`dictation-runtime-final.log`, `companion-validation-final.json`.
Gate final: PASS (15 contrato, 112 servicio/1 omisión previa, 58 navegador,
8 selector). Rust: 27 PASS/2 opt-in; fixture Win32 ejecutado aparte PASS. La
última ejecución obtuvo foreground sin asistencia. Python voz/modelos: 32 PASS.
Sidecar release: 2 PASS, incluye versión ABI. Preparación/transcripción/liberación
de Parakeet y Whisper Small por backend empaquetado: PASS, audios sintéticos.

El hash del AXX personal antes/después fue
`2e409cdb821820afac5d7b967be31aa51ca32e1b04275f1e502333d192bcf4d1`.
No se reemplazó ni se inició esa instalación. Los datos de candidata tienen
namespace propio `com.axx.phase8/Axx`, además del perfil temporal de pruebas.

El bloqueo arquitectónico de captura dependiente del renderer se corrigió:
WASAPI y su heartbeat/cancelación residen en un hilo nativo; los capturadores
actuales esperan confirmación de cierre antes de abrir su stream. El indicador
conserva micrófono abierto/cerrando mientras falta confirmar. Pruebas sintéticas
y compilación pasan; aún falta validar físicamente el driver, UI congelada,
bloqueo y suspensión. No se declara protección de hardware certificada.

La configuración de candidata está versionada en
`src-tauri/tauri.dictation-candidate.conf.json`; producción conserva su configuración.
Los sidecars/licencias están en el paquete privado. Integrar ese empaquetado en
el flujo público y firmar/instalar/aceptar siguen pendientes de la entrega final.

Diagnóstico WebView2 final, solo lectura (CDP local, perfil temporal): PASS. El
SHA256 del módulo servido coincide con la fuente
(`59e24cbeb2cb376442f30c0d1045802c2a41abcd40e82961a2655f5d41d97fd0`), OFF,
micrófono cerrado, atajo registrado, 8 modelos y 1 entrada nativa enumerada sin
captura. Host SHA coincide con el artefacto. No equivale a clic o permiso físico.
Recibo: build/phase8/webview-readonly.json; índice: build/phase8/validation.json.

Pesos Parakeet V3 y Whisper Small descargados tras autorización expresa y
verificados por tamaño/SHA256 en perfil privado, fuera del instalador y Git.
Comparación de 3 clips sintéticos PASS y backend empaquetado PASS: ver
ASR-MODEL-COMPARISON.md, PERFORMANCE-RESULTS.md y packaged-models.json.
No hay ganador demostrado para español/cifras; Canary/Medium no se descargaron.
