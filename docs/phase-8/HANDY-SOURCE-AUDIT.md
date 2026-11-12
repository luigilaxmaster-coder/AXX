# Auditoría de Handy

Fecha: 2026-11-11. Fuente clonada y leída, no una copia integrada de su aplicación.
Handy `f2483011d60fccab639d3c33f40b3456e92f2940`, paquete 0.10.0.
https://github.com/cjpais/Handy/tree/f2483011d60fccab639d3c33f40b3456e92f2940

Revisados: Cargo.toml/Cargo.lock, catalog/catalog.json, transcription_coordinator.rs,
managers/transcription.rs, engine_supervisor/{protocol,worker,supervisor}.rs y
paste_tx/windows.rs. Handy usa transcribe-cpp 0.4.0, handy-recorder 0.1.1,
earshot 1.2.2 y un pegado Windows con recibos de lectura y restauración de formatos.
No portar auto-submit ni registrar una segunda bandeja/interfaz/captura.

AXX reutiliza su supervisor Python (RAM/pipe, cancelación por request_id, deadline,
árbol de procesos) y su lease de native-voice.js. El módulo PCM es propio. No se
ha copiado el coordinador ni paste_tx: SendInput Unicode evita modificar clipboard.
Se conservan metadatos de cuatro modelos Q8_0 con revisión, tamaño, SHA256,
idiomas y licencia en backend/speech/dictation-models.json; aviso MIT en licenses/.

Worker separado: workers/dictation-asr. API comprobada en la fuente de la crate:
Model::load_with, Backend::Cpu, ModelOptions, session_with, SessionOptions,
RunOptions, Task y Session::run (16 kHz mono f32). Wrapper fijado =0.4.0;
Wrapper y transcribe-cpp-sys fijados explícitamente a =0.4.0. El primer lock
resolvió sys 0.4.1: compilaba, pero la carga real rechazó la ABI. Se corrigió la
resolución y se añadió un test del ABI enlazado. No se desactivó el control nativo.
https://crates.io/crates/transcribe-cpp/0.4.0
https://crates.io/crates/transcribe-cpp-sys/0.4.0

Licencias nativas MIT: transcribe.cpp, ggml, Silero VAD y miniz; textos originales
incluidos en licenses/transcribe.cpp-*. Los pesos tienen licencias independientes:
Parakeet/Canary CC-BY-4.0, Whisper GGUF apache-2.0 según este catálogo. No se han
redistribuido pesos. Tras autorización expresa del usuario se descargaron
Parakeet V3 y Whisper Small en el perfil privado de candidata; revisión, tamaño
y SHA256 coinciden. El catálogo es evidencia de metadatos, no de
calidad o funcionamiento del modelo en AXX.

Compilación en este host: el build automático de cmake falló al usar su junction
NTFS corta (TryCompile no encontraba build.ninja/proyecto). La misma fuente
nativa compiló fuera de la junction con MSVC/Ninja; se enlazó con TRANSCRIBE_DIR.
No se modificó la registry de Cargo ni se desactivó un test para ocultarlo.
