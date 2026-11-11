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

Bloqueantes de aceptación: pesos Parakeet/Whisper GGUF/Canary y comparación 50+
frases reales; micrófono físico/permiso Windows; pruebas de aplicaciones,
modificadores/hold físicos, suspensión/bloqueo, 10 min y campos propietarios;
regresión visual WebView2 completa, persistencia y rollback de instalación.

Límites de implementación: ValuePattern requerido, no clipboard paste automático,
no LLM postproceso ni historial/exportación persistente. El audio no sale a chat.
ScriptProcessor necesita medición bajo carga; no prometer captura sin pérdidas.
No actualizar hashes visuales para pasar gates ni fusionar la UI de Claude aquí.

## Artefactos privados finales

Código `164e310886d788eb7983705a9a04e0595f99b3ff`; fuente/commits locales sin push.
Installer: `build/phase8/packages/Axx-Phase8-Candidate-0.22.46-debug.exe`.
Compilación debug de ~673 MiB, no paquete de producción ni evidencia de firma.

| Artefacto | Bytes | SHA256 |
| --- | --- | --- |
| installer | 705745856 | `40b7984ba0e3109577524965f3d02f1764bb8c8eb769732236632ee674f75327` |
| host | 21878272 | `6afb2a4c3da6c43c683c5f3885eec716c3b76677bc8ec354297d0c24657d8415` |
| backend | 23239917 | `0bf2df0b0ad930ce115fd05bb25374dcc81ff06e57fdd03c4a6952b85d236eaa` |
| native_asr | 3736576 | `dfbd1c4b4192a4a7a2115a7a7c213e85e785a394649171e0ae3214f610b6bb52` |

Recibos: `build/phase8/artifacts.json`, `package-final/backend-bundle.json`,
`native-final-result.json`, `native-fixture-final.log`, `rust-final.log`,
`dictation-runtime-final.log`, `companion-validation-final.json`.
Gate final: PASS (15 contrato, 112 servicio/1 omisión previa, 58 navegador,
8 selector). Rust: 26 PASS/2 opt-in; fixture Win32 ejecutado aparte PASS con
activación expresa de su ventana por Computer Use. Python de voz/modelos: 32 PASS.

El hash del AXX personal antes/después fue
`2e409cdb821820afac5d7b967be31aa51ca32e1b04275f1e502333d192bcf4d1`.
No se reemplazó ni se inició esa instalación. Los datos de candidata tienen
namespace propio `com.axx.phase8/Axx`, además del perfil temporal de pruebas.

Bloqueante de arquitectura pendiente: la autorización/foco se cancelan en Rust,
pero el cierre del stream físico se ejecuta en el renderer. Inferencia de código:
una UI congelada no puede ejecutar ese cierre; no se garantiza stop físico
independiente en ese escenario. Requiere captura/watchdog nativo comprobado antes
de READY. No confundir el timeout nativo del permiso de inserción con cierre del
micrófono. No se ha probado bloqueo/suspensión físicos.

La configuración de candidata está versionada en
`src-tauri/tauri.dictation-candidate.conf.json`; producción conserva su configuración.
Los sidecars/licencias están en el paquete privado. Integrar ese empaquetado en
el flujo público y firmar/instalar/aceptar siguen pendientes de la entrega final.

Diagnóstico WebView2 final, solo lectura (CDP local, perfil temporal): PASS. El SHA256 del módulo servido coincide exactamente con la fuente (`4f0358cd070da31b0158c72f0553ca58fa8a9c46645d79125cfe56d47e333325`), modo OFF, micrófono cerrado, atajo registrado y catálogo de 8 modelos consultado mediante IPC al backend empaquetado. No equivale a clic nativo, permiso de micrófono o reconocimiento con modelos nuevos. Recibo: `build/phase8/webview-readonly.json`; índice de comprobaciones y fuentes: `build/phase8/validation.json`.
