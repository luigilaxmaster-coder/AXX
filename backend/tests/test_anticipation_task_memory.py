"""Task epochs fence initiative without changing grants or immutable effect receipts."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService, StaleContext
from backend.commands import CommandService
from backend.action_learning import ActionLearning
from backend.memory import selection_policy, task_memory


class AnticipationTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.service = AnticipationService(self.commands)
        self.learning = None
        self.db = sqlite3.connect(self.root / 'state.db')
        self.service.configure({'profile': 'copiloto', 'profiles': {'copiloto': {'cooldown_seconds': 0,
            'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}}})

    def tearDown(self):
        if self.learning: self.learning.close()
        self.db.close()
        self.service.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def write(self, task):
        command = self.commands.prepare('axx.artifact.write', {'path': task + '.txt', 'content': task + ' private'},
            conversation_id=task, memory_scope=task_memory.snapshot(self.db, task))
        result = self.commands.execute(command['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded')
        return result

    def pending(self):
        self.db.execute('BEGIN IMMEDIATE')
        state = task_memory.begin_forget(self.db, 'a', 'forget-a', 0)
        self.db.commit()
        return state

    def finish(self, state):
        result = self.service.forget_task('a')
        self.db.execute('BEGIN IMMEDIATE')
        task_memory.finish_forget(self.db, state, result)
        self.db.commit()
        return result

    def target(self):
        selected = self.root / 'selected'
        selected.mkdir()
        target = {'id': 'source-a', 'source': 'folder', 'task_id': 'a', 'root': str(selected),
                  'observe': True, 'retain': True, 'memory_scope': task_memory.snapshot(self.db, 'a')}
        self.service.configure({'sources': {'folders': True}, 'observation_targets': [target]})
        return selected, target

    def test_old_unseen_receipt_never_recreates_a_and_known_b_remains_eligible(self):
        receipt_a = self.write('a')
        self.write('b')
        state = self.pending()
        self.service.tick()
        self.assertEqual(self.service.suggestions('a'), [])
        self.assertEqual(len(self.service.suggestions('b')), 1)
        self.finish(state)
        self.service.tick()
        rows = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM anticipation_events')]
        self.assertEqual([row['task_id'] for row in rows], ['b'])
        self.assertEqual(self.commands.get(receipt_a['operation_id']), receipt_a)

    def test_late_save_and_completion_blocked_cleanup_preserves_b_grants_and_receipts(self):
        receipt = self.write('a')
        self.write('b')
        self.service.tick()
        old = self.service.suggestions('a')[0]
        b = self.service.suggestions('b')[0]
        self.service.grant({'task_id': 'a', 'capability': 'verify_artifact', 'root': str(self.executor.workspace_root), 'expires_at': None})
        grants = list(self.db.execute('SELECT * FROM anticipation_grants'))
        state = self.pending()
        self.assertTrue(self.service.accept(old['suggestion_id'], old['plan_hash'])['forgotten'])
        with self.service.db, self.assertRaises(StaleContext): self.service._save(copy.deepcopy(old))
        self.service.db.rollback()
        self.assertTrue(self.service._finish(old['suggestion_id'], {'output': {'private': 'late'}})['forgotten'])
        result = self.finish(state)
        self.assertEqual(result['forgotten_suggestions'], 1)
        self.assertEqual(self.service.suggestions('b')[0]['suggestion_id'], b['suggestion_id'])
        self.assertEqual(list(self.db.execute('SELECT * FROM anticipation_grants')), grants)
        self.assertEqual(self.commands.get(receipt['operation_id']), receipt)

    def test_target_is_not_rearmed_during_pending_or_after_forgetting(self):
        selected, target = self.target()
        self.service._poll_sources()
        self.assertIn(target['id'], self.service.source_state)
        state = self.pending()
        with patch.object(self.service, '_folder_snapshot') as read:
            self.service._poll_sources()
            read.assert_not_called()
        self.finish(state)
        (selected / 'private.txt').write_text('still delivered on disk', encoding='utf-8')
        with patch.object(self.service, '_folder_snapshot') as read:
            self.service._poll_sources()
            read.assert_not_called()
        self.assertEqual(self.service.status()['source_observations'], [])
        self.assertTrue((selected / 'private.txt').is_file())
        self.assertEqual(self.service.status()['observation_targets'][0]['memory_scope'], {'task_id': 'a', 'generation': 0})
        unchanged = self.service.status()['observation_targets']
        self.service.configure({'observation_targets': unchanged})
        self.assertIsNone(self.service._source_target(target['id']))

    def test_pending_barrier_during_reader_prevents_snapshot_publication(self):
        selected, target = self.target()
        def read(*args):
            self.pending()
            return {'PRIVATE_A': {'path': str(selected / 'private.txt')}}, False
        with patch.object(self.service, '_folder_snapshot', side_effect=read): self.service._poll_sources()
        self.assertNotIn(target['id'], self.service.source_state)
        self.assertEqual(self.service.source_observations, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM anticipation_events').fetchone()[0], 0)

    def routine(self, seed_a=False):
        class Model:
            def route(model, request):
                return {'ok': True, 'message': {'content': json.dumps({'title': 'Estado local',
                    'steps': [{'command_id': 'axx.system.telemetry', 'inputs': {}}]})}}
        self.learning = ActionLearning(self.commands, Model())
        self.commands.learning = self.learning
        if seed_a:
            plan = self.learning.propose('prepara un diagnóstico', conversation_id='a')
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
        for _ in range(3):
            plan = self.learning.propose('prepara un diagnóstico', conversation_id='b')
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
        self.service._observe_preparations()
        candidate = next(item for item in self.service.suggestions('b') if item.get('candidate_kind') == 'prepare_routine')
        skill = self.learning.skills.get(candidate['plan']['skill_id'])
        return candidate, skill

    def test_retired_routine_is_invalidated_and_no_new_automatic_candidate_appears(self):
        candidate, skill = self.routine()
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            selection_policy.apply(self.learning.db, skill, 'retire_procedure', '', None,
                                   task_memory.snapshot(self.db, 'b'), 'retire-b', 0)
        self.service.tick()
        self.assertEqual(self.service.status_item(candidate['suggestion_id'])['state'], 'CANCELLED')
        with self.service.db:
            self.service.db.execute('DELETE FROM anticipation_suggestions WHERE suggestion_id=?', (candidate['suggestion_id'],))
        self.service._observe_preparations()
        self.assertFalse(any(item.get('candidate_kind') == 'prepare_routine' for item in self.service.suggestions('b')))

    def test_forgotten_policy_origin_blocks_b_routine_without_removing_b_definition(self):
        candidate, skill = self.routine()
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            selection_policy.apply(self.learning.db, skill, 'prefer_folder', '', str(self.executor.workspace_root),
                                   task_memory.snapshot(self.db, 'a'), 'preference-a', 0)
        self.pending()
        self.service.tick()
        self.assertEqual(self.service.status_item(candidate['suggestion_id'])['state'], 'CANCELLED')
        self.assertEqual(self.learning.skills.get(skill['id'])['id'], skill['id'])

    def test_b_candidate_depending_on_a_skill_is_fenced_without_deleting_b_plans(self):
        candidate, skill = self.routine(seed_a=True)
        self.assertEqual(skill['memory_scope']['task_id'], 'a')
        self.assertEqual(candidate['memory_dependencies'], [skill['memory_scope']])
        state = self.pending()
        self.assertEqual(self.service.suggestions('b'), [])
        result = self.finish(state)
        self.assertEqual(result['forgotten_suggestions'], 1)
        count = self.db.execute("SELECT COUNT(*) FROM learning_plans WHERE json_extract(payload,'$.conversation_id')='b'").fetchone()[0]
        self.assertEqual(count, 3)
        self.service._observe_preparations()
        self.assertEqual(self.service.suggestions('b'), [])

    def test_fresh_epoch_for_same_file_has_new_command_id_and_cannot_replay_old_receipt(self):
        receipt = self.write('a')
        self.service.tick()
        old = self.service.suggestions('a')[0]
        self.finish(self.pending())
        event = {'event_id': 'fresh-observation', 'task_id': 'a', 'path': receipt['output']['path'],
                 'sha256': None, 'context': {'source': 'events'}, 'provenance': {'origin': 'fresh_observation'},
                 'memory_scope': task_memory.snapshot(self.db, 'a')}
        options = self.service._config()['profiles']['copiloto']
        with self.service._policy_transaction(immediate=True):
            fresh = self.service._propose(event, 'copiloto', options)
        self.assertNotEqual(fresh['suggestion_id'], old['suggestion_id'])
        self.assertNotEqual(fresh['operation_id'], old['operation_id'])
        self.assertEqual(fresh['memory_scope']['generation'], 1)


if __name__ == '__main__':
    unittest.main()
