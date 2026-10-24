"""Smoke test for Axx Local Loopback Bridge Server.
Starts the server in a daemon thread, executes HTTP requests against all endpoints,
and asserts expected status codes and payloads.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

from backend.server import run_server, AxxBridgeHandler, ThreadedHTTPServer, local_realtime_models
from backend.inference.adapter import InferenceAdapter
from backend.actions.executor import ActionExecutor
from backend.memory.procedural_memory import ProceduralMemory
from backend.sync.identity_sync import IdentityStore


class LocalRealtimeEligibilityTests(unittest.TestCase):
    def test_requires_exact_enabled_loopback_provider_and_ready_model(self):
        status = {'providers': [{'name': 'ollama-local', 'model': 'test-model', 'state': 'ready_locally'}]}
        provider = {'name': 'ollama-local', 'model': 'test-model', 'enabled': True,
                    'protocol': 'openai', 'base_url': 'http://127.0.0.1:11434/v1'}
        self.assertEqual(local_realtime_models({'providers': [provider]}, status), ['test-model'])
        for change in ({'enabled': False}, {'base_url': 'http://192.168.1.20:11434/v1'},
                       {'base_url': 'http://127.0.0.1:1234/v1'}, {'protocol': 'anthropic'}):
            self.assertEqual(local_realtime_models({'providers': [{**provider, **change}]}, status), [])
        self.assertEqual(local_realtime_models({'providers': [provider]},
                         {'providers': [{**status['providers'][0], 'state': 'disabled'}]}), [])

class ServerSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmp.name) / 'server_state.db'
        
        cfg = {
            'timeout_seconds': 5,
            'global_deadline_seconds': 70,
            'max_attempts': 1,
            'allow_paid': False,
            'providers': [{
                'name': 'mock-prov',
                'base_url': 'https://api.example.com/v1',
                'model': 'mock-model-free',
                'api_key_env': 'MOCK_KEY',
                'enabled': True,
                'free_confirmed': True,
                'daily_attempt_limit': 100,
                'capabilities': ['text']
            }]
        }
        import os
        os.environ['MOCK_KEY'] = 'mock-secret'

        def dummy_transport(p, body, timeout):
            return {
                'choices': [{
                    'message': {'role': 'assistant', 'content': 'Hello from Axx Bridge!'}
                }]
            }

        adapter = InferenceAdapter(cfg, state_path=cls.db_path)
        adapter.router.transport = dummy_transport
        executor = ActionExecutor(db_path=cls.db_path)
        memory = ProceduralMemory(db_path=cls.db_path)
        identity = IdentityStore(db_path=cls.db_path)

        AxxBridgeHandler.adapter = adapter
        AxxBridgeHandler.executor = executor
        AxxBridgeHandler.memory = memory
        AxxBridgeHandler.identity = identity

        # Start on ephemeral port with ThreadedHTTPServer
        cls.server = ThreadedHTTPServer(('127.0.0.1', 0), AxxBridgeHandler)
        cls.port = cls.server.server_port
        cls.auth = {'Authorization': 'Bearer ' + cls.server.host_token}
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        AxxBridgeHandler.adapter.close()
        AxxBridgeHandler.executor.close()
        AxxBridgeHandler.memory.close()
        AxxBridgeHandler.identity.close()
        cls.tmp.cleanup()

    def test_serve_html_root(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = resp.read()
            self.assertIn(b'<title>Axx', data)

    def test_status_endpoint(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/axx-api/status", headers=self.auth)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertNotIn('csrf', data)
            self.assertTrue(data['ready'])
            self.assertEqual(data['provider'], 'Axx Hardened Inference Router')

    def test_models_endpoint_with_csrf(self):
        # 1. Get CSRF token
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/axx-api/status", headers=self.auth)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertNotIn('csrf', json.loads(resp.read().decode('utf-8')))

        # 2. Get Models with token
        models_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/axx-api/models",
            headers=self.auth
        )
        with urllib.request.urlopen(models_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            models_data = json.loads(resp.read().decode('utf-8'))
            self.assertIn('mock-model-free', models_data['models'])

    def test_chat_endpoint_sse_stream(self):
        # Get CSRF
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/axx-api/status", headers=self.auth)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertNotIn('csrf', json.loads(resp.read().decode('utf-8')))

        chat_body = {
            'model': 'mock-model-free',
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'stream': True
        }
        chat_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/axx-api/chat",
            data=json.dumps(chat_body).encode('utf-8'),
            headers={'Content-Type': 'application/json', **self.auth},
            method='POST'
        )
        with urllib.request.urlopen(chat_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode('utf-8')
            self.assertIn('"choices":', content)
            self.assertIn('"delta":', content)
            self.assertIn('Hello from Axx Bridge!', content)
            self.assertIn('data: [DONE]', content)

    def test_action_execution_endpoint(self):
        act_body = {
            'tool_name': 'system_telemetry',
            'inputs': {}
        }
        act_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/axx-api/actions/execute",
            data=json.dumps(act_body).encode('utf-8'),
            headers={'Content-Type': 'application/json', **self.auth},
            method='POST'
        )
        with urllib.request.urlopen(act_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(data['state'], 'succeeded')
    def test_save_key_endpoint(self):
        save_body = {
            'provider': 'openrouter',
            'api_key': 'sk-or-v1-mocked-test-key-12345'
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/axx-api/auth/save-key",
            data=json.dumps(save_body).encode('utf-8'),
            headers={'Content-Type': 'application/json', **self.auth},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertTrue(data['ok'])
            self.assertIn('guardada', data['message'])
        import os
        provider = next(p for p in AxxBridgeHandler.adapter.config['providers'] if p['name'] == 'openrouter-user')
        self.assertEqual(os.environ.get(provider['api_key_env']), 'sk-or-v1-mocked-test-key-12345')
        self.assertNotIn('api_key', provider)

    def test_cli_anything_rejects_parallel_executor_and_untyped_macros(self):
        for route, body, status in (
            ('/axx-api/cli-anything/execute', {'target':'0x123','command':'type','approved':True}, 409),
            ('/axx-api/cli-anything/commands/develop', {'name':'unsafe','steps':[{'action':'click'}],'risk':'read'}, 400),
        ):
            req = urllib.request.Request(f'http://127.0.0.1:{self.port}'+route,
                data=json.dumps(body).encode(), headers={'Content-Type':'application/json', **self.auth})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req, timeout=3)
            self.assertEqual(caught.exception.code, status)

    def test_cli_catalog_is_observation_and_history_is_existing_ledger(self):
        from unittest.mock import patch, Mock
        from backend.actions.cli_anything_engine import CLIAppInterface
        app = CLIAppInterface(0x123,99,'Fixture','Editor',True,[],False,1)
        with patch('backend.actions.cli_anything_engine.ENGINE.resolve', return_value=app):
            req=urllib.request.Request(f'http://127.0.0.1:{self.port}/axx-api/cli-anything/commands?target=0x123',headers=self.auth)
            with urllib.request.urlopen(req,timeout=3) as response: catalog=json.load(response)
            self.assertEqual({c['name'] for c in catalog['commands']},{'inspect','read','focus'})
            self.assertFalse(any(c['execution_verified'] for c in catalog['commands']))
        ledger=Mock();ledger.operations.return_value=[{'operation_id':'recorded','state':'failed'}]
        with patch.object(AxxBridgeHandler,'commands',ledger):
            req=urllib.request.Request(f'http://127.0.0.1:{self.port}/axx-api/cli-anything/history?limit=1',headers=self.auth)
            with urllib.request.urlopen(req,timeout=3) as response: history=json.load(response)
            self.assertEqual(history['history'],ledger.operations.return_value)
            ledger.operations.assert_called_once_with()

if __name__ == '__main__':
    unittest.main()
