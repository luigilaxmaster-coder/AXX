"""Planning privacy checks use temporary SQLite, real files and an offline model."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import get_action_env_fingerprint
from backend.memory.skill_memory import validate_schema


class LocalModel:
    def __init__(self):
        self.calls = []
        self.answer = {'needs_input': 'Indica un objetivo explícito.'}
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False

    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        self.entered.set()
        if self.block and not self.release.wait(10):
            raise RuntimeError('The local test did not release the model')
        return {'ok': True, 'message': {'content': json.dumps(self.answer)},
                'route': {'provider_name': 'offline-fixture', 'model': 'fixture'}}


class PlanningContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = LocalModel()
        self.learning = ActionLearning(self.commands, self.model)
        self.file = self.executor.workspace_root / 'synthetic-source.txt'
        self.file.write_text('Synthetic local fixture.', encoding='utf-8')

    def tearDown(self):
        self.model.release.set()
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def payload(self, context, *, task='task-b', text='context reference'):
        messages = self.learning._prompt(text, context, 'project-a', task)
        return json.loads(messages[-1]['content'])

    def hash_receipt(self, *, task='task-a', fail=False):
        if not self.file.exists(): self.file.write_text('Synthetic local fixture.', encoding='utf-8')
        prepared = self.commands.prepare('axx.file.sha256', {'path': str(self.file)}, conversation_id=task)
        if fail: self.file.unlink()
        return self.commands.execute(prepared['operation_id'], approved=True)

    def insert_hash_skill(self):
        return self.learning.skills.insert({'id': 'synthetic.hash', 'version': 1,
            'trigger': 'synthetic.hash', 'title': 'Synthetic hash', 'examples': [],
            'templates': [{'command_id': 'axx.file.sha256', 'inputs': {'path': str(self.file)}}],
            'schema': validate_schema({}), 'project_id': 'project-a', 'favorite': False,
            'environment': get_action_env_fingerprint(['axx.file.sha256']),
            'checks': ['executor_postconditions'], 'provenance': {}, 'created_at': time.time(), 'executable': True})

    def test_prompt_replaces_foreign_and_expired_cached_ambient_context(self):
        now = time.time()
        self.learning.update_context('project-a', {
            'current_file': 'FOREIGN_TASK_PRIVATE_SENTINEL',
            'current_folder': 'EXPIRED_PRIVATE_SENTINEL',
            'current_project': 'CURRENT_TASK_VISIBLE',
            'context_meta': {
                'current_file': {'kind': 'observed', 'source_id': 'task-source', 'task_id': 'task-a'},
                'current_folder': {'kind': 'observed', 'expires_at': now + 10},
                'current_project': {'kind': 'confirmed_user', 'task_id': 'task-b'}}})
        snapshot = self.learning.context('project-a')
        with patch('backend.memory.skill_memory.time.time', return_value=now + 20):
            payload = self.payload({'operational_context': snapshot, 'context': copy.deepcopy(snapshot)})
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn('FOREIGN_TASK_PRIVATE_SENTINEL', serialized)
        self.assertNotIn('EXPIRED_PRIVATE_SENTINEL', serialized)
        self.assertIn('CURRENT_TASK_VISIBLE', serialized)
        self.assertIn('FOREIGN_TASK_PRIVATE_SENTINEL', json.dumps(snapshot))
        self.assertEqual(self.model.calls, [])

    def test_forgotten_snapshot_is_not_sent_again_and_real_receipts_are_preserved(self):
        receipt = self.hash_receipt()
        self.assertEqual(receipt['state'], 'succeeded', receipt)
        before_command = self.commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?',
                                                  (receipt['operation_id'],)).fetchone()[0]
        before_action = self.executor.db.execute('SELECT result_json FROM operations WHERE operation_id=?',
                                                (receipt['action_operation_id'],)).fetchone()[0]
        self.learning.update_context('project-a', {'current_file': 'FORGOTTEN_AMBIENT_SENTINEL',
            'context_meta': {'current_file': {'kind': 'observed', 'source_id': 'forgotten-source', 'task_id': 'task-a'}}})
        snapshot = self.learning.context('project-a')
        self.learning.invalidate_context('project-a', {'source_id': 'forgotten-source', 'forget': True})
        payload = self.payload({'operational_context': snapshot, 'context': copy.deepcopy(snapshot),
                                'completed': [receipt]}, task='task-a')
        self.assertNotIn('FORGOTTEN_AMBIENT_SENTINEL', json.dumps(payload))
        self.assertEqual(payload['previous_action']['completed'], [receipt])
        self.assertEqual(self.commands.db.execute('SELECT result_json FROM command_runs WHERE operation_id=?',
                                                 (receipt['operation_id'],)).fetchone()[0], before_command)
        self.assertEqual(self.executor.db.execute('SELECT result_json FROM operations WHERE operation_id=?',
                                                (receipt['action_operation_id'],)).fetchone()[0], before_action)

    def test_alias_and_repeat_track_the_exact_task_and_forget_invalidates_prepared_plans(self):
        skill = self.insert_hash_skill()
        self.learning.update_context('project-a', {'aliases': {'mi referencia': skill['id']},
            'last_skill_id': skill['id'], 'context_meta': {
                'aliases': {'kind': 'confirmed_user', 'source_id': 'selection-source', 'task_id': 'task-a'},
                'last_skill_id': {'kind': 'observed', 'source_id': 'selection-source', 'task_id': 'task-a'}}})
        plans = []
        for phrase, field in (('mi referencia', 'aliases'), ('hazlo otra vez', 'last_skill_id')):
            with self.subTest(phrase=phrase):
                plan = self.learning.propose(phrase, project_id='project-a', conversation_id='task-a')
                self.assertEqual(plan['state'], 'awaiting_approval', plan)
                self.assertEqual(plan['model_calls_used'], 0)
                self.assertTrue(any(ref['field'] == field and ref['project_id'] == 'project-a'
                                    for ref in plan['context_dependencies']))
                plans.append(plan)
                foreign = self.learning.propose(phrase, project_id='project-a', conversation_id='task-b')
                self.assertNotEqual(foreign['state'], 'awaiting_approval', foreign)
                self.assertEqual(foreign['steps'], [])
        self.learning.invalidate_context('project-a', {'source_id': 'selection-source', 'forget': True})
        for plan in plans:
            persisted = self.learning.get(plan['operation_id'])
            self.assertEqual(persisted['state'], 'needs_input', persisted)
            self.assertFalse(persisted.get('approved_hash'))
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'needs_input')
        self.assertEqual(self.executor.list_operations(), [])

    def test_forget_during_model_call_does_not_resurrect_derived_intent_or_effects(self):
        marker = 'INFLIGHT_FORGOTTEN_SENTINEL'
        self.learning.update_context('project-a', {'current_file': marker, 'context_meta': {
            'current_file': {'kind': 'observed', 'source_id': 'inflight-source', 'task_id': 'task-a'}}})
        self.model.block = True
        self.model.answer = {'title': marker, 'steps': [{'command_id': 'axx.artifact.write',
            'inputs': {'path': 'unapproved-derived.txt', 'content': marker}}], 'goal_spec': {'intent': marker}}
        result, failures = [], []
        def propose():
            try:
                result.append(self.learning.propose('Prepara una entrega local', operation_id='inflight-forget',
                    project_id='project-a', conversation_id='task-a'))
            except Exception as exc:
                failures.append(exc)
        worker = threading.Thread(target=propose)
        worker.start()
        try:
            self.assertTrue(self.model.entered.wait(5), 'The local model was not entered')
            self.assertIn(marker, self.model.calls[0]['messages'][-1]['content'])
            self.learning.invalidate_context('project-a', {'source_id': 'inflight-source', 'forget': True})
        finally:
            self.model.release.set()
            worker.join(8)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        persisted = self.learning.get('inflight-forget')
        self.assertEqual(persisted['state'], 'needs_input', persisted)
        self.assertNotIn('model_data', persisted)
        self.assertNotIn(marker, json.dumps(persisted, ensure_ascii=False))
        self.assertEqual(persisted['steps'], [])
        self.assertFalse(persisted.get('approved_hash'))
        self.assertEqual(self.learning.execute('inflight-forget', approved=True)['state'], 'needs_input')
        self.assertFalse((self.executor.workspace_root / 'unapproved-derived.txt').exists())
        self.assertEqual(self.commands.operations(), [])
        self.assertEqual(self.executor.list_operations(), [])

    def test_prompt_caps_total_lessons_and_filters_consent_and_task_before_limit(self):
        failure = self.hash_receipt()
        self.assertEqual(failure['state'], 'succeeded', failure)
        failure = self.hash_receipt(fail=True)
        self.assertEqual(failure['state'], 'failed', failure)
        consented = []
        for index in range(3):
            item = self.learning.skills.record_lesson({'operation_id': failure['operation_id'],
                'hypothesis': 'reference allowed-' + str(index) + ' ' + 'x' * 850,
                'project_id': 'project-a', 'task_id': 'task-a', 'allow_provider': True})
            consented.append(item['id'])
        for index in range(4):
            self.learning.skills.record_lesson({'operation_id': failure['operation_id'],
                'hypothesis': 'reference local-only-' + str(index), 'project_id': 'project-a', 'task_id': 'task-a'})
        foreign = self.hash_receipt(task='task-b', fail=True)
        self.learning.skills.record_lesson({'operation_id': foreign['operation_id'], 'hypothesis': 'reference FOREIGN_LESSON',
            'project_id': 'project-a', 'task_id': 'task-b', 'allow_provider': True})
        local = self.learning.skills.lessons('reference', project_id='project-a', task_id='task-a')
        self.assertEqual(len(local), 3)
        self.assertTrue(all(item['allow_provider'] is False for item in local))
        lessons = self.payload({}, task='task-a', text='reference')['previous_action']['incident_references']['lessons']
        self.assertTrue(lessons)
        self.assertLessEqual(len(lessons), 3)
        self.assertLessEqual(len(json.dumps(lessons, ensure_ascii=False)), 3500)
        self.assertTrue(all(item['id'] in consented and item['allow_provider'] is True and item['task_id'] == 'task-a'
                            for item in lessons))
        self.assertTrue(all(item['permissions_granted'] is False and item['cause_confirmed'] is False for item in lessons))


if __name__ == '__main__':
    unittest.main()
