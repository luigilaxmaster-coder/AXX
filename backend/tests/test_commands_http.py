"""Actual authenticated loopback HTTP -> catalog -> executor, without external services."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class CommandsHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.executor = ActionExecutor(Path(self.tmp.name) / 'state.db', Path(self.tmp.name) / 'artifacts')
        self.commands = CommandService(self.executor)
        self.memory = ProceduralMemory(self.executor.db_path)
        handler = type('CommandsHandler', (AxxBridgeHandler,), {'executor': self.executor, 'commands': self.commands, 'memory': self.memory})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.commands.close()
        self.memory.close()
        self.executor.close()
        self.tmp.cleanup()

    def request(self, path, body=None, auth=True, origin=None, raw=None):
        headers = {'Authorization': 'Bearer ' + self.server.host_token} if auth else {}
        if origin:
            headers['Origin'] = origin
        if body is not None or raw is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/axx-api/' + path,
            data=raw if raw is not None else json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            try:
                return response.code, json.loads(response.read())
            finally:
                response.close()

    def test_legacy_routes_cannot_bypass_catalog_policy(self):
        for tool in ('file_artifact_writer', 'blender_render_fixture'):
            inputs = {'path': 'bypass.txt', 'content': 'x'} if tool == 'file_artifact_writer' else {'filename': 'fixture.png'}
            status, result = self.request('actions/execute', {'tool_name': tool, 'inputs': inputs})
            self.assertEqual(status, 403)
            self.assertEqual(result['error']['code'], 'USE_COMMAND_POLICY')
        self.memory.register_recipe(id='legacy-write', intent_key='legacy-write', status='verified',
            steps=[{'tool': 'file_artifact_writer', 'args': {'path': '$inputs.path', 'content': '$inputs.content'}}],
            schema={'path': {'type': 'string', 'required': True}, 'content': {'type': 'string', 'required': True}})
        status, _ = self.request('recipes/execute', {'intent_key': 'legacy-write', 'inputs': {'path': 'legacy.txt', 'content': 'x'}})
        self.assertEqual(status, 403)
        status, pending = self.request('recipes/prepare', {'intent_key': 'legacy-write', 'inputs': {'path': 'legacy.txt', 'content': 'x'}})
        self.assertEqual(status, 200)
        self.assertEqual(pending['state'], 'awaiting_approval')
        self.assertFalse((self.executor.workspace_root / 'legacy.txt').exists())
        status, result = self.request('commands/execute', {'operation_id': pending['operation_id'], 'approved': True})
        self.assertEqual(result['state'], 'succeeded')
        self.assertFalse((self.executor.workspace_root / 'bypass.txt').exists())

    def test_saved_recipe_listing_exposes_actual_parameter_schema(self):
        self.memory.register_recipe(id='telemetry', intent_key='telemetry', status='verified',
            steps=[{'tool': 'system_telemetry', 'args': {}}], schema={})
        self.memory.register_recipe(id='write', intent_key='write', status='verified',
            steps=[{'tool': 'file_artifact_writer', 'args': {'path': '$inputs.path', 'content': '$inputs.content'}}],
            schema={'path': {'type': 'string', 'required': True}, 'content': {'type': 'string', 'required': True}})
        status, result = self.request('recipes')
        self.assertEqual(status, 200)
        by_id = {row['id']: row for row in result['recipes']}
        self.assertEqual(by_id['telemetry']['schema'], {})
        self.assertEqual(set(by_id['write']['schema']), {'path', 'content'})
        status, pending = self.request('recipes/prepare', {'intent_key': 'telemetry', 'inputs': {}})
        self.assertEqual(status, 200)
        self.assertEqual(pending['command_id'], 'axx.system.telemetry')
        self.assertEqual(self.request('commands/execute', {'operation_id': pending['operation_id']})[1]['state'], 'succeeded')

    def test_catalog_search_and_real_text_voice_resolution_require_host(self):
        self.assertEqual(self.request('commands', auth=False)[0], 401)
        self.assertEqual(self.request('commands', origin='https://untrusted.invalid')[0], 403)
        status, catalog = self.request('commands?q=axx.system.telemetry&limit=1')
        self.assertEqual(status, 200)
        self.assertEqual(catalog['commands'][0]['id'], 'axx.system.telemetry')
        for source in ('text', 'voice'):
            status, result = self.request('commands/resolve', {'text': 'estado del sistema', 'source': source})
            self.assertEqual(status, 200)
            self.assertEqual(result['command_id'], 'axx.system.telemetry')

    def test_typed_prepare_approval_hash_verification_and_observation(self):
        status, operation = self.request('commands/prepare', {'command_id': 'axx.artifact.write',
            'inputs': {'path': 'http.txt', 'content': 'local HTTP evidence'}, 'source': 'text'})
        self.assertEqual(status, 200)
        op_id = operation['operation_id']
        status, denied = self.request('commands/execute', {'operation_id': op_id})
        self.assertEqual(status, 403)
        self.assertEqual(denied['error']['code'], 'APPROVAL_REQUIRED')
        self.assertFalse((self.executor.workspace_root / 'http.txt').exists())
        status, result = self.request('commands/execute', {'operation_id': op_id, 'approved': True})
        self.assertEqual(status, 200)
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        observed = self.request('commands/operations?operation_id=' + op_id)[1]['operation']
        self.assertEqual(observed['evidence']['sha256'], result['evidence']['sha256'])

    def test_cancel_and_invalid_requests_never_write(self):
        for body in ({'command_id': [], 'inputs': {}, 'source': 'text'},
                     {'command_id': 'axx.process.inspect', 'inputs': {'pid': True}, 'source': 'text'},
                     {'command_id': 'axx.system.telemetry', 'inputs': {}, 'source': 'voice', 'shell': 'calc'}):
            self.assertEqual(self.request('commands/prepare', body)[0], 400)
        status, operation = self.request('commands/prepare', {'command_id': 'axx.artifact.write',
            'inputs': {'path': 'cancel.txt', 'content': 'x'}, 'source': 'voice'})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('commands/cancel', {'operation_id': operation['operation_id']})[1]['state'], 'cancelled')
        self.assertEqual(self.request('commands/execute', {'operation_id': operation['operation_id'], 'approved': True})[1]['state'], 'cancelled')
        self.assertFalse((self.executor.workspace_root / 'cancel.txt').exists())
        self.assertEqual(self.request('commands?limit=100000')[0], 400)
        self.assertEqual(self.request('commands?limit=1&limit=2')[0], 400)

    def test_duplicate_json_keys_rejected_at_transport(self):
        status, _ = self.request('commands/execute', raw=b'{"operation_id":"x","approved":false,"approved":true}')
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
