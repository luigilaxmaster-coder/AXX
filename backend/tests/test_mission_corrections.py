"""Deterministic model fixtures, independent SQLite owners, and disposable files only."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from backend.action_learning import ActionLearning, NeedsInput
from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.mobile.trust_store import MobileTrustStore


class FixtureModel:
    def __init__(self):
        self.calls = []
        self.entered, self.release = threading.Event(), threading.Event()
        self.hold = False
        self.path = 'corrected.txt'

    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        self.entered.set()
        if self.hold and not self.release.wait(10): raise RuntimeError('Fixture was not released')
        return {'ok': True, 'message': {'content': json.dumps({'title': 'Corrected delivery', 'steps': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': self.path, 'content': 'CORRECTED'}}]})},
            'route': {'provider_name': 'deterministic-fixture', 'model': 'fixture',
                      'upstream_attempts': 1, 'attempt_budget_used': 1}}


class MissionCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model = FixtureModel()
        self.services = []
        self.learning = self.service()
        self.other = self.service()
        self.chats = ChatStore(self.root / 'state.db')
        self.chat = self.chats.mutate('create', {'title': 'Correction fixture'})['id']
        self.trust = MobileTrustStore(self.root / 'state.db')

    def service(self):
        executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        commands = CommandService(executor)
        learning = ActionLearning(commands, self.model)
        commands.learning = learning
        self.services.append((learning, commands, executor))
        return learning

    def tearDown(self):
        self.model.release.set()
        self.chats.close()
        for learning, commands, executor in reversed(self.services):
            learning.close(); commands.close(); executor.close()
        self.temp.cleanup()

    def goal(self, path='corrected.txt'):
        return {'intent': 'Deliver the corrected file', 'criteria': [
            {'id': 'delivery', 'kind': 'text_exact', 'parameters': {'path': path, 'text': 'CORRECTED'}}]}

    def plan(self, *, completed=False):
        plan = self.learning.prepare_steps('Deliver the corrected file', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'prefix.txt', 'content': 'PREFIX'}}],
            'correction-mission', 'fixture-project', self.chat,
            goal_spec=self.goal('old-target.txt'))
        return self.learning.execute(plan['operation_id'], approved=True) if completed else plan

    def request(self, plan, **extra):
        return {'key': plan['operation_id'], 'text': 'Use the corrected delivery target',
                'correction_id': str(uuid.uuid4()), 'plan_hash': plan['plan_hash'],
                'goal_spec': self.goal(), 'goal_revision': plan['goal_revision'], **extra}

    def raw(self):
        return self.learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', ('correction-mission',)).fetchone()[0]

    def held(self, request, mutate):
        self.model.hold = True
        results, errors = [], []
        def repair():
            try: results.append(self.learning.repair(**request))
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=repair)
        thread.start()
        try:
            self.assertTrue(self.model.entered.wait(5), errors)
            mutate()
        finally:
            self.model.release.set(); thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        return results[0]

    def device(self, scopes=('query', 'tools.control')):
        return self.trust.consume_pairing(self.trust.create_pairing(scopes), 'Fixture phone')['device_id']

    def test_correction_preserves_mission_prefix_budget_and_requires_new_approval(self):
        before = self.plan(completed=True)
        self.assertEqual(before['state'], 'goal_pending', before)
        prefix = copy.deepcopy(before['step_records'][0])
        request = self.request(before)
        corrected = self.learning.repair(**request)
        self.assertEqual(corrected['state'], 'awaiting_approval', corrected)
        self.assertEqual(corrected['operation_id'], before['operation_id'])
        self.assertEqual(corrected['step_records'][0], prefix)
        self.assertEqual(corrected['results'], before['results'])
        self.assertEqual(corrected['goal_revision'], before['goal_revision'] + 1)
        self.assertEqual(corrected['model_calls_used'], before['model_calls_used'] + 1)
        self.assertEqual(corrected['model_call_limit'], before['model_call_limit'])
        self.assertIsNone(corrected['approved_hash'])
        self.assertEqual(corrected['skill_versions'], [])
        receipt = corrected['correction_receipt']
        self.assertEqual(receipt['id'], request['correction_id'])
        self.assertEqual(receipt['from_plan_hash'], before['plan_hash'])
        self.assertEqual(receipt['plan_hash'], corrected['plan_hash'])
        self.assertEqual(self.learning._plan_hash(corrected), corrected['plan_hash'])
        journal_changed = copy.deepcopy(corrected)
        journal_changed['correction_requests'][request['correction_id']]['state'] = 'audit-only'
        self.assertEqual(self.learning._plan_hash(journal_changed), corrected['plan_hash'])
        self.assertFalse((self.root / 'artifacts' / 'corrected.txt').exists())
        self.assertEqual(len(self.services[0][2].list_operations()), 1)

    def test_correction_requires_new_exact_hash_for_execute_and_resume(self):
        before = self.plan(completed=True)
        result = self.learning.repair(**self.request(before))
        for reviewed in (None, before['plan_hash']):
            with self.assertRaises(ValueError): self.learning.execute(result['operation_id'], approved=True, plan_hash=reviewed)
            with self.assertRaises(ValueError): self.learning.resume(result['operation_id'], approved=True, plan_hash=reviewed)
        self.assertFalse((self.root / 'artifacts' / 'corrected.txt').exists())
        self.assertEqual(len(self.services[0][2].list_operations()), 1)
        completed = self.learning.execute(result['operation_id'], approved=True, plan_hash=result['plan_hash'])
        self.assertEqual(completed['state'], 'succeeded', completed)
        self.assertEqual(len(self.services[0][2].list_operations()), 2)

    def test_replay_conflict_and_historical_receipt_after_newer_correction(self):
        request = self.request(self.plan())
        first = self.learning.repair(**request)
        raw = self.raw()
        replay = self.other.repair(**request)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['correction_receipt'], first['correction_receipt'])
        self.assertEqual(self.raw(), raw)
        self.assertEqual(len(self.model.calls), 1)
        with self.assertRaises(ValueError): self.other.repair(**(request | {'text': 'Different human correction'}))
        self.model.path = 'newer.txt'
        newer = self.learning.repair(**self.request(first, goal_spec=self.goal('newer.txt')))
        replay = self.other.repair(**request)
        self.assertEqual(replay['plan_hash'], newer['plan_hash'])
        self.assertEqual(replay['correction_receipt'], first['correction_receipt'])
        self.assertNotEqual(replay['correction_receipt']['plan_hash'], replay['plan_hash'])
        self.assertEqual(len(self.model.calls), 2)

    def test_independent_services_race_one_reviewed_hash_and_only_one_inference(self):
        plan = self.plan()
        barrier = threading.Barrier(2)
        results, errors = [], []
        original_first, original_second = self.learning._assert_request, self.other._assert_request
        def wait(original):
            def checked(*args, **kwargs):
                value = original(*args, **kwargs)
                barrier.wait(5)
                return value
            return checked
        def repair(service):
            try: results.append(service.repair(**self.request(plan)))
            except ValueError as exc: errors.append(str(exc))
        with patch.object(self.learning, '_assert_request', wait(original_first)), patch.object(self.other, '_assert_request', wait(original_second)):
            threads = [threading.Thread(target=repair, args=(service,)) for service in (self.learning, self.other)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(results), 1, errors)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(self.model.calls), 1)
        durable = self.learning.get(plan['operation_id'])
        self.assertEqual(len(durable['correction_requests']), 1)
        self.assertEqual(durable['model_calls_used'], 1)

    def test_pending_same_id_replays_while_local_worker_is_waiting(self):
        request = self.request(self.plan())
        def replay():
            pending = self.learning.repair(**request)
            self.assertTrue(pending['replayed'])
            self.assertEqual(pending['correction_receipt']['state'], 'pending')
            self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(self.held(request, replay)['state'], 'awaiting_approval')

    def test_correction_keeps_original_references_without_retrieving_fresh_lessons_or_context(self):
        before = self.plan()
        with (patch.object(self.learning.skills, 'lessons', side_effect=AssertionError('No fresh lesson selection')),
                patch.object(self.learning, '_capture_planning_context', side_effect=AssertionError('No fresh context capture'))):
            result = self.learning.repair(**self.request(before))
        self.assertEqual(result['state'], 'awaiting_approval', result)
        for key in ('memory_scope', 'memory_context_id', 'memory_dependencies', 'lesson_dependencies', 'context_dependencies', 'document_references'):
            self.assertEqual(result.get(key), before.get(key))

    def test_raw_plan_hash_change_and_journal_limit_refuse_without_inference(self):
        plan = self.plan()
        raw = json.loads(self.raw())
        raw['steps'][0]['inputs']['content'] = 'changed outside review'
        with self.learning.db:
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(raw), plan['operation_id']))
        with self.assertRaises(ValueError): self.learning.repair(**self.request(plan))
        raw = copy.deepcopy(plan)
        raw['correction_requests'] = {str(uuid.uuid4()): {'state': 'interrupted'} for _ in range(32)}
        with self.learning.db:
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(raw), plan['operation_id']))
        with self.assertRaises(ValueError): self.learning.repair(**self.request(plan))
        self.assertEqual(len(self.model.calls), 0)
        self.assertEqual(len(json.loads(self.raw())['correction_requests']), 32)

    def test_other_service_cancel_while_result_is_held_wins_over_late_worker(self):
        request = self.request(self.plan(completed=True))
        result = self.held(request, lambda: self.other.cancel(request['key']))
        self.assertEqual(result['state'], 'cancelled', result)
        self.assertEqual(result['correction_receipt']['state'], 'cancelled')
        self.assertNotIn('plan_hash', result['correction_receipt'])
        self.assertEqual(result['step_records'][0]['state'], 'succeeded')
        self.assertNotIn('model_data', json.loads(self.raw()))
        self.assertFalse((self.root / 'artifacts' / 'corrected.txt').exists())

    def test_newer_durable_marker_while_result_is_held_cannot_be_overwritten(self):
        request = self.request(self.plan())
        newer_id = str(uuid.uuid4())
        def replace_owner():
            with closing(sqlite3.connect(self.root / 'state.db')) as db, db:
                current = json.loads(db.execute('SELECT payload FROM learning_plans WHERE id=?', (request['key'],)).fetchone()[0])
                current['current_correction_id'] = newer_id
                current['correction_requests'][newer_id] = {'id': newer_id, 'state': 'pending', 'request_hash': 'later-owner'}
                db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(current), request['key']))
        self.held(request, replace_owner)
        current = self.learning.get(request['key'])
        self.assertEqual(current['current_correction_id'], newer_id)
        self.assertEqual(current['correction_requests'][newer_id]['state'], 'pending')
        self.assertNotIn('model_data', current)

    def test_original_memory_revoked_during_provider_wait_discards_result(self):
        request = self.request(self.plan())
        def revoke():
            with closing(sqlite3.connect(self.root / 'state.db')) as db, db:
                db.execute('INSERT OR REPLACE INTO memory_task_scopes(task_id,generation,forgetting) VALUES(?,?,0)', (self.chat, 1))
        result = self.held(request, revoke)
        self.assertTrue(result['memory_forgotten'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['correction_receipt']['state'], 'cancelled')
        self.assertNotIn('model_data', json.loads(self.raw()))

    def test_forgotten_correction_receipts_project_only_audit_headers_without_ledger_mutation(self):
        request = self.request(self.plan())
        result = self.learning.repair(**request)
        raw = json.loads(self.raw())
        raw['correction_requests'][request['correction_id']].update(text='PRIVATE_RECEIPT_CANARY',
            extra={'goal': {'intent': 'PRIVATE_NESTED_CANARY'}})
        with self.learning.db:
            self.learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(raw), request['key']))
            self.learning.db.execute('INSERT OR REPLACE INTO memory_task_scopes(task_id,generation,forgetting) VALUES(?,?,0)', (self.chat, 1))
        ledger = self.raw()
        forgotten = self.learning.get(request['key'])
        response = self.learning._correction_response(json.loads(ledger), request['correction_id'], replayed=True)
        for view in (forgotten, response):
            self.assertTrue(view['memory_forgotten'])
            self.assertEqual(view['current_correction_id'], request['correction_id'])
            self.assertEqual(view['correction_requests'][request['correction_id']], result['correction_receipt'])
            self.assertNotIn('PRIVATE_RECEIPT_CANARY', json.dumps(view))
            self.assertNotIn('PRIVATE_NESTED_CANARY', json.dumps(view))
        self.assertEqual(response['correction_receipt'], result['correction_receipt'])
        self.assertEqual(self.raw(), ledger)

    def test_actual_session_forget_finalizes_pending_receipt_without_stale_worker_write(self):
        before = self.plan(completed=True)
        request = self.request(before)
        original_receipt = copy.deepcopy(before['step_records'][0]['result'])
        chat = self.chats.get(self.chat)
        def forget():
            result = self.other.forget_session(self.chat, 'forget-held-correction', chat['memory_scope'],
                chats=self.chats, memory_context_id=chat['context_id'])
            self.assertEqual(result['state'], 'applied')
        result = self.held(request, forget)
        self.assertTrue(result['memory_forgotten'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['correction_receipt']['state'], 'cancelled')
        self.assertNotIn('plan_hash', result['correction_receipt'])
        durable = json.loads(self.raw())
        self.assertEqual(durable['step_records'][0]['result'], original_receipt)
        self.assertNotIn('model_data', durable)
        self.assertEqual((self.root / 'artifacts' / 'prefix.txt').read_text(), 'PREFIX')

    def test_upstream_succeeded_then_forgotten_during_wait_cannot_authorize_correction(self):
        source_chat = self.chats.mutate('create', {'title': 'Upstream source'})['id']
        source = self.learning.prepare_steps('Source fixture', [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'source.txt', 'content': 'SOURCE'}}],
            'upstream-source', 'fixture-project', source_chat)
        source = self.learning.execute(source['operation_id'], approved=True)
        self.assertEqual(source['state'], 'succeeded', source)
        target = self.plan()
        target = self.learning.link_dependencies(target['operation_id'], [source['operation_id']], target['plan_hash'])
        self.assertNotIn(source_chat, [ref['task_id'] for ref in target.get('memory_dependencies', [])])
        chat = self.chats.get(source_chat)
        result = self.held(self.request(target), lambda: self.other.forget_session(source_chat,
            'forget-upstream-source', chat['memory_scope'], chats=self.chats, memory_context_id=chat['context_id']))
        self.assertEqual(result['state'], 'needs_input', result)
        self.assertEqual(result['correction_receipt']['state'], 'needs_input')
        self.assertNotIn('plan_hash', result['correction_receipt'])
        self.assertNotIn('model_data', json.loads(self.raw()))

    def test_original_context_revocation_before_and_during_wait_is_preserved(self):
        context = self.learning.update_context('fixture-project', {'current_file': 'original.txt', 'context_meta': {
            'current_file': {'kind': 'observed', 'source_id': 'fixture-source'}}})
        plan = self.plan()
        plan['context_dependencies'] = [{'project_id': 'fixture-project', 'field': 'current_file',
                                        'revision': context['context_meta']['current_file']['revision']}]
        plan['plan_hash'] = self.learning._plan_hash(plan)
        self.learning._save(plan)
        request = self.request(plan)
        result = self.held(request, lambda: self.other.invalidate_context('fixture-project', {'source_id': 'fixture-source', 'forget': True}))
        self.assertEqual(result['state'], 'needs_input', result)
        self.assertEqual(result['correction_receipt']['state'], 'needs_input')
        self.assertNotIn('model_data', json.loads(self.raw()))
        with self.assertRaises(ValueError): self.learning.repair(**self.request(result))
        self.assertEqual(len(self.model.calls), 1)

    def test_mobile_origin_is_rechecked_before_provider_and_after_wait(self):
        origin = self.device()
        plan = self.plan()
        request = self.request(plan, origin_device_id=origin)
        original = self.learning._infer
        def revoke_first(*args, **kwargs):
            self.trust.revoke(origin)
            return original(*args, **kwargs)
        with patch.object(self.learning, '_infer', revoke_first):
            result = self.learning.repair(**request)
        self.assertEqual(result['state'], 'needs_input', result)
        self.assertEqual(len(self.model.calls), 0)
        self.assertEqual(result['correction_receipt']['origin_device_id'], origin)
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_versions').fetchone()[0], 0)

    def test_missing_mobile_control_scope_refuses_before_claim_and_model(self):
        request = self.request(self.plan(), origin_device_id=self.device(('query',)))
        raw = self.raw()
        with self.assertRaises(NeedsInput): self.learning.repair(**request)
        self.assertEqual(self.raw(), raw)
        self.assertEqual(len(self.model.calls), 0)

    def test_revocation_after_response_prevents_publication_but_later_pc_approval_is_independent(self):
        origin = self.device()
        request = self.request(self.plan(), origin_device_id=origin)
        result = self.held(request, lambda: self.trust.revoke(origin))
        self.assertEqual(result['state'], 'needs_input', result)
        self.assertEqual(result['correction_receipt']['state'], 'needs_input')
        self.assertNotIn('model_data', json.loads(self.raw()))
        self.assertEqual(self.learning.db.execute('SELECT COUNT(*) FROM skill_versions').fetchone()[0], 0)

    def test_mobile_revocation_after_preparation_does_not_block_independent_pc_approval(self):
        origin = self.device()
        request = self.request(self.plan(completed=True), origin_device_id=origin)
        result = self.learning.repair(**request)
        receipt = copy.deepcopy(result['correction_receipt'])
        self.trust.revoke(origin)
        completed = self.learning.execute(request['key'], approved=True, plan_hash=result['plan_hash'])
        self.assertEqual(completed['state'], 'succeeded', completed)
        self.assertEqual(completed['correction_requests'][request['correction_id']], receipt)
        self.assertEqual((self.root / 'artifacts' / 'corrected.txt').read_text(), 'CORRECTED')
        self.assertEqual((self.root / 'artifacts' / 'prefix.txt').read_text(), 'PREFIX')

    def test_crash_restart_preserves_interrupted_receipt_without_implicit_inference(self):
        class SimulatedCrash(BaseException): pass
        request = self.request(self.plan())
        with patch.object(self.model, 'route', side_effect=SimulatedCrash) as dispatch:
            with self.assertRaises(SimulatedCrash): self.learning.repair(**request)
            self.assertEqual(dispatch.call_count, 1)
        self.learning.close()
        restarted = self.service()
        interrupted = restarted.get(request['key'])
        self.assertEqual(interrupted['state'], 'interrupted')
        self.assertEqual(interrupted['correction_requests'][request['correction_id']]['state'], 'interrupted')
        replay = restarted.repair(**request)
        self.assertTrue(replay['replayed'])
        self.assertEqual(restarted.resume(request['key'], plan_hash=interrupted['plan_hash'])['state'], 'interrupted')
        restarted.retry_waiting()
        self.assertEqual(len(self.model.calls), 0)
        self.assertFalse((self.root / 'artifacts' / 'corrected.txt').exists())

    def test_list_exact_chat_requires_known_original_identity_and_keeps_legacy_project_filter(self):
        plan = self.plan()
        other_chat = self.chats.mutate('create', {'title': 'Independent fixture'})['id']
        self.other.prepare_steps('Independent', [{'command_id': 'axx.artifact.write', 'inputs': {'path': 'other.txt', 'content': 'OTHER'}}],
            'other-mission', 'fixture-project', other_chat)
        self.assertEqual([item['operation_id'] for item in self.learning.list_plans(conversation_id=self.chat)], [plan['operation_id']])
        self.assertEqual(len(self.learning.list_plans('fixture-project')), 2)
        self.assertEqual(self.learning.list_plans(), [])
        with self.assertRaises(ValueError): self.learning.list_plans('fixture-project', conversation_id=self.chat)
        with self.assertRaises(ValueError): self.learning.list_plans(conversation_id='missing-chat')
        with self.assertRaises(ValueError): self.learning.list_plans(conversation_id=self.chats.get(self.chat)['context_id'])
