# Axx delivery rules

## Autoría y asistencia de IA

- La autoría de este proyecto pertenece a su creador humano. Las herramientas y modelos de IA pueden asistir con análisis, código, documentación y correcciones, pero no son autores ni coautores y no deben atribuirse crédito de autoría.
- No añadas trailers `Co-authored-by` para modelos, asistentes, proveedores de IA ni cuentas operadas por IA. No añadas sus nombres a créditos de autoría, contribuyentes o propiedad intelectual. Conserva la atribución humana existente y los avisos legales de terceros que correspondan.
- Al crear commits, usa la identidad humana configurada por el propietario; no cambies la configuración Git del usuario. No reescribas ni elimines atribuciones históricas.
- El workflow `Author policy / no-ai-coauthor` rechaza trailers de coautoría y commits que no usen la identidad Git del propietario. Para bloquear la integración, GitHub debe exigir ese estado y firmas verificadas en la rama protegida, sin actores de bypass.
- Esta es una regla obligatoria para agentes y colaboradores y se debe respetar en cada cambio.

- When changing the desktop version, update the manifests and README with `python scripts/release.py sync --version X.Y.Z`. Do not edit version fields independently.
- The user's standing instruction is to update the installed app and its published Windows download whenever the desktop version changes. A source push alone does not complete delivery.
- Follow `docs/RELEASING.md`: build, install and verify, push the source, then publish with the verified receipts. Keep existing native visual and functional acceptance checks. Report any blocked step explicitly.
- Never label an artifact published before GitHub confirms its asset hash. Do not overwrite an existing release asset with different bytes; use a new version.
- Keep Android's version independent. Report Android build, installation and physical validation separately.
- Preserve local changes, credentials, settings and the existing 3D interface. Never publish user voice samples, model weights or runtime state.

# Permanent desktop/phone compatibility and design protocol

- Follow `docs/mobile/COMPATIBILITY-PROTOCOL.md` for every desktop or phone update. Keep the current approved appearance; `mobile/design-baseline.json` protects shared desktop styles, phone home, themes and avatar rendering. Do not refresh its hashes merely to pass a check. A visual change needs explicit user authorization and recorded regression review.
- Keep `/v1` backward compatible: retain existing routes, methods, scopes and required payload meanings; add optional response fields/capabilities. A breaking change needs a separately supported API and a documented migration. Never clear pairing, credentials, grants, drafts or pending operation IDs to repair compatibility.
- Run `python scripts/validate_companion.py --output build/companion-validation.json` on the final integrated source. `release.py publish` requires `--companion-result` pointing to that matching successful receipt, including for `--dry-run`. A stale, incomplete or failed receipt blocks publication.
- Keep desktop and Android versions independent. Rebuild phone assets from the current desktop renderer, preserve Android application ID/signing identity, and advance its versionCode for a new Android release. Source/browser checks do not replace APK hash/signature verification, installation or physical acceptance.
- Use `docs/mobile/SCREEN-STUDY-20261029.md` when adding a device/window class. Extend the matrix and native acceptance for new panes and hardware; do not label untested iPhones, foldables, screen sizes or accessibility modes supported. Preserve the existing layout while adding adaptation rules.
- During coordinated delivery, use one owner for version changes, builds, installation and publication. Do not stage, overwrite or publish another task's changes or private evidence indiscriminately.
