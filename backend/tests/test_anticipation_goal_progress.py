"""Resident goal progress uses real temporary files and the existing mission executor."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions import file_inspection
from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService, MISSION_CAPABILITY
from backend.commands import CommandService


class NoModel:
    def route(self, request):
        raise AssertionError('Goal progress must not initiate inference')


class AnticipationGoalProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoModel())
        self.commands.learning = self.learning
        self.service = AnticipationService(self.commands)
        self.learning.anticipation = self.service
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.commands.mission_guard = self.learning.assert_dispatch_context
        self.executor.result_filter = self.service.filter_result
        self.service.configure({'profile': 'copiloto', 'profiles': {
            name: {'cooldown_seconds': 0, 'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}
            for name in ('discreto', 'copiloto', 'full')}})

    def tearDown(self):
        self.learning.close()
        self.service.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def pending(self, criteria=None):
        goal = {'intent': 'Completar entrega', 'criteria': criteria or [
            {'id': 'delivery', 'kind': 'text_exact', 'parameters': {'path': 'delivery.txt', 'text': 'entrega real'}}]}
        plan = self.learning.prepare_steps('Completar entrega', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'prefix.txt', 'content': 'conservar prefijo'}}],
            operation_id='mission', conversation_id='task-a', goal_spec=goal)
        result = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(result['state'], 'goal_pending', result)
        return result

    def grant(self, **changes):
        return self.service.grant({'capability': MISSION_CAPABILITY, 'task_id': 'task-a',
            'root': str(self.executor.workspace_root), 'command_ids': ['axx.artifact.write'],
            'expires_at': None, 'lifetime': 'session', **changes})

    def candidate(self):
        return next(row for row in self.service.suggestions() if row['candidate_kind'] == 'goal_progress')

    def test_copilot_prepares_same_mission_and_preserves_verified_prefix_until_new_hash_approved(self):
        source = self.pending()
        prefix = copy.deepcopy(source['step_records'])
        self.service.tick()
        item = self.candidate()
        self.assertEqual(item['state'], 'AWAITING_APPROVAL')
        self.assertEqual(item['plan']['criterion_id'], 'delivery')
        get = self.learning.get
        def unlocked_get(*args, **kwargs):
            self.assertFalse(self.service.lock._is_owned(), 'Policy lock must not precede planner lock')
            return get(*args, **kwargs)
        with patch.object(self.learning, 'get', side_effect=unlocked_get):
            prepared = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertEqual(prepared['state'], 'PREPARED', prepared)
        self.assertEqual(prepared['learning_plan_id'], source['operation_id'])
        plan = self.learning.get(source['operation_id'])
        self.assertEqual(plan['state'], 'awaiting_approval')
        self.assertEqual(plan['step_records'][:1], prefix)
        self.assertEqual(plan['model_calls_used'], source['model_calls_used'])
        self.assertNotEqual(plan['plan_hash'], source['plan_hash'])
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())
        self.assertEqual(len(self.executor.list_operations()), 1)
        final = self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertEqual(final['step_records'][:1], prefix)
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_full_prior_session_permission_executes_only_new_step_with_new_hash(self):
        self.service.configure({'profile': 'full'})
        grant = self.grant()
        source = self.pending()
        execute = self.learning.execute_with_grant
        calls = []
        def record(key, grant_id, plan_hash, **memory):
            self.assertFalse(self.service.lock._is_owned())
            calls.append((key, grant_id, plan_hash))
            return execute(key, grant_id, plan_hash, **memory)
        with patch.object(self.learning, 'execute_with_grant', side_effect=record):
            self.service.tick()
        item = self.candidate()
        self.assertEqual(item['state'], 'VERIFIED', item)
        final = self.learning.get(source['operation_id'])
        self.assertEqual(calls, [(source['operation_id'], grant['grant_id'], final['plan_hash'])])
        self.assertNotEqual(final['plan_hash'], source['plan_hash'])
        self.assertEqual(final['step_records'][:1], source['step_records'])
        self.assertEqual((self.executor.workspace_root / 'delivery.txt').read_text(), 'entrega real')
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_old_reviewed_hash_and_late_generic_grants_do_not_auto_advance(self):
        self.service.configure({'profile': 'full'})
        source = self.pending()
        self.grant(learning_plan_id=source['operation_id'], reviewed_plan_hash=source['plan_hash'])
        self.service.tick()
        item = self.candidate()
        self.assertFalse(item.get('auto_continue'))
        self.assertEqual(item['state'], 'AWAITING_APPROVAL')
        self.grant()
        self.service.tick()
        self.assertEqual(self.candidate()['state'], 'AWAITING_APPROVAL')
        self.assertEqual(len(self.learning.get(source['operation_id'])['steps']), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())

    def test_discreet_never_assesses_or_proposes_progress(self):
        self.pending()
        self.service.configure({'profile': 'discreto'})
        with patch.object(self.learning, 'refresh_goal_progress', wraps=self.learning.refresh_goal_progress) as refresh:
            self.service.tick()
            self.assertEqual(refresh.call_count, 0)
        self.assertEqual([row for row in self.service.suggestions() if row['candidate_kind'] == 'goal_progress'], [])
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_refresh_reads_files_only_after_planner_or_command_revision_changes(self):
        source = self.pending()
        refresh = self.learning.refresh_goal_progress
        def unlocked_refresh(*args, **kwargs):
            self.assertFalse(self.service.lock._is_owned())
            return refresh(*args, **kwargs)
        with patch.object(self.learning, 'refresh_goal_progress', side_effect=unlocked_refresh) as observed:
            self.service.tick()
            self.service.tick()
            stable_count = observed.call_count
            (self.executor.workspace_root / 'delivery.txt').write_text('cambio externo')
            self.service.tick()
            self.service.tick()
            self.assertEqual(observed.call_count, stable_count)
            prepared = self.commands.prepare('axx.file.sha256', {'path': str(self.executor.workspace_root / 'prefix.txt')},
                operation_id='fresh-command', conversation_id='task-a')
            self.commands.execute(prepared['operation_id'], approved=True)
            self.service.tick()
            self.assertGreater(observed.call_count, stable_count)
            after_command = observed.call_count
            self.service.tick()
            self.service.tick()
            stable_count = observed.call_count
            self.learning.pause(source['operation_id'])
            self.service.tick()
            self.assertEqual(observed.call_count, stable_count)
            self.assertGreaterEqual(stable_count, after_command)

    def test_changed_producer_inputs_cannot_prepare_or_execute_stale_candidate(self):
        source = self.pending([{'id': 'archive', 'kind': 'file_bundle', 'parameters': {
            'paths': ['prefix.txt'], 'destination': 'delivery', 'max_output_bytes': 65536}}])
        self.service.tick()
        item = self.candidate()
        (self.executor.workspace_root / 'prefix.txt').write_text('origen cambiado')
        stopped = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertEqual(stopped['state'], 'FAILED', stopped)
        self.assertEqual(len(self.learning.get(source['operation_id'])['steps']), 1)
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery').exists())

    def stopped_after_preparation(self, change):
        self.service.configure({'profile': 'full'})
        grant = self.grant()
        source = self.pending()
        prepare = self.learning.prepare_goal_progress
        def stop(*args, **kwargs):
            self.assertFalse(self.service.lock._is_owned())
            result = prepare(*args, **kwargs)
            if change == 'pause': self.service.pause()
            elif change == 'cancel': self.service.cancel(self.candidate()['suggestion_id'])
            else: self.service.revoke(grant['grant_id'])
            return result
        with patch.object(self.learning, 'prepare_goal_progress', side_effect=stop):
            self.service.tick()
        stopped = self.learning.get(source['operation_id'])
        self.assertEqual(stopped['state'], 'paused', stopped)
        self.assertEqual(stopped['step_records'][:1], source['step_records'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())

    def test_pause_after_preparation_stops_before_new_effect(self):
        self.stopped_after_preparation('pause')

    def test_revocation_after_preparation_stops_before_new_effect(self):
        self.stopped_after_preparation('revoke')

    def test_cancel_after_preparation_stops_before_new_effect(self):
        self.stopped_after_preparation('cancel')

    def test_prepare_mode_only_appends_for_review(self):
        self.service.configure({'profiles': {'copiloto': {'mode': 'PREPARE'}}})
        source = self.pending()
        self.service.tick()
        item = self.candidate()
        self.assertEqual(item['state'], 'PREPARED', item)
        self.assertEqual(item['approval'], 'profile_preparation')
        self.assertEqual(item['result']['state'], 'awaiting_approval')
        self.assertEqual(item['learning_plan_id'], source['operation_id'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())

    def test_full_parameter_limits_still_block_actual_effect(self):
        self.service.configure({'profile': 'full'})
        self.grant(parameter_constraints={'axx.artifact.write': {'content': 'otro literal'}})
        source = self.pending()
        self.service.tick()
        self.assertNotEqual(self.candidate()['state'], 'VERIFIED')
        self.assertNotEqual(self.learning.get(source['operation_id'])['state'], 'succeeded')
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())

    def test_forgotten_pending_mission_is_neither_reassessed_nor_reproposed(self):
        source = self.pending()
        self.service.tick()
        self.service.forget({'task_id': 'task-a', 'routine_id': 'advance_pending_goal'})
        self.assertEqual(self.learning.get(source['operation_id'])['state'], 'goal_pending')
        with patch.object(self.learning, 'refresh_goal_progress', wraps=self.learning.refresh_goal_progress) as refresh:
            self.service.tick()
            self.assertEqual(refresh.call_count, 0)
        self.assertEqual([row for row in self.service.suggestions() if row['candidate_kind'] == 'goal_progress'], [])
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_full_advances_two_criteria_without_claiming_completion_after_first_step(self):
        self.service.configure({'profile': 'full'})
        self.grant()
        source = self.pending([{'id': name, 'kind': 'text_exact', 'parameters': {
            'path': name + '.txt', 'text': name}} for name in ('first', 'second')])
        self.service.tick()
        partial = self.learning.get(source['operation_id'])
        self.assertEqual(partial['state'], 'goal_pending', partial)
        self.assertFalse(partial['mission']['completed'])
        first = self.candidate()
        self.assertEqual(first['state'], 'PREPARED', first)
        self.assertIsNone(first['error'])
        self.assertIn('criterios pendientes', first['message'])
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.service.tick()
        final = self.learning.get(source['operation_id'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertTrue(final['mission']['completed'])
        self.assertEqual(final['step_records'][:2], partial['step_records'])
        self.assertEqual(final['model_calls_used'], source['model_calls_used'])
        self.assertEqual(len(self.executor.list_operations()), 3)
        self.assertEqual((self.executor.workspace_root / 'first.txt').read_text(), 'first')
        self.assertEqual((self.executor.workspace_root / 'second.txt').read_text(), 'second')
        stats = next(row for row in self.service.status()['routines'] if row['routine_id'] == 'advance_pending_goal')
        self.assertEqual(stats['goal_steps_verified'], 1)
        self.assertEqual(stats['verified'], 1)
        self.assertNotIn('failed', stats)
        self.service.tick()
        self.assertEqual(self.service.status_item(first['suggestion_id'])['state'], 'PREPARED')

    def test_external_satisfied_criteria_finish_without_preparing_or_executing_a_suffix(self):
        self.service.configure({'profile': 'full'})
        self.grant()
        source = self.pending()
        (self.executor.workspace_root / 'delivery.txt').write_text('entrega real', encoding='utf-8')
        self.service.tick()
        final = self.learning.get(source['operation_id'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertTrue(final['mission']['completed'])
        self.assertEqual(final['step_records'], source['step_records'])
        self.assertEqual(final['plan_hash'], source['plan_hash'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertEqual([row for row in self.service.suggestions() if row['candidate_kind'] == 'goal_progress'], [])

    def test_cpu_budget_cancels_read_keeps_snapshot_and_retries_only_after_policy_change(self):
        self.service.configure({'profile': 'full'})
        self.grant(command_ids=['axx.file.bundle'])
        source = self.pending([{'id': 'archive', 'kind': 'file_bundle', 'parameters': {
            'paths': ['prefix.txt'], 'destination': 'delivery', 'max_output_bytes': 65536}}])
        hash_file = file_inspection.hash_file
        denied, exhausted = False, False
        def exhaust_once(path, cancelled):
            nonlocal denied, exhausted
            result = hash_file(path, cancelled)
            if not exhausted:
                denied, exhausted = True, True
                self.assertTrue(cancelled.is_set(), 'File reads must see the exhausted CPU admission budget')
            return result
        with patch.object(self.service, '_within_budget', side_effect=lambda options: not denied), \
             patch.object(file_inspection, 'hash_file', side_effect=exhaust_once), \
             patch.object(self.learning, 'refresh_goal_progress', wraps=self.learning.refresh_goal_progress) as refresh:
            self.service.tick()
            self.assertEqual(self.learning.get(source['operation_id'])['goal_progress'], source['goal_progress'])
            denied = False
            self.service.tick()
            self.assertEqual(refresh.call_count, 1)
            self.assertEqual([row for row in self.service.suggestions() if row['candidate_kind'] == 'goal_progress'], [])
            self.assertFalse((self.executor.workspace_root / 'delivery').exists())
            self.service.configure({'profiles': {'full': {'resources': {'max_events_tick': 24}}}})
            self.service.tick()
        self.assertEqual(self.learning.get(source['operation_id'])['state'], 'succeeded')
        self.assertEqual(len(self.executor.list_operations()), 2)


if __name__ == '__main__':
    unittest.main()
