"""Regression checks for mismatched versions and unverified release artifacts."""
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
from pathlib import Path

import release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("package.json", "package-lock.json", "src-tauri/Cargo.toml",
                     "src-tauri/Cargo.lock", "src-tauri/tauri.conf.json", "README.md", "release.json"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release.ROOT / name, target)
        release.sync(self.root)
        self.current = release.check(self.root)

    def receipt(self):
        for name in ("axx-backend.spec", "src-tauri/resources/ai-memory.exe"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"unit test source fixture")
        installer = self.root / f"Axx_{self.current}_x64-setup.exe"
        installer.write_bytes(b"unit test artifact fixture")
        build = {"artifacts": [{"path": str(installer), "version": self.current,
                                 "sha256": release.digest(installer)}],
                 "steps": [{"exit_code": 0}],
                 "source_hashes": {str(p): release.digest(p) for p in release.source_inventory(self.root)}}
        installed = {"result": "INSTALLED_RUNTIME_STARTED", "version": self.current,
                     "installer_sha256": release.digest(installer), "installer_exit": 0,
                     "native_window_visible": True,
                     "backend": {"authenticated_by_native_host": True, "unauthenticated_http_status": 401}}
        b, i = self.root / "build.json", self.root / "installed.json"
        release.write_json(b, build)
        release.write_json(i, installed)
        return installer, b, i

    def test_bump_preserves_confirmed_download(self):
        published = release.read_json(self.root / "release.json")
        major, minor, patch = map(int, self.current.split("."))
        newer = f"{major}.{minor}.{patch + 1}"
        release.sync(self.root, newer)
        self.assertEqual(release.check(self.root), newer)
        self.assertEqual(release.read_json(self.root / "release.json"), published)
        self.assertIn(f"Axx_{published['version']}_x64-setup.exe", (self.root / "README.md").read_text(encoding="utf-8"))

    def test_sync_without_bump_preserves_build_input_bytes(self):
        paths = [self.root / n for n in ("src-tauri/Cargo.toml", "src-tauri/tauri.conf.json")]
        before = [p.read_bytes() for p in paths]
        release.sync(self.root)
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_mismatched_manifest_is_rejected(self):
        path = self.root / "src-tauri/tauri.conf.json"
        data = release.read_json(path)
        data["version"] = "99.0.0"
        release.write_json(path, data)
        with self.assertRaisesRegex(ValueError, "manifests disagree"):
            release.check(self.root)

    def test_stale_readme_is_rejected(self):
        path = self.root / "README.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Source%20Version-v", "Source%20Version-v9"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "README"):
            release.check(self.root)

    def test_corrupt_binary_is_rejected(self):
        installer, b, i = self.receipt()
        self.assertEqual(release.validate_receipts(self.root, b, i), installer)
        installer.write_bytes(b"changed bytes")
        with self.assertRaisesRegex(ValueError, "artifact hash"):
            release.validate_receipts(self.root, b, i)

    def test_added_source_after_build_is_rejected(self):
        _, b, i = self.receipt()
        (self.root / "backend").mkdir()
        (self.root / "backend/new_feature.py").write_text("pass\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            release.validate_receipts(self.root, b, i)

    def test_modified_source_after_build_is_rejected(self):
        _, b, i = self.receipt()
        (self.root / "axx-backend.spec").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            release.validate_receipts(self.root, b, i)

    def test_unready_install_is_rejected(self):
        _, b, i = self.receipt()
        data = release.read_json(i)
        data["backend"]["authenticated_by_native_host"] = False
        release.write_json(i, data)
        with self.assertRaisesRegex(ValueError, "installed runtime"):
            release.validate_receipts(self.root, b, i)

    def test_remote_digest_must_match(self):
        path = self.root / "asset.exe"
        path.write_bytes(b"fixture")
        asset = {"state": "uploaded", "size": path.stat().st_size,
                 "digest": "sha256:" + release.digest(path)}
        release.verify_asset(asset, path)
        asset["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "GitHub asset differs"):
            release.verify_asset(asset, path)

    def test_invalid_version_rejected_without_writes(self):
        original = (self.root / "package.json").read_bytes()
        for value in ("1.2", "v1.2.3", "1.2.3;command", "01.2.3"):
            with self.assertRaises(ValueError):
                release.sync(self.root, value)
        self.assertEqual(original, (self.root / "package.json").read_bytes())

    def test_draft_is_resolved_by_database_id(self):
        result = CompletedProcess([], 0, '{"databaseId": 123}', '')
        with patch.object(release.subprocess, "run", return_value=result) as command:
            with patch.object(release, "run", return_value='{"draft": true}') as api:
                self.assertTrue(release.remote_release("v1.2.3")["draft"])
                self.assertIn("view", command.call_args.args[0])
                api.assert_called_once_with("gh", "api", f"repos/{release.REPO}/releases/123")

    def test_auth_failure_is_not_treated_as_missing_release(self):
        result = CompletedProcess([], 1, '', 'HTTP 401: unauthorized')
        with patch.object(release.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "401"):
                release.remote_release("v1.2.3")


if __name__ == "__main__":
    unittest.main()
