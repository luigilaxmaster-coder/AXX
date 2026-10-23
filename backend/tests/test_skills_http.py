"""Authenticated API contract with real SQLite and filesystem effects."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.demonstration import DemonstrationService, planning_reference
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class Model:
    calls = 0
    def route(self, envelope):
        self.calls += 1
        self.envelope = envelope
        return {'ok': True, 'message': {'content': json.dumps({'title': 'Crear informe', 'steps': [
            {'command_id': 'axx.artifact.write', 'inputs': {'path': 'first.txt', 'content': 'real'}}]})}}
    def cancel(self, *args): return {}


class SkillsHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.executor = ActionExecutor(Path(self.tmp.name) / 'state.db', Path(self.tmp.name) / 'artifacts')
        self.commands = CommandService(self.executor)
        self.model = Model()
        self.learning = ActionLearning(self.commands, self.model)
        self.demonstration = DemonstrationService(self.executor.db_path)
        handler = type('SkillsHandler', (AxxBridgeHandler,), {'executor': self.executor, 'commands': self.commands,
            'learning': self.learning, 'adapter': self.model, 'demonstration': self.demonstration})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        self.demonstration.close(); self.learning.close(); self.commands.close(); self.executor.close(); self.tmp.cleanup()

    def request(self, path, body=None, auth=True):
        req = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/axx-api/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json', **({'Authorization':'Bearer '+self.server.host_token} if auth else {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as response: return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error: return error.code, json.loads(error.read())

    def test_parameterized_skill_context_and_resume_cross_http_without_duplicate_effects(self):
        code, plan = self.request('learning/propose', {'text':'crear informe', 'operation_id':'first', 'project_id':'office', 'selection_mode':'automatic_free'})
        self.assertEqual(code, 200, plan); self.assertEqual(self.model.envelope['selection_mode'], 'automatic_free')
        self.assertEqual(self.request('learning/execute', {'operation_id':'first','approved':True})[1]['state'], 'succeeded')
        skill = self.request('learning/actions?project_id=office')[1]['actions'][0]
        self.assertEqual(self.request('learning/actions?project_id=')[1]['actions'], [])
        code, configured = self.request('learning/configure', {'id':skill['id'], 'changes':{
            'schema':{'type':'object','properties':{'filename':{'type':'string'}},'required':['filename']},
            'templates':[{'command_id':'axx.artifact.write','inputs':{'path':'{{filename}}','content':'real'}}],
            'examples':['otra entrega']}})
        self.assertEqual(code, 200, configured)
        self.assertEqual(self.request('learning/context', {'project_id':'office','changes':{'current_folder':'Office','aliases':{'informe habitual':skill['id']}}})[0], 200)
        self.commands.learning = self.learning
        self.assertEqual(self.request('commands/resolve', {'text':'informe habitual','source':'voice','project_id':'office'})[1]['match'],'learned')
        self.assertNotEqual(self.request('commands/resolve', {'text':'informe habitual','project_id':''})[1]['match'],'learned')
        code, second = self.request('learning/propose', {'text':'informe habitual', 'inputs':{'filename':'second.txt'},'project_id':'office','operation_id':'second'})
        self.assertEqual(code,200,second); self.assertEqual(second['model_calls_used'],0)
        result = self.request('learning/resume', {'operation_id':'second','approved':False})[1]
        self.assertEqual(result['state'],'awaiting_approval')
        self.assertEqual(self.request('learning/execute', {'operation_id':'second','approved':True})[1]['state'],'succeeded')
        count = len(self.executor.list_operations())
        self.request('learning/resume', {'operation_id':'second','approved':True})
        self.assertEqual(len(self.executor.list_operations()),count)
        self.assertEqual((self.executor.workspace_root/'second.txt').read_text(),'real')
        self.assertEqual(len(self.request('learning/plans?project_id=office')[1]['plans']),2)
        self.assertEqual(self.request('learning/plans?project_id=other')[1]['plans'],[])

    def test_new_boundaries_require_auth_and_reject_unexpected_fields(self):
        for path in ('learning/actions','learning/plans','learning/context','demonstration/status','demonstration/inventory'):
            self.assertEqual(self.request(path,auth=False)[0],401)
        self.assertEqual(self.request('learning/context', {'changes':{'execute':True}})[0],400)
        self.assertEqual(self.request('learning/resume', {'operation_id':'missing','approved':True,'shell':'x'})[0],400)
        self.assertEqual(self.request('demonstration/start', {'window_id':True,'pid':1})[0],400)
        self.assertEqual(self.request('demonstration/status')[1]['status'],'idle')

    def test_demonstration_prompt_samples_without_losing_stored_evidence(self):
        events = [{'sequence':i, 'name':'Control ' + 'x'*180, 'event':'invoke'} for i in range(200)]
        record = {'status':'stopped','event_count':len(events),'reference':{'demonstration_id':'demo','trust':'untrusted_observation','verified':False,'events':events}}
        summary = planning_reference(record)
        self.assertLessEqual(len(json.dumps(summary)),6000)
        self.assertGreater(summary['omitted_events'],0)
        self.assertEqual(summary['events'][0]['sequence'],0)
        self.assertEqual(summary['events'][-1]['sequence'],199)
        self.assertEqual(len(record['reference']['events']),200)
        with self.assertRaises(ValueError): planning_reference(record | {'status':'recording'})


if __name__ == '__main__': unittest.main()
