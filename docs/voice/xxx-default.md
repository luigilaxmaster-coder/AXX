# Xxx default and MOSS playback

`moss:axx-sam` is displayed as **Xxx default** when the private reference exists
at `%LOCALAPPDATA%\Axx\speech\voices\axx-sam.wav`. The reference is local user
data; it must never be committed, packaged or uploaded with a release. The
current reference uses the first 5.76 seconds from the supplied recording, ending in a
measured pause, as mono PCM16 at 48 kHz. Converting to stereo must preserve
interleaving; the runtime already duplicates mono correctly.

Fresh preferences choose this voice when available, then Valeria. An explicit
saved voice choice (including automatic Windows speech) is preserved. To change
an existing profile, select **Xxx default** in the voice control once. It uses
MOSS reference conditioning; no model weights were trained or replaced.

## Latency and continuity

- The existing MOSS worker and reference-code cache remain resident/reusable.
- A completed utterance is stored under `speech/audio-cache` as PCM WAV. Its
  content key includes normalized spoken text, language, the reference and
  model/engine fingerprints. Text is not written in filenames or a transcript
  index. Changing the voice or engine invalidates the relevant entries.
- Cache storage is bounded to 64 MiB and 256 utterances. Corrupt or truncated
  entries fall back to generation; cancelled/failed streams are not saved.
  Cache I/O failures do not fail otherwise valid speech.
- Repeated speech can play without loading the model. Background model loading
  no longer holds the synthesis lock, so it does not block cached replies.
- Web Audio starts with a reserve derived from observed generation speed,
  playback speed and an estimate of the remaining spoken duration. Slow phrases
  buffer longer. After a CPU stall, the remaining phrase buffers completely to
  prevent repeated stuttering. Duration estimates cannot guarantee no stall
  under arbitrary CPU contention.
- The extra fixed 280 ms playback delay is reduced to 40 ms. Pause,
  interruption, ordered PCM delivery and conversation text gaps remain handled
  by the existing reader owner.
- Existing reader chunks are split with the conversation phrase helper, so
  synthesis of the next sentence can overlap playback of the previous sentence.

## Local evidence, 2026-10-27

The source backend with the real local MOSS model and Web Audio completed all
three runs below with zero detected underruns. The measured phrase was
“Vamos a revisar ese archivo juntos.”

| Case | Request to playback |
| --- | ---: |
| New utterance, prepared model | 3,268 ms |
| Identical utterance from local cache | 146 ms |
| Cached utterance after restarting the backend process | 442 ms |

These are individual local measurements, not percentiles or end-to-end live
conversation latency. Microphone capture, ASR and chat-model response time are
excluded. The initial model load still takes seconds. Web Audio clocks and
completion events do not prove acoustic speaker output or subjective naturalness.

Five reference cuts (3.69, 5.76, 6.98, 10.48 and 31.84 seconds) were compared
with the same sampling state and two Spanish phrases. The 5.76-second cut had
the lowest combined transcription error in that small comparison. ASR is only
a proxy: generated Spanish still contains pronunciation/word errors. Explicit
Spanish prompt conditioning helped those two phrases but regressed on three
new phrases, so it was rejected. Neither this selection nor these timings
establish Windows-voice quality or a sub-two-second live conversation.

One/two/four/eight CPU threads and an isolated INT8 candidate were investigated.
The INT8 candidate did not show enough benefit to justify its changed outputs;
the original model and four-thread default remain in use. The private candidate
is inactive. No voice sample or model weights belong in the published artifact.

## Checks

```powershell
python -m unittest backend.tests.test_moss_stream backend.tests.test_speech_text -q
$env:AXX_TEST_CHROMIUM = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
node 1.AXX/scripts/test-custom-speech.cjs
node 1.AXX/scripts/test-dictation-runtime.cjs
node scripts/test-installed-speech.cjs
```

The last check requires an installed Axx WebView exposed on loopback CDP port
9224. It exercises real synthesis and a repeated cached response, records
playback evidence under `build/chat-<version>/installed-speech.json`, and restores
the prior reader selection. Installed acceptance and release publication must
be reported separately from the source/backend checks above.
