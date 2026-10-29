"""Full mission grants use the existing planner and real temporary artifacts."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.action_learning import ActionLearning
from backend.anticipation import AnticipationService, MISSION_CAPABILITY
from backend.commands import CommandService


class NoInference:
    calls = 0
    def route(self, request):
        self.calls += 1
        raise AssertionError('A grant cannot initiate provider inference')


class MissionGrantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = NoInference()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.service = AnticipationService(self.commands)
        self.learning.anticipation = self.service
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.commands.mission_guard = self.learning.assert_dispatch_context
        self.executor.result_filter = self.service.filter_result
        self.service.configure({'profile': 'full', 'profiles': {'full': {'cooldown_seconds': 0,
            'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}}})

    def tearDown(self):
        self.learning.close(); self.service.close(); self.commands.close(); self.executor.close(); self.temp.cleanup()

    def plan(self, name='result.txt', content='authorized new output', steps=None, task='task-a'):
        return self.learning.prepare_steps('Guardar y verificar', steps or [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': name, 'content': content}},
            {'command_id': 'axx.file.sha256', 'inputs': {}, 'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}],
            conversation_id=task)

    def grant(self, **changes):
        body = {'capability': MISSION_CAPABILITY, 'task_id': 'task-a', 'root': str(self.executor.workspace_root),
                'command_ids': ['axx.artifact.write', 'axx.file.sha256'], 'expires_at': None, 'lifetime': 'until_revoked'}
        body.update(changes)
        return self.service.grant(body)

    def authorized(self, plan, grant):
        return plan | {'initiative_authorization': {'grant_id': grant['grant_id'],
            'admitted_plan_hash': plan['plan_hash'], 'authorized_at': time.time()}}

    def run_granted(self, plan, grant):
        return self.learning.execute_with_grant(plan['operation_id'], grant['grant_id'], plan['plan_hash'])

    def test_persistent_grant_covers_future_plans_with_dynamic_verified_bindings(self):
        grant = self.grant()
        for name, content in [('first.txt', 'first human scope'), ('second.txt', 'different content in the same scope')]:
            plan = self.plan(name, content)
            result = self.run_granted(plan, grant)
            self.assertEqual(result['state'], 'succeeded', result)
            self.assertTrue(result['postconditions_passed'])
            self.assertEqual((self.executor.workspace_root / name).read_text(), content)
        self.assertEqual(len(self.executor.list_operations()), 4)
        self.assertEqual(self.model.calls, 0)

    def test_explicitly_customized_profile_uses_effective_mode_and_still_requires_grant(self):
        self.service.configure({'profile': 'copiloto'})
        grant = self.grant()
        plan = self.plan()
        with self.assertRaises(ValueError): self.run_granted(plan, grant)
        self.service.configure({'profiles': {'copiloto': {'mode': 'EXECUTE'}}})
        with self.assertRaises(ValueError):
            self.learning.execute_with_grant(plan['operation_id'], 'missing-grant', plan['plan_hash'])
        self.assertEqual(self.run_granted(plan, grant)['state'], 'succeeded')
        self.assertEqual(self.service.status()['profiles']['discreto']['mode'], 'OFF')

    def test_mission_grant_is_hash_task_and_command_bound_before_any_prefix(self):
        plan = self.plan()
        grant = self.grant(lifetime='mission', learning_plan_id=plan['operation_id'], reviewed_plan_hash=plan['plan_hash'])
        other = self.plan('other.txt')
        with self.assertRaises(ValueError): self.run_granted(other, grant)
        with self.assertRaises(ValueError): self.run_granted(self.plan('foreign.txt', task='task-b'), grant)
        limited = self.grant(command_ids=['axx.artifact.write'])
        with self.assertRaises(ValueError): self.run_granted(plan, limited)
        forbidden = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'prefix.txt', 'content': 'must not exist'}},
                                    {'command_id': 'axx.desktop.open_app', 'inputs': {'app': 'notepad'}}])
        with self.assertRaises(ValueError): self.run_granted(forbidden, grant)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse((self.executor.workspace_root / 'prefix.txt').exists())

    def test_mission_without_chat_uses_its_existing_plan_identity_as_task(self):
        plan = self.learning.prepare_steps('standalone output', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'standalone.txt', 'content': 'standalone'}}])
        grant = self.grant(task_id=plan['operation_id'], lifetime='mission', learning_plan_id=plan['operation_id'],
            reviewed_plan_hash=plan['plan_hash'], command_ids=['axx.artifact.write'])
        self.assertEqual(self.run_granted(plan, grant)['state'], 'succeeded')

    def test_exact_subset_constraints_and_each_resource_root_are_enforced(self):
        grant = self.grant(parameter_constraints={'axx.artifact.write': {'content': 'fixed literal'}})
        with self.assertRaises(ValueError): self.run_granted(self.plan(content='different'), grant)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.run_granted(self.plan(content='fixed literal'), grant)['state'], 'succeeded')
        subfolder = self.executor.workspace_root / 'limited'; subfolder.mkdir()
        narrow = self.grant(root=str(subfolder))
        with self.assertRaises(ValueError): self.run_granted(self.plan('outside.txt'), narrow)
        read = self.root / 'read'; read.mkdir(); source = read / 'source.txt'; source.write_text('source')
        reader = self.plan(steps=[{'command_id': 'axx.file.sha256', 'inputs': {'path': str(source)}}])
        with self.assertRaises(ValueError): self.run_granted(reader, self.grant(command_ids=['axx.file.sha256']))
        self.assertEqual(self.run_granted(reader, self.grant(command_ids=['axx.file.sha256'], read_roots=[str(read)]))['state'], 'succeeded')

    def test_downshift_revocation_and_expiry_stop_the_next_real_step(self):
        for change in ('revoke', 'downshift', 'expire'):
            with self.subTest(change=change):
                self.service.configure({'profile': 'full'})
                grant = self.grant(expires_at=time.time() + 3600)
                plan = self.plan(change + '.txt')
                run = self.learning._run_step
                def stop_after_first(*args, **kwargs):
                    result = run(*args, **kwargs)
                    if args[1]['command_id'] == 'axx.artifact.write':
                        if change == 'revoke': self.service.revoke(grant['grant_id'])
                        elif change == 'downshift': self.service.configure({'profile': 'copiloto'})
                        else: self.service.clock = lambda: time.time() + 7200
                    return result
                before = len(self.executor.list_operations())
                with patch.object(self.learning, '_run_step', side_effect=stop_after_first):
                    result = self.run_granted(plan, grant)
                self.assertEqual(result['state'], 'failed', result)
                self.assertTrue((self.executor.workspace_root / (change + '.txt')).is_file())
                self.assertEqual(len(self.executor.list_operations()), before + 1)
                self.service.clock = time.time

    def test_session_expires_on_service_restart_while_persistent_grant_survives(self):
        session, persistent = self.grant(lifetime='session'), self.grant()
        self.service.close()
        self.service = AnticipationService(self.commands)
        self.learning.anticipation = self.service
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.executor.result_filter = self.service.filter_result
        plan = self.plan()
        with self.assertRaises(ValueError): self.run_granted(plan, session)
        session_status = next(row for row in self.service.status()['grants'] if row['grant_id'] == session['grant_id'])
        self.assertFalse(session_status['active'])
        self.assertEqual(session_status['inactive_reason'], 'session_ended')
        self.assertEqual(self.run_granted(plan, persistent)['state'], 'succeeded')

    def test_one_action_claim_is_atomic_and_same_operation_is_idempotent(self):
        grant = self.grant(lifetime='one_action', command_ids=['axx.artifact.write'])
        plan = self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'one.txt', 'content': 'one'}}])
        plan = self.authorized(plan, grant)
        plan.update(state='running', approved_hash=plan['plan_hash'])
        plan['step_records'][0]['state'] = 'running'
        with self.learning.lock: self.learning._save(plan)
        op = plan['step_records'][0]['operation_id']
        for _ in range(2):
            reference = self.service.authorize_mission_step(plan, plan['steps'][0], plan['steps'][0]['inputs'], op, claim=True)
            self.assertEqual(reference['grant_id'], grant['grant_id'])
        consumed = next(row for row in self.service.status()['grants'] if row['grant_id'] == grant['grant_id'])
        self.assertEqual(consumed['inactive_reason'], 'consumed')
        other = self.plan('two.txt', steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': 'two.txt', 'content': 'two'}}])
        with self.assertRaises(ValueError): self.run_granted(other, grant)
        self.assertEqual(self.executor.list_operations(), [])

    def test_two_services_cannot_claim_one_action_for_different_operations(self):
        grant = self.grant(lifetime='one_action', command_ids=['axx.artifact.write'])
        plans = []
        for name in ('left', 'right'):
            plan = self.authorized(self.plan(steps=[{'command_id': 'axx.artifact.write', 'inputs': {'path': name, 'content': name}}]), grant)
            plan.update(state='running', approved_hash=plan['plan_hash'])
            plan['step_records'][0]['state'] = 'running'
            with self.learning.lock: self.learning._save(plan)
            plans.append(plan)
        other = AnticipationService(self.commands)
        gate, outcomes = threading.Barrier(2), []
        def claim(service, plan):
            gate.wait()
            try:
                service.authorize_mission_step(plan, plan['steps'][0], plan['steps'][0]['inputs'],
                    plan['step_records'][0]['operation_id'], claim=True)
                outcomes.append('claimed')
            except ValueError: outcomes.append('denied')
        try:
            workers = [threading.Thread(target=claim, args=args) for args in zip((self.service, other), plans)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(10); self.assertFalse(worker.is_alive())
            self.assertCountEqual(outcomes, ['claimed', 'denied'])
            self.assertEqual(self.executor.list_operations(), [])
        finally: other.close()

    def checkpoint(self, name='checkpoint.txt', interrupted=False):
        plan = self.plan(name)
        run = self.learning._run_step
        def pause_after_first(*args, **kwargs):
            result = run(*args, **kwargs)
            self.learning.pause(plan['operation_id'])
            return result
        with patch.object(self.learning, '_run_step', side_effect=pause_after_first):
            paused = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(paused['state'], 'paused')
        if interrupted:
            self.learning.pause_events[plan['operation_id']].clear()
            paused.update(state='interrupted', pause_requested=False)
            with self.learning.lock: self.learning._save(paused)
        return paused

    def test_full_continues_only_interrupted_prepared_checkpoint_with_preexisting_grant(self):
        self.grant()
        plan = self.checkpoint(interrupted=True)
        self.service.tick()
        item = next(item for item in self.service.suggestions() if item['candidate_kind'] == 'resume_task')
        self.assertEqual(item['state'], 'VERIFIED', item)
        self.assertTrue(item['result']['postconditions_passed'])
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'succeeded')
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertEqual(self.model.calls, 0)

    def test_human_pause_and_later_new_grant_never_reactivate_a_checkpoint(self):
        self.grant()
        paused = self.checkpoint()
        with patch.object(self.learning, 'resume', wraps=self.learning.resume) as resume:
            self.service.tick(); resume.assert_not_called()
        self.assertEqual(self.learning.get(paused['operation_id'])['state'], 'paused')
        # A different task has no matching grant when its interrupted candidate is born.
        self.service.configure({'profile': 'copiloto'})
        interrupted = self.checkpoint('late.txt', interrupted=True)
        with self.service.lock:
            rows = self.service.db.execute('SELECT grant_id FROM anticipation_grants').fetchall()
        for row in rows: self.service.revoke(row[0])
        self.service.configure({'profile': 'full'})
        self.service.tick()
        candidate = next(item for item in self.service.suggestions() if item.get('candidate_kind') == 'resume_task'
                         and item['plan']['learning_operation_id'] == interrupted['operation_id'])
        self.assertFalse(candidate.get('auto_continue', False))
        self.grant()
        self.service.tick()
        self.assertEqual(self.learning.get(interrupted['operation_id'])['state'], 'interrupted')
        self.assertEqual(self.service.status_item(candidate['suggestion_id'])['state'], 'AWAITING_APPROVAL')

    def test_explicit_revalidation_never_becomes_an_autonomous_resume_or_overlap_verification(self):
        self.grant()
        self.service.grant({'capability': 'verify_artifact', 'task_id': 'task-a', 'root': str(self.executor.workspace_root)})
        self.service.configure({'sources': {'folders': True}, 'observation_targets': [
            {'id': 'overlap', 'source': 'folder', 'root': str(self.executor.workspace_root),
             'task_id': 'task-a', 'observe': True, 'retain': True}]})
        self.service.tick()
        plan = self.checkpoint(interrupted=True)
        plan['revalidation'] = {'id': 'trial.version', 'version': 1}
        with self.learning.lock: self.learning._save(plan)
        self.service.clock = lambda: time.time() + 60
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'interrupted')
        event = json.loads(self.service.db.execute("SELECT payload FROM anticipation_events WHERE event_id LIKE 'artifact-%'").fetchone()[0])
        self.assertEqual(event['provenance']['origin'], 'explicit_revalidation')
        self.assertFalse(event['provenance']['human_preference_evidence'])

    def test_prepare_mode_compiles_existing_routine_locally_without_new_effects_or_inference(self):
        source = self.executor.workspace_root / 'known.txt'; source.write_text('same verified fact')
        first = self.learning.prepare_steps('diagnóstico archivo', [{'command_id': 'axx.file.sha256', 'inputs': {'path': str(source)}}], conversation_id='task-a')
        self.assertEqual(self.learning.execute(first['operation_id'], approved=True)['state'], 'succeeded')
        for _ in range(2):
            plan = self.learning.propose('diagnóstico archivo', conversation_id='task-a')
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
        self.service.configure({'profiles': {'full': {'mode': 'PREPARE'}}})
        before = len(self.executor.list_operations())
        self.service.tick()
        item = next(item for item in self.service.suggestions() if item['candidate_kind'] == 'prepare_routine')
        self.assertEqual(item['state'], 'PREPARED', item)
        self.assertTrue(item['preparation_complete'])
        self.assertEqual(item['approval'], 'profile_preparation')
        self.assertEqual(item['feedback']['acceptance'], 'profile_preparation')
        self.assertEqual(item['result']['state'], 'awaiting_approval')
        self.assertEqual(len(self.executor.list_operations()), before)
        self.assertEqual(self.model.calls, 0)

    def test_granted_repetitions_never_inflate_human_preference_or_survive_as_manual_evidence(self):
        source = self.executor.workspace_root / 'stable.txt'; source.write_text('stable content')
        first = self.learning.prepare_steps('diagnóstico con permiso', [
            {'command_id': 'axx.file.sha256', 'inputs': {'path': str(source)}}], conversation_id='task-a')
        self.assertEqual(self.learning.execute(first['operation_id'], approved=True)['state'], 'succeeded')
        grant = self.grant(command_ids=['axx.file.sha256'])
        for _ in range(3):
            plan = self.learning.propose('diagnóstico con permiso', conversation_id='task-a')
            self.assertEqual(self.run_granted(plan, grant)['state'], 'succeeded')
            with self.service.lock: self.assertTrue(self.service._initiated_plan(plan['operation_id']))
        self.service.tick()
        self.assertEqual([item for item in self.service.suggestions() if item['candidate_kind'] == 'prepare_routine'], [])
        self.assertEqual(len(self.executor.list_operations()), 4)
        self.assertEqual(self.model.calls, 0)

    def test_external_verification_requires_exact_observer_consent_and_false_grant_never_runs_auto(self):
        folder = self.root / 'selected'; folder.mkdir()
        target = {'id': 'selected', 'source': 'folder', 'root': str(folder), 'task_id': 'task-a', 'observe': True, 'retain': True}
        self.service.configure({'sources': {'folders': True}, 'observation_targets': [target]})
        grant = self.service.grant({'capability': 'verify_artifact', 'task_id': 'task-a', 'root': str(folder),
            'source_target_id': 'selected', 'metadata_only': True, 'observe_events': False})
        self.service.tick()
        (folder / 'manual.txt').write_text('metadata-only authorization')
        self.service.clock = lambda: time.time() + 60
        self.service.tick()
        item = self.service.suggestions()[0]
        self.assertEqual(item['state'], 'AWAITING_APPROVAL')
        self.assertEqual(self.executor.list_operations(), [])
        self.assertFalse(grant['observe_events'])
        self.assertEqual(self.service.accept(item['suggestion_id'], item['plan_hash'])['state'], 'VERIFIED')
        self.service.grant({'capability': 'verify_artifact', 'task_id': 'task-a', 'root': str(folder),
            'source_target_id': 'selected', 'metadata_only': True, 'observe_events': True})
        self.service.tick()
        self.assertEqual(len(self.executor.list_operations()), 1)
        (folder / 'automatic.txt').write_text('new event under existing permission')
        self.service.clock = lambda: time.time() + 120
        self.service.tick()
        self.assertEqual(len(self.executor.list_operations()), 2)
        automatic = next(row for row in self.service.suggestions() if row['plan']['inputs']['path'].endswith('automatic.txt'))
        self.assertEqual(automatic['state'], 'VERIFIED')
        self.assertEqual(automatic['approval'], 'persistent')
        target['retain'] = False
        self.service.configure({'observation_targets': [target]})
        with self.assertRaises(ValueError):
            self.service.grant({'capability': 'verify_artifact', 'task_id': 'task-a', 'root': str(folder),
                'source_target_id': 'selected', 'metadata_only': True})

    def test_bad_grant_shapes_physical_categories_and_unknown_adapters_fail_closed(self):
        for change in ({'command_ids': ['axx.desktop.window.focus']}, {'command_ids': ['axx.shell.cmd']},
            {'command_ids': ['axx.mcp.external']}, {'command_ids': ['axx.convert.file']}, {'command_ids': [{}]},
            {'parameter_constraints': {'axx.artifact.write': {'content': 5}}},
            {'parameter_constraints': {'axx.artifact.write': {'unknown': True}}},
            {'lifetime': 'mission'}, {'lifetime': 'forever'}, {'root': str(self.root)}, {'read_roots': 'all'}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.grant(**change)
        capability = self.service.status()['capabilities']['mission_steps']
        self.assertEqual(capability['parameter_constraints'], 'exact_subset')
        self.assertFalse(capability['provider_inference'])
        self.assertEqual(capability['workspace_root'], str(self.executor.workspace_root))
        self.assertNotIn('axx.desktop.open_app', [row['command_id'] for row in capability['commands']])

    def test_helper_rejects_tampered_hash_inputs_and_noncurrent_dispatch_without_lock_inversion(self):
        grant = self.grant()
        plan = self.authorized(self.plan(), grant)
        step, op = plan['steps'][0], plan['step_records'][0]['operation_id']
        changed = copy.deepcopy(plan); changed['steps'][0]['inputs']['content'] = 'changed'
        with self.assertRaises(ValueError): self.service.authorize_mission_step(changed, changed['steps'][0], changed['steps'][0]['inputs'], op)
        with self.assertRaises(ValueError): self.service.authorize_mission_step(plan, step, step['inputs'] | {'content': 'changed'}, op)
        with self.assertRaises(ValueError): self.service.authorize_mission_step(plan, step, step['inputs'], op, claim=True)
        with patch.object(self.learning, 'get', side_effect=AssertionError('No learning lock APIs under policy lock')), \
             patch.object(self.commands, 'get', side_effect=AssertionError('No command lock APIs under policy lock')):
            with self.commands.lock, self.executor.lock:
                self.assertEqual(self.service.authorize_mission_step(plan, step, step['inputs'], op)['grant_id'], grant['grant_id'])
        self.learning.pause(plan['operation_id'])
        with self.assertRaises(ValueError):
            self.service.authorize_mission_step(plan, step, step['inputs'], op)


if __name__ == '__main__': unittest.main()
