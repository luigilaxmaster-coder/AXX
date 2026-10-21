# Area recording — 2026-10-21

Reviewed locally by the implementing agent; no independent reviewer.

## Changes

- Native transparent selection window accepts a dragged rectangle or Escape. Coordinates map to physical virtual-desktop pixels, including negative origins.
- A separate click-through halo marks the region and uses Windows capture exclusion. Paused state is amber. Auxiliary windows cannot stop the backend or change resident geometry.
- One backend recording service writes H.264 MP4 directly to disk through the bundled PyAV 18 runtime. It rejects concurrent starts and stale controls, excludes paused time, verifies the completed file, and preserves partial files on failure.
- Native screen controls use icons with accessible names. The avatar controls pause/resume, results expose open-video/open-folder, and the start button waits for backend readiness.

## Validation

All commands completed with exit code 0:

- `py -3.14 -m unittest discover -s backend/tests -q`: 68 tests passed. Includes real authenticated HTTP validation of start/status/control, invalid bounds, stale IDs, concurrent start rejection and countdown cancellation without a video file.
- `cargo test --manifest-path src-tauri/Cargo.toml --lib --quiet`: 14 passed, one pre-existing test ignored. Includes physical-pixel normalization and invalid region rejection.
- `node 1.AXX/scripts/test-native-capture.cjs`: controlled browser/IPC contract for real frontend controls, icon persistence, avatar pause/resume, duplicate suppression, direct-disk result, cancelled selection, reverse drag and Escape. This fixture does not by itself prove native recording.
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: 18 existing desktop contracts passed, no uncaught errors.
- `py -3.14 -m backend.tests.verify_screen_native`: real Windows GDI capture of an owned green test window, pause/resume, MP4 decode and pixel verification. Result: `native.json`.
- `py -3.14 -m PyInstaller --noconfirm axx-backend.spec` and `tauri build --no-bundle`: backend and host built locally. Binary hashes: `build-result.json`.
- `node 1.AXX/scripts/verify-capture-packaged.cjs`: real release Tauri/WebView2 application with the bundled backend and isolated app data. Dragged the native selector, paused/resumed using the avatar action, finalized MP4, decoded its 200 × 160 pixels, and checked center and near-edge colors. Halo exclusion passed. Escape destroyed the selector while the backend remained available. Result: `packaged-native.json`.

The first packaged test exposed premature test readiness (an asynchronous page predicate); the test now polls resolved native status before interaction. The UI also prevents starting before its first successful backend status response.

## Limits

- Native rectangular recording currently has no system audio or microphone track. This is disclosed in the panel and usage guide; the browser recorder remains available in browser mode.
- No claim of physical mixed-DPI/multi-monitor testing, long-duration endurance, or sustained 60 fps. Negative coordinates and limits have unit coverage.
- Maximum 30 active minutes, 4 GB, 7680 × 4320 pixels. Dimensions are rounded down to even values. Unexpected process termination can leave a partial MP4; automatic repair is not implemented.
- No installer release was published. The locally rebuilt application and repository sources were updated.
