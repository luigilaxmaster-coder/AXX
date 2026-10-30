"""Regression tests for the complete onedir backend integrity boundary."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.backend_bundle import inventory, verify


class BackendBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "_internal" / "pkg").mkdir(parents=True)
        (self.root / "axx-backend.exe").write_bytes(b"launcher")
        (self.root / "_internal" / "python.dll").write_bytes(b"python")
        (self.root / "_internal" / "pkg" / "data.json").write_text("{}", encoding="utf-8")
        self.bundle = inventory(self.root)

    @staticmethod
    def rehash(bundle):
        bundle["manifest_sha256"] = hashlib.sha256(
            json.dumps(bundle["files"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return bundle

    def test_deterministic_manifest_and_unrelated_resources(self):
        (self.root / "ai-memory.exe").write_bytes(b"preserved")
        self.assertEqual(inventory(self.root), self.bundle)
        self.assertEqual(self.bundle["manifest_sha256"], self.rehash(copy.deepcopy(self.bundle))["manifest_sha256"])
        self.assertEqual([entry["path"] for entry in self.bundle["files"]], sorted(entry["path"] for entry in self.bundle["files"]))
        self.assertIsNone(verify(self.root, self.bundle))

    def test_tampered_dependency_same_length_fails(self):
        (self.root / "_internal" / "python.dll").write_bytes(b"PYTHON")
        with self.assertRaisesRegex(ValueError, "hashes or byte counts"):
            verify(self.root, self.bundle)

    def test_missing_dependency_fails(self):
        (self.root / "_internal" / "python.dll").unlink()
        with self.assertRaisesRegex(ValueError, "missing="):
            verify(self.root, self.bundle)

    def test_unexpected_dependency_fails(self):
        (self.root / "_internal" / "extra.dll").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "extra="):
            verify(self.root, self.bundle)

    def test_unsafe_manifest_paths_fail(self):
        for path in ("../escape", "/outside", "C:/outside", "_internal/../escape", "_internal\\escape", "_internal//file", "axx-backend.exe/extra"):
            with self.subTest(path=path):
                bundle = copy.deepcopy(self.bundle)
                bundle["files"][0]["path"] = path
                self.rehash(bundle)
                with self.assertRaises(ValueError):
                    verify(self.root, bundle)

    def test_duplicate_windows_path_fails(self):
        bundle = copy.deepcopy(self.bundle)
        duplicate = dict(bundle["files"][0])
        duplicate["path"] = duplicate["path"].upper().replace("_INTERNAL", "_internal")
        bundle["files"].append(duplicate)
        self.rehash(bundle)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify(self.root, bundle)

    def test_manifest_hash_or_type_corruption_fails(self):
        for key, value in (("sha256", "ABC"), ("bytes", True), ("bytes", -1)):
            bundle = copy.deepcopy(self.bundle)
            bundle["files"][0][key] = value
            self.rehash(bundle)
            with self.assertRaises(ValueError):
                verify(self.root, bundle)
        bundle = copy.deepcopy(self.bundle)
        bundle["manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "manifest SHA256"):
            verify(self.root, bundle)

    def test_model_weights_fail(self):
        (self.root / "_internal" / "weights.onnx").write_bytes(b"private")
        with self.assertRaisesRegex(ValueError, "Model weight"):
            inventory(self.root)

    def test_reparse_point_fails_even_without_symlink_privilege(self):
        original = Path.lstat
        def reparse_info(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if path == self.root / "_internal" / "python.dll":
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(Path, "lstat", reparse_info):
            with self.assertRaisesRegex(ValueError, "Links and reparse points"):
                inventory(self.root)

    def test_symlink_dependency_fails(self):
        link = self.root / "_internal" / "link.dll"
        try:
            link.symlink_to(self.root / "axx-backend.exe")
        except OSError:
            self.skipTest("Symlink creation is unavailable for this Windows account")
        with self.assertRaisesRegex(ValueError, "Links and reparse points"):
            inventory(self.root)


if __name__ == "__main__":
    unittest.main()
