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
from backend.action_learning import ActionLearning
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

    def test_mission_attention_transport_admits_once_without_executing_or_marking_children_shown(self):
        learning = ActionLearning(self.commands, None)
        self.commands.learning = learning
        learning.anticipation = self.anticipation
        try:
            self.request('anticipation/configure', {'profile': 'copiloto', 'profiles': {
                'copiloto': {'cooldown_seconds': 0}}})
            plan = learning.prepare_steps('Entrega HTTP real', [{'command_id': 'axx.artifact.write',
                'inputs': {'path': f'http-{index}.txt', 'content': str(index)}} for index in range(3)],
                conversation_id='task-a', project_id='project-a')
            completed = learning.execute(plan['operation_id'], approved=True)
            self.assertTrue(completed['mission']['completed'])
            self.anticipation.tick()
            code, status = self.request('anticipation/status?task_id=task-a')
            self.assertEqual(code, 200)
            self.assertEqual(len(status['mission_attention']), 1)
            group = status['mission_attention'][0]
            self.assertEqual(group['category'], 'done')
            self.assertEqual(len(group['suggestion_ids']), 3)
            before = self.executor.list_operations()
            body = {'suggestion_id': group['representative_suggestion_id'], 'action': 'shown',
                'attention_key': group['attention_key'], 'phase': 'claim'}
            self.assertEqual(self.request('anticipation/feedback', body, auth=False)[0], 401)
            self.assertEqual(self.request('anticipation/feedback', body, origin='https://untrusted.invalid')[0], 403)
            self.assertEqual(self.request('anticipation/feedback', body | {'approved': True})[0], 400)
            self.assertEqual(self.request('anticipation/feedback', body | {'action': 'accept'})[0], 400)
            self.assertEqual(self.request('anticipation/feedback', body | {'phase': 'unknown'})[0], 400)
            code, claimed = self.request('anticipation/feedback', body)
            self.assertEqual(code, 200, claimed)
            self.assertTrue(claimed['admission']['new_claim'])
            self.assertFalse(claimed['admission']['presented'])
            repeated = self.request('anticipation/feedback', body)[1]
            self.assertTrue(repeated['admission']['accepted'])
            self.assertFalse(repeated['admission']['new_claim'])
            confirmed = self.request('anticipation/feedback', body | {'phase': 'presented'})[1]
            self.assertTrue(confirmed['admission']['presented'])
            self.assertFalse(confirmed['admission']['new_claim'])
            current = self.request('anticipation/status?task_id=task-a')[1]
            self.assertEqual(current['metrics']['shown'], 0)
            self.assertEqual(current['metrics']['attention_interruptions'], 1)
            self.assertEqual(current['metrics']['attention_presented'], 1)
            self.assertFalse(any(row.get('shown_at') for row in current['suggestions']))
            self.assertEqual(self.executor.list_operations(), before)
            self.assertEqual(self.request('anticipation/status?task_id=task-b')[1]['mission_attention'], [])
        finally:
            learning.close()

    def test_explicit_response_acknowledges_current_manual_mission_without_proactive_charge(self):
        learning = ActionLearning(self.commands, None)
        self.commands.learning = learning
        learning.anticipation = self.anticipation
        try:
            plan = learning.prepare_steps('Respuesta solicitada', [{'command_id': 'axx.artifact.write',
                'inputs': {'path': 'manual.txt', 'content': 'manual'}}], conversation_id='task-a')
            group = self.request('anticipation/status?task_id=task-a')[1]['mission_attention'][0]
            self.assertEqual(group['category'], 'decision')
            self.assertIsNone(group['representative_suggestion_id'])
            self.assertFalse(group['interruption']['eligible'])
            body = {'mission_id': plan['operation_id'], 'action': 'shown', 'attention_key': group['attention_key'],
                'phase': 'response', 'response_digest': group['response_digest']}
            self.assertEqual(self.request('anticipation/feedback', {key: value for key, value in body.items() if key != 'response_digest'})[0], 400)
            self.assertEqual(self.request('anticipation/feedback', body | {'phase': 'claim'})[0], 400)
            denied = self.request('anticipation/feedback', body | {'attention_key': '0' * 64})[1]
            self.assertFalse(denied['admission']['accepted'])
            with learning.db:
                current_plan = json.loads(learning.db.execute('SELECT payload FROM learning_plans WHERE id=?', (plan['operation_id'],)).fetchone()[0])
                current_plan['message'] = 'Nuevo diagnóstico después del GET, antes del reconocimiento.'
                learning.db.execute('UPDATE learning_plans SET payload=? WHERE id=?', (json.dumps(current_plan), plan['operation_id']))
            raced = self.request('anticipation/feedback', body)[1]
            self.assertFalse(raced['admission']['accepted'])
            self.assertEqual(raced['admission']['reason'], 'stale_response')
            self.assertEqual(self.anticipation.db.execute('SELECT COUNT(*) FROM anticipation_attention_receipts').fetchone()[0], 0)
            refreshed = self.request('anticipation/status?task_id=task-a')[1]['mission_attention'][0]
            self.assertEqual(refreshed['attention_key'], group['attention_key'])
            self.assertNotEqual(refreshed['response_digest'], body['response_digest'])
            body['response_digest'] = refreshed['response_digest']
            code, acknowledged = self.request('anticipation/feedback', body)
            self.assertEqual(code, 200, acknowledged)
            self.assertTrue(acknowledged['admission']['accepted'])
            self.assertTrue(acknowledged['admission']['presented'])
            self.assertFalse(acknowledged['admission']['new_claim'])
            self.assertFalse(self.request('anticipation/feedback', body)[1]['admission']['new_claim'])
            current = self.request('anticipation/status?task_id=task-a')[1]
            self.assertEqual(current['metrics']['attention_budget_used_last_hour'], 0)
            self.assertEqual(current['metrics']['attention_interruptions'], 0)
            self.assertEqual(current['metrics']['attention_response_acknowledgements'], 1)
            self.assertEqual(self.executor.list_operations(), [])
            dismissed = self.request('anticipation/feedback', {'mission_id': plan['operation_id'], 'action': 'dismiss', 'attention_key': group['attention_key']})
            self.assertEqual(dismissed[0], 200, dismissed)
            self.assertTrue(dismissed[1]['attention']['interruption']['dismissed'])
            suppression = {'mission_id': plan['operation_id'], 'action': 'suppress', 'attention_key': group['attention_key']}
            self.assertTrue(self.request('anticipation/feedback', suppression)[1]['attention']['interruption']['mission_suppressed'])
            self.assertEqual(self.request('anticipation/feedback', suppression | {'phase': 'claim'})[0], 400)
            restored = self.request('anticipation/feedback', suppression | {'action': 'restore'})[1]['attention']
            self.assertFalse(restored['interruption']['mission_suppressed'])
            self.assertTrue(restored['interruption']['dismissed'])
            self.assertEqual(self.executor.list_operations(), [])
        finally:
            learning.close()
