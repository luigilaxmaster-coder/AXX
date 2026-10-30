"""Mission continuation uses real disposable file receipts, without desktop input."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.action_learning import ActionLearning


class NoModel:
    def route(self, request):
        raise AssertionError('Deterministic progress must not call a model')


class GoalProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoModel())
        self.commands.learning = self.learning

    def tearDown(self):
        self.learning.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def prepare(self, key='mission', count=1):
        goal = {'intent': 'Entregar texto exacto', 'criteria': [
            {'id': 'delivery', 'kind': 'text_exact', 'parameters': {'path': 'delivery.txt', 'text': 'entrega verificada'}}]}
        steps = [{'command_id': 'axx.artifact.write', 'inputs': {'path': f'{key}-prefix-{i}.txt', 'content': 'conservar'}} for i in range(count)]
        return self.learning.prepare_steps('Preparar entrega', steps, key, goal_spec=goal)

    def pending(self):
        plan = self.prepare()
        done = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(done['state'], 'goal_pending', done)
        self.assertFalse(self.learning._mission(done)['completed'])
        self.assertEqual(done['goal_progress']['status'], 'ready')
        return done

    def test_append_preserves_identity_receipts_budget_and_requires_new_hash(self):
        done = self.pending()
        prefix = copy.deepcopy(done['step_records'])
        budget = done['model_calls_used']
        progress = done['goal_progress']
        next_plan = self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'],
            progress['criterion_id'], progress['fingerprint'])
        self.assertEqual(next_plan['operation_id'], done['operation_id'])
        self.assertEqual(next_plan['step_records'][:1], prefix)
        self.assertEqual(next_plan['model_calls_used'], budget)
        self.assertNotEqual(next_plan['plan_hash'], done['plan_hash'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())
        with self.assertRaises(ValueError):
            self.learning.execute(done['operation_id'], approved=True, plan_hash=done['plan_hash'])
        with self.assertRaises(ValueError):
            self.learning.execute(done['operation_id'], approved=True)
        final = self.learning.execute(done['operation_id'], approved=True, plan_hash=next_plan['plan_hash'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertTrue(self.learning._mission(final)['completed'])
        self.assertEqual(final['step_records'][:1], prefix)
        self.assertEqual((self.executor.workspace_root / 'delivery.txt').read_text(), 'entrega verificada')
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertFalse(final.get('learned_action_id'))
        self.assertEqual(self.learning.list_actions(), [])
        with self.assertRaises(ValueError):
            self.learning.prepare_goal_progress(final['operation_id'], final['plan_hash'])

    def test_stale_candidate_output_pause_and_total_step_limit_abstain(self):
        done = self.pending()
        with self.assertRaises(ValueError):
            self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'], candidate_hash='0' * 64)
        (self.executor.workspace_root / 'delivery.txt').write_text('otro contenido')
        with self.assertRaises(ValueError):
            self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'], candidate_hash=done['goal_progress']['fingerprint'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        paused = self.learning.pause(done['operation_id'])
        self.assertTrue(paused['pause_requested'])
        with self.assertRaises(ValueError):
            self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'])
        plan = self.prepare('full', 8)
        done = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(done['goal_progress']['status'], 'needs_input')
        self.assertEqual(done['goal_progress']['reason_code'], 'STEP_LIMIT')

    def test_goal_is_in_idempotency_signature_and_cannot_be_rewritten_by_model(self):
        plan = self.prepare()
        altered = copy.deepcopy(plan['goal_spec']); altered['criteria'][0]['parameters']['text'] = 'cambiado'
        with self.assertRaises(ValueError):
            self.learning.prepare_steps('Preparar entrega', plan['steps'], 'mission', goal_spec=altered)
        class Rewriter:
            def route(self, request):
                return {'ok': True, 'message': {'content': json.dumps({'title': 'Cambio',
                    'goal_spec': altered, 'steps': plan['steps']})},
                    'route': {'upstream_attempts': 1, 'attempt_budget_used': 1}}
        self.learning.adapter = Rewriter()
        rejected = self.learning.propose('Preparar entrega explícita', 'rewriter', goal_spec=plan['goal_spec'])
        self.assertEqual(rejected['state'], 'failed', rejected)
        self.assertEqual(rejected['goal_spec'], plan['goal_spec'])
        self.assertEqual(self.executor.list_operations(), [])

    def test_cancel_restart_and_changed_admission_never_replay_a_prefix(self):
        done = self.pending()
        self.learning.close()
        self.learning = ActionLearning(self.commands, NoModel()); self.commands.learning = self.learning
        restored = self.learning.get(done['operation_id'])
        self.assertEqual(restored['state'], 'goal_pending')
        prepared = self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'])
        altered = copy.deepcopy(prepared)
        altered['goal_progress_admissions'][0]['criterion_id'] = 'other'
        self.assertNotEqual(self.learning._plan_hash(altered), prepared['plan_hash'])
        cancelled = self.learning.cancel(done['operation_id'])
        final = self.learning.execute(done['operation_id'], approved=True, plan_hash=prepared['plan_hash'])
        self.assertEqual(final['state'], cancelled['state'])
        self.assertEqual(final['state'], 'cancelled')
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())

    def test_verified_external_delivery_stops_without_preparing_an_unneeded_step(self):
        done = self.pending()
        (self.executor.workspace_root / 'delivery.txt').write_text('entrega verificada', encoding='utf-8')
        final = self.learning.refresh_goal_progress(done['operation_id'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertTrue(final['mission']['completed'])
        self.assertEqual(final['step_records'], done['step_records'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse(final.get('goal_progress_admissions'))

    def test_persisted_locked_legacy_goal_normalizes_only_when_preparing_new_revision(self):
        plan = self.learning.prepare_steps('Conservar contrato anterior', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'legacy.txt', 'content': 'conservar'}}], 'legacy-plan')
        plan['goal_spec'].pop('criteria')
        old_goal = copy.deepcopy(plan['goal_spec'])
        plan['plan_hash'] = self.learning._plan_hash(plan)
        old_hash = plan['plan_hash']
        plan.update(state='waiting_capability', capability_build={'id': 'legacy-build'},
            preparation={'kind': 'propose', 'selection': None, 'candidates': [], 'context': {}},
            model_data={'goal_spec': old_goal, 'title': 'Mismo contrato', 'steps': copy.deepcopy(plan['steps'])})
        self.learning._save(plan)
        stored = self.learning.get(plan['operation_id'])
        self.assertNotIn('criteria', stored['goal_spec'])
        self.assertEqual(stored['plan_hash'], old_hash)
        self.assertEqual(self.learning._plan_hash(stored), old_hash)
        prepared = self.learning._prepare_plan(stored)
        self.assertEqual(prepared['state'], 'awaiting_approval', prepared)
        self.assertEqual(prepared['goal_spec'], old_goal | {'criteria': []})
        self.assertNotEqual(prepared['plan_hash'], old_hash)
        self.assertIsNone(prepared.get('approved_hash'))
        self.assertEqual(self.executor.list_operations(), [])

    def bundle_pending(self, execute_bundle=False):
        goal = {'intent': 'Agrupar y completar entrega', 'criteria': [
            {'id': 'archive', 'kind': 'file_bundle', 'parameters': {
                'paths': ['input.txt'], 'destination': 'bundle', 'max_output_bytes': 65536}},
            {'id': 'corrected', 'kind': 'text_exact', 'parameters': {'path': 'corrected.txt', 'text': 'corregido'}}]}
        plan = self.learning.prepare_steps('Agrupar y completar entrega', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'input.txt', 'content': 'v1'}}],
            'repair-admission', goal_spec=goal)
        done = self.learning.execute(plan['operation_id'], approved=True)
        prepared = self.learning.prepare_goal_progress(done['operation_id'], done['plan_hash'])
        return self.learning.execute(prepared['operation_id'], approved=True, plan_hash=prepared['plan_hash']) if execute_bundle else prepared

    def repair_writer(self, plan, change_goal=False):
        class RepairModel:
            def route(self, request):
                return {'ok': True, 'message': {'content': json.dumps({'title': 'Entrega corregida', 'steps': [
                    {'command_id': 'axx.artifact.write', 'inputs': {'path': 'corrected.txt', 'content': 'corregido'}}]})},
                    'route': {'upstream_attempts': 1, 'attempt_budget_used': 1}}
        self.learning.adapter = RepairModel()
        goal = {'intent': 'Entrega corregida', 'criteria': [
            {'id': 'corrected', 'kind': 'text_exact', 'parameters': {'path': 'corrected.txt', 'text': 'corregido'}}]}
        return self.learning.repair(plan['operation_id'], text='Descartar el sufijo pendiente y completar la entrega corregida',
            **({'goal_spec': goal, 'goal_revision': plan['goal_revision']} if change_goal else {}))

    def test_repair_discards_pending_admission_preserves_history_and_still_requires_new_hash(self):
        before = self.bundle_pending()
        prefix = copy.deepcopy(before['step_records'][:1])
        (self.executor.workspace_root / 'input.txt').write_text('v2')
        repaired = self.repair_writer(before, change_goal=True)
        self.assertEqual(repaired['state'], 'awaiting_approval', repaired)
        self.assertEqual(repaired.get('goal_progress_admissions', []), [])
        self.assertNotIn('goal_progress', repaired)
        history = repaired['revisions'][-1]
        self.assertEqual(history['goal_progress_admissions'], before['goal_progress_admissions'])
        self.assertEqual(history['goal_progress'], before['goal_progress'])
        self.assertEqual(history['plan_hash'], before['plan_hash'])
        self.assertEqual(history['step_records'], before['step_records'])
        self.assertEqual(repaired['step_records'][:1], prefix)
        self.assertEqual(repaired['operation_id'], before['operation_id'])
        self.assertEqual(repaired['model_calls_used'], before['model_calls_used'] + 1)
        with self.assertRaises(ValueError): self.learning.execute(repaired['operation_id'], approved=True)
        with self.assertRaises(ValueError): self.learning.resume(repaired['operation_id'], approved=True)
        with self.assertRaises(ValueError): self.learning.execute(repaired['operation_id'], approved=True, plan_hash=before['plan_hash'])
        self.assertEqual(len(self.executor.list_operations()), 1)
        final = self.learning.execute(repaired['operation_id'], approved=True, plan_hash=repaired['plan_hash'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertEqual(final['step_records'][:1], prefix)
        self.assertEqual((self.executor.workspace_root / 'corrected.txt').read_text(), 'corregido')
        self.assertEqual((self.executor.workspace_root / 'input.txt').read_text(), 'v2')
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertFalse((self.executor.workspace_root / 'bundle').exists())

    def test_repair_unchanged_goal_keeps_admission_of_verified_prefix(self):
        before = self.bundle_pending(execute_bundle=True)
        self.assertEqual(before['state'], 'goal_pending')
        repaired = self.repair_writer(before)
        self.assertEqual(repaired['state'], 'awaiting_approval', repaired)
        self.assertEqual(repaired['goal_progress_admissions'], before['goal_progress_admissions'])
        self.assertEqual(repaired['revisions'][-1]['goal_progress_admissions'], before['goal_progress_admissions'])
        self.assertNotIn('goal_progress', repaired)
        self.assertEqual(repaired['goal_spec'], before['goal_spec'])
        self.assertEqual(repaired['step_records'][:2], before['step_records'])
        final = self.learning.execute(repaired['operation_id'], approved=True, plan_hash=repaired['plan_hash'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertEqual(final['step_records'][:2], before['step_records'])
        self.assertEqual(len(self.executor.list_operations()), 3)
        (self.executor.workspace_root / 'input.txt').write_text('v2')
        with self.assertRaises(ValueError): self.learning._assert_progress_inputs(final, threading.Event())

    def test_repair_unchanged_goal_discards_admission_of_removed_pending_step(self):
        before = self.bundle_pending()
        (self.executor.workspace_root / 'input.txt').write_text('v2')
        repaired = self.repair_writer(before)
        self.assertEqual(repaired['state'], 'awaiting_approval', repaired)
        self.assertEqual(repaired.get('goal_progress_admissions', []), [])
        self.assertEqual(repaired['goal_spec'], before['goal_spec'])
        self.assertNotIn('goal_progress', repaired)
        self.assertEqual(repaired['revisions'][-1]['goal_progress_admissions'], before['goal_progress_admissions'])
        final = self.learning.execute(repaired['operation_id'], approved=True, plan_hash=repaired['plan_hash'])
        self.assertEqual(final['state'], 'goal_pending', final)
        self.assertEqual(final['step_records'][:1], before['step_records'][:1])
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertFalse((self.executor.workspace_root / 'bundle').exists())

    def test_explicit_new_goal_retires_admission_of_verified_prefix(self):
        before = self.bundle_pending(execute_bundle=True)
        (self.executor.workspace_root / 'input.txt').write_text('v2')
        repaired = self.repair_writer(before, change_goal=True)
        self.assertEqual(repaired['state'], 'awaiting_approval', repaired)
        self.assertEqual(repaired.get('goal_progress_admissions', []), [])
        self.assertEqual(repaired['revisions'][-1]['goal_progress_admissions'], before['goal_progress_admissions'])
        self.assertEqual(repaired['step_records'][:2], before['step_records'])
        final = self.learning.execute(repaired['operation_id'], approved=True, plan_hash=repaired['plan_hash'])
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertEqual(final['step_records'][:2], before['step_records'])
        self.assertEqual(len(self.executor.list_operations()), 3)

    def test_http_prepare_progress_and_exact_approval_reach_real_service(self):
        from backend.server import AxxBridgeHandler, ThreadedHTTPServer
        class Handler(AxxBridgeHandler):
            learning = self.learning
            commands = self.commands
            chats = None
            def log_message(self, *args): pass
        server = ThreadedHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def post(action, body):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/axx-api/learning/{action}',
                data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + server.host_token,
                    'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)
        try:
            template = self.prepare('template')
            plan = post('prepare', {'text': 'HTTP mission', 'operation_id': 'http-mission',
                'steps': template['steps'], 'goal_spec': template['goal_spec']})
            done = post('execute', {'operation_id': plan['operation_id'], 'approved': True, 'plan_hash': plan['plan_hash']})
            self.assertEqual(done['state'], 'goal_pending')
            prepared = post('goal-progress', {'operation_id': done['operation_id'], 'plan_hash': done['plan_hash'],
                'criterion_id': done['goal_progress']['criterion_id'], 'candidate_hash': done['goal_progress']['fingerprint']})
            with self.assertRaises(urllib.error.HTTPError) as rejection:
                post('execute', {'operation_id': done['operation_id'], 'approved': True, 'plan_hash': done['plan_hash']})
            self.assertEqual(rejection.exception.code, 400)
            self.assertFalse((self.executor.workspace_root / 'delivery.txt').exists())
            final = post('execute', {'operation_id': done['operation_id'], 'approved': True, 'plan_hash': prepared['plan_hash']})
            self.assertTrue(final['mission']['completed'], final)
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
