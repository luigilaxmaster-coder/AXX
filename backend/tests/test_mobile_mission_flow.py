"""Same-mission phone correction crosses real TLS/HTTP and temp-file receipts.

The two model responses are deterministic fixtures, not provider evidence.
"""
import copy
import hashlib
import http.client
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.mobile.gateway import MobileGateway
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


PREFIX = b'CONFIRMED_PREFIX\n'
RESULT = b'REVIEWED_PHONE_DESTINATION\n'


class TwoResponseModel:
    def __init__(self):
        self.calls = []

    def route(self, request):
        self.calls.append(copy.deepcopy(request))
        if len(self.calls) > 2:
            raise AssertionError('A reconciled correction must not infer again')
        path, content = ('prefix.txt', PREFIX) if len(self.calls) == 1 else ('new-target.txt', RESULT)
        answer = {'title': 'Misión de ensayo', 'steps': [{'command_id': 'axx.artifact.write',
            'inputs': {'path': path, 'content': content.decode('utf-8')}}]}
        return {'ok': True, 'message': {'content': json.dumps(answer)},
            'route': {'upstream_attempts': 1, 'attempt_budget_used': 1}}


class MobileMissionFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = TwoResponseModel()
        self.learning = ActionLearning(self.commands, self.model)
        self.commands.learning = self.learning
        self.chats = ChatStore(self.executor.db_path)
        chat_id = self.chats.mutate('create', {'title': 'PC original'})['id']
        self.chat = self.chats.get(chat_id)
        self.scope = {'memory_scope': copy.deepcopy(self.chat['memory_scope']), 'memory_context_id': self.chat['context_id']}
        handler = type('MissionFlowBackend', (AxxBridgeHandler,), {'executor': self.executor,
            'commands': self.commands, 'learning': self.learning, 'chats': self.chats})
        self.backend = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.backend_thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()
        self.gateway = MobileGateway.for_backend(self.backend, self.executor.db_path, self.root)
        self.gateway.host_resolver = lambda: '127.0.0.1'
        self.gateway.share_history = True
        self.gateway.preferences = {'provider': 'bridge', 'provider_name': 'offline-fixture',
            'model': 'two-response-fixture', 'selection_mode': 'manual'}
        self.info = self.gateway.start()
        self.device = self.gateway.store.consume_pairing(self.info['pairing_code'], 'Fixture phone')
        self.gateway.store.set_tool_permission(self.device['device_id'], True)
        self.tls = ssl.create_default_context(cafile=str(self.gateway._identity[0]))
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.https = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=self.tls))
        self.gateway.shared.merge_messages([{'id': 'fixture-activate', 'role': 'user', 'text': 'Misión de ensayo'}],
            'pc', self.chat['shared_id'], activate=True, **self.scope)

    def tearDown(self):
        self.gateway.close()
        self.backend.shutdown()
        self.backend.server_close()
        self.backend_thread.join(3)
        self.chats.close()
        self.learning.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def request(self, route, body=None, *, phone=False):
        base = self.info['endpoint'] if phone else f'http://127.0.0.1:{self.backend.server_port}'
        credential = self.device['credential'] if phone else self.backend.host_token
        headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + credential}
        request = urllib.request.Request(base + route, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with (self.https if phone else self.http).open(request, timeout=20) as response:
                data = json.loads(response.read())
                return response.status, data.get('data', data) if phone else data
        except urllib.error.HTTPError as response:
            with response:
                return response.status, json.loads(response.read())

    def prepare_pc_prefix(self):
        goal = {'intent': 'Guardar el resultado acordado', 'destination': 'old-target.txt', 'criteria': [
            {'id': 'report', 'kind': 'text_exact', 'parameters': {'path': 'old-target.txt', 'text': RESULT.decode('utf-8')}}]}
        code, proposed = self.request('/axx-api/learning/propose', {'text': 'Preparar una misión de ensayo',
            'operation_id': 'pc-existing-mission', 'project_id': 'fixture-project', 'conversation_id': self.chat['id'],
            'goal_spec': goal, **self.scope})
        self.assertEqual(code, 200, proposed)
        self.assertEqual(proposed['state'], 'awaiting_approval', proposed)
        code, partial = self.request('/axx-api/learning/execute', {'operation_id': proposed['operation_id'],
            'approved': True, 'plan_hash': proposed['plan_hash'], **self.scope})
        self.assertEqual(code, 200, partial)
        self.assertEqual(partial['state'], 'goal_pending', partial)
        self.assertEqual((self.executor.workspace_root / 'prefix.txt').read_bytes(), PREFIX)
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertEqual(len(self.model.calls), 1)
        return partial

    def test_lost_phone_ack_and_lost_effect_response_reconcile_one_existing_mission(self):
        partial = self.prepare_pc_prefix()
        original_id = partial['operation_id']
        original_receipt = copy.deepcopy(partial['step_records'][0])
        code, listing = self.request('/v1/work/missions', phone=True)
        self.assertEqual(code, 200, listing)
        self.assertIn(original_id, [row['operation_id'] for row in listing['missions']])
        code, detail = self.request('/v1/work/mission?operation_id=' + urllib.parse.quote(original_id), phone=True)
        self.assertEqual(code, 200, detail)
        self.assertEqual(detail['goal_revision'], partial['goal_revision'])
        self.assertEqual(detail['plan_hash'], partial['plan_hash'])
        self.assertEqual(detail['conversation_id'], self.chat['shared_id'])
        self.assertTrue(detail['can_correct'], detail)
        goal = copy.deepcopy(detail['goal_spec'])
        goal['destination'] = 'new-target.txt'
        goal['criteria'][0]['parameters']['path'] = 'new-target.txt'
        body = {'command_id': str(uuid.uuid4()), 'operation_id': original_id,
            'conversation_id': detail['conversation_id'], 'plan_hash': detail['plan_hash'],
            'goal_revision': detail['goal_revision'], 'text': 'Guarda el resultado en new-target.txt y conserva el prefijo.',
            'goal_spec': goal, 'memory_scope': detail['memory_scope'], 'memory_context_id': detail['memory_context_id']}
        handler = self.gateway.httpd.RequestHandlerClass
        send = handler._send
        dropped = []

        def lose_correction_reply(instance, status, payload):
            if urllib.parse.urlsplit(instance.path).path == '/v1/work/mission-correct':
                dropped.append(True)
                instance.close_connection = True
                try: instance.connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                instance.connection.close()
                return
            return send(instance, status, payload)

        with patch.object(handler, '_send', new=lose_correction_reply):
            with self.assertRaises((http.client.RemoteDisconnected, urllib.error.URLError, ConnectionError)):
                self.request('/v1/work/mission-correct', body, phone=True)
        self.assertEqual(dropped, [True])
        self.assertEqual(len(self.model.calls), 2)
        code, receipt = self.request('/v1/work/mission-correction?command_id=' + body['command_id'], phone=True)
        self.assertEqual(code, 200, receipt)
        self.assertEqual(receipt['state'], 'confirmed', receipt)
        self.assertEqual(receipt['operation_id'], original_id)
        self.assertEqual(receipt['from_plan_hash'], partial['plan_hash'])
        code, corrected = self.request('/axx-api/learning/plan?id=' + urllib.parse.quote(original_id))
        self.assertEqual(code, 200, corrected)
        self.assertEqual(corrected['state'], 'awaiting_approval', corrected)
        self.assertEqual(corrected['goal_revision'], partial['goal_revision'] + 1)
        self.assertNotEqual(corrected['plan_hash'], partial['plan_hash'])
        self.assertIsNone(corrected.get('approved_hash'))
        self.assertEqual(corrected['step_records'][0], original_receipt)
        self.assertEqual(corrected['model_calls_used'], 2)
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertFalse((self.executor.workspace_root / 'old-target.txt').exists())
        self.assertFalse((self.executor.workspace_root / 'new-target.txt').exists())
        code, duplicate = self.request('/v1/work/mission-correct', body, phone=True)
        self.assertEqual(code, 200, duplicate)
        self.assertEqual(duplicate['state'], 'confirmed', duplicate)
        self.assertEqual(len(self.model.calls), 2)
        self.assertEqual(len(self.executor.list_operations()), 1)
        approval = {'operation_id': original_id, 'approved': True, 'plan_hash': corrected['plan_hash'], **self.scope}
        backend_handler = self.backend.RequestHandlerClass
        backend_send = backend_handler._send_json
        effect_reply_dropped = []

        def lose_effect_reply(instance, status, payload):
            if urllib.parse.urlsplit(instance.path).path == '/axx-api/learning/execute' and payload.get('state') == 'succeeded':
                effect_reply_dropped.append(True)
                instance.close_connection = True
                try: instance.connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                instance.connection.close()
                return
            return backend_send(instance, status, payload)

        with patch.object(backend_handler, '_send_json', new=lose_effect_reply):
            with self.assertRaises((http.client.RemoteDisconnected, urllib.error.URLError, ConnectionError)):
                self.request('/axx-api/learning/execute', approval)
        self.assertEqual(effect_reply_dropped, [True])
        code, final = self.request('/v1/work/mission?operation_id=' + urllib.parse.quote(original_id), phone=True)
        self.assertEqual(code, 200, final)
        self.assertEqual(final['operation_id'], original_id)
        self.assertEqual(final['state'], 'succeeded', final)
        self.assertTrue(final['mission']['completed'], final)
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertEqual(len(self.model.calls), 2)
        self.assertEqual((self.executor.workspace_root / 'prefix.txt').read_bytes(), PREFIX)
        output = self.executor.workspace_root / 'new-target.txt'
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), hashlib.sha256(RESULT).hexdigest())
        self.assertFalse((self.executor.workspace_root / 'old-target.txt').exists())
        repeated = self.request('/axx-api/learning/execute', approval)[1]
        self.assertEqual(repeated['state'], 'succeeded', repeated)
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertEqual(len(self.model.calls), 2)
        current = self.learning.get(original_id)
        self.assertEqual(current['step_records'][0], original_receipt)


if __name__ == '__main__':
    unittest.main()
