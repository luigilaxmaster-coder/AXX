# Axxmorcito

`moss:axx-morcito` uses two private MOSS reference clips in
`%LOCALAPPDATA%\Axx\speech\voices\`:

- `axx-morcito.wav` for Spanish (required for the voice to appear).
- `axx-morcito-en.wav` for English (optional; Spanish is used if absent).

The recordings stay in the user's AppData directory. They are not part of Git,
the Windows installer, or the public download. To use this voice on another PC,
copy the reference clips privately to the same folder and refresh the voice list.
The active MOSS ONNX model clones the selected reference at inference time;
these recordings do not change its weights. A private CPU fine-tuning experiment
exists under the local training directory, but its checkpoint is not active:
the earlier held-out comparison improved Spanish recognition while English
speaker similarity declined. A local single-phrase speaker check measured
baseline/trained cosine similarity of 0.7843/0.7880 in Spanish and
0.7254/0.6872 in English; these scores do not measure listening quality.
Another training run should use more clean,
transcribed speech and an independent Spanish/English comparison before any
checkpoint replaces the current inference model. Keep all weights and recordings
private.

When available, Axxmorcito appears in **Voces de Axx** and the chat and live
voice selectors. A new profile prefers it; an existing saved voice selection is
kept. Spanish and English use distinct reference hashes in the audio cache, so
changing either clip invalidates only its own synthesized phrases. MOSS warmup
is required on first use. Audio cache reuse accelerates repeated text, but does
not prove a first-response latency or subjective voice quality. The sound panel
offers per-voice bass, clarity, brightness, sibilance, volume and height/tempo
controls with explanations on their info icons. Sibilance is a fixed frequency
reduction, not a trained pronunciation model; height also changes duration.
PCM packet boundaries use a short fade to reduce clicks. Listen to both
languages in the installed app before acoustic acceptance.

An isolated CPU comparison tried joining the two Spanish references. On one
new phrase the ASR result improved, but on another the generated voice changed
the requested sentence into an unrelated question. The joined reference was
rejected; the installed voice sample and selected model were not replaced.
