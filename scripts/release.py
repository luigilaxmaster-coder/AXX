"""Synchronize desktop versions and publish only verified Windows installers.

Uses Python 3.11+ and the authenticated GitHub CLI. No credentials are read or
stored by this script. All subprocess arguments are passed without a shell.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "luigilaxmaster-coder/AXX"
BASE = f"https://github.com/{REPO}/releases"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def version(value: str) -> str:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value):
        raise ValueError("Use a desktop version in X.Y.Z format")
    return value


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(*args: str, root: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=root, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def replace_once(pattern: str, replacement, text: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected version/documentation field missing: {pattern}")
    return updated


def render_readme(root: Path, current: str) -> str:
    published = version(read_json(root / "release.json")["version"])
    text = (root / "README.md").read_text(encoding="utf-8")
    status = (f"Source and published Windows installer are both **v{current}**."
              if current == published else
              f"Source is **v{current}**; the published Windows installer is **v{published}**. "
              "Delivery of the newer source is pending publication.")
    block = f"""## Download Axx for Windows

<!-- release:download:start -->
**[Download Windows x64 test installer · v{published}]({BASE}/download/v{published}/Axx_{published}_x64-setup.exe)** · [Release files]({BASE}/tag/v{published}) · [SHA-256]({BASE}/download/v{published}/SHA256SUMS.txt)

Run the installer and open Axx. Python and Node are not required. Start with **Automático gratis · Sin claves**; Axx checks available free routes, whose availability can change. Personal API keys are optional in Settings. Credentials and conversation history are not included in the installer. Windows may need Internet to install WebView2. The installer is unsigned.

The packaged backend may take longer on its first launch while Windows extracts and scans it. The native host allows up to 90 seconds for backend readiness and reports a startup error if that limit is exceeded.

{status} Android APKs remain local test artifacts until separately published. See [mobile setup and validation](docs/mobile/README.md) and the [version and release procedure](docs/RELEASING.md).
<!-- release:download:end -->

"""
    text = replace_once(r"(?s)## Download Axx for Windows\n.*?(?=---)", lambda _: block, text)
    text = replace_once(r'Source%20Version-v[^" ]+-informational', f"Source%20Version-v{current}-informational", text)
    text = replace_once(r'alt="Source version [^"]+"', f'alt="Source version {current}"', text)
    text = replace_once(r"^> \*\*Axx is under active development\.\*\*.*$",
                        f"> **Axx is under active development.** {status} Validation is recorded per feature; a working UI or build does not by itself certify every hardware-dependent behavior.", text)
    return text


def sync(root: Path, target: str | None = None):
    package = read_json(root / "package.json")
    target = version(target or package["version"])
    published = version(read_json(root / "release.json")["version"])
    if tuple(map(int, target.split("."))) < tuple(map(int, published.split("."))):
        raise ValueError("Desktop version cannot precede the published version")
    for name in ("package.json", "package-lock.json", "src-tauri/tauri.conf.json"):
        path = root / name
        data = read_json(path)
        original = json.dumps(data, sort_keys=True)
        data["version"] = target
        if name == "package-lock.json":
            data["packages"][""]["version"] = target
        if json.dumps(data, sort_keys=True) != original:
            write_json(path, data)
    for name, pattern in (
        ("src-tauri/Cargo.toml", r'(\[package\]\s+name = "axx"\s+version = ")[^"]+(")'),
        ("src-tauri/Cargo.lock", r'(\[\[package\]\]\s+name = "axx"\s+version = ")[^"]+(")'),
    ):
        path = root / name
        text = path.read_text(encoding="utf-8")
        updated = replace_once(pattern, lambda m: m[1] + target + m[2], text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    ui = root / "1.AXX/Axx.html"
    text = ui.read_text(encoding="utf-8")
    updated = replace_once(r"^(\s*Axx\.VERSION = ')[^']+(';)$", lambda m: m[1] + target + m[2], text)
    if updated != text:
        ui.write_text(updated, encoding="utf-8")
    (root / "README.md").write_text(render_readme(root, target), encoding="utf-8")
    check(root)


def check(root: Path) -> str:
    current = version(read_json(root / "package.json")["version"])
    published = read_json(root / "release.json")
    if not re.fullmatch(r"[0-9a-f]{64}", published.get("sha256", "")):
        raise ValueError("Published release metadata must include its confirmed SHA-256")
    if tuple(map(int, version(published["version"]).split("."))) > tuple(map(int, current.split("."))):
        raise ValueError("Source version precedes published version")
    lock = read_json(root / "package-lock.json")
    cargo = tomllib.loads((root / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    cargo_lock = tomllib.loads((root / "src-tauri/Cargo.lock").read_text(encoding="utf-8"))
    values = [lock["version"], lock["packages"][""]["version"],
              read_json(root / "src-tauri/tauri.conf.json")["version"], cargo["package"]["version"]]
    values += [p["version"] for p in cargo_lock["package"] if p["name"] == "axx"]
    if len(values) != 5 or any(v != current for v in values):
        raise ValueError("Desktop manifests disagree; run scripts/release.py sync --version X.Y.Z")
    ui_version = re.search(r"^\s*Axx\.VERSION = '([^']+)';$", (root / "1.AXX/Axx.html").read_text(encoding="utf-8"), re.MULTILINE)
    if not ui_version or ui_version[1] != current:
        raise ValueError("Axx UI version disagrees; run scripts/release.py sync --version X.Y.Z")
    if render_readme(root, current) != (root / "README.md").read_text(encoding="utf-8"):
        raise ValueError("README release information is stale; run scripts/release.py sync")
    return current


def source_inventory(root: Path) -> set[Path]:
    paths = {root / p for p in ("axx-backend.spec", "scripts/setup-freellmapi.ps1", "scripts/configure-native-gateway.py", "scripts/anythingmcp-local.py", "src-tauri/tauri.conf.json",
                                "src-tauri/Cargo.toml", "src-tauri/resources/ai-memory.exe")}
    paths.update(p for p in (root / "1.AXX").rglob("*") if p.is_file() and
                 p.suffix in (".html", ".js", ".css", ".json", ".png", ".ico", ".svg", ".woff", ".woff2"))
    paths.update(p for p in (root / "src-tauri/resources/license-notices").rglob("*") if p.is_file())
    for folder in ("backend", "src-tauri/src", "resources", "vendor"):
        paths.update(p for p in (root / folder).rglob("*") if p.is_file() and
                     p.suffix in (".ps1", ".py", ".rs", ".json", ".bin", ".txt", ".zip") and
                     not {"tests", "__pycache__"}.intersection(p.relative_to(root).parts) and
                     not p.name.startswith("test_"))
    return {p.resolve() for p in paths}


def validate_receipts(root: Path, build_path: Path, installed_path: Path) -> Path:
    current = check(root)
    build, installed = read_json(build_path), read_json(installed_path)
    artifacts = build["artifacts"]
    installers = [a for a in artifacts if Path(a["path"]).name == f"Axx_{current}_x64-setup.exe"]
    if len(installers) != 1 or not build.get("source_hashes") or not build.get("steps"):
        raise ValueError("Missing complete build receipt for current version")
    if any(step["exit_code"] != 0 for step in build["steps"]):
        raise ValueError("Build receipt contains failed steps")
    built_root = build_path.resolve().parent
    if built_root.name in ("build", "evidence"):
        built_root = built_root.parent
    elif built_root.parent.name in ("build", "evidence"):
        built_root = built_root.parent.parent
    sources = {}
    for name, sha in build["source_hashes"].items():
        path = Path(name)
        try:
            relative = path.resolve().relative_to(built_root) if path.is_absolute() else path
        except ValueError as exc:
            raise ValueError("Build receipt names a source outside its checkout") from exc
        sources[relative] = sha
    if {(root / name).resolve() for name in sources} != source_inventory(root):
        raise ValueError("Source inventory changed since build; rebuild before publication")
    for artifact in artifacts:
        if artifact["version"] != current or digest(Path(artifact["path"])) != artifact["sha256"].lower():
            raise ValueError("Build artifact hash or version mismatch")
    text_sources = {'.py', '.js', '.html', '.css', '.rs', '.ps1', '.json', '.toml', '.txt'}
    for name, sha in sources.items():
        if digest(root / name) == sha.lower():
            continue
        built = built_root / name
        # Check the exact build bytes first; another checkout may differ only in line endings.
        if (name.suffix.lower() not in text_sources or not built.is_file() or digest(built) != sha.lower()
                or (root / name).read_bytes().replace(b'\r\n', b'\n') != built.read_bytes().replace(b'\r\n', b'\n')):
            raise ValueError(f"Source changed since build: {name}")
    item = installers[0]
    if (installed.get("result") != "INSTALLED_RUNTIME_STARTED" or installed.get("version") != current
            or installed.get("installer_sha256", "").lower() != item["sha256"].lower()
            or installed.get("installer_exit") != 0 or not installed.get("native_window_visible")
            or not installed.get("backend", {}).get("authenticated_by_native_host")
            or installed.get("backend", {}).get("unauthenticated_http_status") != 401):
        raise ValueError("Installer has no matching successful installed runtime receipt")
    return Path(item["path"])


def remote_release(tag: str):
    # The REST lookup by tag omits unpublished drafts. gh release view also
    # searches the authenticated draft list, then its database ID is unambiguous.
    result = subprocess.run(["gh", "release", "view", tag, "--repo", REPO, "--json", "databaseId"],
                            text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        if result.stderr.strip().lower() == "release not found":
            return None
        raise RuntimeError(result.stderr.strip())
    release_id = int(json.loads(result.stdout)["databaseId"])
    return json.loads(run("gh", "api", f"repos/{REPO}/releases/{release_id}"))


def verify_asset(asset, path: Path):
    if (asset.get("state") != "uploaded" or asset.get("size") != path.stat().st_size
            or asset.get("digest") != "sha256:" + digest(path)):
        raise ValueError(f"GitHub asset differs from verified local file: {path.name}")


def publish(args):
    current = check(ROOT)
    installer = validate_receipts(ROOT, args.build_result.resolve(), args.install_result.resolve())
    if not args.notes.is_file() or not args.notes.read_text(encoding="utf-8").strip():
        raise ValueError("A nonempty release notes file is required")
    if args.dry_run:
        print(f"PASS: v{current} build, source hashes and installed runtime match. No publication performed.")
        return
    if run("git", "status", "--porcelain"):
        raise ValueError("Commit source and release tooling before publishing; working tree must be clean")
    if run("git", "branch", "--show-current") != "main":
        raise ValueError("Publish from main")
    if run("git", "remote", "get-url", "origin") not in (f"https://github.com/{REPO}.git", f"git@github.com:{REPO}.git"):
        raise ValueError("Unexpected origin repository")
    run("git", "fetch", "origin", "main")
    commit = run("git", "rev-parse", "HEAD")
    if commit != run("git", "rev-parse", "origin/main"):
        raise ValueError("Push the verified source to origin/main before publishing")
    tag = "v" + current
    staging = ROOT / "build" / f"publish-{tag}"
    staging.mkdir(parents=True, exist_ok=True)
    sums = staging / "SHA256SUMS.txt"
    sums.write_text(f"{digest(installer)}  {installer.name}\n", encoding="utf-8")
    release = remote_release(tag)
    if release is None:
        run("gh", "release", "create", tag, "--repo", REPO, "--target", commit,
            "--draft", "--prerelease", "--title", f"Axx {current} - Windows x64 test release",
            "--notes-file", str(args.notes.resolve()))
        release = remote_release(tag)
    if release is None:
        raise RuntimeError("GitHub has not returned the new draft; retry after confirming it exists")
    if release["draft"] and release["target_commitish"] != commit:
        raise ValueError("Existing draft points to different source; inspect it before continuing")
    if not release["draft"]:
        resolved = json.loads(run("gh", "api", f"repos/{REPO}/commits/{tag}"))["sha"]
        if resolved != commit:
            raise ValueError("Existing release points to a different commit; use a new version")
    for path in (installer, sums):
        asset = next((a for a in release["assets"] if a["name"] == path.name), None)
        if asset:
            verify_asset(asset, path)
        elif release["draft"]:
            print(f"Uploading {path.name}", flush=True)
            run("gh", "release", "upload", tag, str(path), "--repo", REPO)
        else:
            raise ValueError("Published release is missing an expected asset")
    release = remote_release(tag)
    for path in (installer, sums):
        verify_asset(next(a for a in release["assets"] if a["name"] == path.name), path)
    if release["draft"]:
        run("gh", "release", "edit", tag, "--repo", REPO, "--draft=false", "--prerelease")
    release = remote_release(tag)
    if release["draft"]:
        raise RuntimeError("GitHub still reports a draft; README was not changed")
    write_json(ROOT / "release.json", {"version": current, "sha256": digest(installer),
                                       "prerelease": True, "source_commit": commit})
    (ROOT / "README.md").write_text(render_readme(ROOT, current), encoding="utf-8")
    check(ROOT)
    run("git", "add", "--", "README.md", "release.json")
    run("git", "commit", "-m", f"docs: point Windows download to verified {tag} release")
    run("git", "push", "origin", "main")
    print(f"Published and README pushed: {release['html_url']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    change = commands.add_parser("sync")
    change.add_argument("--version")
    upload = commands.add_parser("publish")
    upload.add_argument("--build-result", type=Path, required=True)
    upload.add_argument("--install-result", type=Path, required=True)
    upload.add_argument("--notes", type=Path, required=True)
    upload.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "sync":
            sync(ROOT, args.version)
            print("Desktop versions and README synchronized")
        elif args.command == "check":
            print(f"PASS: desktop versions and README agree (v{check(ROOT)})")
        else:
            publish(args)
    except (ValueError, RuntimeError, OSError, KeyError, StopIteration) as error:
        print(f"Release stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
