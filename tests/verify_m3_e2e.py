"""Milestone 3 E2E Verification: Conversation, Local Ollama Router, Command Library, Action Desk & File Isolation."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.server import AxxBridgeHandler, ThreadedHTTPServer, resolve_app_paths
from backend.inference.router import parse_strict_json
from backend.inference.adapter import InferenceAdapter
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.sync.identity_sync import IdentityStore

class Milestone3E2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls.tmp.name)
        cfg_path, state_path = resolve_app_paths('providers.json', 'state.db', data_dir=cls.data_dir)
        cfg = parse_strict_json(Path(cfg_path).read_bytes())
        cls.adapter = InferenceAdapter(cfg, state_path=state_path)
        cls.executor = ActionExecutor(db_path=state_path, workspace_root=cls.data_dir / 'artifacts')
        cls.commands = CommandService(cls.executor)
        cls.memory = ProceduralMemory(db_path=state_path)
        cls.identity = IdentityStore(db_path=state_path)

        handler = type('M3Handler', (AxxBridgeHandler,), {
            'adapter': cls.adapter,
            'executor': cls.executor,
            'commands': cls.commands,
            'memory': cls.memory,
            'identity': cls.identity,
            'config_path': Path(cfg_path),
        })
        cls.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        cls.port = cls.server.server_port
        cls.auth = {'Authorization': 'Bearer ' + cls.server.host_token}
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.commands.close()
        cls.adapter.close()
        cls.executor.close()
        cls.memory.close()
        cls.identity.close()
        cls.tmp.cleanup()

    def api(self, method: str, path: str, body: dict | None = None):
        headers = dict(self.auth)
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=35) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))

    def test_01_ollama_local_provider_ready_and_models_listed(self):
        status, data = self.api('GET', '/axx-api/status')
        self.assertEqual(status, 200)
        providers = data['details']['providers']
        ollama = next((p for p in providers if p['name'] == 'ollama-local'), None)
        self.assertIsNotNone(ollama, "ollama-local must be present in providers")
        self.assertEqual(ollama['state'], 'ready_locally')
        m_status, models = self.api('GET', '/axx-api/models')
        self.assertEqual(m_status, 200)
        self.assertIn('llama3.2:1b', models['models'])

    def test_02_real_chat_completion_via_ollama_local(self):
        status, res = self.api('POST', '/axx-api/chat', {
            'model': 'llama3.2:1b',
            'messages': [{'role': 'user', 'content': 'Responde únicamente con la palabra OK.'}],
            'stream': False
        })
        self.assertEqual(status, 200)
        content = res['choices'][0]['message']['content']
        self.assertTrue(isinstance(content, str) and len(content.strip()) > 0)
        self.assertEqual(res['axx_router']['provider'], 'ollama-local')

    def test_03_command_telemetry_and_artifact_write_e2e(self):
        status, resolved = self.api('POST', '/axx-api/commands/resolve', {'text': 'estado del sistema', 'source': 'text'})
        self.assertEqual(status, 200)
        self.assertEqual(resolved['command_id'], 'axx.system.telemetry')

        status, prep = self.api('POST', '/axx-api/commands/prepare', {
            'command_id': 'axx.system.telemetry', 'inputs': {}, 'source': 'text'
        })
        self.assertEqual(status, 200)
        self.assertEqual(prep['state'], 'prepared')

        status, exec_res = self.api('POST', '/axx-api/commands/execute', {'operation_id': prep['operation_id']})
        self.assertEqual(status, 200)
        self.assertEqual(exec_res['state'], 'succeeded')
        self.assertTrue(exec_res['postconditions_passed'])
        self.assertIn('disk_free_gb', exec_res['evidence'])
        self.assertGreater(exec_res['evidence']['memory_total_mb'], 0)

        # File write with approval inside isolated workspace
        status, write_prep = self.api('POST', '/axx-api/commands/prepare', {
            'command_id': 'axx.artifact.write',
            'inputs': {'path': 'm3_verified.txt', 'content': 'Verificación M3 real'},
            'source': 'text'
        })
        self.assertEqual(status, 200)
        self.assertEqual(write_prep['state'], 'awaiting_approval')
        status, write_exec = self.api('POST', '/axx-api/commands/execute', {
            'operation_id': write_prep['operation_id'],
            'approved': True
        })
        self.assertEqual(status, 200)
        self.assertEqual(write_exec['state'], 'succeeded')
        self.assertTrue(write_exec['postconditions_passed'])
        target = self.executor.workspace_root / 'm3_verified.txt'
        self.assertTrue(target.exists())
        self.assertEqual(write_exec['evidence']['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())

if __name__ == '__main__':
    unittest.main()
