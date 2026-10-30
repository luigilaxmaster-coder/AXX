"""Isolated TLS routing and durable mission admission; no installed app or providers."""
import copy
import json
from pathlib import Path
import ssl
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

from backend.chat_store import ChatStore
from backend.memory import task_memory
from backend.mobile.gateway import MobileGateway
from backend.mobile.trust_store import MobileTrustStore, assert_device_scope


class MissionGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.db'
        self.chats = ChatStore(self.path)
        self.chat = self.chats.get(self.chats.mutate('create', {})['id'])
        self.other = self.chats.get(self.chats.mutate('create', {})['id'])
        self.calls = []
        self.after_get = None
        self.after_repair = None
        self.drop_ack = False
        self.claim = True
        self.plan = {'operation_id': str(uuid.uuid4()), 'conversation_id': self.chat['id'], 'project_id': '',
                     'state': 'awaiting_approval', 'goal_revision': 1, 'plan_hash': 'reviewed-original-hash',
                     'goal_spec': {'intent': 'Write report', 'destination': 'old/report.txt', 'checks': []},
                     'mission': {'objective': 'Write report', 'destination': 'old/report.txt'},
                     'memory_scope': self.chat['memory_scope'], 'memory_context_id': self.chat['context_id'],
                     'model_calls_used': 0, 'model_call_limit': 2,
                     'planning_settings': {'model': 'host-model', 'provider_name': 'host-provider', 'selection_mode': 'manual'}}
        self.gateway = MobileGateway(self.path, self.temp.name, self.backend, host_resolver=lambda: '127.0.0.1')
        self.gateway.share_history = True
        self.info = self.gateway.start()
        self.device = self.gateway.store.consume_pairing(self.info['pairing_code'], 'Phone')
        self.gateway.store.set_tool_permission(self.device['device_id'], True)
        self.tls = ssl.create_default_context(cafile=str(self.gateway._identity[0]))
        self.gateway.shared.merge_messages([], 'desktop', self.chat['shared_id'], activate=True)

    def tearDown(self):
        self.gateway.close()
        self.chats.close()
        self.temp.cleanup()

    def backend(self, method, path, body):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path.startswith('/axx-api/learning/plans?'):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            self.assertEqual(query, {'conversation_id': [self.chat['id']]})
            return {'plans': [copy.deepcopy(self.plan)]}
        if path.startswith('/axx-api/learning/plan?'):
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(path).query), {'id': [self.plan['operation_id']]})
            result = copy.deepcopy(self.plan)
            if self.after_get:
                self.after_get()
            return result
        self.assertEqual((method, path), ('POST', '/axx-api/learning/repair'))
        if self.claim:
            self.plan.update(goal_revision=2, plan_hash='corrected-review-hash', goal_spec=copy.deepcopy(body['goal_spec']))
            self.plan.setdefault('correction_requests', {})[body['correction_id']] = {
                'id': body['correction_id'], 'request_hash': 'core-request-hash', 'state': 'awaiting_approval',
                'from_plan_hash': body['plan_hash'], 'from_goal_revision': body['goal_revision'],
                'plan_hash': self.plan['plan_hash'], 'goal_revision': 2, 'origin_device_id': body['origin_device_id']}
        if self.after_repair:
            self.after_repair()
        if self.drop_ack:
            raise ConnectionResetError('lost acknowledgement')
        return copy.deepcopy(self.plan)

    def request(self, path, body=None, device=None):
        device = device or self.device
        request = urllib.request.Request(self.info['endpoint'] + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + device['credential']})
        with urllib.request.urlopen(request, context=self.tls, timeout=3) as response:
            return json.load(response)['data']

    def denied(self, path, body=None, status=400, device=None):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(path, body, device)
        self.assertEqual(error.exception.code, status)
        error.exception.close()

    def correction(self):
        return {'command_id': 'review-1', 'operation_id': self.plan['operation_id'], 'conversation_id': self.chat['shared_id'],
                'plan_hash': 'reviewed-original-hash', 'goal_revision': 1, 'text': 'Move the report to the reviewed destination',
                'goal_spec': {'intent': 'Write report', 'destination': 'new/report.txt', 'checks': []},
                'memory_scope': self.chat['memory_scope'], 'memory_context_id': self.chat['context_id']}

    def repair_calls(self):
        return [call for call in self.calls if call[1].endswith('/repair')]

    def test_lists_original_pc_mission_and_reads_old_chat_without_retargeting(self):
        result = self.request('/v1/work/missions')
        self.assertEqual(result['conversation_id'], self.chat['shared_id'])
        self.assertEqual(result['missions'][0]['operation_id'], self.plan['operation_id'])
        self.assertNotIn('goal_spec', result['missions'][0])
        self.gateway.shared.merge_messages([], 'desktop', self.other['shared_id'], activate=True)
        detail = self.request('/v1/work/mission?operation_id=' + self.plan['operation_id'])
        self.assertEqual(detail['conversation_id'], self.chat['shared_id'])
        self.assertEqual(detail['goal_spec'], self.plan['goal_spec'])
        self.assertEqual(detail['memory_scope']['task_id'], self.chat['id'])
        self.assertTrue(detail['can_correct'])
        self.assertEqual(detail['executor'], 'pc')
        self.assertIsNone(self.gateway.store.work_request(self.plan['operation_id']))
        self.denied('/v1/work/mission?operation_id=' + self.plan['operation_id'] + '&operation_id=another')

    def test_exact_cas_body_host_settings_duplicate_and_changed_payload(self):
        body = self.correction()
        response = self.request('/v1/work/mission-correct', body)
        self.assertEqual(response['state'], 'confirmed')
        self.assertEqual(response['receipt']['plan_hash'], 'corrected-review-hash')
        call = self.repair_calls()[0][2]
        expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'axx-mobile-mission:' + self.device['device_id'] + ':review-1'))
        self.assertEqual(call, {key: body[key] for key in ('operation_id', 'plan_hash', 'goal_revision', 'text', 'goal_spec')} |
                         {'correction_id': expected_id, 'origin_device_id': self.device['device_id'],
                          'conversation_id': self.chat['id'], 'memory_scope': body['memory_scope'],
                          'memory_context_id': body['memory_context_id'], **self.plan['planning_settings']})
        self.assertEqual(self.request('/v1/work/mission-correct', body)['receipt'], response['receipt'])
        self.denied('/v1/work/mission-correct', body | {'text': 'Different request'}, 409)
        self.denied('/v1/work/mission-correct', body | {'provider_name': 'phone-provider'})
        self.assertEqual(len(self.repair_calls()), 1)
        command = self.gateway.store.command(self.device['device_id'], body['command_id'])
        self.assertEqual(command['result']['correction_id'], expected_id)
        self.assertNotIn('goal_spec', command['result'])
        self.assertNotIn('text', command['result'])

    def test_lost_ack_reconciles_exact_claim_and_never_replays(self):
        self.drop_ack = True
        body = self.correction()
        result = self.request('/v1/work/mission-correct', body)
        self.assertEqual(result['state'], 'confirmed')
        self.gateway.store.recover_commands()
        self.assertEqual(self.request('/v1/work/mission-correction?command_id=review-1')['receipt'], result['receipt'])
        self.request('/v1/work/mission-correct', body)
        self.assertEqual(len(self.repair_calls()), 1)

    def test_missing_claim_stays_unknown_across_recovery_and_newer_revision(self):
        self.drop_ack, self.claim = True, False
        body = self.correction()
        self.assertEqual(self.request('/v1/work/mission-correct', body)['state'], 'outcome_unknown')
        self.plan.update(goal_revision=9, plan_hash='unrelated-newer-hash')
        restarted = MobileTrustStore(self.path)
        restarted.recover_commands()
        binding = restarted.command(self.device['device_id'], body['command_id'])['result']
        self.assertEqual(binding['from_plan_hash'], body['plan_hash'])
        self.assertEqual(binding['from_goal_revision'], body['goal_revision'])
        self.assertEqual(binding['memory_context_id'], body['memory_context_id'])
        self.assertEqual(self.request('/v1/work/mission-correct', body)['state'], 'outcome_unknown')
        self.assertEqual(len(self.repair_calls()), 1)
        foreign = self.gateway.store.consume_pairing(self.gateway.store.create_pairing(), 'Other phone')
        self.gateway.store.set_tool_permission(foreign['device_id'], True)
        self.denied('/v1/work/mission-correction?command_id=review-1', status=404, device=foreign)

    def test_aborted_preparation_never_confirms_even_with_new_hash_and_revision(self):
        body = self.correction()
        prepared = self.request('/v1/work/mission-correct', body)
        receipt = self.plan['correction_requests'][prepared['receipt']['id']]
        for state in ('failed', 'cancelled', 'needs_input', 'interrupted', 'waiting_capacity'):
            with self.subTest(state=state):
                receipt['state'] = state
                result = self.request('/v1/work/mission-correction?command_id=review-1')
                self.assertEqual(result['state'], 'rejected')
                self.assertEqual(result['receipt']['state'], state)
        receipt['state'] = 'pending'
        self.assertEqual(self.request('/v1/work/mission-correction?command_id=review-1')['state'], 'pending')
        receipt['state'] = 'awaiting_approval'
        self.plan.update(state='succeeded', plan_hash='later-current-hash', goal_revision=3)
        historical = self.request('/v1/work/mission-correction?command_id=review-1')
        self.assertEqual(historical['state'], 'confirmed')
        self.assertEqual(historical['receipt']['plan_hash'], 'corrected-review-hash')
        self.assertEqual(historical['receipt']['goal_revision'], 2)
        self.assertEqual(historical['mission']['state'], 'succeeded')
        self.assertEqual(len(self.repair_calls()), 1)

    def test_scope_history_cross_chat_and_live_recheck(self):
        body = self.correction()
        self.denied('/v1/work/mission-correct', body | {'conversation_id': self.other['shared_id']})
        self.gateway.share_history = False
        self.denied('/v1/work/missions')
        self.assertNotIn('mission_continuity', self.request('/v1/snapshot')['capabilities'])
        self.gateway.share_history = True
        self.assertTrue(self.request('/v1/snapshot')['capabilities']['mission_continuity'])
        self.gateway.store.set_tool_permission(self.device['device_id'], False)
        self.denied('/v1/work/missions', status=403)
        self.gateway.store.set_tool_permission(self.device['device_id'], True)
        self.after_get = lambda: setattr(self.gateway, 'share_history', False)
        self.denied('/v1/work/mission?operation_id=' + self.plan['operation_id'])
        self.assertEqual(self.repair_calls(), [])

    def test_memory_forget_returns_only_unavailable_headers_and_cannot_rebind(self):
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            reference = task_memory.begin_forget(db, self.chat['id'], 'forget', self.chat['memory_scope']['generation'])
        self.chats.forget_task(self.chat['id'], reference)
        self.gateway.shared.forget_task(self.chat['id'], reference)
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(db, reference, {})
        detail = self.request('/v1/work/mission?operation_id=' + self.plan['operation_id'])
        self.assertTrue(detail['memory_forgotten'])
        self.assertFalse(detail['can_correct'])
        self.assertNotIn('goal_spec', detail)
        self.assertNotIn('Write report', json.dumps(detail))
        fresh = self.gateway.shared.capture_scope(self.chat['shared_id'])
        self.denied('/v1/work/mission-correct', self.correction() | {key: fresh[key] for key in ('memory_scope', 'memory_context_id')})
        self.assertEqual(self.repair_calls(), [])

    def test_original_restrictions_remain_read_only(self):
        for fields in ({'resource_binding_selectors': {}}, {'revalidation': True}, {'workshop_validation': True},
                       {'state': 'running'}, {'model_calls_used': 2}):
            with self.subTest(fields=fields):
                original = copy.deepcopy(self.plan)
                self.plan.update(fields)
                self.assertFalse(self.request('/v1/work/mission?operation_id=' + self.plan['operation_id'])['can_correct'])
                self.denied('/v1/work/mission-correct', self.correction())
                self.plan = original
        self.assertEqual(self.repair_calls(), [])

    def test_scope_helper_reads_live_grant_without_writes(self):
        with self.gateway.store._connect() as db:
            before = db.total_changes
            assert_device_scope(db, self.device['device_id'], 'tools.control')
            self.assertEqual(db.total_changes, before)
        self.gateway.store.revoke(self.device['device_id'])
        with self.gateway.store._connect() as db:
            with self.assertRaises(ValueError):
                assert_device_scope(db, self.device['device_id'], 'tools.control')


if __name__ == '__main__':
    unittest.main()
