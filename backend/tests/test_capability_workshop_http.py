"""Authenticated workshop HTTP contracts with real SQLite and command receipts."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.action_learning import ActionLearning
from backend.capability_workshop import CapabilityWorkshop
from backend.chat_store import ChatStore
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class Model:
    def route(self, request):
        return {'ok': True, 'message': {'content': json.dumps(definition())}}


def definition():
    return {'kind': 'workflow', 'title': 'Diagnóstico local', 'objective': 'Consultar estado del equipo',
            'schema': {'type': 'object', 'properties': {}, 'required': []},
            'templates': [{'command_id': 'axx.system.telemetry', 'inputs': {}}], 'sample_inputs': {}}


class WorkshopHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name)
        self.executor = ActionExecutor(path / 'state.db', path / 'artifacts')
        self.commands = CommandService(self.executor)
        self.learning = ActionLearning(self.commands, Model())
        self.commands.learning = self.learning
        self.workshop = CapabilityWorkshop(self.learning)
        self.chats = ChatStore(path / 'state.db')
        handler = type('WorkshopHandler', (AxxBridgeHandler,), {'workshop': self.workshop,
            'commands': self.commands, 'learning': self.learning, 'chats': self.chats})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)
        self.workshop.close(); self.learning.close(); self.commands.close(); self.chats.close(); self.executor.close()
        self.tmp.cleanup()

    def request(self, path, body=None, auth=True, origin=None):
        headers = {'Content-Type': 'application/json'}
        if auth: headers['Authorization'] = 'Bearer ' + self.server.host_token
        if origin: headers['Origin'] = origin
        req = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/axx-api/' + path,
            data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as result: return result.status, json.loads(result.read())
        except urllib.error.HTTPError as result:
            with result: return result.status, json.loads(result.read())

    @staticmethod
    def ref(record): return {k: record[k] for k in ('id', 'revision', 'digest')}

    def test_auth_origin_and_unknown_fields(self):
        self.assertEqual(self.request('capabilities/list', auth=False)[0], 401)
        self.assertEqual(self.request('capabilities/list', origin='https://untrusted.invalid')[0], 403)
        self.assertEqual(self.request('capabilities/create', {'definition': definition(), 'approved': True})[0], 400)
        self.assertEqual(self.request('capabilities/list?execute=true')[0], 400)
        self.assertEqual(self.request('capabilities/export?id=x&revision=nan')[0], 400)

    def test_complete_verified_lifecycle_and_revocation(self):
        status, draft = self.request('capabilities/create', {'definition': definition()})
        self.assertEqual(status, 200, draft)
        ref = self.ref(draft)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.request('capabilities/activate', ref)[0], 400)
        status, approved = self.request('capabilities/approve', ref | {'confirmed': True})
        self.assertEqual(status, 200, approved)
        status, plan = self.request('capabilities/prepare', ref)
        self.assertEqual(status, 200, plan)
        self.assertEqual(plan['state'], 'awaiting_approval')
        status, result = self.request('learning/execute', {'operation_id': plan['operation_id'], 'approved': True})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        status, active = self.request('capabilities/activate', ref)
        self.assertEqual(status, 200, active)
        self.assertEqual(active['active_revision'], draft['revision'])
        self.assertTrue(active['validation']['runtime_verified'])
        self.assertEqual(self.request('capabilities/revoke', ref)[0], 200)
        self.assertEqual(self.request('capabilities/get?id=' + draft['id'])[1]['state'], 'revoked')

    def test_generation_creates_only_a_draft_and_stale_changes_fail(self):
        status, draft = self.request('capabilities/generate', {'goal': 'Consulta el estado del equipo'})
        self.assertEqual(status, 200, draft)
        self.assertIsNone(draft['active_revision'])
        self.assertEqual(self.executor.list_operations(), [])
        changed = definition() | {'title': 'Otro nombre'}
        status, revised = self.request('capabilities/revise', self.ref(draft) | {'definition': changed})
        self.assertEqual(status, 200, revised)
        self.assertEqual(self.request('capabilities/approve', self.ref(draft) | {'confirmed': True})[0], 400)
        self.assertEqual(self.request('capabilities/get?id=' + draft['id'] + '&id=duplicate')[0], 400)
        status, exported = self.request('capabilities/export?id=' + draft['id'])
        self.assertEqual(status, 200, exported)
        self.assertIn('Otro nombre', exported['content'])

    def test_source_is_exportable_text_and_never_executable(self):
        source = {'kind': 'source_proposal', 'title': 'Nueva herramienta', 'objective': 'Revisión manual',
                  'language': 'python', 'source': "print('proposal only')", 'readme': 'Requiere integración y pruebas.'}
        status, draft = self.request('capabilities/create', {'definition': source})
        self.assertEqual(status, 200, draft)
        self.assertEqual(self.request('capabilities/prepare', self.ref(draft))[0], 400)
        self.assertEqual(self.request('capabilities/activate', self.ref(draft))[0], 400)
        self.assertEqual(self.executor.list_operations(), [])

    def test_unknown_conversation_cannot_bind_a_generation(self):
        self.assertEqual(self.request('capabilities/generate', {'goal': 'Consulta estado', 'conversation_id': 'not-a-chat'})[0], 400)


if __name__ == '__main__': unittest.main()
