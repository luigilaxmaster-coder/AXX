"""Application compatibility uses real temporary bytes; no application is launched."""
from pathlib import Path
import copy
from contextvars import copy_context
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from backend.actions.file_inspection import hash_file
from backend.memory.procedural_memory import get_action_env_fingerprint


class ApplicationVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binary = Path(self.temp.name) / 'blender.exe'
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_A')
        self.enterContext(patch.dict(os.environ, {'ProgramFiles': self.temp.name}))
        from backend.actions.cli_blender import find_blender
        self.original_finder = find_blender
        self.discovery = patch('backend.actions.cli_blender.find_blender', return_value=self.binary)
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        self.enterContext(patch('backend.actions.blender_scene.find_blender', return_value=self.binary))

    def test_binary_update_invalidates_only_its_application_commands(self):
        app = get_action_env_fingerprint(['axx.blender.scene.render'])
        writer = get_action_env_fingerprint(['axx.artifact.write'])
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_B')
        self.assertNotEqual(get_action_env_fingerprint(['axx.blender.scene.render']), app)
        self.assertEqual(get_action_env_fingerprint(['axx.artifact.write']), writer)

    def test_historical_receipt_is_not_relabelled_with_current_binary(self):
        recorded = hash_file(str(self.binary), threading.Event())
        original = get_action_env_fingerprint(['axx.blender.scene.render'])
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_B')
        historical = get_action_env_fingerprint(['axx.blender.scene.render'], application_receipts={'blender': recorded})
        self.assertEqual(historical, original)
        self.assertNotEqual(historical, get_action_env_fingerprint(['axx.blender.scene.render']))
        with self.assertRaises(ValueError):
            get_action_env_fingerprint(['axx.blender.scene.render'], application_receipts={})

    def test_unknown_application_version_abstains(self):
        with patch('backend.actions.cli_blender.find_blender', side_effect=RuntimeError('Synthetic missing application')):
            with self.assertRaises(ValueError):
                get_action_env_fingerprint(['axx.blender.scene.render'])

    @unittest.skipUnless(os.name == 'nt', 'Requires Windows file custody; no application launch')
    def test_snapshot_is_reused_only_while_binary_is_locked(self):
        from backend.actions.cli_blender import blender_version_lease
        with patch('backend.actions.file_inspection.hash_file', wraps=hash_file) as hashing:
            with blender_version_lease():
                first = get_action_env_fingerprint(['axx.blender.scene.render'])
                self.assertEqual(first, get_action_env_fingerprint(['axx.blender.scene.render']))
                self.assertEqual(hashing.call_count, 1)
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_B')
        self.assertNotEqual(first, get_action_env_fingerprint(['axx.blender.scene.render']))

    @unittest.skipUnless(os.name == 'nt', 'Requires Windows file custody; no application launch')
    def test_copied_context_cannot_reuse_a_released_binary_snapshot(self):
        from backend.actions.cli_blender import blender_version_lease
        with blender_version_lease():
            original = get_action_env_fingerprint(['axx.blender.scene.render'])
            copied = copy_context()
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_B')
        self.assertNotEqual(copied.run(get_action_env_fingerprint, ['axx.blender.scene.render']), original)

    @unittest.skipUnless(os.name == 'nt', 'Requires Windows file custody; no application launch')
    def test_copied_context_holds_its_own_custody_after_parent_exits(self):
        from backend.actions.cli_blender import blender_version_lease
        ready, release = threading.Event(), threading.Event()
        failures = []
        def child():
            try:
                with blender_version_lease():
                    ready.set()
                    if not release.wait(5): raise AssertionError('Synthetic lease timeout')
            except BaseException as exc:
                failures.append(exc); ready.set()
        worker = None
        try:
            with blender_version_lease():
                copied = copy_context()
                worker = threading.Thread(target=copied.run, args=(child,))
                worker.start()
                self.assertTrue(ready.wait(3))
                self.assertEqual(failures, [])
            with self.assertRaises(OSError):
                self.binary.write_bytes(b'FORBIDDEN_UPDATE_DURING_CHILD_CUSTODY')
        finally:
            release.set()
            if worker: worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])

    @unittest.skipUnless(os.name == 'nt', 'Requires Windows file custody; no application launch')
    def test_journal_proof_selective_revalidation_and_approved_binary_custody(self):
        from backend.actions.executor import ActionExecutor
        from backend.commands import CommandService
        from backend.action_learning import ActionLearning
        from backend.actions import cli_blender
        executor = ActionExecutor(Path(self.temp.name) / 'state.db', Path(self.temp.name) / 'artifacts')
        self.addCleanup(executor.close)
        commands = CommandService(executor)
        self.addCleanup(commands.close)
        model = Mock()
        model.route.side_effect = AssertionError('Application revalidation must not invoke a model')
        learning = ActionLearning(commands, model)
        self.addCleanup(learning.close)
        source = executor.workspace_root / 'source.blend'
        source.write_bytes(b'SYNTHETIC_BLEND_SOURCE')
        inputs = {'source': str(source), 'destination': '{{destination}}', 'scene': 'Scene',
            'camera': 'Camera', 'object': 'Cube', 'position': [0, 0, 0], 'width': 64, 'height': 64}
        skill = learning.skills.insert({'id': 'application.blender', 'version': 1, 'title': 'Application fixture',
            'trigger': 'application.blender', 'schema': {'type': 'object', 'properties': {'destination': {'type': 'string'}}, 'required': ['destination']},
            'templates': [{'command_id': 'axx.blender.scene.render', 'inputs': inputs}], 'examples': [],
            'project_id': '', 'favorite': False, 'checks': ['executor_postconditions'],
            'environment': get_action_env_fingerprint(['axx.blender.scene.render']), 'executable': True, 'created_at': 1})
        self.assertFalse(skill['effect_verified'])
        self.assertFalse(skill['environment_matches'])
        initial = hash_file(str(self.binary), threading.Event())
        def simulated_effect(*args, **kwargs):
            binary = hash_file(str(self.binary), threading.Event())
            return {'state': 'succeeded', 'postconditions_passed': True, 'output': {'simulated': True},
                'evidence': {'verification': 'synthetic_effect_only', 'application_binary': binary}, 'duration_ms': 0}
        unproven = commands.prepare('axx.blender.scene.render', inputs | {'destination': 'unproven'}, conversation_id='task-a')
        missing = simulated_effect()
        missing['evidence'].pop('application_binary')
        with patch.object(executor, 'execute_action', return_value=missing):
            no_proof = commands.execute(unproven['operation_id'], approved=True)
        forged_missing = copy.deepcopy(no_proof)
        forged_missing['evidence']['application_binary'] = initial
        learning.skills.record(skill['id'], 1, no_proof['operation_id'], {'effect_verified': True, 'results': [forged_missing],
            'inputs': {'destination': 'unproven'}, 'task_id': 'task-a', 'observed_applications': {'blender': initial}})
        self.assertFalse(learning.skills.get(skill['id'])['environment_matches'])
        prepared = commands.prepare('axx.blender.scene.render', inputs | {'destination': 'initial'}, conversation_id='task-a')
        with patch.object(executor, 'execute_action', side_effect=simulated_effect):
            receipt = commands.execute(prepared['operation_id'], approved=True)
        forged = copy.deepcopy(receipt)
        forged['evidence']['application_binary']['sha256'] = '0' * 64
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_B')
        learning.skills.record(skill['id'], 1, receipt['operation_id'], {'effect_verified': True, 'results': [forged],
            'inputs': {'destination': 'initial'}, 'task_id': 'task-a', 'revalidation': True,
            'observed_applications': {'blender': forged['evidence']['application_binary']}})
        self.assertFalse(learning.skills.get(skill['id'])['environment_matches'])
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_A')
        health = learning.skills.get(skill['id'])
        self.assertTrue(health['environment_matches'])
        self.assertEqual(health['compatibility']['applications']['blender'], initial)
        old = learning.propose(skill['id'], inputs={'destination': 'old-plan'}, conversation_id='task-a')
        self.assertEqual(old['state'], 'awaiting_approval')
        unrelated = get_action_env_fingerprint(['axx.artifact.write'])
        self.binary.write_bytes(b'SYNTHETIC_EXECUTABLE_VERSION_B')
        self.assertFalse(learning.skills.get(skill['id'])['environment_matches'])
        trial = learning.prepare_revalidation(skill['id'], 1, {'destination': 'trial'}, conversation_id='task-a')
        finder = self.original_finder
        def guarded_effect(*args, **kwargs):
            # The unpatched finder reads the dispatch binding instead of rediscovering another version.
            self.assertEqual(finder(), self.binary)
            with self.assertRaises(OSError):
                self.binary.write_bytes(b'FORBIDDEN_UPDATE_DURING_DISPATCH')
            return simulated_effect(*args, **kwargs)
        with patch.object(executor, 'execute_action', side_effect=guarded_effect):
            completed = learning.execute(trial['operation_id'], approved=True)
        self.assertTrue(completed['revalidation_completed'], completed)
        self.assertIsNone(cli_blender._selected_binary.get())
        self.assertTrue(learning.skills.get(skill['id'])['environment_matches'])
        self.assertEqual(get_action_env_fingerprint(['axx.artifact.write']), unrelated)
        with self.assertRaises(ValueError):
            learning.execute(old['operation_id'], approved=True)
        model.route.assert_not_called()


if __name__ == '__main__':
    unittest.main()
