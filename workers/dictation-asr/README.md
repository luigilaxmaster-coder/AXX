# AXX native ASR sidecar

CPU only. No weights, downloads, UI or command permissions. Pinned Rust wrapper
and native dependency are in Cargo.lock. Parent Python supervisor owns the
request deadline and kills the process tree on cancellation/unload.

Build with an installed MSVC C++ toolchain and CMake:

```powershell
cargo test --release --locked --manifest-path workers/dictation-asr/Cargo.toml
cargo build --release --locked --manifest-path workers/dictation-asr/Cargo.toml
```

This host's transcribe-cpp-sys junction build failed in CMake TryCompile. The
same vendored source built in a real directory, using MSVC/Ninja. To reproduce
that fallback, use a Visual Studio Developer shell with Ninja on PATH:

```powershell
$metadata = cargo metadata --locked --format-version 1 --manifest-path workers/dictation-asr/Cargo.toml | ConvertFrom-Json
$nativeSource = Split-Path ($metadata.packages | Where-Object name -eq 'transcribe-cpp-sys').manifest_path
$nativeBuild = Join-Path $env:TEMP 'axx-phase8-native-asr'
$nativeInstall = Join-Path $env:TEMP 'axx-phase8-native-asr-install'
cmake -S $nativeSource -B $nativeBuild -G Ninja -DTRANSCRIBE_INSTALL=ON -DTRANSCRIBE_BUILD_TESTS=OFF -DTRANSCRIBE_BUILD_EXAMPLES=OFF -DTRANSCRIBE_BUILD_TOOLS=OFF -DTRANSCRIBE_USE_OPENMP=OFF -DTRANSCRIBE_BUILD_SHARED=OFF -DCMAKE_BUILD_TYPE=Release "-DCMAKE_INSTALL_PREFIX=$nativeInstall"
cmake --build $nativeBuild -j 2
cmake --install $nativeBuild
$env:TRANSCRIBE_DIR = $nativeInstall
cargo build --release --locked --manifest-path workers/dictation-asr/Cargo.toml
```

This CPU build used AVX2, not Vulkan/Iris Xe. It is a private candidate, not a
portable CPU distribution claim. Preserve the licenses in docs/phase-8/licenses.

Protocol: bounded JSON header line (4096 bytes), then `samples * 4` bytes of
little-endian mono f32 at 16 kHz, maximum 60 s. Header fields: model_path,
language (ISO or null), task (transcribe/translate/prepare), samples (prepare=0).
Result is a bounded line prefixed `AXX_ASR_V1 `; other native diagnostic output
is discarded by the parent. Translations target English explicitly.

Models are manually authorized local files under `%LOCALAPPDATA%/Axx/models/dictation/`.
Use only catalog filenames/hashes; Python checks the full SHA256 before loading.
Model licenses/attribution are independent of the engine license. Wrapper AND
native sys are pinned to 0.4.0: the wrapper rejects a different patch ABI even
when Cargo's semver resolver accepts it. The native-version test catches this
without weights. Model quality still requires the same real corpus on each engine.

Private Windows candidate after building/staging the backend with the official
build script (`-BackendOnly`):

```powershell
npm ci --ignore-scripts
npm run tauri -- build --debug --bundles nsis --config src-tauri/tauri.dictation-candidate.conf.json
```

The candidate has its own identifier, binary, mutex and default data namespace.
Do not publish it or replace the personal installation. Production packaging of
the optional sidecar remains a release-readiness task, with receipts and native
acceptance; the ordinary release configuration is intentionally unchanged.
