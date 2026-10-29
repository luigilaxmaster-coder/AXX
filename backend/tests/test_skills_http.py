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

    def test_context_forget_is_authenticated_scoped_and_does_not_clear_commands(self):
        changes = {'current_file': 'project-file.txt', 'context_meta': {'current_file': {
            'kind': 'observed', 'source_id': 'trial-source', 'session_id': 'trial-session'}}}
        self.assertEqual(self.request('learning/context', {'project_id': 'project-a', 'changes': changes})[0], 200)
        self.assertEqual(self.request('learning/forget-context', {'project_id': 'project-a', 'source_id': 'trial-source', 'forget': True}, auth=False)[0], 401)
        self.assertEqual(self.learning.context('project-a')['current_file'], 'project-file.txt')
        code, forgotten = self.request('learning/forget-context', {'project_id': 'project-a', 'source_id': 'trial-source', 'forget': True})
        self.assertEqual(code, 200, forgotten)
        self.assertNotIn('current_file', forgotten)
        self.assertEqual(self.executor.list_operations(), [])
        self.assertEqual(self.request('learning/forget-context', {'project_id': 'project-a', 'source_id': 'trial-source', 'delete_grants': True})[0], 400)

    def test_dependency_api_requires_exact_review_and_waits_without_dispatch(self):
        def prepare(name):
            return self.request('learning/prepare', {'text': 'Crear ' + name, 'project_id': 'a', 'steps': [
                {'command_id': 'axx.artifact.write', 'inputs': {'path': name + '.txt', 'content': name}}]})[1]
        source, target = prepare('source'), prepare('target')
        body = {'operation_id': target['operation_id'], 'dependencies': [source['operation_id']], 'plan_hash': target['plan_hash']}
        self.assertEqual(self.request('learning/dependencies', body | {'plan_hash': 'stale'})[0], 400)
        code, linked = self.request('learning/dependencies', body)
        self.assertEqual(code, 200, linked)
        self.assertEqual(linked['mission']['mission_dependencies'][0]['operation_id'], source['operation_id'])
        code, waiting = self.request('learning/execute', {'operation_id': target['operation_id'], 'approved': True})
        self.assertEqual(waiting['state'], 'waiting_dependency', waiting)
        self.assertEqual(self.executor.list_operations(), [])

    def test_incident_routes_use_real_receipts_and_keep_hypothesis_unconfirmed(self):
        path = self.executor.workspace_root / 'incident.txt'
        path.write_text('trial')
        failed = self.commands.prepare('axx.file.sha256', {'path':str(path)}, conversation_id='trial-chat')
        path.unlink()
        failed = self.commands.execute(failed['operation_id'], True)
        self.assertEqual(failed['state'], 'failed')
        path.write_text('trial')
        success = self.commands.prepare('axx.file.sha256', {'path':str(path)}, conversation_id='trial-chat')
        success = self.commands.execute(success['operation_id'], True)
        self.assertEqual(success['state'], 'succeeded')
        body = {'operation_id':failed['operation_id'], 'hypothesis':'El archivo dejó de existir',
                'user_correction':'Restauré el archivo de ensayo', 'verification_operation_id':success['operation_id'], 'task_id':'trial-chat'}
        self.assertEqual(self.request('learning/lesson', body, auth=False)[0], 401)
        code, lesson = self.request('learning/lesson', body)
        self.assertEqual(code, 200, lesson)
        self.assertFalse(lesson['cause_confirmed'])
        self.assertEqual(lesson['verification']['status'], 'verified_test')
        listed = self.request('learning/lessons?task_id=trial-chat')[1]['lessons']
        self.assertEqual(len(listed), 1)
        self.assertEqual(self.request('learning/lessons?task_id=other-chat')[1]['lessons'], [])
        self.assertEqual(self.request('learning/forget-lesson', {'id':lesson['id']})[0], 200)
        self.assertEqual(self.request('learning/lessons?task_id=trial-chat')[1]['lessons'], [])
        self.assertEqual(self.commands.get(success['operation_id'])['state'], 'succeeded')

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
