# Axxmorcito

`moss:axx-morcito` uses two private MOSS reference clips in
`%LOCALAPPDATA%\Axx\speech\voices\`:

- `axx-morcito.wav` for Spanish (required for the voice to appear).
- `axx-morcito-en.wav` for English (optional; Spanish is used if absent).

The recordings stay in the user's AppData directory. They are not part of Git,
the Windows installer, or the public download. To use this voice on another PC,
copy the reference clips privately to the same folder and refresh the voice list.
The existing MOSS model clones the selected reference at inference time; these
recordings do not train or fine-tune its weights.
The [official fine-tuning workflow](https://github.com/OpenMOSS/MOSS-TTS-Nano/blob/main/finetuning/README.md)
requires a CUDA GPU and separate PyTorch checkpoints. Keep its output private
and compare it with the current ONNX voice before replacing the inference model.

When available, Axxmorcito appears in **Voces de Axx** and the chat and live
voice selectors. A new profile prefers it; an existing saved voice selection is
kept. Spanish and English use distinct reference hashes in the audio cache, so
changing either clip invalidates only its own synthesized phrases. MOSS warmup
is required on first use. Audio cache reuse accelerates repeated text, but does
not prove a first-response latency or subjective voice quality. Listen to both
languages in the installed app before acoustic acceptance.
