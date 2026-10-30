"""Typed outcome unit checks use owned files/OOXML; never Excel or mission holdout."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from backend import goal_contract as goals
from backend.actions import office_workflows as office
from backend.actions.file_workflows import FileBundleTool, MANIFEST
from backend.actions.file_inspection import hash_file
from backend.tests.test_office_workflows import workbook_fixture


class GoalCriteriaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cancelled = threading.Event()

    def goal(self, *criteria, **changes):
        return goals.contract('Synthetic mission', {'intent': 'Synthetic mission', 'criteria': list(criteria), **changes})

    def criterion(self, kind='text_exact', id='deliverable', **parameters):
        return {'id': id, 'kind': kind, 'parameters': parameters or {'path': 'output.txt', 'text': 'exact'}}

    def evaluate(self, goal, **kwargs):
        return goals.evaluate_criteria(goal, self.root, self.cancelled, **kwargs)

    def csv_goal(self):
        (self.root / 'source.csv').write_text('Name;Amount\n001;2.5\n002;-0.25\n', encoding='utf8')
        return self.goal(self.criterion('xlsx_from_csv', source='source.csv', destination='result.xlsx', delimiter=';', numeric_column='Amount'))

    def test_legacy_checks_remain_unchanged_and_catalog_has_no_availability_claim(self):
        goal = goals.contract('Legacy', {'intent': 'Legacy', 'checks': [{'path': 'legacy.txt', 'text': 'old'}]})
        (self.root / 'legacy.txt').write_text('old')
        self.assertTrue(goals.verify(goal, self.root, self.cancelled)['passed'])
        self.assertEqual(goals.verify(goal, self.root, self.cancelled)['coverage'], 'artifact_content')
        catalog = goals.criteria_catalog()
        self.assertEqual({row['kind'] for row in catalog}, {'text_exact', 'xlsx_from_csv', 'file_bundle'})
        self.assertTrue(all('available' not in row for row in catalog))

    def test_schema_and_conflicting_outputs_are_rejected(self):
        valid = self.criterion()
        invalid = [valid | {'kind': 'invented'}, valid | {'kind': []}, valid | {'kind': {}}, valid | {'id': ''}, valid | {'extra': True},
            valid | {'parameters': {'path': '../escape', 'text': 'x'}},
            valid | {'parameters': {'path': 'C:\\escape.txt', 'text': 'x'}},
            valid | {'parameters': {'path': '.axx-quarantine/x', 'text': 'x'}}]
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ValueError): self.goal(row)
        with self.assertRaises(ValueError): self.goal(valid, valid)
        with self.assertRaises(ValueError): self.goal(*[valid | {'id': str(i)} for i in range(9)])
        with self.assertRaises(ValueError):
            self.goal(valid, self.criterion(id='conflict', path='OUTPUT.txt', text='different'))
        # A criterion's output can be a later criterion's input.
        self.goal(self.criterion(path='source.csv', text='Name,Amount\nA,2\n'),
            self.criterion('xlsx_from_csv', id='workbook', source='source.csv', destination='new.xlsx', delimiter=',', numeric_column='Amount'))
        with patch('backend.goal_criteria.artifact_path_error', side_effect=AssertionError('Schema inspected CWD')):
            self.goal(valid)
        with self.assertRaises(ValueError):
            self.goal(*[self.criterion(id='large-' + str(i), path=str(i) + '.txt', text='x'*7900) for i in range(3)])

    def test_text_missing_proposal_and_existing_wrong_output_never_overwrite(self):
        goal = self.goal(self.criterion())
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'OUTPUT_MISSING')
        proposed = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)
        self.assertEqual(proposed['step'], {'command_id': 'axx.artifact.write', 'inputs': {'path': 'output.txt', 'content': 'exact'}})
        self.assertEqual(proposed['input_versions'], [])
        self.assertFalse((self.root / 'output.txt').exists())
        (self.root / 'output.txt').write_text('wrong')
        self.assertEqual(self.evaluate(goal)[0]['status'], 'unsatisfied')
        with self.assertRaises(ValueError): goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)
        self.assertEqual((self.root / 'output.txt').read_text(), 'wrong')
        (self.root / 'output.txt').write_text('exact')
        report = goals.verify(goal, self.root, self.cancelled)
        self.assertTrue(report['passed']); self.assertEqual(report['coverage'], 'typed_outcomes')

    def test_xlsx_reopens_independently_and_rejects_wrong_total(self):
        goal = self.csv_goal()
        step = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)
        self.assertEqual(step['step']['command_id'], 'axx.office.excel.csv')
        self.assertEqual(step['step']['inputs']['source'], str(self.root / 'source.csv'))
        data = office.csv_data(step['step']['inputs'])
        workbook_fixture(self.root / 'result.xlsx', data)
        self.assertEqual(self.evaluate(goal)[0]['status'], 'satisfied')
        workbook_fixture(self.root / 'result.xlsx', data, wrong_total=True)
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'OUTPUT_MISMATCH')
        with self.assertRaises(ValueError): goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)

    def test_missing_or_ambiguous_csv_input_is_indeterminate(self):
        goal = self.csv_goal()
        (self.root / 'source.csv').write_text('Amount;Amount\n1;2\n')
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'INPUT_INVALID')
        with self.assertRaises(ValueError): goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)
        (self.root / 'source.csv').unlink()
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'INPUT_MISSING')

    def test_versions_detect_changed_bytes_and_same_bytes_replacement(self):
        goal = self.csv_goal()
        versions = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)['input_versions']
        self.assertTrue(versions)
        goals.assert_input_versions(versions, self.root, self.cancelled)
        path = self.root / 'source.csv'; original = path.read_bytes()
        path.write_bytes(original + b'003;1\n')
        with self.assertRaises(ValueError): goals.assert_input_versions(versions, self.root, self.cancelled)
        path.write_bytes(original)
        current = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)['input_versions']
        path.rename(self.root / 'previous.csv'); path.write_bytes(original)
        with self.assertRaises(ValueError): goals.assert_input_versions(current, self.root, self.cancelled)

    def test_bundle_manifest_cannot_redefine_expected_sources(self):
        (self.root / 'source.txt').write_text('original')
        goal = self.goal(self.criterion('file_bundle', paths=['source.txt'], destination='package', archive_name='data.zip'))
        proposed = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)
        tool = FileBundleTool()
        result = tool.execute_cancellable(proposed['step']['inputs'], self.root, self.cancelled)
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.evaluate(goal)[0]['status'], 'satisfied')
        manifest = self.root / 'package' / MANIFEST
        declared = json.loads(manifest.read_text())
        declared['files'][0]['source'] = str(self.root / 'package' / 'source.txt')
        manifest.write_text(json.dumps(declared))
        # Make the forged declaration internally consistent, including ZIP.
        # Trusting its own file list would pass the existing bundle verifier.
        with zipfile.ZipFile(self.root / 'package' / 'data.zip', 'w') as archive:
            archive.write(self.root / 'package' / 'source.txt', 'source.txt')
            archive.write(manifest, MANIFEST)
        from backend.actions.file_workflows import _verify_bundle
        _verify_bundle({'files': declared['files'], 'manifest': hash_file(str(manifest), self.cancelled),
            'archive': hash_file(str(self.root / 'package' / 'data.zip'), self.cancelled)}, self.cancelled)
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'OUTPUT_MISMATCH')

    def test_existing_bundle_must_obey_total_output_cap_including_metadata(self):
        (self.root / 'small.txt').write_bytes(b'x')
        goal = self.goal(self.criterion('file_bundle', paths=['small.txt'], destination='package', archive_name='data.zip'))
        proposed = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)
        self.assertTrue(FileBundleTool().execute_cancellable(proposed['step']['inputs'], self.root, self.cancelled).success)
        goal['criteria'][0]['parameters']['max_output_bytes'] = 64
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'OUTPUT_MISMATCH')

    @unittest.skipUnless(os.name == 'nt', 'Native source lease')
    def test_read_lease_respects_profile_cap_without_raising_compensation_default(self):
        from backend.actions.artifact_compensation import _kernel, _open
        source = self.root / 'larger.txt'; source.write_bytes(b'x' * (2 * 1024 * 1024))
        goal = self.goal(self.criterion('file_bundle', paths=['larger.txt'], destination='package'))
        versions = goals.propose_goal_step(goal, 'deliverable', self.root, self.cancelled)['input_versions']
        with goals.input_version_lease(versions, self.root, self.cancelled, max_file_bytes=3 * 1024 * 1024):
            with self.assertRaises(OSError): source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            with _open(_kernel(), source): pass

    def test_linked_paths_cancel_and_file_cap_abstain_before_hash(self):
        goal = self.csv_goal()
        with patch('backend.actions.file_inspection.hash_file', side_effect=AssertionError('Oversized input was read')):
            self.assertEqual(self.evaluate(goal, max_file_bytes=1)[0]['status'], 'indeterminate')
        self.cancelled.set()
        self.assertEqual(self.evaluate(goal)[0]['reason_code'], 'CANCELLED')
        self.cancelled.clear()
        self.assertFalse(goals.verify(goal, self.root, self.cancelled, max_file_bytes=1)['passed'])

    def test_linked_paths_are_rejected_without_following_them(self):
        self.csv_goal()
        link = self.root / 'linked'
        try: link.symlink_to(self.root, target_is_directory=True)
        except OSError: self.skipTest('Directory symlink unavailable for this fixture account')
        linked = self.goal(self.criterion('xlsx_from_csv', source='linked/source.csv', destination='linked/result.xlsx', delimiter=';', numeric_column='Amount'))
        self.assertEqual(self.evaluate(linked)[0]['reason_code'], 'PATH_UNSAFE')


if __name__ == '__main__': unittest.main()
