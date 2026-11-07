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
`@emocion` and `@atencion` prosody variants (~0.22–0.39 s synthesis on CPU after
initial warmup). Build or refresh the dataset and Colab/WSL training bundle with:

- `python scripts/voice/prepare_piper_dataset.py`
- `python scripts/voice/prepare_moss_references.py`
- `python scripts/voice/colab_piper_bundle.py pack` / `install <zip>`
- `scripts/voice/train_axxmorcito_colab.ipynb` (GPU T4) or `scripts/voice/wsl-train-piper.sh` (WSL CPU)

The recordings and trained models stay in the user's AppData directory. They are
not part of Git, the Windows installer, or the public download. To use this voice
on another PC, copy the reference clips or ONNX files privately to the same folders
and refresh the voice list.
