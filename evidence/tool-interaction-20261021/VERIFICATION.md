# Tool interaction repair — 2026-10-21

Branch: `codex/fix-tool-interaction`. Self-review; no independent reviewer.

## Reproduced causes

- Orbit layout sets `pointer-events: none !important` on `flow-sheet`. The catalog reused that container without restoring pointer events. The new browser pointer test reproduced `none !== auto`, and category clicks timed out with the body intercepting input.
- The hover tendril stopped extending after 1,250 ms even while the pointer remained over its button. The regression test measured progress `0.002295397872361611` after a sustained hover.
- Tool captions were visible, contrary to the requested icon-only controls.

## Changes

- Restore pointer input for the catalog and include the complete catalog surface in the native hit map, including scrolling and drag areas.
- Compact icon controls, accessible names and hover titles, distinct tool symbols, and no detached orbit resize handle.
- Maintain hover attachment; interpolate endpoints; retain the endpoint while retracting. Render the whole curved tube within its bounds, close its tip, and fade the final retraction pixels.
- Keep existing body shape, material, preferences, and backend data.

## Automated verification

Windows environment: Node v24.14.0, Cargo 1.97.1. Browser executable: installed Chromium headless shell 1234.

`AXX_TEST_CHROMIUM` was set to the installed `chrome-headless-shell.exe`.

- `node 1.AXX/scripts/test-tools-interaction.cjs`: exit 0, four groups passed, no uncaught browser errors. Real browser pointer actions with native IPC simulated. Covers orbit-to-catalog, Chat/Notes/Calculator, tabs/search/repeated navigation, icon labels, sustained hover and continuous retraction.
- `node 1.AXX/scripts/test-desktop-frontend.cjs`: exit 0, 18 existing contract tests passed, no uncaught browser errors.
- `git diff --check`: exit 0.

Screenshots: `catalog.png`, `tentacle.png` (controlled browser, not native screenshots).

Original HTML SHA256: `455EB4A9838B17A2AAF7B2800835EFE6DC79FBCBC4B73820D9277B2FCF16CACD`.
Original EXE SHA256: `67B18116344639C68D8CCA759E152D7173764711D9F56B0430233D4B957785C7`.
Original executable retained locally as `Axx-before.exe` (ignored by Git).

Native build and physical UI verification are recorded below after completion.
