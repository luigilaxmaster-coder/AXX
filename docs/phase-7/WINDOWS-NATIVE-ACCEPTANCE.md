# Fase 7 · aceptación Windows de Codex

Dictamen: **READY_WITH_LIMITATIONS**, exclusivamente para la candidata visual
aislada. No es aceptación de entrega pública ni de Handy. Pruebas propias de
Codex; no se atribuye a Claude una aprobación que no emitió.

## Fuente y congelación

| Referencia | SHA completo |
| --- | --- |
| Base recuperada de Claude | `8371e010d588509a1f15a2fcde872449e2eca35f` |
| Tres ajustes visuales cerrados | `234ffa85743dbd16e6d0c5d0ab79d8460d4cd6e2` |
| DESIGN_FROZEN_FOR_NATIVE_ACCEPTANCE | `9f87f7fcaa1ecb06ec87747c233308d1aa7b8c13` |
| Fuente empaquetada, añade aislamiento nativo | `a1eb51d76978c99185d0dfc43cda7e6f51930b9d` |

El renderizador empaquetado coincide byte por byte con la congelación. El
último commit solo añade identidad de candidata y separación de su directorio
de datos; producción conserva su ruta anterior. Rust: 22 PASS, 1 omitida previa.
No se avanzó la versión: candidata debug 0.22.46, Android sin cambios.

Se conserva la punta de Claude y todos los hashes de su WIP original. Handy
continúa limpio en `898df5f48f236b23148d203fc558f9ea0e80c0b1`. No se modificaron
`main`, configuraciones personales ni el exterior del avatar.

## Candidata y artefactos

Raíz privada de evidencia: `build/phase7/` de este worktree. NSIS se ejecutó con
`/S /NS /D=<raíz privada>/installed`, con salida 0. Identidad
`com.axx.phase7`, producto `Axx Phase7 Candidate`, proceso `AxxPhase7.exe`,
registro HKCU `Uninstall\Axx Phase7 Candidate`. El backend tiene su ejecutable,
PID, job y puerto propios dentro de esa instalación; no se comparte el proceso
de la instalación personal.

| Artefacto | SHA-256 |
| --- | --- |
| `cargo-target/debug/bundle/nsis/Axx Phase7 Candidate_0.22.46_x64-setup.exe` | `92c814a4a7cb1fbb8e96780bf7462c9c9af5d1db54dd2e108edb5f9dea992b23` |
| Host independiente antes del empaquetado NSIS | `0e90e04a456d4a8ff652494d0e15f8ff33dae87a71d8f91785820378c243afa8` |
| `installed/AxxPhase7.exe` | `a19a2fae4b992fddd8867138f200643abf95a250416bff7bbace01f7d1e04a79` |
| `installed/resources/axx-backend.exe` | `e02eb774ef39e6480644430261ec90fcc9dd74017c3cf41a48dccc767a5d60e1` |

El host instalado cambia únicamente el marcador `__TAURI_BUNDLE_TYPE_VAR_UNK`
a `__TAURI_BUNDLE_TYPE_VAR_NSS`: se comprobó la igualdad de todos los bytes
tras esa única sustitución en memoria. Se conservó el primer fallo del
verificador; no se reescribió ningún binario. Es el mecanismo de empaquetado de
[Tauri bundler](https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-bundler/src/bundle.rs).
Paquete de depuración, sin firma; no es instalador de distribución.

Durante la aceptación, LOCALAPPDATA, APPDATA y WebView2 apuntaron a
`build/phase7/native-profile/`. Datos reales de la candidata:
`native-profile/local/com.axx.phase7/Axx`. Incluso sin ese entorno de prueba,
su namespace nativo es distinto del personal. No se heredaron claves de
proveedores desde el entorno. El perfil Windows USERPROFILE se conservó porque
el plugin de logs de Tauri necesita un perfil reconocido por Windows.

## Resultado real observado

WebView2 **157.0.4341.46**, IPC genuino y backend empaquetado `backendReady=true`.
Sin host simulado. Assets servidos JS/CSS verificados por bytes contra fuente.
DPI disponible **120 (125%)**, escritorio lógico **1536×816**.

| Comprobación | Resultado |
| --- | --- |
| Sistema y datos, IA, las cinco pestañas y ambos temas | PASS; 12 combinaciones, 424 controles únicos, sin overflow |
| Navegación de Personalizar | PASS; geometría nativa estable 540×620, sin reescribir tamaños guardados; foco por teclado WebView |
| Arrastre/redimensionamiento | PASS por instrumentación en WebView2; posiciones/tamaños persistidos y paneles independientes |
| Forma y materiales | PASS; prueba, descartar, guardar, recargar, avanzados y barra de acciones accesibles |
| Preferencias | PASS; nombre/rol en backend real; sonido, tema, tipografía y tamaño tras recarga |
| Conexión/modelos | PASS; catálogo y respuesta real de `llama3.2:1b` mediante Ollama propio en loopback |
| Apariencia instalada existente | PASS; seis contratos de persistencia, temas, resize, voz compacta, catálogo y órbita |
| Tentáculos instalados | PASS; adjuntos, retracción y capturas con puntero instrumentado |
| Calidad de tentáculos | PASS al repetir; 60 casos analíticos, huecos/recortes cero, cobertura subpíxel |
| Chat instalado | PASS; 18 conversaciones de prueba en ambos temas, eliminadas solo en el perfil aislado |
| Errores de página sin capturar | 0 |
| Gate PC/móvil final | PASS; 15 contrato, 112 servicio (1 omitida), 58 navegador, 8 selector |

Ollama usó pesos ya instalados y un proceso/puerto propios. No se descargaron
modelos para esta prueba ni se conectaron cuentas cloud. La respuesta recibida
fue una negativa del modelo: certifica inferencia/transporte, no calidad de
instrucciones. La primera prueba intentó guardar durante la conexión asíncrona
y agotó la espera; al esperar el estado estable antes de guardar, el recorrido
completo pasó. No se cambió código de producto para obtener ese resultado.

La prueba de calidad nativa original completó los asserts, pero no pudo escribir
`build/chat-0.21.4/tentacles/quality.json` porque faltaba la carpeta. Se creó
únicamente ese destino de evidencia y se repitió el mismo script: PASS, 60 casos.
El recibo bruto `native-acceptance.json` conserva NOT_READY de ese fallo; el
dictamen agregado y su justificación están en `final-validation.json`, junto
al hash del log y del recibo de repetición. No se ocultó ni debilitó un assert.

## Regresión y límites

Los 29 contratos, 42 checks desktop, 12 suites UI y Magic Pen descritos en
`CODEX-VALIDATION.md` pasan. Los cinco fallos preexistentes se reprodujeron
en baseline y cierre: tools-interaction, providers, skills (ruta de fixture),
capability-workshop y goal-cycle. El backend onedir empaquetado sí se verificó
y ejecutó; eso no convierte el fixture skills ausente en PASS. No se detectó
una regresión nueva atribuible a estos tres ajustes.

Limitaciones que permanecen explícitas:

- La entrada OS por Sky no permitió certificar el ratón: devolvió
  `coordinate input geometry is unavailable`. Los PASS de clic/drag anteriores
  son instrumentación dentro del WebView2 real, no certificación física del
  ratón. El árbol de accesibilidad Windows sí expuso los controles.
- La app informó vista compatible sin WebGL. No se certifican shaders/GPU,
  calidad gráfica por hardware ni otros monitores/DPI. Los DPR 1/1.5/2 del test
  de tentáculos son cálculos sintéticos, no pantallas físicas.
- Ctrl+Alt+Espacio estaba ocupado (Windows 1409); la UI informa el conflicto y
  ofrece Alt+Mayús+A. Inicio automático figura deshabilitado/no implementado.
- No se autenticaron cuentas cloud, teléfono físico ni micrófono. El gate PC/móvil
  es contractual y de navegador; no equivale a instalar/aceptar un APK.
- Voces mantiene las 18 alertas del medidor plano sobre gradientes, fuera del
  alcance. Los 16 contornos de chat claro y el oscuro adicional quedaron en cero.

## Evidencia y conservación

`final-validation.json` indexa SHA-256 de capturas, logs, recibos y artefactos.
Antes/después: `screenshots/baseline/` y `screenshots/finish/` (38 finales).
Capturas nativas: `native-profile/screenshots/` (ambos temas y áreas),
`native-profile/appearance/` y `native-profile/tendrils/`. Las imágenes de
monitor completo observadas por Sky no se guardaron porque incluían otras apps.

Reproducción privada: `native-acceptance.cjs` inicia solo la candidata y Ollama
propios; requiere los pesos locales ya existentes. Usa puertos libres, IPC real,
perfil aislado y limpieza por PID propietario. Los scripts de aceptación
instalada conservan los asserts originales; solo se adaptaron su puerto CDP y
el límite de captura a la pantalla disponible. `final-audit.py` verifica
congelación, recibos vigentes, preservación de árboles y hashes personales.

Tras probar se cerraron solo los procesos de candidata/Ollama propios. La
instalación privada queda disponible para revisión. AXX personal 0.22.37 conserva
ejecutable SHA-256 `2e409cdb821820afac5d7b967be31aa51ca32e1b04275f1e502333d192bcf4d1`
y su registro de desinstalación. No hubo push, publicación, merge a main,
sustitución personal ni limpieza de configuraciones.
