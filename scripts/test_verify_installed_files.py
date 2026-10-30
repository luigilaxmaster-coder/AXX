"""Installed delivery checks must include every onedir dependency."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from backend_bundle import inventory

SCRIPT = Path(__file__).with_name('verify-installed-files.py')
SPEC = importlib.util.spec_from_file_location('verify_installed_files', SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class InstalledFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'installed'
        resources = self.app / 'resources'
        (resources / 'license-notices/example').mkdir(parents=True)
        (resources / 'license-notices/example/LICENSE').write_bytes(b'license')
        (resources / 'ai-memory.exe').write_bytes(b'memory')
        (resources / 'axx-backend.exe').write_bytes(b'backend')
        release = self.root / 'Axx.exe'
        release.write_bytes(b'prefix BUNDLE_TYPE_VAR_UNK suffix')
        (self.app / 'Axx.exe').write_bytes(release.read_bytes().replace(b'_UNK', b'_NSS'))
        self.build = {
            'artifacts': [
                {'path': str(self.root / 'setup.exe'), 'version': '1.2.3'},
                {'path': str(release), 'sha256': self.sha(release.read_bytes())},
                {'path': str(self.root / 'dist/axx-backend.exe'), 'sha256': self.sha(b'backend')},
            ],
            'source_hashes': {'src-tauri/resources/ai-memory.exe': self.sha(b'memory'),
                              'src-tauri/resources/license-notices/example/LICENSE': self.sha(b'license')},
        }

    @staticmethod
    def sha(data):
        return hashlib.sha256(data).hexdigest()

    def add_bundle(self):
        resources = self.app / 'resources'
        (resources / '_internal').mkdir()
        (resources / '_internal/python312.dll').write_bytes(b'python DLL')
        (resources / '_internal/runtime.pyd').write_bytes(b'runtime')
        self.build['backend_bundle'] = inventory(resources)
        self.build['artifacts'][2]['path'] = str(self.root / 'dist/axx-backend/axx-backend.exe')

    def test_legacy_verifies_exact_nsis_marker_without_claiming_bundle(self):
        result = verifier.verify_installed_files(self.app, self.build)
        self.assertEqual(result['tauri_bundle_marker'], 'Tauri UNK -> NSS; exactly three bytes')
        self.assertNotIn('backend_bundle', result)

    def test_legacy_identical_release_is_still_valid(self):
        shutil.copyfile(self.root / 'Axx.exe', self.app / 'Axx.exe')
        self.assertEqual(verifier.verify_installed_files(self.app, self.build)['tauri_bundle_marker'],
                         'identical-release')

    def test_unrelated_exe_mutation_is_rejected(self):
        with (self.app / 'Axx.exe').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'outside the exact NSIS'):
            verifier.verify_installed_files(self.app, self.build)

    def test_bundle_manifest_identity_is_reported(self):
        self.add_bundle()
        result = verifier.verify_installed_files(self.app, self.build)
        self.assertEqual(result['backend_bundle'], {
            'layout': 'onedir', 'manifest_sha256': self.build['backend_bundle']['manifest_sha256'],
            'files_verified': 3,
        })

    def test_missing_tampered_and_extra_dll_are_rejected(self):
        self.add_bundle()
        dll = self.app / 'resources/_internal/python312.dll'
        dll.unlink()
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            verifier.verify_installed_files(self.app, self.build)
        dll.write_bytes(b'tampered DLL')
        with self.assertRaisesRegex(ValueError, 'hashes or byte counts differ'):
            verifier.verify_installed_files(self.app, self.build)
        dll.write_bytes(b'python DLL')
        (dll.parent / 'unexpected.dll').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            verifier.verify_installed_files(self.app, self.build)

    def test_onedir_cannot_fall_back_to_legacy_exe_proof(self):
        self.add_bundle()
        del self.build['backend_bundle']
        with self.assertRaisesRegex(RuntimeError, 'requires a complete bundle'):
            verifier.verify_installed_files(self.app, self.build)

    def test_traversal_manifest_is_rejected(self):
        self.add_bundle()
        self.build['backend_bundle'] = copy.deepcopy(self.build['backend_bundle'])
        self.build['backend_bundle']['files'][0]['path'] = '../outside.dll'
        with self.assertRaisesRegex(ValueError, 'namespace'):
            verifier.verify_installed_files(self.app, self.build)

    def test_isolated_python_cli_retains_sibling_import_and_bundle_check(self):
        self.add_bundle()
        build_path = self.root / 'build.json'
        output = self.root / 'verified.json'
        build_path.write_text(json.dumps(self.build), encoding='utf-8')
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--installed', str(self.app),
                                 '--build-result', str(build_path), '--output', str(output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text())['backend_bundle']['files_verified'], 3)


if __name__ == '__main__':
    unittest.main()
