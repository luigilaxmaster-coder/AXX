"""Sealed synthetic ZIP holdouts, frozen before producer evaluation.

The identical versioned fixture keeps CI reproducible. Execution uses only real
disposable files and commands, without a model, network, or native input API.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.actions import file_workflows
from backend.commands import CommandService


REPOSITORY = Path(__file__).resolve().parents[2]
VERSIONED_FIXTURE = REPOSITORY / 'backend/tests/fixtures/goal-progress-holdout.json'
FIXTURE = (VERSIONED_FIXTURE if VERSIONED_FIXTURE.is_file() else
           REPOSITORY / 'build/source-context-destinations/goal-holdout/file-bundle-cases.json')
FIXTURE_SHA256 = '2188acd937e26d2d98bb9a9cb7116a200238824ab3aab56b8703d23dd15d082f'
MANIFEST = 'axx-manifest.json'


class NoModel:
    config = {'allow_paid': False}

    def route(self, request, **kwargs):
        raise AssertionError('A holdout must use the deterministic producer, never a model')


class GoalProgressZipHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
            raise AssertionError('Private ZIP holdout fixture seal changed')
        cls.cases = json.loads(raw)['cases']

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoModel())
        self.commands.learning = self.learning
        self.workspace = self.executor.workspace_root

    def tearDown(self):
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def prepare(self, case, suffix='', source_count=2):
        steps = [{'command_id': 'axx.artifact.write', 'inputs': {
            'path': row['path'], 'content': row['text']}} for row in case['sources'][:source_count]]
        goal = {'intent': case['intent'], 'criteria': [{'id': case['criterion_id'], 'kind': 'file_bundle',
            'parameters': {'paths': [row['path'] for row in case['sources']], 'destination': case['destination'],
                           'archive_name': case['archive_name'], 'max_output_bytes': 65536}}]}
        return self.learning.prepare_steps(case['intent'], steps, case['mission_id'] + suffix,
            project_id='sealed-zip-holdout', conversation_id='sealed-zip-holdout', goal_spec=goal)

    def execute(self, plan):
        return self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])

    def pending(self, case=None, prior_charge=False):
        case = case or self.cases[0]
        plan = self.prepare(case)
        if prior_charge:
            request_id = case['mission_id'] + '-prior-synthetic-charge'
            self.learning._reserve_model_call(plan, request_id, 'plan')
            self.learning._settle_model_call(plan, request_id, {'ok': True, 'route': {
                'upstream_attempted': True, 'upstream_attempts': 1, 'attempt_budget_used': 1}})
            self.learning._save(plan)
            self.assertEqual(plan['model_calls_used'], 1)
        done = self.execute(plan)
        self.assertEqual(done['state'], 'goal_pending')
        self.assertFalse(done['mission']['completed'])
        self.assertEqual(len(done['step_records']), 2)
        self.assertTrue(all(row['state'] == 'succeeded' and row['result']['postconditions_passed']
                            for row in done['step_records']))
        progress = done['goal_progress']
        self.assertEqual(progress['status'], 'ready')
        self.assertEqual(progress['criterion_id'], case['criterion_id'])
        self.assertEqual(progress['prefix_length'], 2)
        self.assertEqual(progress['source_plan_hash'], done['plan_hash'])
        self.assertTrue(progress['input_versions'])
        self.assertEqual(progress['step']['command_id'], 'axx.file.bundle')
        self.assertEqual(set(progress['step']['inputs']['paths']),
                         {str(self.workspace / row['path']) for row in case['sources']})
        self.assertFalse((self.workspace / case['destination']).exists())
        self.assert_sources(case)
        return done

    def continue_goal(self, done):
        progress = done['goal_progress']
        return self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'],
            criterion_id=progress['criterion_id'], candidate_hash=progress['fingerprint'])

    @staticmethod
    def budget(plan):
        return {field: plan.get(field) for field in ('model_call_limit', 'model_calls_used', 'model_calls_confirmed',
            'model_calls_reserved', 'model_calls_uncertain', 'route_requests')}

    def assert_sources(self, case):
        snapshot = {}
        for row in case['sources']:
            source = self.workspace / row['path']
            self.assertEqual(source.read_bytes(), row['text'].encode('utf8'))
            snapshot[row['path']] = (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns)
        return snapshot

    def assert_bundle(self, case):
        directory = self.workspace / case['destination']
        expected = {Path(row['path']).name: row for row in case['sources']}
        self.assertEqual({path.name for path in directory.iterdir()}, set(expected) | {MANIFEST, case['archive_name']})
        manifest_bytes = (directory / MANIFEST).read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual(len(manifest['files']), len(expected))
        self.assertEqual({row['name'] for row in manifest['files']}, set(expected))
        for entry in manifest['files']:
            source = expected[entry['name']]
            content = source['text'].encode('utf8')
            self.assertEqual(Path(entry['source']).resolve(), (self.workspace / source['path']).resolve())
            self.assertEqual(Path(entry['path']).resolve(), (directory / entry['name']).resolve())
            self.assertEqual(entry['sha256'], hashlib.sha256(content).hexdigest())
            self.assertEqual(entry['bytes'], len(content))
            self.assertEqual((directory / entry['name']).read_bytes(), content)
        with zipfile.ZipFile(directory / case['archive_name']) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()), len(expected) + 1)
            self.assertEqual(set(archive.namelist()), set(expected) | {MANIFEST})
            self.assertEqual(archive.read(MANIFEST), manifest_bytes)
            for name, source in expected.items():
                self.assertEqual(archive.read(name), source['text'].encode('utf8'))
        self.assert_sources(case)

    def test_two_unseen_missions_append_zip_without_replaying_or_resetting(self):
        pending = [(case, copy.deepcopy(self.pending(case, prior_charge=index == 0)))
                   for index, case in enumerate(self.cases)]
        original_sources = [self.assert_sources(case) for case in self.cases]
        self.assertEqual(len(self.executor.list_operations()), 4)
        for case, done in reversed(pending):
            with self.subTest(mission=case['mission_id']):
                prefix = copy.deepcopy(done['step_records'])
                budget = self.budget(done)
                prepared = self.continue_goal(done)
                self.assertEqual(prepared['operation_id'], done['operation_id'])
                self.assertEqual(prepared['goal_spec'], done['goal_spec'])
                self.assertEqual(prepared['goal_revision'], done['goal_revision'])
                self.assertEqual(prepared['steps'][:2], done['steps'])
                self.assertEqual(prepared['step_records'][:2], prefix)
                self.assertEqual(len(prepared['steps']), 3)
                self.assertEqual(prepared['steps'][-1]['command_id'], 'axx.file.bundle')
                self.assertEqual(self.budget(prepared), budget)
                self.assertNotEqual(prepared['plan_hash'], done['plan_hash'])
                self.assertIsNone(prepared.get('approved_hash'))
                self.assertFalse((self.workspace / case['destination']).exists())
                with self.assertRaises(ValueError):
                    self.execute(done)
                final = self.execute(prepared)
                self.assertEqual(final['state'], 'succeeded')
                self.assertTrue(final['mission']['completed'])
                self.assertEqual(final['step_records'][:2], prefix)
                self.assertEqual(self.budget(final), budget)
                self.assert_bundle(case)
                operations = len(self.executor.list_operations())
                self.assertEqual(self.execute(final)['state'], 'succeeded')
                with self.assertRaises(ValueError):
                    self.learning.prepare_goal_progress(final['operation_id'], final['plan_hash'])
                self.assertEqual(len(self.executor.list_operations()), operations)
        self.assertEqual(len(self.executor.list_operations()), 6)
        self.assertEqual([self.assert_sources(case) for case in self.cases], original_sources)

    def test_missing_input_abstains_without_inventing_or_dispatching(self):
        case = self.cases[0]
        done = self.execute(self.prepare(case, source_count=1))
        self.assertEqual(done['state'], 'goal_pending')
        self.assertEqual(done['goal_progress']['status'], 'needs_input')
        with self.assertRaises(ValueError):
            self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.workspace / case['sources'][1]['path']).exists())
        self.assertFalse((self.workspace / case['destination']).exists())

    def test_dependency_waits_then_reuses_receipts_and_stops_at_goal(self):
        case = self.cases[0]
        source = case['sources'][1]
        upstream = self.learning.prepare_steps('Crear entrada independiente', [{'command_id': 'axx.artifact.write',
            'inputs': {'path': source['path'], 'content': source['text']}}], case['mission_id'] + '-upstream',
            project_id='sealed-zip-holdout')
        target = self.prepare(case, source_count=1)
        target = self.learning.link_dependencies(target['operation_id'], [upstream['operation_id']], target['plan_hash'])
        waiting = self.execute(target)
        self.assertEqual(waiting['state'], 'waiting_dependency')
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.learning.retry_dependencies(), [])
        parent = self.execute(upstream)
        parent_receipt = copy.deepcopy(parent['step_records'])
        resumed = self.learning.retry_dependencies()
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0]['operation_id'], target['operation_id'])
        self.assertEqual(resumed[0]['state'], 'goal_pending')
        self.assertEqual(len(self.executor.list_operations()), 2)
        prepared = self.continue_goal(resumed[0])
        final = self.execute(prepared)
        self.assertTrue(final['mission']['completed'])
        self.assert_bundle(case)
        self.assertEqual(self.learning.get(parent['operation_id'])['step_records'], parent_receipt)
        self.assertEqual(self.learning.retry_dependencies(), [])
        self.assertEqual(len(self.executor.list_operations()), 3)

    def test_changed_source_rejects_candidate_and_approved_suffix_before_effect(self):
        case = self.cases[0]
        done = copy.deepcopy(self.pending(case))
        source = self.workspace / case['sources'][0]['path']
        source.write_bytes(b'changed before continuation\n')
        with self.assertRaises(ValueError):
            self.continue_goal(done)
        self.assertEqual(len(self.executor.list_operations()), 2)
        case = self.cases[1]
        done = copy.deepcopy(self.pending(case))
        prepared = self.continue_goal(done)
        source = self.workspace / case['sources'][0]['path']
        source.write_bytes(b'changed after reviewed continuation\n')
        try:
            result = self.execute(prepared)
        except ValueError:
            result = self.learning.get(prepared['operation_id'])
        self.assertFalse(result['mission']['completed'])
        self.assertFalse((self.workspace / case['destination']).exists())
        self.assertEqual(len(self.executor.list_operations()), 4)

    def test_revoked_producer_pause_and_cancel_cannot_extend_authority(self):
        for control in ('revoke', 'pause', 'cancel'):
            with self.subTest(control=control):
                case = copy.deepcopy(self.cases[0])
                case['mission_id'] += '-' + control
                case['destination'] += '-' + control
                case['sources'] = [dict(row, path=control + '/' + row['path']) for row in case['sources']]
                done = copy.deepcopy(self.pending(case))
                count = len(self.executor.list_operations())
                if control == 'revoke':
                    self.commands.commands['axx.file.bundle']['execution_enabled'] = False
                elif control == 'pause':
                    self.assertTrue(self.learning.pause(done['operation_id'])['pause_requested'])
                else:
                    self.assertEqual(self.learning.cancel(done['operation_id'])['state'], 'cancelled')
                try:
                    with self.assertRaises(ValueError):
                        self.continue_goal(done)
                finally:
                    self.commands.commands['axx.file.bundle']['execution_enabled'] = True
                self.assertEqual(len(self.executor.list_operations()), count)
                self.assertFalse((self.workspace / case['destination']).exists())
                self.assert_sources(case)

    def test_real_partial_copy_uncertain_receipt_is_never_replayed(self):
        case = self.cases[0]
        done = copy.deepcopy(self.pending(case))
        prepared = self.continue_goal(done)
        copy_file = file_workflows._copy_file

        def interrupt_after_copy(*args, **kwargs):
            copy_file(*args, **kwargs)
            raise OSError('Synthetic interruption after a real completed copy')

        with patch.object(file_workflows, '_copy_file', side_effect=interrupt_after_copy) as interrupted:
            uncertain = self.execute(prepared)
            self.assertEqual(interrupted.call_count, 1)
            self.assertEqual(uncertain['state'], 'unknown')
            receipt = uncertain['step_records'][-1]['result']
            self.assertEqual(receipt['state'], 'unknown')
            self.assertTrue(receipt['evidence']['effect_uncertain'])
            self.assertFalse(uncertain['mission']['completed'])
            partial = self.workspace / case['destination']
            self.assertEqual({row.name for row in partial.iterdir()}, {Path(case['sources'][0]['path']).name})
            self.assertEqual((partial / Path(case['sources'][0]['path']).name).read_bytes(),
                             case['sources'][0]['text'].encode('utf8'))
            operations = len(self.executor.list_operations())
            with self.assertRaises(ValueError):
                self.learning.prepare_goal_progress(uncertain['operation_id'], uncertain['plan_hash'])
            self.assertEqual(self.learning.resume(uncertain['operation_id'])['state'], 'unknown')
            self.assertEqual(self.execute(uncertain)['state'], 'unknown')
            self.assertEqual(interrupted.call_count, 1)
            self.assertEqual(len(self.executor.list_operations()), operations)
        self.assert_sources(case)


if __name__ == '__main__':
    unittest.main()
