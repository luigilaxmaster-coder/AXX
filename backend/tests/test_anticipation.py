"""Real temporary artifacts through the production journal and executor."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService, CAPABILITY, ROUTINE, canonical
from backend.commands import CommandService
from backend.action_learning import ActionLearning


class AnticipationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.service = AnticipationService(self.commands)
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.sequence = 0
        self.learning = None

    def tearDown(self):
        if self.learning:
            self.learning.close()
        self.service.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def configure(self, profile='copiloto', **changes):
        settings = {'profiles': {name: {'cooldown_seconds': 0} for name in ('discreto', 'copiloto', 'full')}}
        settings.update(profile=profile, **changes)
        return self.service.configure(settings)

    def write(self, task='task-a', content='archivo de ensayo'):
        self.sequence += 1
        operation = 'writer-' + str(self.sequence)
        prepared = self.commands.prepare('axx.artifact.write', {'path': str(self.sequence) + '.txt', 'content': content}, operation_id=operation, conversation_id=task)
        result = self.commands.execute(prepared['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        return result

    def propose(self, task='task-a'):
        self.write(task)
        self.service.tick()
        return self.service.suggestions(task)[0]

    def grant(self, task='task-a', **values):
        return self.service.grant({'task_id': task, 'capability': CAPABILITY,
            'root': str(self.executor.workspace_root), 'expires_at': None, **values})

    def verifications(self):
        return [op for op in self.executor.list_operations(100) if op['tool_name'] == 'file_inspection']

    def restart(self):
        self.service.close()
        self.service = AnticipationService(self.commands)
        self.commands.dispatch_guard = self.service.dispatch_guard

    def test_three_profiles_have_distinct_real_outcomes(self):
        self.configure('discreto')
        self.write()
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.verifications(), [])
        self.configure('copiloto')
        suggestion = self.propose()
        self.assertEqual(suggestion['state'], 'AWAITING_APPROVAL')
        self.assertEqual(self.verifications(), [])
        result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertEqual(result['state'], 'VERIFIED')
        self.assertEqual(result['result']['output']['files'][0]['sha256'], hashlib.sha256('archivo de ensayo'.encode()).hexdigest())
        self.configure('full')
        self.grant()
        self.write()
        results = self.service.tick()
        self.assertEqual(results[0]['state'], 'VERIFIED')
        self.assertEqual(len(self.verifications()), 2)
        self.assertEqual(self.service.status()['metrics']['model_calls'], 0)

    def test_full_without_grant_never_reads_and_permission_is_task_bound(self):
        self.configure('full')
        self.grant('task-a')
        suggestion = self.propose('task-b')
        self.assertEqual(suggestion['state'], 'AWAITING_APPROVAL')
        self.assertEqual(self.verifications(), [])
        self.assertEqual(self.service.status('task-b')['grants'], [])
        self.assertEqual(self.service.status('task-a')['suggestions'], [])

    def test_restart_preserves_profile_grant_suppression_and_no_repeat(self):
        self.configure('full')
        self.grant()
        suggestion = self.propose()
        self.assertEqual(suggestion['state'], 'VERIFIED')
        self.service.feedback(suggestion['suggestion_id'], 'suppress')
        self.restart()
        self.assertEqual(self.service.status()['profile'], 'full')
        self.assertEqual(len(self.service.status()['grants']), 1)
        self.write()
        self.service.tick()
        self.assertEqual(len(self.verifications()), 1)
        self.assertEqual(len(self.service.suggestions()), 1)
        self.assertEqual(self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])['state'], 'VERIFIED')

    def test_wrong_hash_mutation_and_identity_replacement_never_dispatch(self):
        self.configure()
        suggestion = self.propose()
        with self.assertRaises(ValueError):
            self.service.accept(suggestion['suggestion_id'], '0' * 64)
        path = Path(suggestion['plan']['inputs']['path'])
        path.write_text('contenido cambiado')
        result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertEqual(result['state'], 'FAILED')
        self.assertEqual(result['context_state'], 'stale')
        self.assertEqual(self.verifications(), [])
        second = self.propose()
        path = Path(second['plan']['inputs']['path'])
        content = path.read_bytes()
        replacement = path.with_suffix('.new')
        replacement.write_bytes(content)
        replacement.replace(path)
        self.assertEqual(self.service.accept(second['suggestion_id'], second['plan_hash'])['state'], 'FAILED')
        self.assertEqual(self.verifications(), [])

    def test_changed_file_at_dispatch_boundary_fails_without_executor_receipt(self):
        self.configure()
        suggestion = self.propose()
        execute = self.commands.execute
        def mutate(operation_id, *args, **kwargs):
            Path(suggestion['plan']['inputs']['path']).write_text('cambio después de aceptar')
            return execute(operation_id, *args, **kwargs)
        with patch.object(self.commands, 'execute', side_effect=mutate):
            result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertEqual(result['state'], 'FAILED')
        self.assertEqual(result['result']['error']['code'], 'DISPATCH_REJECTED')
        self.assertEqual(self.verifications(), [])

    def test_same_bytes_replaced_after_guard_never_claims_original_identity(self):
        self.configure()
        suggestion = self.propose()
        original = self.executor.execute_action
        def replace(tool, *args, **kwargs):
            path = Path(suggestion['plan']['inputs']['path'])
            replacement = path.with_suffix('.replacement')
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
            return original(tool, *args, **kwargs)
        with patch.object(self.executor, 'execute_action', side_effect=replace):
            result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertEqual(result['state'], 'FAILED')
        self.assertEqual(result['result']['state'], 'succeeded')

    def test_reserved_operation_cannot_dispatch_a_different_command(self):
        self.configure()
        suggestion = self.propose()
        path = self.executor.workspace_root / 'foreign.txt'
        self.commands.prepare('axx.artifact.write', {'path': 'foreign.txt', 'content': 'unexpected'},
            operation_id=suggestion['operation_id'], conversation_id='task-a', delivery_mode='background')
        original = self.commands.prepare
        def foreign(*args, **kwargs):
            result = self.commands.execute(suggestion['operation_id'], approved=True)
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')
            return original(*args, **kwargs)
        with patch.object(self.commands, 'prepare', side_effect=foreign):
            self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertFalse(path.exists())
        self.assertEqual(self.verifications(), [])

    def test_duplicate_accept_and_two_service_claims_execute_once(self):
        self.configure()
        suggestion = self.propose()
        other = AnticipationService(self.commands)
        barrier = threading.Barrier(2)
        results = []
        def accept(service):
            barrier.wait(timeout=3)
            results.append(service.accept(suggestion['suggestion_id'], suggestion['plan_hash']))
        threads = [threading.Thread(target=accept, args=(service,)) for service in (self.service, other)]
        try:
            for thread in threads: thread.start()
            for thread in threads: thread.join(5)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(results), 2)
            self.assertEqual(len(self.verifications()), 1)
            result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
            self.assertEqual(result['state'], 'VERIFIED')
            self.assertTrue(result['replayed'])
        finally:
            other.close()

    def test_new_service_preserves_another_live_owners_claim(self):
        self.configure()
        suggestion = self.propose()
        original = self.commands.prepare
        observed = []
        def inspect(*args, **kwargs):
            other = AnticipationService(self.commands)
            try:
                observed.append(other.status_item(suggestion['suggestion_id'])['state'])
            finally:
                other.close()
            return original(*args, **kwargs)
        with patch.object(self.commands, 'prepare', side_effect=inspect):
            result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertEqual(observed, ['EXECUTING'])
        self.assertEqual(result['state'], 'VERIFIED')

    def test_downshift_revocation_cancel_and_global_pause_do_not_revive(self):
        self.configure()
        suggestion = self.propose()
        self.service.configure({'profile': 'discreto'})
        self.assertEqual(self.service.status_item(suggestion['suggestion_id'])['state'], 'CANCELLED')
        self.service.configure({'profile': 'full'})
        grant = self.grant()
        self.service.tick()
        self.assertEqual(self.verifications(), [])
        self.configure('copiloto')
        queued = self.propose()
        self.service.cancel(queued['suggestion_id'])
        self.assertEqual(self.service.accept(queued['suggestion_id'], queued['plan_hash'])['state'], 'CANCELLED')
        self.service.pause()
        self.write()
        self.service.tick()
        self.assertEqual(len(self.service.suggestions()), 2)
        self.assertTrue(self.service.status()['observation_paused'])
        self.service.revoke(grant['grant_id'])
        self.assertTrue(self.service.status()['grants'][0]['revoked'])

    def test_revocation_while_queued_for_executor_prevents_dispatch(self):
        self.configure('full')
        grant = self.grant()
        self.write()
        entered = threading.Event()
        original = self.commands.execute
        def execute(operation_id, *args, **kwargs):
            entered.set()
            return original(operation_id, *args, **kwargs)
        with self.executor.lock, patch.object(self.commands, 'execute', side_effect=execute):
            worker = threading.Thread(target=self.service.tick)
            worker.start()
            self.assertTrue(entered.wait(3))
            self.service.revoke(grant['grant_id'])
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.verifications(), [])
        self.assertEqual(self.service.suggestions()[0]['state'], 'CANCELLED')

    def test_scoped_conflict_and_exclusion_abstain(self):
        self.configure('full', scopes=[{'task_id': 'task-a', 'profile': 'full'},
            {'root': str(self.executor.workspace_root), 'profile': 'copiloto'}])
        self.grant()
        self.write()
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])
        self.configure('full', scopes=[{'task_id': 'task-a', 'exclude': True}])
        self.write()
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.verifications(), [])

    def test_expiry_no_backfill_and_profile_upgrade_never_executes_old_plan(self):
        self.write()
        self.configure()
        self.service.tick()
        # Discreto's already generated artifact is not eligible for a later profile.
        self.assertEqual(self.service.suggestions(), [])
        suggestion = self.propose()
        self.service.configure({'profile': 'full'})
        self.grant()
        self.service.tick()
        self.assertEqual(self.verifications(), [])
        self.service.clock = lambda: time.time() + 600
        self.service.tick()
        self.assertEqual(self.service.status_item(suggestion['suggestion_id'])['state'], 'EXPIRED')

    def test_new_grant_does_not_automatically_accept_an_old_full_proposal(self):
        self.configure('full')
        suggestion = self.propose()
        self.grant()
        self.service.tick()
        self.assertEqual(self.verifications(), [])
        self.assertEqual(self.service.status_item(suggestion['suggestion_id'])['state'], 'AWAITING_APPROVAL')
        self.write()
        self.service.tick()
        self.assertEqual(len(self.verifications()), 1)

    def test_terminal_card_can_hide_without_changing_verified_receipt(self):
        self.configure()
        suggestion = self.propose()
        result = self.service.accept(suggestion['suggestion_id'], suggestion['plan_hash'])
        self.assertEqual(result['state'], 'VERIFIED')
        self.service.feedback(suggestion['suggestion_id'], 'dismiss')
        hidden = self.service.suggestions()[0]
        self.assertFalse(hidden['visible'])
        self.assertEqual(hidden['state'], 'VERIFIED')
        self.assertEqual(hidden['result'], result['result'])

    def test_event_retention_follows_its_profile_instead_of_longest_profile(self):
        self.configure(profiles={'copiloto': {'retention_days': 1, 'cooldown_seconds': 0}})
        self.propose()
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM anticipation_events').fetchone()[0], 1)
        self.service.clock = lambda: time.time() + 2 * 86400
        self.service.tick()
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM anticipation_events').fetchone()[0], 0)

    def test_existing_artifacts_at_first_initialization_are_not_observed(self):
        self.service.close()
        self.commands.dispatch_guard = None
        self.write()
        with self.commands.db:
            for table in ('anticipation_config', 'anticipation_seen'):
                self.commands.db.execute('DELETE FROM ' + table)
        self.service = AnticipationService(self.commands)
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.configure()
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])

    def test_shadow_prepare_silent_cooldown_and_real_shown_budget(self):
        self.configure(profiles={'copiloto': {'mode': 'SHADOW', 'cooldown_seconds': 0}})
        shadow = self.propose()
        self.assertEqual(shadow['state'], 'DETECTED')
        self.assertFalse(shadow['visible'])
        self.service.configure({'profiles': {'copiloto': {'mode': 'PREPARE'}}})
        prepared = self.propose()
        self.assertEqual(prepared['state'], 'PREPARED')
        self.assertEqual(self.verifications(), [])
        self.service.configure({'profiles': {'copiloto': {'mode': 'SUGGEST', 'max_interruptions_hour': 1}}})
        card = self.propose()
        self.assertTrue(card['visible'])
        self.assertEqual(self.service.status()['metrics']['shown'], 0)
        self.service.feedback(card['suggestion_id'], 'shown')
        deferred = self.propose()
        self.assertFalse(deferred['visible'])
        self.assertEqual(self.service.status()['metrics']['shown'], 1)
        self.service.configure({'profiles': {'copiloto': {'cooldown_seconds': 86400}}})
        before = len(self.service.suggestions())
        self.write()
        self.service.tick()
        self.assertEqual(len(self.service.suggestions()), before)

    def test_recovery_after_effect_reconciles_without_reading_again(self):
        self.configure()
        suggestion = self.propose()
        simulated = copy.deepcopy(suggestion) | {'state': 'EXECUTING', 'approval': 'manual', 'accepted_hash': suggestion['plan_hash']}
        with self.service.db:
            self.service._save(simulated)
        self.commands.prepare(suggestion['plan']['command_id'], suggestion['plan']['inputs'], operation_id=suggestion['operation_id'], conversation_id='task-a', delivery_mode='background')
        self.commands.execute(suggestion['operation_id'], approved=True)
        self.assertEqual(len(self.verifications()), 1)
        self.restart()
        self.assertEqual(self.service.status_item(suggestion['suggestion_id'])['state'], 'VERIFIED')
        self.service.tick()
        self.assertEqual(len(self.verifications()), 1)

    def test_crash_before_dispatch_is_uncertain_and_never_retried(self):
        self.configure()
        suggestion = self.propose()
        with self.service.db:
            self.service._save(suggestion | {'state': 'EXECUTING', 'approval': 'manual'})
        self.restart()
        self.assertEqual(self.service.status_item(suggestion['suggestion_id'])['state'], 'UNCERTAIN')
        self.service.tick()
        self.assertEqual(self.verifications(), [])

    def test_foreign_sources_bad_grants_and_unsafe_parameters_fail_closed(self):
        for changes in ({'sources': {'microphone': True}}, {'sources': {'unknown-source': True}},
            {'profiles': {'full': {'cooldown_seconds': -1}}}, {'profile': 'invalid'}, {'scopes': [{}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.configure(changes)
        for values in ({'capability': 'send'}, {'task_id': ''}, {'root': str(self.root)}, {'expires_at': 0}, {'observe_events': 'false'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.grant(**values)

    def test_forget_only_anticipation_memory_and_preserves_command_receipts(self):
        self.configure()
        suggestion = self.propose()
        self.service.feedback(suggestion['suggestion_id'], 'suppress')
        before = len(self.commands.operations())
        result = self.service.forget({'task_id': 'task-a'})
        self.assertEqual(result['forgotten_suggestions'], 1)
        self.assertEqual(len(self.commands.operations()), before)
        self.assertEqual(self.service.suggestions(), [])
        self.assertEqual(self.service.status()['routines'], [])

    def enable_learning(self):
        class Model:
            calls = 0
            def route(model, request):
                model.calls += 1
                return {'ok': True, 'message': {'content': json.dumps({'title': 'Estado local',
                    'steps': [{'command_id': 'axx.system.telemetry', 'inputs': {}}]})}}
        self.model = Model()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning

    def checkpoint(self, steps=None):
        self.enable_learning()
        self.configure()
        plan = self.learning.prepare_steps('crear archivo y comprobar hash', steps or [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'checkpoint.txt', 'content': 'guardado'}},
            {'command_id': 'axx.file.sha256', 'inputs': {}, 'bindings': {'path': {'step': 0, 'path': ['output', 'path']}}}],
            conversation_id='task-a')
        original = self.learning._run_step
        def pause_after_first(*args, **kwargs):
            result = original(*args, **kwargs)
            self.learning.pause(plan['operation_id'])
            return result
        with patch.object(self.learning, '_run_step', side_effect=pause_after_first):
            paused = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(paused['state'], 'paused')
        self.service.tick()
        candidate = next(row for row in self.service.suggestions() if row['candidate_kind'] == 'resume_task')
        return plan, candidate

    def test_checkpoint_prepares_existing_plan_without_repeating_verified_effect(self):
        plan, candidate = self.checkpoint()
        self.assertEqual(candidate['plan']['last_verified_step'], 0)
        before = len(self.executor.list_operations(100))
        get = self.learning.get
        def unlocked_get(*args, **kwargs):
            self.assertFalse(self.service.lock._is_owned(), 'Policy lock must not precede learning lock')
            return get(*args, **kwargs)
        with patch.object(self.learning, 'get', side_effect=unlocked_get):
            prepared = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertEqual(prepared['state'], 'PREPARED')
        self.assertTrue(prepared['preparation_complete'])
        self.assertEqual(prepared['learning_plan_id'], plan['operation_id'])
        self.assertEqual(prepared['result']['state'], 'awaiting_approval')
        self.assertEqual(len(self.executor.list_operations(100)), before)
        self.assertEqual(self.model.calls, 0)

    def test_preparation_cancel_before_body_never_overwrites_cancellation(self):
        plan, candidate = self.checkpoint()
        original = self.service._prepare_existing
        def cancel_first(item):
            self.service.cancel(item['suggestion_id'])
            return original(item)
        with patch.object(self.service, '_prepare_existing', side_effect=cancel_first):
            result = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertEqual(result['state'], 'CANCELLED')
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'paused')

    def test_preparation_cancel_during_body_pauses_existing_plan(self):
        plan, candidate = self.checkpoint()
        resume = self.learning.resume
        def cancel_during(*args, **kwargs):
            result = resume(*args, **kwargs)
            self.service.cancel(candidate['suggestion_id'])
            return result
        with patch.object(self.learning, 'resume', side_effect=cancel_during):
            result = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertEqual(result['state'], 'CANCELLED')
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'paused')

    def test_forget_during_preparation_pauses_plan_without_recreating_context(self):
        plan, candidate = self.checkpoint()
        resume = self.learning.resume
        def forget_during(*args, **kwargs):
            result = resume(*args, **kwargs)
            self.service.forget({'task_id': 'task-a'})
            return result
        with patch.object(self.learning, 'resume', side_effect=forget_during):
            result = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertEqual(result['state'], 'CANCELLED')
        self.assertTrue(result['forgotten'])
        self.assertEqual(self.learning.get(plan['operation_id'])['state'], 'paused')
        self.assertEqual(self.service.suggestions(), [])

    def test_resource_conditioned_preparation_abstains_instead_of_ignoring_targets(self):
        _, candidate = self.checkpoint()
        folder = self.executor.workspace_root / 'excluded'
        folder.mkdir()
        self.service.configure({'scopes': [{'task_id': 'task-a', 'root': str(folder), 'exclude': True}]})
        self.assertEqual(self.service.status_item(candidate['suggestion_id'])['state'], 'CANCELLED')
        self.service.tick()
        self.assertEqual(len([item for item in self.service.suggestions() if item.get('candidate_kind') == 'resume_task']), 1)

    def test_recurring_routine_needs_three_same_task_verified_runs_and_only_prepares(self):
        self.enable_learning()
        self.configure()
        for index in range(3):
            plan = self.learning.propose('prepara un diagnóstico', conversation_id='task-a')
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
            self.service.tick()
            candidates = [row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine']
            if index < 2:
                self.assertEqual(candidates, [])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(len(candidate['plan']['evidence_ids']), 3)
        before = len(self.executor.list_operations(100))
        calls = self.model.calls
        prepared = self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertEqual(prepared['state'], 'PREPARED')
        self.assertEqual(prepared['result']['state'], 'awaiting_approval')
        self.assertEqual(self.model.calls, calls)
        self.assertEqual(len(self.executor.list_operations(100)), before)
        self.assertTrue(self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])['replayed'])

    def test_recurring_evidence_does_not_transfer_between_tasks(self):
        self.enable_learning()
        self.configure()
        for task in ('task-a', 'task-b', 'task-c'):
            plan = self.learning.propose('prepara un diagnóstico', conversation_id=task)
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
        self.service.tick()
        self.assertEqual([row for row in self.service.suggestions() if row.get('candidate_kind') == 'prepare_routine'], [])

    def test_causal_chain_stops_after_one_verification_and_never_infers_preference(self):
        self.configure('full')
        self.grant()
        item = self.propose()
        for _ in range(5):
            self.service.tick()
        self.assertEqual(len(self.service.suggestions()), 1)
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertEqual(item['initiative_chain']['budget'], 1)
        self.assertEqual(item['feedback']['acceptance'], 'persistent_grant')
        self.assertEqual(item['feedback']['usefulness'], 'unknown')
        event = json.loads(self.service.db.execute('SELECT payload FROM anticipation_events').fetchone()[0])
        self.assertEqual(event['provenance']['actor'], 'axx')
        self.assertEqual(event['provenance']['origin'], 'direct_instruction')
        self.assertFalse(event['provenance']['human_preference_evidence'])
        stats = self.service.status()['routines'][0]
        self.assertEqual(stats['technical_verified'], 1)
        self.assertEqual(stats['autonomous_executions'], 1)
        self.assertEqual(stats.get('explicit_acceptances', 0), 0)
        self.assertEqual(stats.get('explicit_useful_feedback', 0), 0)

    def test_acceptance_usefulness_and_correction_are_distinct(self):
        self.configure()
        item = self.propose()
        verified = self.service.accept(item['suggestion_id'], item['plan_hash'])
        self.assertEqual(verified['feedback']['acceptance'], 'explicit')
        self.assertEqual(verified['feedback']['usefulness'], 'unknown')
        self.service.feedback(item['suggestion_id'], 'useful')
        corrected = self.service.feedback(item['suggestion_id'], 'correction')
        self.assertEqual(corrected['state'], 'VERIFIED')
        self.assertEqual(corrected['feedback']['usefulness'], 'corrected')
        self.assertEqual(corrected['feedback']['corrections'], 1)
        self.assertEqual(self.service.feedback(item['suggestion_id'], 'useful')['feedback']['usefulness'], 'corrected')

    def test_correction_required_feedback_is_one_signal_across_retries_restart_and_connections(self):
        self.configure()
        item = self.propose()
        self.service.accept(item['suggestion_id'], item['plan_hash'])
        operations = self.executor.list_operations()
        other = AnticipationService(self.commands)
        barrier, errors = threading.Barrier(2), []
        def report(service):
            try:
                barrier.wait(5)
                service.feedback(item['suggestion_id'], 'correction')
            except BaseException as error:
                errors.append(error)
                barrier.abort()
        workers = [threading.Thread(target=report, args=(service,), daemon=True) for service in (self.service, other)]
        try:
            for worker in workers: worker.start()
            for worker in workers: worker.join(10)
            self.assertFalse(any(worker.is_alive() for worker in workers))
            self.assertEqual(errors, [])
        finally:
            other.close()
        self.restart()
        for _ in range(3):
            corrected = self.service.feedback(item['suggestion_id'], 'correction')
        self.assertEqual(corrected['feedback']['corrections'], 1)
        self.assertEqual(self.service.status()['metrics']['explicit_corrections'], 1)
        self.assertEqual(self.service.feedback(item['suggestion_id'], 'useful')['feedback']['usefulness'], 'corrected')
        self.assertEqual(self.executor.list_operations(), operations)
        second = self.propose('task-b')
        self.service.feedback(second['suggestion_id'], 'correction')
        self.assertEqual(self.service.status()['metrics']['explicit_corrections'], 2)

    def test_legacy_correction_totals_are_preserved_without_counting_new_replays(self):
        self.configure()
        item = self.propose()
        with self.service._policy_transaction(immediate=True):
            legacy = self.service._get(item['suggestion_id'])
            legacy['feedback'].update(usefulness='corrected', corrections=7)
            self.service._save(legacy)
            for _ in range(7): self.service._stats(item['task_id'], item['routine_id'], 'explicit_corrections')
        before = self.service.status()['metrics']['explicit_corrections']
        result = self.service.feedback(item['suggestion_id'], 'correction')
        self.assertEqual(result['feedback']['corrections'], 7)
        self.assertEqual(self.service.status()['metrics']['explicit_corrections'], before)

    def test_anticipation_initiated_runs_never_inflate_routine_preference_evidence(self):
        self.enable_learning()
        self.configure()
        for _ in range(3):
            plan = self.learning.propose('prepara un diagnóstico', conversation_id='task-a')
            self.learning.execute(plan['operation_id'], approved=True)
        self.service.tick()
        candidate = next(item for item in self.service.suggestions() if item['candidate_kind'] == 'prepare_routine')
        self.service.feedback(candidate['suggestion_id'], 'dismiss')
        for index in range(3):
            plan = self.learning.propose('prepara un diagnóstico', operation_id='ant-plan-loop-' + str(index), conversation_id='task-a')
            self.assertEqual(self.learning.execute(plan['operation_id'], approved=True)['state'], 'succeeded')
        self.service.tick()
        candidates = [item for item in self.service.suggestions() if item['candidate_kind'] == 'prepare_routine']
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(candidates[0]['plan']['evidence_ids']), 3)

    def test_forgetting_task_excludes_old_evidence_from_future_derived_routines(self):
        self.enable_learning()
        self.configure()
        for _ in range(3):
            plan = self.learning.propose('prepara un diagnóstico', conversation_id='task-a')
            self.learning.execute(plan['operation_id'], approved=True)
        self.service.tick()
        self.assertEqual(len(self.service.suggestions()), 1)
        self.service.forget({'task_id': 'task-a'})
        self.restart()
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])
        fresh = self.learning.propose('prepara un diagnóstico', conversation_id='task-a')
        self.learning.execute(fresh['operation_id'], approved=True)
        self.service.tick()
        self.assertEqual(self.service.suggestions(), [])

    def test_resumed_original_plan_keeps_causation_after_proposal_retention(self):
        plan, candidate = self.checkpoint([
            {'command_id': 'axx.system.telemetry', 'inputs': {}},
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'after-resume.txt', 'content': 'causa conservada'}}])
        self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        self.assertFalse(plan['operation_id'].startswith('ant-plan-'))
        self.service.clock = lambda: time.time() + 31 * 86400
        self.service._purge()
        self.assertEqual(self.service.suggestions(), [])
        self.assertTrue(self.service._initiated_plan(plan['operation_id']))
        finished = self.learning.execute(plan['operation_id'], approved=True)
        self.assertEqual(finished['state'], 'succeeded')
        self.service.tick()
        event = json.loads(self.service.db.execute('SELECT payload FROM anticipation_events').fetchone()[0])
        self.assertEqual(event['provenance']['origin'], 'suggestion_accepted')
        self.assertEqual(event['provenance']['causation_id'], plan['operation_id'])
        self.assertFalse(event['provenance']['human_preference_evidence'])


if __name__ == '__main__':
    unittest.main()
