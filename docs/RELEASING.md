# Desktop version and release procedure

Changing the desktop version includes updating the installed app, the Windows
download on GitHub, and the README. Source pushes do not upload installers.
Android keeps its own version and physical verification requirements.

## 1. Synchronize the version

Use Python 3.11 or newer:

```powershell
python scripts/release.py sync --version 0.20.19
python scripts/release.py check
```

Use the actual next version in place of the example. The command updates the npm
manifests, Tauri configuration, Cargo manifests, Axx UI version and README source
badge. It keeps the published download on its confirmed version until publication succeeds.
Write the release notes in `docs/releases/X.Y.Z.md`; include measured behavior,
required setup and outstanding hardware checks.

## 2. Build, install and verify

Run the relevant tests and native visual/function checks for the changed features.
Close the installed Axx before running the installation step.

Every desktop release also follows the [permanent companion protocol](mobile/COMPATIBILITY-PROTOCOL.md), even when the Android version is unchanged. On the final integrated source, install the test requirements and Chromium once, then run the paired gate:

```powershell
python -m pip install -r requirements-companion-tests.txt
python -m playwright install chromium
python scripts/validate_companion.py --output build/companion-validation.json
```

The gate rebuilds web assets, checks the protected design and shared renderer, and runs service/TLS/browser/screen contracts. It does not build or install an APK and does not certify physical phones. Android binary/signature, upgrade-with-data and hardware receipts remain separate. Re-run the gate after any tested source changes; copied receipts work from a clean publication checkout only when its canonical inputs and both application versions match.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1 -EvidenceDirectory build/release-current
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-verified-windows.ps1 -BuildResult build/release-current/build-result.json -EvidenceDirectory build/release-current
```

The build checks version consistency first. Keep both receipts. Source changes
after the build require rebuilding; do not substitute another installer with the
same version. Installation readiness does not replace native feature acceptance.

## 3. Commit, push and publish

Review and commit the intended source changes, then `git push origin main`.
The GitHub CLI must already be authenticated with release write access.

```powershell
python scripts/release.py publish --build-result build/release-current/build-result.json --install-result build/release-current/installed-runtime.json --companion-result build/companion-validation.json --notes docs/releases/0.20.19.md --dry-run
python scripts/release.py publish --build-result build/release-current/build-result.json --install-result build/release-current/installed-runtime.json --companion-result build/companion-validation.json --notes docs/releases/0.20.19.md
```

Publication requires clean, synchronized `main`, matching versions, unchanged
build inputs, matching binary hashes and a successful installed runtime receipt.
It creates a draft at the exact source commit, uploads the installer and
`SHA256SUMS.txt`, verifies the GitHub asset digests, then publishes a **prerelease**.
It updates `release.json` and the README only after publication, commits those two
files and pushes them. The command does not publish private build receipts.

If upload fails, the draft remains unpublished and the README keeps the previous
download. Retry the same command from the same commit; matching assets are reused.
Conflicting assets are rejected. If the final documentation push fails, finish
that push; the release itself may already be public. Never claim delivery is
complete without checking both the release and `git status`.

GitHub Actions checks version/documentation consistency on pushes and pull
requests. It does not build Windows releases automatically: the verified native
installation and local dependencies are still required by the release procedure.
