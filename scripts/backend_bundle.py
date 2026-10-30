"""Inventory and verify the public PyInstaller onedir backend (stdlib only).

Usage: python scripts/backend_bundle.py inventory ROOT [--output MANIFEST]
       python scripts/backend_bundle.py verify ROOT MANIFEST

Only axx-backend.exe and _internal belong to this bundle; sibling Tauri resources
are preserved. Every file in _internal must match the signed-off build inventory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys

MODEL_EXTENSIONS = frozenset({".onnx", ".bin", ".pt", ".pth", ".safetensors", ".npz"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _canonical_hash(files: list[dict]) -> str:
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError(f"Invalid bundle path: {value!r}")
    path = PurePosixPath(value)
    if (path.is_absolute() or PureWindowsPath(value).is_absolute()
            or path.as_posix() != value or any(part in {".", ".."} for part in path.parts)
            or not (value == "axx-backend.exe" or len(path.parts) > 1 and path.parts[0] == "_internal")):
        raise ValueError(f"Bundle path escapes its namespace: {value!r}")
    if path.suffix.lower() in MODEL_EXTENSIONS:
        raise ValueError(f"Model weight files must not be bundled: {value}")
    return value


def _check_regular(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Links and reparse points are not allowed in the backend bundle: {path}")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError(f"Expected {'directory' if directory else 'regular file'}: {path}")


def inventory(root: str | Path) -> dict:
    """Return a deterministic, complete onedir inventory; reject links/weights."""
    root = Path(root)
    try:
        _check_regular(root, directory=True)
        executable = root / "axx-backend.exe"
        internal = root / "_internal"
        _check_regular(executable)
        _check_regular(internal, directory=True)
        paths = [executable]
        # Explicitly check directories before descent: never follow a junction.
        pending = [internal]
        while pending:
            directory = pending.pop()
            for path in directory.iterdir():
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode):
                    _check_regular(path, directory=True)
                    pending.append(path)
                else:
                    _check_regular(path)
                    paths.append(path)
        files = []
        seen = set()
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
            relative = _validate_path(path.relative_to(root).as_posix())
            identity = relative.casefold()
            if identity in seen:
                raise ValueError(f"Duplicate Windows bundle path: {relative}")
            seen.add(identity)
            digest = hashlib.sha256()
            size = 0
            before = path.stat()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            after = path.stat()
            if (after.st_size != size or (before.st_size, before.st_mtime_ns, before.st_ino)
                    != (after.st_size, after.st_mtime_ns, after.st_ino)):
                raise ValueError(f"Bundle file changed while hashing: {relative}")
            files.append({"path": relative, "sha256": digest.hexdigest(), "bytes": size})
        if len(files) < 2:
            raise ValueError("The onedir bundle has no _internal files")
        return {"layout": "onedir", "files": files, "manifest_sha256": _canonical_hash(files)}
    except OSError as error:
        raise ValueError(f"Cannot inventory backend bundle at {root}: {error}") from error


def verify(root: str | Path, bundle: dict) -> None:
    """Validate manifest and exact bundle contents. Raise ValueError on failure."""
    if not isinstance(bundle, dict) or set(bundle) != {"layout", "files", "manifest_sha256"}:
        raise ValueError("Invalid backend bundle manifest fields")
    files = bundle.get("files")
    if bundle.get("layout") != "onedir" or not isinstance(files, list) or not files:
        raise ValueError("Expected a nonempty onedir backend manifest")
    paths = []
    seen = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
            raise ValueError("Invalid backend bundle file fields")
        path = _validate_path(entry["path"])
        if path.casefold() in seen:
            raise ValueError(f"Duplicate Windows bundle path: {path}")
        seen.add(path.casefold())
        paths.append(path)
        if not isinstance(entry["sha256"], str) or not _SHA256.fullmatch(entry["sha256"]):
            raise ValueError(f"Invalid SHA256 for bundle file: {path}")
        if type(entry["bytes"]) is not int or entry["bytes"] < 0:
            raise ValueError(f"Invalid byte count for bundle file: {path}")
    if paths != sorted(paths) or "axx-backend.exe" not in paths:
        raise ValueError("Backend manifest paths must be sorted and include axx-backend.exe")
    if bundle["manifest_sha256"] != _canonical_hash(files):
        raise ValueError("Backend manifest SHA256 does not match its file inventory")
    actual = inventory(root)
    actual_paths = {entry["path"] for entry in actual["files"]}
    expected_paths = set(paths)
    if actual_paths != expected_paths:
        raise ValueError(f"Backend file inventory differs: missing={sorted(expected_paths - actual_paths)}, extra={sorted(actual_paths - expected_paths)}")
    if actual != bundle:
        expected = {entry["path"]: entry for entry in files}
        changed = [entry["path"] for entry in actual["files"] if entry != expected[entry["path"]]]
        raise ValueError(f"Backend file hashes or byte counts differ: {changed}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("inventory")
    create.add_argument("root", type=Path)
    create.add_argument("--output", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("root", type=Path)
    check.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result = inventory(args.root)
            output = json.dumps(result, indent=2) + "\n"
            if args.output:
                args.output.write_text(output, encoding="utf-8")
            else:
                print(output, end="")
        else:
            verify(args.root, json.loads(args.manifest.read_text(encoding="utf-8-sig")))
            print("Backend onedir bundle verified")
        return 0
    except (OSError, ValueError) as error:
        print(f"Backend bundle verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
