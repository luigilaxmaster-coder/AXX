"""Offline Codex protocol contracts for the isolated proposal-only purpose."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from backend.connect.provider import ProviderError, TERMINAL
from backend.connect.tests.test_provider import ControlledProvider


def request(**changes):
    return {'request_id': 'cap-fixture', 'model': 'gpt-6.1-sol', 'provider_name': '@codex',
            'task': 'code', 'allow_paid': False, 'deadline_ms': 2000,
            'messages': [{'role': 'system', 'content': 'Return one python_transform JSON definition.'},
                         {'role': 'user', 'content': 'Normalizar texto.'}], **changes}


class CapabilityProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.dispatched = []
        self.provider = ControlledProvider(None, Path(self.temporary.name) / 'state.db', self.temporary.name,
                                          dispatcher=lambda *args: self.dispatched.append(args))

    def tearDown(self): self.provider.close(); self.temporary.cleanup()

    def wait_started(self, request_id='cap-fixture'):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try: run = self.provider.get(request_id)
            except ProviderError: run = None
            if run and (run.get('turn_id') or run['state'] in TERMINAL): return run
            time.sleep(.005)
        self.fail('Controlled proposal turn did not start')

    def background(self, body=None, planning=False):
        results = {}
        def work():
            try: results['result'] = (self.provider.generate_plan if planning else self.provider.generate_capability)(body or request())
            except Exception as exc: results['error'] = exc
        thread = threading.Thread(target=work, daemon=True); thread.start()
        return thread, results

    def test_planning_has_its_own_contract_and_cannot_request_tools(self):
        thread,results=self.background(request(task='plan'),planning=True)
        run=self.wait_started()
        self.assertEqual(run['purpose'],'planning')
        self.assertTrue(run['conversation_id'].startswith('axx-planning-'))
        start=next(params for method,params in self.provider.rpc_calls if method=='thread/start')
        self.assertEqual(start['dynamicTools'],[])
        self.assertIn('capability_request',start['developerInstructions'])
        self.provider._server_request({'id':88,'method':'item/tool/call','params':{
            'threadId':'thread-test','turnId':'turn-test','tool':'axx_execute_action','arguments':{}}})
        thread.join(2)
        self.assertEqual(results['error'].code,'CAPABILITY_TOOLS_FORBIDDEN')
        self.assertEqual(self.dispatched,[])

    def finish(self, text='{"unavailable":"fixture"}', status='completed'):
        self.provider._notification({'method': 'item/agentMessage/delta', 'params': {
            'threadId': 'thread-test', 'turnId': 'turn-test', 'delta': text}})
        self.provider._notification({'method': 'turn/completed', 'params': {
            'threadId': 'thread-test', 'turn': {'id': 'turn-test', 'status': status}}})

    def test_exact_selected_model_json_response_and_fresh_thread_without_tools(self):
        isolated = 'axx-capability-' + hashlib.sha256(b'cap-fixture').hexdigest()[:32]
        with self.provider.lock, self.provider.db:
            self.provider.db.execute('INSERT INTO connect_conversations VALUES (?,?,?,?)',
                                     (isolated + ':axx-direct-v1', 'untrusted-old-chat', 'gpt-6.1-sol', time.time()))
        self.provider._tool_specs = lambda: [{'name': 'axx_execute_action'}]
        thread, results = self.background(); run = self.wait_started()
        self.assertEqual(run['conversation_id'], isolated)
        start = next(params for method, params in self.provider.rpc_calls if method == 'thread/start')
        self.assertEqual(start['dynamicTools'], []); self.assertFalse(start['allowProviderModelFallback'])
        self.assertTrue(start['ephemeral'])
        self.assertEqual(start['sandbox'], 'read-only'); self.assertIn('Return JSON only', start['developerInstructions'])
        self.assertFalse(any(method == 'thread/resume' for method, _ in self.provider.rpc_calls))
        turn = next(params for method, params in self.provider.rpc_calls if method == 'turn/start')
        self.assertEqual(json.loads(turn['input'][0]['text'])['goal'], 'Normalizar texto.')
        self.finish(); thread.join(2)
        self.assertNotIn('error', results, results)
        result = results['result']; self.assertTrue(result['ok'])
        self.assertEqual(result['route'], {'model': 'gpt-6.1-sol', 'provider_name': '@codex'})
        self.assertEqual(result['message']['content'], '{"unavailable":"fixture"}')
        self.assertEqual(self.dispatched, []); self.assertTrue(self.provider.get('cap-fixture')['inference_verified'])
        self.assertTrue(any(method == 'account/rateLimits/read' for method, _ in self.provider.rpc_calls))
        with self.provider.lock:
            self.assertIsNone(self.provider.db.execute('SELECT 1 FROM connect_conversations WHERE conversation_id=?',
                              (isolated+':axx-direct-v2',)).fetchone())

    def test_runtime_must_confirm_ephemeral_before_receiving_private_context(self):
        original = self.provider._request
        def rpc(method, params=None, timeout=20):
            answer = original(method, params, timeout)
            if method == 'thread/start':answer['thread']['ephemeral']=False
            return answer
        self.provider._request = rpc
        with self.assertRaises(ProviderError) as raised:self.provider.generate_plan(request(task='plan'))
        self.assertEqual(raised.exception.code,'EPHEMERAL_UNVERIFIED')
        self.assertFalse(any(method=='turn/start' for method,_ in self.provider.rpc_calls))

    def assert_request_denied(self, method, params):
        thread, results = self.background(); self.wait_started()
        self.provider._server_request({'id': 99, 'method': method, 'params': {
            'threadId': 'thread-test', 'turnId': 'turn-test', **params}})
        thread.join(2)
        self.assertIsInstance(results.get('error'), ProviderError)
        self.assertEqual(results['error'].code, 'CAPABILITY_TOOLS_FORBIDDEN')
        self.assertEqual(self.dispatched, []); self.assertFalse(self.provider.approvals)
        reply = next(row for row in self.provider.writes if row.get('id') == 99)
        self.assertIn('error', reply)
        self.assertFalse(self.provider.get('cap-fixture')['inference_verified'])

    def test_dynamic_tools_are_denied_even_if_runtime_requests_one(self):
        self.assert_request_denied('item/tool/call', {'tool': 'axx_execute_action', 'arguments': {}})

    def test_native_shell_permission_and_other_server_requests_are_denied(self):
        self.assert_request_denied('item/commandExecution/requestApproval', {'command': 'read a local file'})

    def test_paid_implicit_provider_model_and_unbounded_requests_rejected_before_inference(self):
        for changes in ({'allow_paid': True}, {'model': ''}, {'provider_name': ''}, {'task': 'shell'},
                        {'deadline_ms': 70001}, {'deadline_ms': True},
                        {'messages': [{'role': 'user', 'content': 'act now'}]}):
            with self.subTest(changes=changes), self.assertRaises(ProviderError):
                self.provider.generate_capability(request(**changes))
        self.assertEqual(self.provider.rpc_calls, [])

    def test_runtime_model_mismatch_has_no_turn_and_no_fallback(self):
        original = self.provider._request
        def rpc(method, params=None, timeout=20):
            answer = original(method, params, timeout)
            return dict(answer, model='different-model') if method == 'thread/start' else answer
        self.provider._request = rpc
        with self.assertRaises(ProviderError) as raised: self.provider.generate_capability(request())
        self.assertEqual(raised.exception.code, 'MODEL_MISMATCH')
        self.assertFalse(any(method == 'turn/start' for method, _ in self.provider.rpc_calls))

    def test_auth_and_included_usage_remain_mandatory(self):
        self.provider.authenticated = False
        with self.assertRaises(ProviderError) as raised: self.provider.generate_capability(request())
        self.assertEqual(raised.exception.code, 'AUTH_REQUIRED')
        self.assertFalse(any(method == 'turn/start' for method, _ in self.provider.rpc_calls))

    def test_generation_deadline_cancels_instead_of_changing_provider(self):
        before = time.monotonic()
        with self.assertRaises(ProviderError) as raised:
            self.provider.generate_capability(request(deadline_ms=50))
        self.assertEqual(raised.exception.code, 'DEADLINE_EXCEEDED')
        self.assertLess(time.monotonic() - before, 1)
        self.assertTrue(self.provider.get('cap-fixture')['cancel_requested'])

    def test_capability_request_cannot_reuse_main_chat_or_change_duplicate_goal(self):
        self.provider.start({'request_id': 'cap-fixture', 'conversation_id': 'axx-main', 'model': 'gpt-6.1-sol',
                             'message': 'Contract and goal', 'purpose': 'capability'})
        run = self.wait_started()
        self.assertNotEqual(run['conversation_id'], 'axx-main')
        with self.assertRaises(ProviderError) as raised:
            self.provider.start({'request_id': 'cap-fixture', 'message': 'Changed goal', 'purpose': 'capability'})
        self.assertEqual(raised.exception.code, 'DUPLICATE_MISMATCH')


if __name__ == '__main__': unittest.main()
