# Sound repair — 2026-10-21

Self-review. This change extends the existing `codex/fix-tool-interaction` work without reverting unrelated local changes.

## Reproduced

The new Web Audio test failed on saved permission after reload, explicit activation with a silent/zero-volume/muted configuration, and resuming a suspended context. The prior opening cue also had a sample-to-sample jump of 0.265 at 48 kHz in its noisy component.

## Fixed

- Resume a permitted AudioContext on trusted pointer/keyboard interaction, preserving a choice to silence effects.
- Explicit activation recovers the silent profile, zero master volume and master mute. If every effect category is muted, restore usable category gains. Persist the resulting settings.
- Connect orbit/catalog navigation to existing sound events.
- Use consonant note intervals, smoother attacks and releases, less noisy opening cues, and a 2.4 kHz synthesis low-pass. Peak-normalize cues to 0.68 and retain three-voice concurrency limits and capture/voice ducking.
- Show the actual sound state in settings instead of only indicating permission.

## Tests

Using installed Chromium headless shell 1234 via `AXX_TEST_CHROMIUM`:

- `node 1.AXX/scripts/test-sound-runtime.cjs`: exit 0, five groups. All 21 generated cues have finite, non-clipped PCM, clean endpoints and bounded DC/sample transitions. The real Web Audio graph measured a peak of 0.1700000018 after the master gain. Capture and master mute block effects.
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: exit 0, 18 groups.
- `node 1.AXX/scripts/test-tools-interaction.cjs`: exit 0, four groups.
- `git diff --check`: exit 0.

These tests verify synthesis and the browser audio graph, not physical speakers or the Windows volume mixer. No microphone recording, external audio download or remote request was needed.

The previous executable is retained locally as `Axx-before-sound.exe` (ignored by Git).
