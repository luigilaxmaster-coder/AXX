import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from backend.actions.file_workflows import FileBundleTool, FindFilesTool, MANIFEST, find_files
from backend.actions import file_workflows


class FileWorkflowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.source = self.root / 'downloads'
        self.source.mkdir()
        self.paths = []
        for name, data in [('plano A.pdf', b'%PDF-fixture-a'), ('plano B.pdf', b'%PDF-fixture-b'), ('notas.txt', b'notes')]:
            path = self.source / name
            path.write_bytes(data)
            self.paths.append(str(path))
        self.inputs = {'paths': self.paths, 'destination': 'revision', 'archive_name': 'entrega.zip'}
        self.tool = FileBundleTool()

    def execute(self, inputs=None, cancelled=None):
        return self.tool.execute_cancellable(inputs or self.inputs, self.workspace, cancelled or threading.Event())

    def test_find_copy_zip_and_original_hashes(self):
        before = {raw: Path(raw).read_bytes() for raw in self.paths}
        discovery = find_files({'directory': str(self.source), 'pattern': '*.PDF'})
        self.assertEqual(len(discovery['files']), 2)
        self.assertEqual(discovery['paths'], [row['path'] for row in discovery['files']])
        self.assertFalse(discovery['truncated'])
        self.assertEqual(discovery['verification'], 'local_metadata_only')
        self.assertTrue(self.tool.verify_preconditions(self.inputs)[0])
        result = self.execute()
        self.assertTrue(result.success, result.error)
        self.assertTrue(self.tool.verify_postconditions(self.inputs, result)[0])
        folder = self.workspace / 'revision'
        manifest = json.loads((folder / MANIFEST).read_text('utf8'))
        self.assertEqual(len(manifest['files']), 3)
        with zipfile.ZipFile(folder / 'entrega.zip') as archive:
            self.assertEqual(set(archive.namelist()), {Path(raw).name for raw in self.paths} | {MANIFEST})
            for row in result.output['files']:
                self.assertEqual(hashlib.sha256(archive.read(row['name'])).hexdigest(), row['sha256'])
        self.assertEqual(before, {raw: Path(raw).read_bytes() for raw in self.paths})

    def test_existing_destination_never_overwrites(self):
        target = self.workspace / 'revision'
        target.mkdir()
        protected = target / 'plano A.pdf'
        protected.write_bytes(b'preserve user data')
        result = self.execute()
        self.assertFalse(result.success)
        self.assertEqual(protected.read_bytes(), b'preserve user data')
        self.assertFalse(result.evidence['partial_effect'])
        self.assertEqual(list(target.iterdir()), [protected])

    def test_cancel_before_dispatch_creates_nothing(self):
        event = threading.Event()
        event.set()
        result = self.execute(cancelled=event)
        self.assertFalse(result.success)
        self.assertTrue(result.evidence['cancelled'])
        self.assertFalse((self.workspace / 'revision').exists())
        self.assertFalse(result.evidence['effect_uncertain'])

    def test_cancel_after_first_copy_preserves_partial_output_and_never_repeats(self):
        event = threading.Event()
        original_copy = file_workflows._copy_file

        def first_copy(source, target, cancelled, created):
            result = original_copy(source, target, cancelled, created)
            event.set()
            return result

        with patch.object(file_workflows, '_copy_file', side_effect=first_copy):
            result = self.execute(cancelled=event)
        self.assertFalse(result.success)
        self.assertEqual(result.evidence['effect_status'], 'partial')
        self.assertEqual(result.evidence['dispatch_status'], 'delivered')
        self.assertTrue(result.evidence['effect_uncertain'])
        copied = self.workspace / 'revision' / Path(self.paths[0]).name
        self.assertEqual(copied.read_bytes(), Path(self.paths[0]).read_bytes())
        self.assertFalse(self.execute().success)
        self.assertEqual(len(list(copied.parent.iterdir())), 1)

    def test_postconditions_detect_copy_source_manifest_and_archive_tampering(self):
        for field in ('path', 'source', 'manifest', 'archive'):
            with self.subTest(field=field):
                inputs = {**self.inputs, 'destination': field}
                result = self.execute(inputs)
                self.assertTrue(result.success, result.error)
                raw = result.output[field]['path'] if field in ('manifest', 'archive') else result.output['files'][0][field]
                target = Path(raw)
                before = target.read_bytes()
                target.write_bytes(b'tampered')
                self.assertFalse(self.tool.verify_postconditions(inputs, result)[0])
                target.write_bytes(before)

    def test_traversal_absolute_destination_and_reserved_names_rejected(self):
        for destination in ('../outside', str(self.root / 'outside'), 'CON', 'folder:stream'):
            with self.subTest(destination=destination):
                result = self.execute({**self.inputs, 'destination': destination})
                self.assertFalse(result.success)
        for archive in ('../outside.zip', str(self.root / 'outside.zip'), 'NUL.zip', 'plain.txt'):
            with self.subTest(archive=archive):
                self.assertFalse(self.execute({**self.inputs, 'archive_name': archive}).success)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_case_insensitive_name_and_manifest_collisions_rejected(self):
        other = self.root / 'other'
        other.mkdir()
        collision = other / Path(self.paths[0]).name.upper()
        collision.write_bytes(b'other')
        self.assertFalse(self.execute({**self.inputs, 'paths': [self.paths[0], str(collision)]}).success)
        reserved = other / MANIFEST
        reserved.write_text('{}')
        self.assertFalse(self.execute({**self.inputs, 'paths': [str(reserved)]}).success)

    def test_reparse_source_and_target_are_rejected(self):
        original = file_workflows._check_path

        def reject_source(raw):
            if raw == str(self.workspace / 'revision'):
                raise ValueError('Artifact paths must not pass through symbolic links or reparse points')
            return original(raw)

        with patch.object(file_workflows, '_check_path', side_effect=reject_source):
            self.assertFalse(self.execute().success)
        with patch.object(file_workflows, 'validate_path', side_effect=ValueError('linked source')):
            self.assertFalse(self.execute().success)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_actual_link_is_excluded_from_search_and_rejected_by_copy(self):
        linked = self.source / 'external.pdf'
        try:
            os.symlink(self.paths[0], linked)
        except OSError as exc:
            self.skipTest('The OS account cannot create a symbolic-link fixture: ' + str(exc))
        result = find_files({'directory': str(self.source), 'pattern': '*.pdf'})
        self.assertEqual(len(result['files']), 2)
        self.assertEqual(result['skipped_unavailable_or_linked'], 1)
        self.assertFalse(self.execute({**self.inputs, 'paths': [str(linked)]}).success)

    def test_total_size_limit_rejects_before_any_creation(self):
        with patch.object(file_workflows, 'MAX_BYTES', 1):
            result = self.execute()
        self.assertFalse(result.success)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_output_budget_is_validated_before_creating_files(self):
        for maximum in (True, 0, -1, 1073741825, '1000'):
            with self.subTest(maximum=maximum):
                result = self.execute({**self.inputs, 'max_output_bytes': maximum})
                self.assertFalse(result.success)
        result = self.execute({**self.inputs, 'max_output_bytes': 1})
        self.assertFalse(result.success)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_output_budget_covers_copies_manifest_and_zip(self):
        maximum = 16384
        result = self.execute({**self.inputs, 'max_output_bytes': maximum})
        self.assertTrue(result.success, result.error)
        files = [path for path in (self.workspace / 'revision').iterdir() if path.is_file()]
        self.assertEqual(len(files), len(self.paths) + 2)
        self.assertLessEqual(sum(path.stat().st_size for path in files), maximum)
        self.assertTrue(self.tool.verify_postconditions(self.inputs, result)[0])

    def test_manifest_and_zip_failures_leave_bounded_partial_files(self):
        copied_bytes = sum(Path(raw).stat().st_size for raw in self.paths)
        result = self.execute({**self.inputs, 'max_output_bytes': copied_bytes})
        self.assertFalse(result.success)
        self.assertIn('manifiesto', result.error)
        self.assertTrue(result.evidence['partial_effect'])
        self.assertLessEqual(sum(path.stat().st_size for path in (self.workspace / 'revision').iterdir()), copied_bytes)

        reference = self.execute({**self.inputs, 'destination': 'reference', 'archive_name': None})
        self.assertTrue(reference.success, reference.error)
        occupied = sum(row['bytes'] for row in reference.output['files']) + reference.output['manifest']['bytes']
        # A few bytes admit a ZIP header but cannot admit its contents and central directory.
        maximum = occupied + 64
        result = self.execute({**self.inputs, 'destination': 'zipbudget', 'max_output_bytes': maximum})
        self.assertFalse(result.success, result)
        self.assertIn('ZIP', result.error)
        partial = self.workspace / 'zipbudget'
        self.assertTrue((partial / 'entrega.zip').exists())
        self.assertLessEqual(sum(path.stat().st_size for path in partial.iterdir()), maximum)

    def test_source_growth_after_admission_cannot_exceed_output_budget(self):
        maximum = 4096
        original = file_workflows._copy_file

        def grow_before_copy(source, target, cancelled, created, **kwargs):
            source.write_bytes(b'x' * (maximum + 1))
            return original(source, target, cancelled, created, **kwargs)

        with patch.object(file_workflows, '_copy_file', side_effect=grow_before_copy):
            result = self.execute({**self.inputs, 'max_output_bytes': maximum})
        self.assertFalse(result.success)
        self.assertIn('presupuesto', result.error)
        partial = self.workspace / 'revision'
        self.assertLessEqual(sum(path.stat().st_size for path in partial.iterdir()), maximum)

    def test_find_is_bounded_and_does_not_recurse_by_default(self):
        nested = self.source / 'nested'
        nested.mkdir()
        (nested / 'hidden.pdf').write_bytes(b'nested')
        first = find_files({'directory': str(self.source), 'limit': 1})
        self.assertEqual(len(first['files']), 1)
        self.assertTrue(first['truncated'])
        self.assertEqual(len(find_files({'directory': str(self.source)})['files']), 3)
        self.assertEqual(len(find_files({'directory': str(self.source), 'recursive': True})['files']), 4)
        with patch.object(file_workflows, 'MAX_ENTRIES', 1):
            bounded = find_files({'directory': str(self.source), 'pattern': '*.absent'})
        self.assertTrue(bounded['truncated'])
        self.assertLessEqual(bounded['inspected_entries'], 1)

    def test_find_invalid_bounds_and_cancellation(self):
        for fields in ({'limit': 0}, {'limit': True}, {'limit': 101}, {'recursive': 'yes'}, {'pattern': '../*.pdf'},
                       {'max_entries_scan':0}, {'max_entries_scan':True}, {'max_entries_scan':10001}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                find_files({'directory': str(self.source), **fields})
        event = threading.Event()
        event.set()
        tool = FindFilesTool()
        result = tool.execute_cancellable({'directory': str(self.source)}, self.workspace, event)
        self.assertFalse(result.success)
        self.assertFalse(tool.verify_postconditions({}, result)[0])

    def test_explicit_scan_budget_limits_actual_entries_not_just_results(self):
        for number in range(12): (self.source / ('scan-' + str(number) + '.txt')).write_text('test')
        result = find_files({'directory':str(self.source),'pattern':'*.absent','limit':100,'max_entries_scan':1})
        self.assertEqual(result['inspected_entries'],1)
        self.assertEqual(result['files'],[])
        self.assertTrue(result['truncated'])

    def test_source_growth_or_replacement_during_copy_is_not_success(self):
        original = file_workflows._copy_file

        def change_after_copy(source, target, cancelled, created):
            result = original(source, target, cancelled, created)
            source.write_bytes(b'changed source')
            return result

        with patch.object(file_workflows, '_copy_file', side_effect=change_after_copy):
            result = self.execute()
        self.assertFalse(result.success)
        self.assertTrue(result.evidence['partial_effect'])
        self.assertIn('hash', result.error)


if __name__ == '__main__':
    unittest.main()
