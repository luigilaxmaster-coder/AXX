# Change log

## 0.20.10 — 2026-10-22 · Windows test release

- Publish the [Windows x64 installer](https://github.com/luigilaxmaster-coder/AXX/releases/tag/v0.20.10), checksum and installation notes as GitHub release assets.
- Add Magic Pen MP-H1: clean capture, point/rectangle/lasso selection, editable ink, provider-backed visual questions and verified PNG export.
- Modernize shared panels, restore the transparent circular menu and stabilize panel/avatar drag handling without changing saved avatar identity.
- Add verified desktop action learning, installed-app discovery, file hashes and bounded local image/PDF conversion.
- Preserve provider capabilities when saving the same model; include procedure archives in build integrity checks.
- Verify 99 Python tests, 14 Rust tests and frontend contracts. Preserve the pending physical shortcut, mixed-DPI and intermittent drag checks in the [delivery review](docs/REVISION-ENTREGA-20261022.md).

## Unreleased — 2026-10-21

At that point, the source version was 0.20.3, matching package.json and the Tauri manifests.

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

- Add native rectangular desktop recording with a separate click-through halo excluded from capture, physical-pixel bounds validation, Escape cancellation and avatar pause/resume.
- Encode H.264 MP4 directly to disk using bundled PyAV, verify decoding before reporting success, and retain partial files on errors. Native area recording is video-only, bounded to 30 active minutes or 4 GB.
- Keep auxiliary capture-window lifecycle separate from the resident window so closing the selector cannot stop the backend or overwrite avatar geometry.

- Add the supplied 720p concept video, preserving its original MP4 and audio, with a linked preview in the README.
- Add regression tests, setup guides, screenshots and feature-level verification reports under `evidence/*-20261021/`.
- Update Windows launch fallback and dependency lock metadata; ignore transient stdout/stderr files.
- Pre-push regression: 45 backend tests and 12 Rust tests passed (one pre-existing Rust test ignored). Provider, sound, tool interaction, chat, music, dictation and desktop frontend browser checks passed. Feature reports distinguish browser/IPC fixtures, native tests and hardware limitations.
- Latest local Windows build: `evidence/system-music-20261021/build-result.json`. Build outputs, runtime credentials and local logs remain outside Git.
