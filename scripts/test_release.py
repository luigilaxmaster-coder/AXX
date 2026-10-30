"""Regression checks for mismatched versions and unverified release artifacts."""
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess
from pathlib import Path

import release
from backend_bundle import inventory


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("package.json", "package-lock.json", "src-tauri/Cargo.toml",
                     "src-tauri/Cargo.lock", "src-tauri/tauri.conf.json", "README.md", "release.json", "1.AXX/Axx.html"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release.ROOT / name, target)
        release.sync(self.root)
        self.current = release.check(self.root)

    def receipt(self):
        for name in ("axx-backend.spec", "scripts/backend_bundle.py", "scripts/build-windows.ps1", "scripts/setup-freellmapi.ps1", "scripts/configure-native-gateway.py", "scripts/anythingmcp-local.py", "src-tauri/resources/ai-memory.exe", "requirements-telegram.txt", "backend/telegram/webapp.html", "backend/telegram/webapp.css", "backend/telegram/webapp.js", "mobile/www/js/desktop-avatar.js", "mobile/js/avatar-renderer.js"):
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

    def onedir_receipt(self):
        installer, b, i = self.receipt()
        bundle_root = self.root / 'dist/axx-backend'
        (bundle_root / '_internal').mkdir(parents=True)
        (bundle_root / 'axx-backend.exe').write_bytes(b'backend executable')
        (bundle_root / '_internal/python312.dll').write_bytes(b'python DLL fixture')
        resources = self.root / 'src-tauri/resources'
        shutil.copytree(bundle_root, resources, dirs_exist_ok=True)
        app = self.root / 'installed'
        shutil.copytree(bundle_root, app / 'resources')
        bundle = inventory(bundle_root)
        build = release.read_json(b)
        backend = bundle_root / 'axx-backend.exe'
        build['artifacts'].append({'path': str(backend), 'version': self.current,
                                   'sha256': release.digest(backend), 'bytes': backend.stat().st_size})
        build['backend_bundle'] = bundle
        release.write_json(b, build)
        (self.root / 'build').mkdir()
        release.write_json(self.root / 'build/backend-build-receipt.json', {'bundle': bundle})
        runtime = release.read_json(i)
        runtime['executable'] = str(app / 'Axx.exe')
        release.write_json(i, runtime)
        proof = {'result': 'PASS', 'version': self.current, 'installed_directory': str(app),
                 'backend_sha256': release.digest(backend),
                 'backend_bundle': {'layout': 'onedir', 'manifest_sha256': bundle['manifest_sha256'],
                                    'files_verified': len(bundle['files'])}}
        release.write_json(i.with_name('installed-files.json'), proof)
        return installer, b, i

    def test_onedir_delivery_requires_complete_matching_proof(self):
        installer, b, i = self.onedir_receipt()
        self.assertEqual(release.validate_receipts(self.root, b, i), installer)
        proof_path = i.with_name('installed-files.json')
        proof = release.read_json(proof_path)
        proof['backend_bundle']['manifest_sha256'] = '0' * 64
        release.write_json(proof_path, proof)
        with self.assertRaisesRegex(ValueError, 'does not match the build'):
            release.validate_receipts(self.root, b, i)
        proof_path.unlink()
        with self.assertRaisesRegex(ValueError, 'installed-files.json'):
            release.validate_receipts(self.root, b, i)

    def test_onedir_delivery_rejects_tampered_build_or_installed_dependencies(self):
        for relative in ('dist/axx-backend/_internal/python312.dll',
                         'src-tauri/resources/_internal/python312.dll',
                         'installed/resources/_internal/python312.dll'):
            with self.subTest(relative=relative):
                # Each failure must be observed independently, including staging.
                installer, b, i = self.onedir_receipt()
                dependency = self.root / relative
                original = dependency.read_bytes()
                dependency.write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError, 'hashes or byte counts differ'):
                    release.validate_receipts(self.root, b, i)
                dependency.write_bytes(original)
                self.assertEqual(release.validate_receipts(self.root, b, i), installer)
                shutil.rmtree(self.root / 'dist')
                shutil.rmtree(self.root / 'installed')
                shutil.rmtree(self.root / 'build')

    def test_onedir_delivery_rejects_missing_dependency_and_missing_manifest(self):
        _, b, i = self.onedir_receipt()
        (self.root / 'installed/resources/_internal/python312.dll').unlink()
        with self.assertRaisesRegex(ValueError, 'no _internal files|inventory differs'):
            release.validate_receipts(self.root, b, i)
        build = release.read_json(b)
        del build['backend_bundle']
        release.write_json(b, build)
        with self.assertRaisesRegex(ValueError, 'requires a complete bundle'):
            release.validate_receipts(self.root, b, i)

    def test_onedir_delivery_rejects_backend_receipt_mismatch(self):
        _, b, i = self.onedir_receipt()
        release.write_json(self.root / 'build/backend-build-receipt.json', {'bundle': {}})
        with self.assertRaisesRegex(ValueError, 'Backend build receipt'):
            release.validate_receipts(self.root, b, i)

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

    def test_stale_ui_version_is_rejected(self):
        path = self.root / "1.AXX/Axx.html"
        path.write_text(path.read_text(encoding="utf-8").replace(f"Axx.VERSION = '{self.current}'", "Axx.VERSION = '0.0.0'"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "UI version"):
            release.check(self.root)

    def test_corrupt_binary_is_rejected(self):
        installer, b, i = self.receipt()
        self.assertEqual(release.validate_receipts(self.root, b, i), installer)
        installer.write_bytes(b"changed bytes")
        with self.assertRaisesRegex(ValueError, "artifact hash"):
            release.validate_receipts(self.root, b, i)

    def test_added_source_after_build_is_rejected(self):
        _, b, i = self.receipt()
        (self.root / "backend").mkdir(exist_ok=True)
        (self.root / "backend/new_feature.py").write_text("pass\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            release.validate_receipts(self.root, b, i)

    def test_modified_source_after_build_is_rejected(self):
        _, b, i = self.receipt()
        (self.root / "axx-backend.spec").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            release.validate_receipts(self.root, b, i)

    def test_telegram_assets_are_required_and_tampering_is_rejected(self):
        for name in ('backend/telegram/webapp.html', 'backend/telegram/webapp.css', 'backend/telegram/webapp.js',
                     'mobile/www/js/desktop-avatar.js', 'mobile/js/avatar-renderer.js', 'requirements-telegram.txt'):
            with self.subTest(name=name):
                _, b, i = self.receipt()
                self.assertIn((self.root / name).resolve(), release.source_inventory(self.root))
                (self.root / name).write_text('changed', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'Source changed'):
                    release.validate_receipts(self.root, b, i)

    def test_license_notice_bytes_are_part_of_delivery(self):
        notice = self.root / 'src-tauri/resources/license-notices/example/LICENSE'
        notice.parent.mkdir(parents=True)
        notice.write_text('Original notice', encoding='utf-8')
        installer, b, i = self.receipt()
        self.assertEqual(release.validate_receipts(self.root, b, i), installer)
        notice.write_text('Changed notice', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            release.validate_receipts(self.root, b, i)

    def test_verified_receipt_can_publish_from_identical_checkout(self):
        installer, b, i = self.receipt()
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        checkout = Path(other.name)
        shutil.copytree(self.root, checkout, dirs_exist_ok=True)
        self.assertEqual(release.validate_receipts(checkout, b, i), installer)

    def test_cross_checkout_line_endings_are_accepted_but_content_changes_are_not(self):
        source = self.root / 'backend/example.py'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'value = 1\r\n')
        notice = self.root / 'src-tauri/resources/license-notices/example/LICENSE'
        notice.parent.mkdir(parents=True)
        notice.write_bytes(b'License notice\r\n')
        installer, b, i = self.receipt()
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        checkout = Path(other.name)
        shutil.copytree(self.root, checkout, dirs_exist_ok=True)
        copy = checkout / 'backend/example.py'
        copy.write_bytes(b'value = 1\n')
        copied_notice = checkout / 'src-tauri/resources/license-notices/example/LICENSE'
        copied_notice.write_bytes(b'License notice\n')
        self.assertEqual(release.validate_receipts(checkout, b, i), installer)
        copy.write_bytes(b'value = 2\n')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            release.validate_receipts(checkout, b, i)
        copy.write_bytes(b'value = 1\n')
        copied_notice.write_bytes(b'Changed notice\n')
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            release.validate_receipts(checkout, b, i)

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
