"""Forgotten plans expose recovery headers without reviving their private content."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.memory import task_memory


class NoModel:
    def route(self, request):
        raise AssertionError('Recovery projection must never call a provider')


class ForgottenPlanProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'state.db'
        self.store = ChatStore(self.path)
        self.executor = ActionExecutor(self.path, self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoModel())
        self.commands.learning = self.learning
        self.a = self.store.mutate('create', {'connect_id': 'context-a'})['id']
        self.b = self.store.mutate('create', {'connect_id': 'context-b'})['id']

    def tearDown(self):
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.store.close()
        self.temp.cleanup()

    def raw(self, key):
        return json.loads(self.learning.db.execute(
            'SELECT payload FROM learning_plans WHERE id=?', (key,)).fetchone()[0])

    def write_raw(self, plan):
        with self.learning.db:
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?',
                                     (json.dumps(plan), plan['operation_id']))

    def private_plan(self, task, key, *, dependencies=(), kind=True):
        prefix = 'PRIVATE_' + key.upper() + '_'
        name, content = prefix + 'FILE.txt', prefix + 'CONTENT'
        goal = {'intent': prefix + 'INTENT', 'objects': [prefix + 'OBJECT'],
                'sources': [prefix + 'SOURCE'], 'destination': prefix + 'DESTINATION',
                'filters': {'selected': prefix + 'FILTER'}, 'parameters': {'value': prefix + 'PARAMETER'},
                'preserve': [prefix + 'PRESERVE'], 'checks': [{'path': name, 'text': content}],
                'criteria': [{'id': 'private-result', 'kind': 'text_exact',
                              'parameters': {'path': name, 'text': content}}]}
        plan = self.learning.prepare_steps(prefix + 'REQUEST', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': name, 'content': content}}],
            operation_id=key, conversation_id=task, goal_spec=goal,
            memory_scope=task_memory.snapshot(self.learning.db, task))
        self.assertEqual(plan['state'], 'awaiting_approval', plan)
        done = self.learning.execute(key, approved=True, plan_hash=plan['plan_hash'])
        self.assertEqual(done['state'], 'succeeded', done)
        self.assertEqual((self.executor.workspace_root / name).read_text(encoding='utf-8'), content)
        plan = self.raw(key)
        # Delayed legacy snapshots can retain any of these fields after the barrier.
        plan.update(memory_dependencies=list(dependencies), state='blocked',
                    message=prefix + 'MESSAGE', error={'message': prefix + 'ERROR'},
                    inputs={'value': prefix + 'INPUT'},
                    skill_versions=[{'id': 'fixture-skill', 'version': 1,
                                     'inputs': {'value': prefix + 'SKILL_INPUT'}, 'title': prefix + 'SKILL_TITLE'}],
                    route={'diagnostic': prefix + 'ROUTE'},
                    planning_settings={'provider_name': prefix + 'PROVIDER'},
                    document_references=[{'excerpt': prefix + 'DOCUMENT'}],
                    goal_progress_admissions=[{'diagnostic': prefix + 'PROGRESS_ADMISSION'}],
                    capability_build={'diagnostic': prefix + 'CAPABILITY'},
                    observation_dependencies=[{'diagnostic': prefix + 'OBSERVATION'}],
                    context_dependencies=[{'diagnostic': prefix + 'CONTEXT'}],
                    mission_dependencies=[{'diagnostic': prefix + 'DEPENDENCY'}],
                    initiative_authorization={'diagnostic': prefix + 'AUTHORIZATION'},
                    future_private_field={'diagnostic': prefix + 'FUTURE'})
        plan['goal_verification']['private_diagnostic'] = prefix + 'GOAL_VERIFICATION'
        plan['step_records'][0]['state'] = 'blocked'
        plan['step_records'][0]['result']['error'] = {'message': prefix + 'BLOCKER'}
        plan['step_records'][0]['resolved_inputs'] = {'value': prefix + 'RESOLVED_INPUT'}
        plan['results'][0]['error'] = {'message': prefix + 'RESULT_ERROR'}
        if not kind:
            plan.pop('kind')
        with self.learning.db:
            self.learning.db.execute('UPDATE mission_model_budgets SET legacy_used=1,legacy_requests=1,legacy_counts=? WHERE plan_id=?',
                                     (json.dumps({'fixture': 1}), key))
        self.learning._model_budget_view(plan)
        plan['mission'] = self.learning._mission(plan)
        self.write_raw(plan)
        return plan, prefix

    def begin(self, task):
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            return task_memory.begin_forget(self.learning.db, task, 'forget-' + task,
                                            task_memory.state(self.learning.db, task)['generation'])

    def finish(self, ref):
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(self.learning.db, ref, {})

    def snapshot(self):
        tables = ('learning_plans', 'command_runs', 'operations',
                  'mission_model_budgets', 'mission_model_calls')
        rows = {table: [tuple(row) for row in self.learning.db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in tables}
        files = {path.relative_to(self.executor.workspace_root).as_posix(): path.read_bytes()
                 for path in self.executor.workspace_root.rglob('*') if path.is_file()}
        return rows, files

    def public_views(self, key):
        return {'get': self.learning.get(key),
                'list': next(plan for plan in self.learning.list_plans() if plan['operation_id'] == key),
                'operations': next(plan for plan in self.store.operations() if plan['operation_id'] == key)}

    def assert_forgotten(self, original, prefix):
        before = self.snapshot()
        source = copy.deepcopy(original)
        direct = self.learning._memory_view(source, self.learning.db)
        self.assertEqual(source, original, 'Projection mutated the caller-owned raw plan')
        with patch.object(self.executor, 'execute_action', side_effect=AssertionError('Read dispatched an effect')), \
                patch.object(self.commands, 'execute', side_effect=AssertionError('Read executed a command')):
            views = self.public_views(original['operation_id']) | {'direct': direct}
        for surface, view in views.items():
            with self.subTest(surface=surface):
                self.assertTrue(view.get('memory_forgotten'), view)
                self.assertFalse(prefix in json.dumps(view), 'Private content leaked through ' + surface)
                for field in ('operation_id', 'command_id', 'state', 'plan_hash', 'conversation_id',
                              'memory_scope', 'memory_context_id', 'model_call_limit', 'model_calls_used',
                              'model_calls_confirmed', 'model_calls_reserved', 'model_calls_uncertain',
                              'model_calls_legacy', 'route_requests', 'inference_counts', 'postconditions_passed'):
                    self.assertEqual(view.get(field), original.get(field), (surface, field))
                self.assertEqual(view['mission']['mission_id'], original['operation_id'])
                self.assertEqual(view['mission']['budget'], original['mission']['budget'])
                self.assertEqual(view['mission']['verified_steps'], original['mission']['verified_steps'])
                self.assertEqual(view['mission']['pending_steps'], original['mission']['pending_steps'])
                self.assertFalse(view['mission']['completed'])
                self.assertFalse(view['mission']['permission']['exact_plan_approved'])
                self.assertEqual(len(view['results']), len(original['results']))
                self.assertEqual(len(view['step_records']), len(original['step_records']))
                for observed, receipt in zip(view['results'], original['results']):
                    for field in ('operation_id', 'command_id', 'state', 'postconditions_passed', 'action_operation_id'):
                        self.assertEqual(observed.get(field), receipt.get(field), (surface, field))
                for observed, record in zip(view['step_records'], original['step_records']):
                    for field in ('step_id', 'operation_id', 'state'):
                        self.assertEqual(observed.get(field), record.get(field), (surface, field))
        self.assertEqual(self.snapshot(), before, 'Reading recovery views mutated durable state or artifacts')

    def test_pending_forget_barrier_sanitizes_all_public_readers_before_purge(self):
        plan, prefix = self.private_plan(self.a, 'pending')
        self.begin(self.a)
        self.assertTrue(task_memory.state(self.learning.db, self.a)['forgetting'])
        self.assert_forgotten(plan, prefix)

    def test_finished_forget_sanitizes_a_delayed_kindless_raw_plan(self):
        plan, prefix = self.private_plan(self.a, 'delayed', kind=False)
        ref = self.begin(self.a)
        self.finish(ref)
        self.write_raw(plan)
        self.assertFalse(task_memory.state(self.learning.db, self.a)['forgetting'])
        self.assert_forgotten(plan, prefix)

    def test_causal_a_to_b_is_sanitized_while_independent_b_stays_identical(self):
        source, source_prefix = self.private_plan(self.a, 'source')
        scope = task_memory.snapshot(self.learning.db, self.a)
        dependent, dependent_prefix = self.private_plan(self.b, 'dependent', dependencies=[scope])
        independent, _ = self.private_plan(self.b, 'independent')
        unchanged = copy.deepcopy(self.public_views(independent['operation_id']))
        self.begin(self.a)
        self.assertEqual(task_memory.state(self.learning.db, self.b)['generation'], 0)
        self.assert_forgotten(source, source_prefix)
        self.assert_forgotten(dependent, dependent_prefix)
        self.assertEqual(self.public_views(independent['operation_id']), unchanged)

    def test_opaque_context_rotation_without_generation_sanitizes_old_plan(self):
        plan, prefix = self.private_plan(self.b, 'rotated')
        group = self.store.mutate('group', {'title': 'Context rotation'})['id']
        self.store.mutate('update', {'id': self.b, 'group_id': group})
        self.assertEqual(task_memory.state(self.learning.db, self.b)['generation'], 0)
        self.assertNotEqual(self.store.get(self.b)['context_id'], plan['memory_context_id'])
        self.assert_forgotten(plan, prefix)

    def test_cancel_direct_response_after_pending_forget_cannot_restore_content(self):
        plan, prefix = self.private_plan(self.a, 'cancelled')
        plan['state'] = 'interrupted'
        plan['mission'] = self.learning._mission(plan)
        self.write_raw(plan)
        self.begin(self.a)
        rows_before, files_before = self.snapshot()
        with patch.object(self.executor, 'execute_action', side_effect=AssertionError('Cancel dispatched an effect')), \
                patch.object(self.commands, 'execute', side_effect=AssertionError('Cancel executed a command')):
            response = self.learning.cancel(plan['operation_id'])
        self.assertTrue(response.get('memory_forgotten'))
        self.assertEqual(response['state'], 'cancelled')
        self.assertTrue(response['cancel_requested'])
        self.assertFalse(prefix in json.dumps(response), 'Cancellation returned forgotten private content')
        stored = self.raw(plan['operation_id'])
        self.assertEqual(stored['goal_spec'], plan['goal_spec'])
        self.assertEqual(stored['skill_versions'], plan['skill_versions'])
        rows_after, files_after = self.snapshot()
        self.assertEqual(files_after, files_before)
        for table in rows_before.keys() - {'learning_plans'}:
            self.assertEqual(rows_after[table], rows_before[table], table)
        self.assert_forgotten(stored, prefix)

    def test_forgotten_projection_preserves_unavailable_artifact_receipt_indexes(self):
        plan, prefix = self.private_plan(self.a, 'unavailable')
        self.begin(self.a)
        before = self.snapshot()
        with patch.object(self.executor, 'execute_action', side_effect=AssertionError('Projection dispatched an effect')):
            for available in (False, None, True):
                with self.subTest(available_current=available):
                    plan['artifact_compensations'] = [{'step': 0, 'state': 'restored' if available else 'quarantined',
                        'available_current': available, 'operation_id': 'compensation-fixture',
                        'source_operation_id': plan['results'][0]['operation_id'],
                        'quarantine_path': prefix + 'QUARANTINE', 'error': prefix + 'COMPENSATION_ERROR',
                        'verification': {'current_path': prefix + 'CURRENT_PATH'}}]
                    plan['mission'] = self.learning._mission(plan)
                    original = copy.deepcopy(plan)
                    projected = self.learning._memory_view(plan, self.learning.db)
                    self.assertEqual(plan, original)
                    self.assertFalse(prefix in json.dumps(projected))
                    for field in ('verified_steps', 'pending_steps'):
                        self.assertEqual(projected['mission'][field], original['mission'][field])
        self.assertEqual(self.snapshot(), before)

    def test_forget_between_resume_reconciliation_and_save_sanitizes_direct_response(self):
        prefix = 'PRIVATE_RESUME_'
        plan = self.learning.prepare_steps(prefix + 'REQUEST', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': prefix + 'FILE.txt', 'content': prefix + 'CONTENT'}}],
            operation_id='resume-race', conversation_id=self.a,
            goal_spec={'intent': prefix + 'INTENT', 'destination': prefix + 'DESTINATION'},
            memory_scope=task_memory.snapshot(self.learning.db, self.a))
        self.assertEqual(self.learning.pause(plan['operation_id'])['state'], 'paused')
        reconcile = self.learning._reconcile

        def forget_after_reconciliation(current):
            reconciled = reconcile(current)
            self.begin(self.a)
            return reconciled

        rows_before, files_before = self.snapshot()
        with patch.object(self.learning, '_reconcile', side_effect=forget_after_reconciliation), \
                patch.object(self.executor, 'execute_action', side_effect=AssertionError('Resume dispatched an effect')), \
                patch.object(self.commands, 'execute', side_effect=AssertionError('Resume executed a command')):
            response = self.learning.resume(plan['operation_id'], approved=False)
        self.assertTrue(response.get('memory_forgotten'))
        self.assertEqual(response['state'], 'cancelled')
        self.assertFalse(prefix in json.dumps(response), 'Resume returned forgotten private content')
        rows_after, files_after = self.snapshot()
        self.assertEqual(files_after, files_before)
        for table in rows_before.keys() - {'learning_plans'}:
            self.assertEqual(rows_after[table], rows_before[table], table)
        self.assert_forgotten(self.raw(plan['operation_id']), prefix)


if __name__ == '__main__':
    unittest.main()
