"""Mission attention uses real temporary files and the existing durable executor."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService, StaleContext
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.memory import task_memory


class NoModel:
    def route(self, request):
        raise AssertionError('Attention must not initiate inference')


class MissionAttentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = time.time()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, NoModel())
        self.commands.learning = self.learning
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        self.service.configure({'profile': 'copiloto', 'profiles': {
            name: {'cooldown_seconds': 0, 'resources': {'max_tick_ms': 5000, 'max_cpu_ms_tick': 1000}}
            for name in ('discreto', 'copiloto', 'full')}})
        self.sequence = 0

    def wire(self):
        self.learning.anticipation = self.service
        self.commands.dispatch_guard = self.service.dispatch_guard
        self.commands.mission_guard = self.learning.assert_dispatch_context
        self.executor.result_filter = self.service.filter_result

    def tearDown(self):
        self.learning.close()
        self.service.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def mission(self, task='task-a', *, dependencies=(), goal_spec=None, count=3):
        self.sequence += 1
        mid = 'mission-' + str(self.sequence)
        plan = self.learning.prepare_steps('Entrega ' + mid, [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': mid + '-' + str(i) + '.txt', 'content': 'Parte ' + str(i)}}
            for i in range(count)], operation_id=mid, conversation_id=task, project_id='project-a', goal_spec=goal_spec,
            memory_scope=task_memory.snapshot(self.learning.db, task))
        if dependencies:
            # Model-free fixture for the same original scopes inherited by learned plans.
            plan = json.loads(self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', (mid,)).fetchone()[0])
            plan['memory_dependencies'] = list(dependencies)
            self.learning._ready(plan, plan['title'])
            plan = self.learning._save(plan)
        result = self.learning.execute(mid, approved=True, plan_hash=plan['plan_hash'])
        self.assertIn(result['state'], ('succeeded', 'goal_pending'), result)
        self.service.tick()
        return result

    def update_plan(self, mid, **changes):
        with self.learning.db:
            plan = json.loads(self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', (mid,)).fetchone()[0])
            plan.update(changes)
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(plan), mid))

    def group(self, mid, service=None):
        return next(row for row in (service or self.service).status()['mission_attention'] if row['mission_id'] == mid)

    def feedback(self, group, phase='claim', service=None):
        key = group['mission_id'] if phase == 'response' else group['representative_suggestion_id']
        return (service or self.service).feedback(key, {
            'action': 'shown', 'attention_key': group['attention_key'], 'phase': phase,
            **({'response_digest': group['response_digest']} if phase == 'response' else {})})

    def group_feedback(self, group, action):
        return self.service.feedback(group['mission_id'], {'action': action, 'attention_key': group['attention_key']})

    def receipt_count(self):
        return self.service.db.execute('SELECT COUNT(*) FROM anticipation_attention_receipts').fetchone()[0]

    def test_three_real_children_form_one_group_one_charge_and_explicit_exposure(self):
        plan = self.mission()
        before = copy.deepcopy(self.executor.list_operations(100))
        with patch.object(self.learning, 'get', side_effect=AssertionError('Do not acquire the planner through get')), \
                patch.object(self.learning, 'list_plans', side_effect=AssertionError('Do not acquire planner list')):
            group = self.group(plan['operation_id'])
        self.assertEqual(group['category'], 'done')
        self.assertTrue(group['completed'])
        self.assertEqual(len(group['suggestion_ids']), 3)
        self.assertIsNotNone(group['representative_suggestion_id'])
        self.assertTrue(all(row['state'] == 'AWAITING_APPROVAL' for row in self.service.suggestions()))
        self.assertEqual(self.receipt_count(), 0, 'A manual projection is free')
        no_claim = self.feedback(group, 'presented')
        self.assertFalse(no_claim['admission']['accepted'])
        self.assertEqual(no_claim['admission']['reason'], 'not_claimed')
        claimed = self.feedback(group)
        self.assertEqual(claimed['admission'], {'accepted': True, 'new_claim': True, 'presented': False})
        replay = self.feedback(group)
        self.assertTrue(replay['admission']['accepted'])
        self.assertFalse(replay['admission']['new_claim'])
        self.assertTrue(self.feedback(group, 'presented')['admission']['presented'])
        self.assertFalse(self.feedback(group, 'presented')['admission']['new_claim'])
        self.assertEqual(self.receipt_count(), 1)
        self.assertTrue(all('shown_at' not in row for row in self.service.suggestions()))
        metrics = self.service.status()['metrics']
        self.assertEqual((metrics['shown'], metrics['attention_interruptions'], metrics['attention_presented']), (0, 1, 1))
        self.assertEqual(self.executor.list_operations(100), before)
        payload = json.loads(self.service.db.execute('SELECT payload FROM anticipation_attention_receipts').fetchone()[0])
        self.assertNotIn('summary', payload)
        self.assertNotIn('plan', payload)
        self.assertNotIn('request', payload)

    def test_current_mission_state_and_revision_override_stale_children(self):
        goal = {'intent': 'Entrega con criterio final', 'criteria': [
            {'id': 'delivery', 'kind': 'text_exact', 'parameters': {'path': 'delivery.txt', 'text': 'Entrega final'}}]}
        pending = self.mission(goal_spec=goal, count=1)
        old = self.group(pending['operation_id'])
        self.assertEqual(old['category'], 'decision')
        candidate = next(row for row in self.service.suggestions() if row['candidate_kind'] == 'goal_progress')
        self.service.accept(candidate['suggestion_id'], candidate['plan_hash'])
        current = self.group(pending['operation_id'])
        self.assertNotEqual(current['plan_hash'], old['plan_hash'])
        self.assertEqual(current['reason_code'], 'plan_approval')
        stale = self.feedback(old)
        self.assertFalse(stale['admission']['accepted'])
        self.assertEqual(stale['admission']['reason'], 'stale_attention')
        self.assertEqual(self.receipt_count(), 0)
        completed = self.learning.execute(pending['operation_id'], approved=True, plan_hash=current['plan_hash'])
        self.assertTrue(completed['mission']['completed'])
        done = self.group(pending['operation_id'])
        self.assertEqual(done['category'], 'done')
        self.assertEqual(done['plan_hash'], current['plan_hash'])
        self.assertTrue(any(row['state'] == 'AWAITING_APPROVAL' for row in self.service.suggestions()))
        done_key = done['attention_key']
        self.assertEqual(self.group(pending['operation_id'])['attention_key'], done_key, 'Polling does not create a new attention event')
        # These durable-state fixtures retain original effect receipts unchanged.
        self.update_plan(pending['operation_id'], state='needs_input', message='¿Qué destino debo usar?')
        decision = self.group(pending['operation_id'])
        self.assertEqual((decision['category'], decision['reason_code']), ('decision', 'needs_input'))
        self.assertIn('destino', decision['summary'])
        self.update_plan(pending['operation_id'], message='¿Qué carpeta debo usar?')
        self.assertNotEqual(self.group(pending['operation_id'])['attention_key'], decision['attention_key'])
        self.update_plan(pending['operation_id'], state='failed', message='Fallo técnico confirmado')
        self.assertEqual(self.group(pending['operation_id'])['category'], 'problem')
        self.update_plan(pending['operation_id'], state='cancelled', cancel_requested=True)
        self.assertEqual(self.group(pending['operation_id'])['category'], 'progress')

    def test_changed_sealed_plan_cannot_publish_or_acknowledge_old_attention(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        steps = copy.deepcopy(plan['steps'])
        steps[0]['inputs']['content'] = 'A different unapproved request'
        self.update_plan(plan['operation_id'], steps=steps)
        self.assertEqual(self.service.status()['mission_attention'], [])
        for phase in ('claim', 'response'):
            refused = self.feedback(group, phase)
            self.assertFalse(refused['admission']['accepted'])
            self.assertIsNone(refused['attention'])
        self.assertEqual(self.receipt_count(), 0)
        self.assertEqual(self.executor.list_operations(100), effects)

    def test_group_dismiss_survives_representative_rotation_restart_and_allows_only_new_key(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        rejected = self.group_feedback(group, 'dismiss')
        self.assertTrue(rejected['admission']['accepted'])
        self.assertFalse(rejected['admission']['new_claim'])
        self.assertFalse(rejected['attention']['interruption']['eligible'])
        self.assertTrue(rejected['attention']['interruption']['dismissed'])
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 0)
        self.assertEqual(self.service.status()['metrics']['attention_response_acknowledgements'], 0)
        self.service.feedback(group['representative_suggestion_id'], 'dismiss')
        rotated = self.group(plan['operation_id'])
        self.assertNotEqual(rotated['representative_suggestion_id'], group['representative_suggestion_id'])
        self.assertEqual(rotated['attention_key'], group['attention_key'])
        self.assertFalse(rotated['interruption']['eligible'])
        self.service.close()
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        restored = self.group(plan['operation_id'])
        self.assertFalse(self.feedback(restored)['admission']['accepted'])
        self.assertTrue(restored['interruption']['dismissed'])
        self.assertTrue(all(row.get('feedback', {}).get('usefulness') == 'unknown' for row in self.service.suggestions()))
        self.update_plan(plan['operation_id'], state='needs_input', message='¿Qué destino necesitas?')
        new = self.group(plan['operation_id'])
        self.assertNotEqual(new['attention_key'], group['attention_key'])
        self.assertFalse(new['interruption']['dismissed'])
        self.assertTrue(new['interruption']['eligible'])
        self.assertEqual(self.executor.list_operations(100), effects)

    def test_mission_suppression_crosses_keys_restore_preserves_dismissal_charge_and_other_routines(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        self.assertTrue(self.feedback(group)['admission']['new_claim'])
        self.group_feedback(group, 'dismiss')
        self.group_feedback(group, 'suppress')
        self.service.close()
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        original = self.group(plan['operation_id'])
        self.assertEqual(original['interruption']['reason'], 'mission_suppressed')
        original_restored = self.group_feedback(original, 'restore')['attention']
        self.assertFalse(original_restored['interruption']['mission_suppressed'])
        self.assertTrue(original_restored['interruption']['dismissed'])
        self.assertFalse(original_restored['interruption']['eligible'])
        self.group_feedback(original_restored, 'suppress')
        self.update_plan(plan['operation_id'], state='needs_input', message='¿Qué carpeta quieres?')
        # A new sealed revision keeps its mission-level suppression, without
        # changing or replaying any of the original executor receipts.
        with self.learning.db:
            revised = json.loads(self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', (plan['operation_id'],)).fetchone()[0])
            revised['goal_revision'] = revised.get('goal_revision', 1) + 1
            revised['plan_hash'] = self.learning._plan_hash(revised)
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(revised), revised['operation_id']))
        changed = self.group(plan['operation_id'])
        self.assertNotEqual(changed['attention_key'], group['attention_key'])
        self.assertTrue(changed['interruption']['mission_suppressed'])
        self.assertFalse(self.feedback(changed)['admission']['accepted'])
        stale = self.group_feedback(original, 'restore')
        self.assertFalse(stale['admission']['accepted'])
        with self.service.db:
            self.service.db.execute('INSERT INTO anticipation_suppressions VALUES (?,?)', (group['task_id'], 'other-routine'))
        restored = self.group_feedback(changed, 'restore')['attention']
        self.assertTrue(restored['interruption']['eligible'])
        self.assertFalse(restored['interruption']['mission_suppressed'])
        self.assertTrue(self.service._suppressed(group['task_id'], 'other-routine'))
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 1)
        self.assertEqual(self.service.status()['grants'], [])
        self.assertTrue(all(row.get('feedback', {}).get('usefulness') == 'unknown' for row in self.service.suggestions()))

    def test_exact_response_digest_changes_long_question_and_compares_current_message_in_transaction(self):
        plan = self.mission()
        first_message = '¿Destino ' + 'á🙂' * 1200 + ' A?'
        second_message = first_message[:-2] + 'B?'
        self.update_plan(plan['operation_id'], state='needs_input', message=first_message, plan_hash=None)
        first = self.group(plan['operation_id'])
        self.assertIsNone(first['plan_hash'])
        self.assertLessEqual(len(first['summary']), 1000)
        self.assertEqual(first['response_digest'], hashlib.sha256(first_message.encode('utf-8')).hexdigest())
        self.update_plan(plan['operation_id'], message=second_message)
        second = self.group(plan['operation_id'])
        self.assertEqual((second['plan_hash'], second['goal_revision']), (first['plan_hash'], first['goal_revision']))
        self.assertNotEqual(second['attention_key'], first['attention_key'])
        self.assertNotEqual(second['response_digest'], first['response_digest'])
        self.assertFalse(self.feedback(first, 'response')['admission']['accepted'])
        self.assertEqual(self.receipt_count(), 0)
        self.update_plan(plan['operation_id'], state='failed', message='Diagnóstico original')
        old = self.group(plan['operation_id'])
        self.update_plan(plan['operation_id'], message='Diagnóstico actualizado')
        current = self.group(plan['operation_id'])
        self.assertEqual(current['attention_key'], old['attention_key'], 'A diagnostic update is not a new interruption')
        refused = self.feedback(old, 'response')
        self.assertEqual(refused['admission']['reason'], 'stale_response')
        self.assertFalse(refused['admission']['accepted'])
        self.assertEqual(self.receipt_count(), 0)
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 0)
        self.assertTrue(self.feedback(current, 'response')['admission']['presented'])
        self.update_plan(plan['operation_id'], message=None)
        self.assertEqual(self.group(plan['operation_id'])['response_digest'], hashlib.sha256(b'').hexdigest())

    def test_two_services_claim_once_and_restart_does_not_repeat_or_execute(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        other = AnticipationService(self.commands, clock=lambda: self.now)
        barrier = threading.Barrier(2)
        results, errors = [], []
        def claim(service):
            try:
                barrier.wait(timeout=3)
                results.append(self.feedback(group, service=service))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=claim, args=(service,)) for service in (self.service, other)]
        try:
            for thread in threads: thread.start()
            for thread in threads: thread.join(10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertTrue(all(row['admission']['accepted'] for row in results))
            self.assertEqual(sum(row['admission']['new_claim'] for row in results), 1)
            self.assertEqual(self.receipt_count(), 1)
        finally:
            other.close()
        self.service.close()
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        restored = self.group(plan['operation_id'])
        self.assertTrue(restored['interruption']['claimed'])
        self.assertFalse(self.feedback(restored)['admission']['new_claim'])
        self.assertEqual(self.executor.list_operations(100), effects)

    def test_mixed_legacy_and_group_budget_does_not_revert_latest_state(self):
        self.service.configure({'profiles': {'copiloto': {'max_interruptions_hour': 2}}})
        command = self.commands.prepare('axx.artifact.write', {'path': 'legacy.txt', 'content': 'Legacy'}, conversation_id='legacy-task')
        self.commands.execute(command['operation_id'], approved=True)
        self.service.tick()
        legacy = self.service.suggestions('legacy-task')[0]
        self.service.feedback(legacy['suggestion_id'], 'shown')
        first = self.mission()
        self.assertTrue(self.feedback(self.group(first['operation_id']))['admission']['new_claim'])
        second = self.mission('task-b')
        deferred = self.group(second['operation_id'])
        self.assertEqual(deferred['interruption']['reason'], 'budget')
        self.assertFalse(self.feedback(deferred)['admission']['accepted'])
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 2)
        self.assertTrue(all(not row['visible'] for row in self.service.suggestions('task-b')))
        self.update_plan(second['operation_id'], state='failed', message='Error actual')
        latest = self.group(second['operation_id'])
        self.assertEqual((latest['category'], latest['interruption']['reason']), ('problem', 'budget'))
        self.assertNotEqual(latest['attention_key'], deferred['attention_key'])
        self.assertEqual(self.service.status()['metrics']['shown'], 1)
        self.service.forget({'task_id': 'legacy-task'})
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 2, 'Forgetting an old shown row does not refund its charge')

    def test_profiles_scopes_suppression_and_expiry_preserve_effects(self):
        plan = self.mission()
        effects = copy.deepcopy(self.executor.list_operations(100))
        self.service.configure({'profile': 'discreto'})
        quiet = self.group(plan['operation_id'])
        self.assertEqual(quiet['category'], 'done')
        self.assertFalse(self.feedback(quiet)['admission']['accepted'])
        self.service.configure({'scopes': [{'task_id': 'task-scoped', 'profile': 'copiloto'}]})
        self.assertFalse(self.group(plan['operation_id'])['interruption']['eligible'], 'A profile upgrade never revives cancelled children')
        scoped_plan = self.mission('task-scoped')
        scoped = self.group(scoped_plan['operation_id'])
        self.assertEqual(scoped['interruption']['profile'], 'copiloto')
        self.assertTrue(scoped['interruption']['eligible'])
        self.service.configure({'profile': 'full', 'scopes': [], 'profiles': {'full': {'interruptions': 'silent'}}})
        full_plan = self.mission('task-full')
        silent = self.group(full_plan['operation_id'])
        self.assertEqual(silent['interruption']['reason'], 'silent')
        self.assertFalse(self.feedback(silent)['admission']['accepted'])
        self.service.configure({'profiles': {'full': {'interruptions': 'cards'}}})
        full = self.group(full_plan['operation_id'])
        self.assertTrue(full['interruption']['eligible'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        self.service.feedback(full['representative_suggestion_id'], 'suppress')
        self.assertFalse(self.group(full_plan['operation_id'])['interruption']['eligible'])
        self.assertEqual(self.executor.list_operations(100), effects)
        self.assertEqual(self.service.status()['grants'], [])
        self.assertEqual(self.receipt_count(), 0)
        self.service.feedback(full['representative_suggestion_id'], 'restore')
        self.now += 301
        expired = self.group(full_plan['operation_id'])
        self.assertEqual(expired['category'], 'done')
        self.assertFalse(expired['interruption']['eligible'])
        self.assertFalse(self.feedback(expired)['admission']['accepted'])

    def test_cooldown_defers_new_interruption_without_hiding_current_state(self):
        first = self.mission()
        second = self.mission('task-b')
        self.assertTrue(self.feedback(self.group(first['operation_id']))['admission']['new_claim'])
        self.service.configure({'profiles': {'copiloto': {'cooldown_seconds': 60}}})
        deferred = self.group(second['operation_id'])
        self.assertEqual((deferred['category'], deferred['interruption']['reason']), ('done', 'cooldown'))
        self.assertFalse(self.feedback(deferred)['admission']['accepted'])
        self.now += 61
        ready = self.group(second['operation_id'])
        self.assertEqual(ready['attention_key'], deferred['attention_key'])
        self.assertTrue(self.feedback(ready)['admission']['new_claim'])

    def test_explicit_response_without_children_is_durable_free_and_allowed_in_discreto(self):
        self.service.configure({'profile': 'discreto'})
        plan = self.learning.prepare_steps('Respuesta solicitada', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'explicit.txt', 'content': 'No ejecutar todavía'}}],
            operation_id='explicit-mission', conversation_id='explicit-task', project_id='project-a')
        group = self.group(plan['operation_id'])
        self.assertEqual(group['suggestion_ids'], [])
        self.assertFalse(group['interruption']['eligible'])
        response = self.feedback(group, 'response')
        self.assertEqual(response['admission'], {'accepted': True, 'new_claim': False, 'presented': True})
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 0)
        row = self.service.db.execute('SELECT charged,presented_at FROM anticipation_attention_receipts').fetchone()
        self.assertEqual(row['charged'], 0)
        self.assertIsNotNone(row['presented_at'])
        self.assertFalse((self.executor.workspace_root / 'explicit.txt').exists())
        self.assertEqual(self.executor.list_operations(), [])
        self.service.close()
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        restored = self.group(plan['operation_id'])
        self.assertTrue(restored['interruption']['presented'])
        self.assertFalse(restored['interruption']['eligible'])
        self.assertFalse(self.feedback(restored, 'response')['admission']['new_claim'])
        self.assertEqual(self.receipt_count(), 1)
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 0)

    def test_explicit_response_after_admission_does_not_refund_the_charge(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        self.assertTrue(self.feedback(group)['admission']['new_claim'])
        response = self.feedback(group, 'response')
        self.assertEqual(response['admission'], {'accepted': True, 'new_claim': False, 'presented': True})
        self.assertEqual(self.service.db.execute('SELECT charged FROM anticipation_attention_receipts').fetchone()[0], 1)
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 1)
        self.assertFalse(self.feedback(group)['admission']['new_claim'])

    def test_explicit_response_before_claim_survives_restart_without_charge_or_new_notice(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        self.assertTrue(self.feedback(group, 'response')['admission']['presented'])
        self.service.close()
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        restored = self.group(plan['operation_id'])
        self.assertTrue(restored['interruption']['response_acknowledged'])
        self.assertTrue(restored['interruption']['eligible'])
        replay = self.feedback(restored)
        self.assertEqual(replay['admission'], {'accepted': True, 'new_claim': False, 'presented': True})
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 0)
        self.assertEqual(self.executor.list_operations(100), effects)

    def test_attention_charge_schema_migration_keeps_previous_admission(self):
        self.service.close()
        with self.learning.db:
            self.learning.db.execute('DROP TABLE anticipation_attention_receipts')
            self.learning.db.execute('''CREATE TABLE anticipation_attention_receipts (
                attention_key TEXT PRIMARY KEY, claimed_at REAL NOT NULL, presented_at REAL,
                payload TEXT, invalidated INTEGER NOT NULL DEFAULT 0)''')
            self.learning.db.execute('INSERT INTO anticipation_attention_receipts VALUES (?,?,NULL,NULL,1)', ('a' * 64, self.now))
        self.service = AnticipationService(self.commands, clock=lambda: self.now)
        self.wire()
        self.assertEqual(self.service.db.execute('SELECT charged FROM anticipation_attention_receipts').fetchone()[0], 1)
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 1)

    def test_group_cannot_borrow_louder_policy_of_another_child_root(self):
        root_a, root_b = self.executor.workspace_root / 'a', self.executor.workspace_root / 'b'
        root_a.mkdir(); root_b.mkdir()
        plan = self.learning.prepare_steps('Entrega con ámbitos distintos', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': name, 'content': name}}
            for name in ('a/one.txt', 'b/two.txt', 'b/three.txt')], conversation_id='task-roots', project_id='project-a')
        self.learning.execute(plan['operation_id'], approved=True, plan_hash=plan['plan_hash'])
        self.service.tick()
        self.service.configure({'scopes': [{'root': str(root_a), 'profile': 'discreto'},
            {'root': str(root_b), 'profile': 'copiloto'}]})
        group = self.group(plan['operation_id'])
        self.assertEqual(group['category'], 'done')
        self.assertEqual(group['interruption']['reason'], 'ambiguous_policy')
        self.assertFalse(group['interruption']['eligible'])
        self.assertFalse(self.feedback(group)['admission']['accepted'])
        self.assertEqual(self.receipt_count(), 0)

    def test_response_racing_claim_has_one_receipt_and_at_most_one_charge(self):
        plan = self.mission()
        group = self.group(plan['operation_id'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        other = AnticipationService(self.commands, clock=lambda: self.now)
        barrier = threading.Barrier(2)
        results, errors = [], []
        def present(service, phase):
            try:
                barrier.wait(timeout=3)
                results.append(self.feedback(group, phase, service))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=present, args=(self.service, 'claim')),
                   threading.Thread(target=present, args=(other, 'response'))]
        try:
            for thread in threads: thread.start()
            for thread in threads: thread.join(10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertTrue(all(row['admission']['accepted'] for row in results))
            row = self.service.db.execute('SELECT charged,presented_at FROM anticipation_attention_receipts').fetchone()
            self.assertEqual(self.receipt_count(), 1)
            self.assertIn(row['charged'], (0, 1))
            self.assertEqual(sum(result['admission']['new_claim'] for result in results), row['charged'])
            self.assertIsNotNone(row['presented_at'])
            self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], row['charged'])
            self.assertEqual(self.executor.list_operations(100), effects)
        finally:
            other.close()

    def test_forgetting_origin_fences_dependent_group_preserves_independent_and_charge(self):
        source = self.mission('task-a')
        scope = task_memory.snapshot(self.learning.db, 'task-a')
        dependent = self.mission('task-b', dependencies=[scope])
        independent = self.mission('task-c')
        groups = [self.group(plan['operation_id']) for plan in (source, dependent, independent)]
        for group in groups:
            self.assertTrue(self.feedback(group)['admission']['new_claim'])
        self.assertIn(scope, groups[1]['memory_dependencies'])
        effects = copy.deepcopy(self.executor.list_operations(100))
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            barrier = task_memory.begin_forget(self.learning.db, 'task-a', 'forget-a', 0)
        self.assertEqual(self.service.status('task-a')['mission_attention'], [])
        self.assertEqual(self.service.status('task-b')['mission_attention'], [])
        with self.assertRaises(StaleContext): self.feedback(groups[0])
        late_b = self.feedback(groups[1])
        self.assertFalse(late_b['admission']['accepted'])
        self.assertIsNone(late_b['attention'])
        for group in groups[:2]:
            try:
                late_response = self.feedback(group, 'response')
            except ValueError:
                pass
            else:
                self.assertFalse(late_response['admission']['accepted'])
                self.assertIsNone(late_response['attention'])
            for action in ('dismiss', 'suppress', 'restore'):
                late_group = self.group_feedback(group, action)
                self.assertFalse(late_group['admission']['accepted'])
                self.assertIsNone(late_group['attention'])
        result = self.service.forget_task('task-a')
        with self.learning.db:
            self.learning.db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(self.learning.db, barrier, result)
        self.assertEqual(self.service.status('task-a')['mission_attention'], [])
        self.assertEqual(self.service.status('task-b')['mission_attention'], [])
        self.assertEqual(self.group(independent['operation_id'])['attention_key'], groups[2]['attention_key'])
        for group in groups[:2]:
            row = self.service.db.execute('SELECT payload,invalidated FROM anticipation_attention_receipts WHERE attention_key=?', (group['attention_key'],)).fetchone()
            self.assertEqual(tuple(row), (None, 1))
        self.assertEqual(self.service.status()['metrics']['attention_budget_used_last_hour'], 3)
        self.assertEqual(self.executor.list_operations(100), effects)
        fresh = self.mission('task-d')
        self.assertEqual(self.group(fresh['operation_id'])['interruption']['reason'], 'budget')

    def test_context_rotation_rejects_late_claim_without_rebasing(self):
        store = ChatStore(self.root / 'state.db')
        try:
            task = store.mutate('create', {'connect_id': 'original-context'})['id']
            plan = self.mission(task)
            group = self.group(plan['operation_id'])
            original = group['memory_context_id']
            self.assertEqual(original, 'original-context')
            effects = copy.deepcopy(self.executor.list_operations(100))
            project = store.mutate('group', {'title': 'Rotación'})['id']
            store.mutate('update', {'id': task, 'group_id': project})
            self.assertNotEqual(store.get(task)['context_id'], original)
            self.assertEqual(self.service.status(task)['mission_attention'], [])
            with self.assertRaises(StaleContext): self.feedback(group)
            self.assertEqual(self.receipt_count(), 0)
            self.assertEqual(self.executor.list_operations(100), effects)
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
