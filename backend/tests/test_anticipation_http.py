"""Authenticated host transport, real files and the existing command/executor journal."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.anticipation import AnticipationService
from backend.commands import CommandService
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class AnticipationHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.executor = ActionExecutor(Path(self.tmp.name) / 'state.db', Path(self.tmp.name) / 'artifacts')
        self.commands = CommandService(self.executor)
        self.anticipation = AnticipationService(self.commands)
        self.commands.dispatch_guard = self.anticipation.dispatch_guard
        handler = type('AnticipationHandler', (AxxBridgeHandler,), {
            'executor': self.executor, 'commands': self.commands, 'anticipation': self.anticipation})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.anticipation.close()
        self.commands.close()
        self.executor.close()
        self.tmp.cleanup()

    def request(self, action, body=None, *, auth=True, origin=None):
        headers = {'Authorization': 'Bearer ' + self.server.host_token} if auth else {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if origin:
            headers['Origin'] = origin
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/axx-api/' + action,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as response:
            with response:
                return response.code, json.load(response)

    def generated(self, name='trial.txt', task='task-a'):
        command = self.commands.prepare('axx.artifact.write', {'path': name, 'content': 'Ensayo real: Axx'},
                                        conversation_id=task)
        result = self.commands.execute(command['operation_id'], approved=True)
        self.assertTrue(result['postconditions_passed'])
        self.anticipation.tick()
        return result

    def test_host_auth_validation_and_observation_pause(self):
        endpoint = 'anticipation/status'
        self.assertEqual(self.request(endpoint, auth=False)[0], 401)
        self.assertEqual(self.request(endpoint, origin='https://untrusted.invalid')[0], 403)
        self.assertEqual(self.request('anticipation/configure', {'profile': 'invalid'})[0], 400)
        self.assertEqual(self.request('anticipation/accept', {'suggestion_id': 'x', 'plan_hash': 'x', 'approved': True})[0], 400)
        self.assertEqual(self.request(endpoint + '?task_id=a&task_id=b')[0], 400)
        code, status = self.request(endpoint)
        self.assertEqual(code, 200)
        self.assertEqual(status['profile'], 'discreto')
        self.assertEqual(self.request('anticipation/configure', {'profile': 'full'})[0], 200)
        self.assertEqual(self.request('actions/cancel', {})[0], 200)
        self.assertTrue(self.request(endpoint)[1]['paused'])

    def test_copilot_accepts_exact_plan_and_keeps_task_boundary(self):
        self.assertEqual(self.request('anticipation/configure', {'profile': 'copiloto'})[0], 200)
        artifact = self.generated()
        suggestions = self.request('anticipation/status?task_id=task-a')[1]['suggestions']
        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        self.assertEqual(self.request('anticipation/status?task_id=task-b')[1]['suggestions'], [])
        self.assertEqual(self.request('anticipation/accept', {
            'suggestion_id': suggestion['suggestion_id'], 'plan_hash': '0' * 64})[0], 400)
        code, accepted = self.request('anticipation/accept', {
            'suggestion_id': suggestion['suggestion_id'], 'plan_hash': suggestion['plan_hash']})
        self.assertEqual(code, 200, accepted)
        self.assertEqual(accepted['state'], 'VERIFIED', accepted)
        digest = hashlib.sha256(Path(artifact['output']['path']).read_bytes()).hexdigest()
        self.assertEqual(digest, artifact['output']['sha256'])
        self.assertEqual(self.request('anticipation/accept', {
            'suggestion_id': suggestion['suggestion_id'], 'plan_hash': suggestion['plan_hash']})[1]['state'], 'VERIFIED')
        self.assertEqual(len(self.executor.list_operations()), 2)

    def test_full_grant_is_scoped_and_revocable(self):
        self.request('anticipation/configure', {'profile': 'full'})
        code, grant = self.request('anticipation/grant', {'task_id': 'task-a', 'capability': 'verify_artifact',
            'root': str(self.executor.workspace_root), 'expires_at': None})
        self.assertEqual(code, 200, grant)
        self.generated('permitted.txt')
        self.assertEqual(self.request('anticipation/status?task_id=task-a')[1]['suggestions'][0]['state'], 'VERIFIED')
        self.generated('other-task.txt', 'task-b')
        self.assertEqual(len(self.executor.list_operations()), 3)
        self.assertEqual(self.request('anticipation/revoke', {'grant_id': grant['grant_id']})[0], 200)
        self.generated('revoked.txt')
        self.assertEqual(len(self.executor.list_operations()), 4)
