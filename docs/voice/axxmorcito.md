# Axxmorcito

`moss:axx-morcito` and its style variants use private MOSS reference clips in
`%LOCALAPPDATA%\Axx\speech\voices\`:

- `axx-morcito.wav` / `axx-morcito-en.wav` for **Axxmorcito** (Natural).
- `axx-morcito-calma.wav` / `axx-morcito-calma-en.wav` for **Axxmorcito · Tranquila**.
- `axx-morcito-emocion.wav` / `axx-morcito-emocion-en.wav` for **Axxmorcito · Emocionada**.
- `axx-morcito-atencion.wav` / `axx-morcito-atencion-en.wav` for **Axxmorcito · Atenta**.

Private Piper models (`axx-morcito-es.onnx` and `axx-morcito-en.onnx` with matching
`.onnx.json` files in `%LOCALAPPDATA%\Axx\speech\piper\models\`) expose the fast
`piper:axx-morcito-es` and `piper:axx-morcito-en` voices and their `@calma`,
`@emocion` and `@atencion` prosody variants (~0.35–0.65 s synthesis on CPU after
initial warmup).

## Prosody, Fluidity & Humanizer Engine (`backend/speech/prosody.py`)

- **Model Soup VITS Checkpoint (`axx-morcito-es.onnx`)**: Weight-averaged checkpoint combining `epoch=170` (`val_mel=0.3501`, 97-clip phonetic corpus) and `v4-es/epoch=17` (`val_mel=0.4718`, curated conversational timbre), achieving `0.9132` mean speaker similarity and natural 149–155 Hz F0 contour.
- **VITS Boundary Silence Trimming (`HumanizerDSP.trim_silence`)**: Trims leading/trailing dead air from synthesized clauses down to 14–26 ms with 8 ms Hanning anti-click fades and `-68 dBFS` comfort breath transitions (35–55 ms), eliminating mid-sentence hesitation gaps.
- **Mood-Aware Expressive Transitions (`ProsodyAnalyzer`)**: Detects discourse transitions (such as *"Okay, vamos a ponernos serios"*), adjusting neural VITS stochastic parameters (`length_scale`, `noise_scale`, `noise_w_scale`), intimate volume ducking (`0.85x`), and pure-NumPy FFT cascaded biquad tonal warmth (200–225 Hz chest resonance + 3.8–4.5 kHz silk de-harshing) without WSOLA formant distortion.
- **MOSS-TTS-Nano Streaming Fluidity (`backend/speech/moss_worker.py`)**: Uses the verified `v3_ep1` ONNX weights (`0.89–0.92` similarity), caps reference audio prompts to 48 frames (~3.84 s), pins ONNX intra-op threads to 4 P-core threads on hybrid CPUs, increases `voice_clone_max_text_tokens` to 84, and tightens inter-chunk pauses to 50–110 ms.

Build or refresh the dataset and Colab/WSL training bundle with:

- `python scripts/voice/prepare_piper_dataset.py`
- `python scripts/voice/prepare_moss_references.py`
- `python scripts/voice/colab_piper_bundle.py pack` / `install <zip>`
- `scripts/voice/train_axxmorcito_colab.ipynb` (GPU T4) or `scripts/voice/wsl-train-piper.sh` (WSL CPU)

The recordings and trained models stay in the user's AppData directory. They are
not part of Git, the Windows installer, or the public download. To use this voice
on another PC, copy the reference clips or ONNX files privately to the same folders
and refresh the voice list.
