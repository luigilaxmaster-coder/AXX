# Change log

## Unreleased — 2026-10-21

Source version remains 0.20.3, matching package.json and the Tauri manifests.

### Interface and audio

- Repair tool activation and pointer handling; use icon controls with accessible labels.
- Improve tentacle motion and rendering while preserving saved avatar identity.
- Recover sound after browser audio suspension and improve synthesized feedback.
- Give chat more reading space, preserve scroll position/selection and drafts, and improve multiline composition and formatted responses.
- Stabilize dictation layout, share a single capture stream and finalize recorded speech without cancelling unrelated commands.

### Models and desktop actions

- Add named API connections and model catalogs for local/LAN servers and cloud providers, with DPAPI-protected keys.
- Separate Ollama Cloud from local model discovery and keep explicit provider/model selection.
- Handle supported app/site opening and searches locally before model inference.
- Add review and approval for explicitly typed PowerShell, with bounded runtime/output, cancellation and local results. Model output and dictated scripts are not executed.

### Music from Windows

- Discover native Windows media sessions and monitor available output-device peak levels without recording audio.
- Select the player to control, pause/resume by tapping the avatar, and expose only supported transport actions.
- Prevent duplicate commands and reject closed session targets rather than redirecting a command to another app.
- Smooth amplitude-driven motion and decay stale signal to silence; keep the pause button visible in the panel.
- Verified real Edge pause/resume and session removal using the native Rust service. Physical output metering remains unverified in the test session, which had no active output endpoints. Detection does not imply that an arbitrary application supports pause.

### Repository and validation

- Add the supplied 720p concept video, preserving its original MP4 and audio, with a linked preview in the README.
- Add regression tests, setup guides, screenshots and feature-level verification reports under `evidence/*-20261021/`.
- Update Windows launch fallback and dependency lock metadata; ignore transient stdout/stderr files.
- Pre-push regression: 45 backend tests and 12 Rust tests passed (one pre-existing Rust test ignored). Provider, sound, tool interaction, chat, music, dictation and desktop frontend browser checks passed. Feature reports distinguish browser/IPC fixtures, native tests and hardware limitations.
- Latest local Windows build: `evidence/system-music-20261021/build-result.json`. Build outputs, runtime credentials and local logs remain outside Git.
