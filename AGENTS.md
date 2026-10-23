# Axx delivery rules

- When changing the desktop version, update the manifests and README with `python scripts/release.py sync --version X.Y.Z`. Do not edit version fields independently.
- The user's standing instruction is to update the installed app and its published Windows download whenever the desktop version changes. A source push alone does not complete delivery.
- Follow `docs/RELEASING.md`: build, install and verify, push the source, then publish with the verified receipts. Keep existing native visual and functional acceptance checks. Report any blocked step explicitly.
- Never label an artifact published before GitHub confirms its asset hash. Do not overwrite an existing release asset with different bytes; use a new version.
- Keep Android's version independent. Report Android build, installation and physical validation separately.
- Preserve local changes, credentials, settings and the existing 3D interface. Never publish user voice samples, model weights or runtime state.
