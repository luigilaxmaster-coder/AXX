"""Controlled archive tests: imports metadata, never recipe programs or commands."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

try:
    importer = importlib.import_module('scripts.import_command_library')
except ModuleNotFoundError:
    importer = None


def voice_row(recipe_id='AXX-TEST-0001', group='PRINCIPAL_REVISADO'):
    return {
        'recipe_id': recipe_id, 'title': 'Preparar una muestra',
        'catalog_group': group, 'status': 'DOCUMENTED_NOT_EXECUTED',
        'execution_enabled': False, 'voice_runtime_verified': False,
        'coverage_status': 'MAPPED_TEMPLATE_PENDING_REVIEW',
        'source_sha256': 'a' * 64,
        'voice_intent': {'phrases': ['Axx, prepara una muestra']},
        'blockers': ['No adapter validated in Axx'],
    }


class ImportCommandLibraryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importer, 'The validated metadata importer is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, rows=None, recipes=None, extra=None, manifest_changes=None):
        rows = rows if rows is not None else [voice_row()]
        recipes = recipes if recipes is not None else [{
            'id': 'AXX-TEST-0001', 'title': 'Preparar una muestra',
            'category': 'Muestras', 'objective': 'Preparar datos locales.',
            'status': 'DOCUMENTED_NOT_EXECUTED', 'execution_enabled': False,
            'commands': [{'executable': 'DO_NOT_RUN', 'argv': ['untrusted']}],
        }]
        members = {
            'VOICE_MAP_ACUMULADO.jsonl': ''.join(json.dumps(r) + '\n' for r in rows).encode(),
            'recipes.jsonl': ''.join(json.dumps(r) + '\n' for r in recipes).encode(),
        }
        members.update(extra or {})
        manifest = {
            'batch': 'test', 'execution_enabled': False,
            'counts': {'recipes': len(recipes)},
            'reviewed_total': sum(r['catalog_group'] == 'PRINCIPAL_REVISADO' for r in rows),
            'legacy_uncertified': sum(r['catalog_group'] == 'HEREDADO_SIN_CERTIFICAR' for r in rows),
            'nominal_inventory_total': sum(r['catalog_group'] != 'SUPLEMENTO_EXCLUIDO' for r in rows),
            'comparison_unique_ids': len(rows),
            'files': [{'file': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                      for name, content in members.items()],
        }
        manifest.update(manifest_changes or {})
        members['manifest.json'] = json.dumps(manifest).encode()
        archive = self.root / 'source.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
            for name, content in members.items():
                target.writestr(name, content)
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def load(self, archive_and_hash):
        archive, digest = archive_and_hash
        return importer.build_catalog(archive, expected_sha256=digest)

    def test_imports_documentation_and_separates_principal_from_supplement(self):
        rows = [voice_row(), voice_row('AXX-TEST-0002', 'HEREDADO_SIN_CERTIFICAR'),
                voice_row('AXX-TEST-0003', 'SUPLEMENTO_EXCLUIDO')]
        catalog, provenance = self.load(self.archive(rows=rows))
        self.assertEqual(catalog['counts'], {'total': 3, 'principal': 2, 'supplements': 1,
                         'reviewed': 1, 'legacy': 1, 'full_recipes': 1, 'enabled': 0, 'verified': 0})
        command = catalog['commands'][0]
        self.assertEqual(command['id'], 'AXX-TEST-0001')
        self.assertEqual(command['category'], 'Muestras')
        self.assertEqual(command['voice_phrases'], ['Axx, prepara una muestra'])
        self.assertFalse(command['execution_enabled'])
        self.assertTrue(command['has_recipe_details'])
        self.assertEqual(provenance['counts'], catalog['counts'])

    def test_rejects_unexpected_archive_digest(self):
        archive, _ = self.archive()
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            importer.build_catalog(archive, expected_sha256='0' * 64)

    def test_rejects_duplicate_catalog_ids(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate.*ID'):
            self.load(self.archive(rows=[voice_row(), voice_row()]))

    def test_rejects_duplicate_recipe_ids(self):
        recipe = {'id': 'AXX-TEST-0001', 'title': 'Preparar una muestra',
                  'execution_enabled': False, 'status': 'DOCUMENTED_NOT_EXECUTED'}
        with self.assertRaisesRegex(ValueError, 'Duplicate.*ID'):
            self.load(self.archive(recipes=[recipe, recipe]))

    def test_rejects_conflicting_catalog_and_recipe_identity(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.load(self.archive(recipes=[{'id': 'AXX-TEST-0001', 'title': 'Different action',
                       'execution_enabled': False, 'status': 'DOCUMENTED_NOT_EXECUTED'}]))

    def test_rejects_zip_slip_even_for_unused_members(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe.*member'):
            self.load(self.archive(extra={'../escape.py': b'raise RuntimeError()'}))
        self.assertFalse((self.root.parent / 'escape.py').exists())

    def test_rejects_windows_path_members(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe.*member'):
            self.load(self.archive(extra={'C:\\outside.py': b'pass'}))

    def test_never_executes_or_exports_code_from_archive(self):
        marker = self.root / 'executed'
        code = f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"
        catalog, _ = self.load(self.archive(extra={'run_me.py': code.encode()}))
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / 'run_me.py').exists())
        self.assertNotIn('commands', catalog['commands'][0])
        self.assertNotIn('argv', json.dumps(catalog))

    def test_rejects_enabled_recipe_or_voice_source(self):
        row = voice_row()
        row['execution_enabled'] = True
        with self.assertRaisesRegex(ValueError, 'execution_enabled'):
            self.load(self.archive(rows=[row]))

    def test_rejects_nested_enabled_contract(self):
        row = voice_row()
        row['voice_contract'] = {'execution_enabled': True}
        with self.assertRaisesRegex(ValueError, 'execution_enabled'):
            self.load(self.archive(rows=[row]))

    def test_rejects_inconsistent_inventory_claims(self):
        with self.assertRaisesRegex(ValueError, 'count'):
            self.load(self.archive(manifest_changes={'nominal_inventory_total': 999}))

    def test_rejects_member_hash_mismatch(self):
        archive, _ = self.archive()
        with zipfile.ZipFile(archive) as source:
            members = {entry.filename: source.read(entry.filename) for entry in source.infolist()}
        members['recipes.jsonl'] += b'\n'
        with zipfile.ZipFile(archive, 'w') as target:
            for name, content in members.items():
                target.writestr(name, content)
        with self.assertRaisesRegex(ValueError, 'member.*(hash|size)'):
            self.load((archive, hashlib.sha256(archive.read_bytes()).hexdigest()))

    def test_rejects_duplicate_json_keys(self):
        archive, _ = self.archive()
        with zipfile.ZipFile(archive) as source:
            members = {entry.filename: source.read(entry.filename) for entry in source.infolist()}
        members['manifest.json'] = b'{"execution_enabled":false,"execution_enabled":true}'
        with zipfile.ZipFile(archive, 'w') as target:
            for name, content in members.items():
                target.writestr(name, content)
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            self.load((archive, hashlib.sha256(archive.read_bytes()).hexdigest()))

    def test_metadata_strings_are_bounded(self):
        row = voice_row()
        row['voice_intent']['phrases'] = ['z' * 2000]
        catalog, _ = self.load(self.archive(rows=[row]))
        self.assertLessEqual(len(catalog['commands'][0]['voice_phrases'][0]), 256)

    def test_preserves_documented_voice_contract_invocations_without_enabling(self):
        row = voice_row()
        row.pop('voice_intent')
        row['voice_contract'] = {'invocations': ['Axx, prepara archivo de prueba'],
                                 'execution_enabled': False}
        catalog, _ = self.load(self.archive(rows=[row]))
        command = catalog['commands'][0]
        self.assertEqual(command['voice_phrases'], ['Axx, prepara archivo de prueba'])
        self.assertFalse(command['execution_enabled'])
        self.assertFalse(command['voice_runtime_verified'])


if __name__ == '__main__':
    unittest.main()
