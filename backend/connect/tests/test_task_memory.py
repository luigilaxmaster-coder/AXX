"""Memory fences on real isolated SQLite; Codex protocol and effects stay controlled."""
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import ADAPTERS, CommandService
from backend.connect.http_api import ConnectHTTP
from backend.connect.provider import ProviderError
from backend.connect.service import ConnectService
from backend.connect.registry import describe
from backend.connect.tests.test_provider import ControlledProvider
from backend.memory import task_memory
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class ConnectMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'state.db'
        self.chats = ChatStore(self.path)
        self.executor = ActionExecutor(self.path, self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.service = ConnectService(self.commands, None)
        self.provider = ControlledProvider(self.commands, self.path, self.root, dispatcher=self.service.dispatch)
        self.a = self.chats.mutate('create', {})['id']
        self.b = self.chats.mutate('create', {})['id']

    def tearDown(self):
        self.provider.close()
        self.service.close()
        self.commands.close()
        self.executor.close()
        self.chats.close()
        self.temp.cleanup()

    def body(self, task, request='run-a', **changes):
        chat = self.chats.get(task)
        return {'request_id':request, 'message':'Controlled goal', 'conversation_id':chat['connect_id'],
                'memory_scope':chat['memory_scope'], 'memory_context_id':chat['context_id'], **changes}

    def wait_started(self, request='run-a'):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                run = self.provider.get(request)
            except ProviderError as exc:
                if exc.code != 'NOT_FOUND':
                    raise
                time.sleep(.005)
                continue
            if run.get('turn_id') or run['state'] in ('failed','cancelled','unknown'):
                return run
            time.sleep(.005)
        self.fail('Controlled turn did not start')

    def begin(self, task):
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            return task_memory.begin_forget(db, task, 'forget-' + task, task_memory.state(db,task)['generation'])

    def finish(self, task, reference):
        result = self.chats.forget_task(task, reference)
        with self.chats.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(db, reference, result)
        return result

    def notification(self, method, **params):
        self.provider._notification({'method':method, 'params':{'threadId':'thread-test', 'turnId':'turn-test', **params}})

    def test_completed_result_history_and_replay_are_fenced_without_erasing_journal(self):
        body = self.body(self.a)
        self.provider.start(body)
        self.wait_started()
        self.notification('item/agentMessage/delta', delta='PRIVATE_COMPLETION')
        self.notification('turn/completed', turn={'id':'turn-test', 'status':'completed'})
        self.assertEqual(self.provider.get('run-a')['response'], 'PRIVATE_COMPLETION')
        self.begin(self.a)
        result = self.provider.get('run-a')
        self.assertTrue(result['memory_forgotten'])
        self.assertEqual(result['response'], '')
        self.assertEqual(result['events'], [])
        self.assertEqual(result['tool_results'], [])
        self.assertEqual(result['memory_scope'], body['memory_scope'])
        self.assertNotIn('PRIVATE_COMPLETION', json.dumps(self.provider.history()))
        with self.assertRaises(ProviderError) as raised:
            self.provider.start(body)
        self.assertEqual(raised.exception.code, 'MEMORY_SCOPE_CHANGED')
        with self.provider.lock:
            self.assertIn('PRIVATE_COMPLETION', self.provider.db.execute('SELECT body_json FROM connect_runs').fetchone()[0])
            self.assertTrue(self.provider.db.execute('SELECT 1 FROM connect_events').fetchone())
        self.assertTrue(self.provider.local_enabled)
        self.assertTrue(self.provider.authenticated)

    def test_dependency_contract_is_bounded_exact_and_checks_captured_context(self):
        chat = self.chats.get(self.a)
        dependency = dict(chat['memory_scope'],context_id=chat['context_id'])
        with self.chats.db() as db:
            self.assertEqual(task_memory.assert_dependencies(db,[dependency]),[dependency])
            for invalid in ([dependency]*25,[dependency | {'extra':True}],{},[{'task_id':self.a,'generation':True}]):
                with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                    task_memory.assert_dependencies(db,invalid)
        self.chats.mutate('update',{'id':self.a,'group_id':self.chats.mutate('group',{'title':'New'})['id']})
        with self.chats.db() as db,self.assertRaises(ValueError):
            task_memory.assert_dependencies(db,[dependency])
        with self.chats.db() as db:
            db.execute('UPDATE chat_conversations SET memory_context_required=1 WHERE id=?',(self.a,))
            self.assertEqual(task_memory.assert_dependencies(db,[chat['memory_scope']]),[chat['memory_scope']])
            with self.assertRaises(ValueError):
                task_memory.assert_context(db,chat['memory_scope'],None)

    def test_causal_chat_dependency_checks_opaque_rotation_without_recursion(self):
        a,b = self.chats.get(self.a),self.chats.get(self.b)
        dependency = dict(a['memory_scope'],context_id=a['context_id'])
        message = {'id':'derived-context','role':'assistant','text':'Derived','at':time.time()*1000,'status':'complete'}
        self.chats.mutate('save',{'id':self.b,'messages':[message]})
        with self.chats.db() as db:
            db.execute('UPDATE chat_messages SET memory_dependencies=? WHERE id=?',(json.dumps([dependency]),message['id']))
            self.assertIn(dependency,task_memory.chat_dependencies(db,self.b,0))
            db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?',('rotated-context',self.a))
        with self.chats.db() as db,self.assertRaises(ValueError):
            task_memory.assert_context(db,b['memory_scope'],b['context_id'])

    def test_pending_source_blocks_b_run_and_tools_before_context_rotation(self):
        self.chats.mutate('save', {'id':self.a, 'messages':[{'id':'source-a', 'role':'user', 'text':'PRIVATE_A', 'at':time.time()*1000, 'status':'complete'}]})
        self.chats.mutate('link', {'id':self.b, 'source_id':self.a})
        body = self.body(self.b)
        self.provider.start(body)
        self.wait_started()
        ref = self.begin(self.a)
        self.assertEqual(self.chats.get(self.b)['context_id'], body['memory_context_id'])
        self.assertEqual(self.chats.get(self.b)['memory_scope']['generation'], 0)
        with patch.object(self.commands, 'prepare', wraps=self.commands.prepare) as prepare:
            self.provider._server_request({'id':40, 'method':'item/tool/call', 'params':{
                'threadId':'thread-test', 'turnId':'turn-test', 'tool':'axx_execute_action',
                'arguments':{'operation_id':'late-op', 'command_id':'axx.system.telemetry', 'inputs':{}}}})
            prepare.assert_not_called()
        self.notification('item/agentMessage/delta', delta='LATE_PRIVATE_A')
        self.assertTrue(self.provider.get('run-a')['memory_forgotten'])
        self.assertNotIn('LATE_PRIVATE_A', self.provider.db.execute('SELECT body_json FROM connect_runs').fetchone()[0])
        self.finish(self.a, ref)
        current = self.chats.get(self.b)
        self.assertEqual(current['memory_scope'], body['memory_scope'])
        self.assertNotEqual(current['context_id'], body['memory_context_id'])
        with self.assertRaises(ProviderError):
            self.provider.start(body | {'request_id':'old-b-callback'})
        self.provider.start(self.body(self.b, 'fresh-b'))
        self.assertEqual(self.wait_started('fresh-b')['memory_context_id'], current['context_id'])

    def test_unlinked_inference_dependency_masks_completed_b_and_blocks_b_tools(self):
        source = self.chats.get(self.a)
        dependencies = [dict(source['memory_scope'],context_id=source['context_id'])]
        body = self.body(self.b,memory_dependencies=dependencies)
        self.provider.start(body)
        self.wait_started()
        self.notification('item/agentMessage/delta',delta='PRIVATE_INHERITED_A')
        self.notification('turn/completed',turn={'id':'turn-test','status':'completed'})
        self.provider.start(body | {'request_id':'active-b'})
        self.wait_started('active-b')
        self.begin(self.a)
        self.assertEqual(self.chats.get(self.b)['context_id'],body['memory_context_id'])
        self.assertEqual(self.chats.get(self.b)['memory_scope'],body['memory_scope'])
        self.assertNotIn('PRIVATE_INHERITED_A',json.dumps(self.provider.get('run-a')))
        with patch.object(self.commands,'prepare',wraps=self.commands.prepare) as prepare:
            self.provider._server_request({'id':42,'method':'item/tool/call','params':{
                'threadId':'thread-test','turnId':'turn-test','tool':'axx_execute_action','arguments':{
                    'operation_id':'unlinked-late','command_id':'axx.system.telemetry','inputs':{}}}})
            prepare.assert_not_called()
        self.assertTrue(self.provider.get('active-b')['memory_forgotten'])
        self.assertEqual(self.provider.get('active-b')['memory_dependencies'],dependencies)

    def test_pending_group_note_blocks_b_for_known_and_unattributed_sources(self):
        for legacy in (False,True):
            with self.subTest(legacy=legacy):
                group = self.chats.mutate('group', {'title':'Shared'})['id']
                a = self.chats.mutate('create', {'group_id':group})['id']
                b = self.chats.mutate('create', {'group_id':group})['id']
                self.chats.mutate('context', {'group_id':group,'text':'PRIVATE_SHARED',
                    **({} if legacy else {'source_task_id':a})})
                body = self.body(b, 'note-' + str(legacy))
                self.provider.start(body)
                self.wait_started(body['request_id'])
                self.begin(a)
                self.assertEqual(self.chats.get(b)['context_id'], body['memory_context_id'])
                with self.assertRaises(ValueError):
                    with self.chats.db() as db:
                        task_memory.assert_context(db,body['memory_scope'],body['memory_context_id'])
                self.assertTrue(self.provider.get(body['request_id'])['memory_forgotten'])
                self.provider.cancel(body['request_id'])

    def test_late_tool_receipt_is_retained_but_not_published_and_only_owned_effect_is_cancelled(self):
        entered, release = threading.Event(), threading.Event()
        cancelled = []
        def dispatcher(name, arguments, request_id, call_id, *, admission):
            with admission():
                pass
            if name == 'axx_cancel_task':
                cancelled.append(arguments['operation_id'])
                return {'state':'cancelled'}
            entered.set()
            release.wait(3)
            return {'state':'succeeded', 'operation_id':'owned-effect', 'origin':'axx-provider',
                    'parent_execution_id':request_id, 'output':'PRIVATE_LATE_RECEIPT'}
        self.provider.dispatcher = dispatcher
        self.provider.start(self.body(self.a))
        self.wait_started()
        worker = threading.Thread(target=self.provider._server_request, args=({'id':41,'method':'item/tool/call','params':{
            'threadId':'thread-test','turnId':'turn-test','tool':'axx_execute_action','arguments':{
                'operation_id':'owned-effect','command_id':'axx.system.telemetry','inputs':{}}}},))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.begin(self.a)
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(cancelled, ['owned-effect'])
        self.assertNotIn('PRIVATE_LATE_RECEIPT', json.dumps(self.provider.get('run-a')))
        self.assertIn('PRIVATE_LATE_RECEIPT', self.provider.db.execute('SELECT body_json FROM connect_runs').fetchone()[0])

    def test_planning_rewrite_keeps_original_scope_and_rejects_late_generation(self):
        chat = self.chats.get(self.b)
        source = self.chats.get(self.a)
        dependencies = [dict(source['memory_scope'],context_id=source['context_id'])]
        request = {'request_id':'plan-a','provider_name':'@codex','model':'gpt-6.1-sol','task':'plan',
                   'allow_paid':False,'deadline_ms':3000,'conversation_id':self.b,
                   'memory_scope':chat['memory_scope'],'memory_context_id':chat['context_id'],
                   'memory_dependencies':dependencies,
                   'messages':[{'role':'system','content':'JSON only'}, {'role':'user','content':'Controlled goal'}]}
        outcome = {}
        def generate():
            try:
                outcome['value'] = self.provider.generate_plan(request)
            except ProviderError as exc:
                outcome['error'] = exc.code
        worker = threading.Thread(target=generate)
        worker.start()
        run = self.wait_started('plan-a')
        self.assertTrue(run['conversation_id'].startswith('axx-planning-'))
        self.assertEqual(run['memory_scope'], chat['memory_scope'])
        self.assertEqual(run['memory_context_id'], chat['context_id'])
        self.assertEqual(run['memory_dependencies'],dependencies)
        self.assertNotIn('memory_dependencies',json.dumps(self.provider.rpc_calls))
        self.begin(self.a)
        self.notification('item/agentMessage/delta', delta='PRIVATE_PLAN')
        self.notification('turn/completed', turn={'id':'turn-test','status':'completed'})
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(outcome, {'error':'MEMORY_SCOPE_CHANGED'})

    def test_http_preserves_original_context_and_tool_prepare_uses_captured_scope(self):
        output = []
        handler = SimpleNamespace(connect=self.service, provider=self.provider,
                                  _send_json=lambda code,result:output.append((code,result)))
        body = self.body(self.a)
        body.pop('memory_context_id')
        ConnectHTTP(handler).post('/axx-api/connect/start', body)
        self.wait_started()
        with patch.object(self.commands,'prepare',wraps=self.commands.prepare) as prepare:
            result = self.service.dispatch('axx_execute_action', {'operation_id':'ask-op',
                'command_id':'axx.system.telemetry','inputs':{}}, 'run-a','call')
            policy = prepare.call_args.kwargs
        self.assertEqual(result['state'], 'awaiting_approval')
        self.assertEqual(policy['conversation_id'], self.a)
        self.assertEqual(policy['memory_scope'], body['memory_scope'])
        self.assertEqual(policy['memory_context_id'], body['conversation_id'])
        self.begin(self.a)
        with self.assertRaises(ValueError):
            self.service.dispatch('axx_execute_action', {'operation_id':'after-forget',
                'command_id':'axx.system.telemetry','inputs':{}}, 'run-a','call-late')
        projected = self.service.dispatch('axx_get_task', {'operation_id':'ask-op'}, 'other-run','get')
        self.assertTrue(projected['memory_forgotten'])
        self.assertNotIn('inputs', projected)
        self.assertEqual(len(self.commands.operations()), 1)

    def test_derived_effect_registers_recipe_with_original_dependency_provenance(self):
        register = Mock()
        self.service.memory = SimpleNamespace(find_recipe=Mock(return_value=None),register_recipe=register)
        self.service._trace({'state':'succeeded','postconditions_passed':True,'command_id':'axx.system.telemetry',
                             'operation_id':'derived','inputs':{},'memory_dependencies':[self.chats.get(self.a)['memory_scope']]})
        self.assertEqual(register.call_args.kwargs['_memory_dependencies'],[self.chats.get(self.a)['memory_scope']])

    def test_reused_recipe_inherits_durable_origin_and_fences_late_b_execute(self):
        a,b = self.chats.get(self.a),self.chats.get(self.b)
        key = 'axx.system.telemetry'
        version = describe(self.commands,self.commands.commands[key]).get('adapter_version')
        recipe = SimpleNamespace(id='source-a-recipe',version=1,env_fingerprint='fixture',
            steps=[{'tool':ADAPTERS[key]['tool'],'args':{}}],schema=self.commands.commands[key]['parameters'],
            preconditions=['axx-adapter-version:'+str(version)],memory_scope=a['memory_scope'],
            memory_context_id=a['context_id'],memory_dependencies=[])
        self.service.memory = SimpleNamespace(find_recipe=Mock(return_value=recipe),register_recipe=Mock())
        with self.chats.db() as db:
            db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?',('new-a-context',self.a))
        result = self.service.execute({'operation_id':'recipe-b','command_id':key,'inputs':{}},chat_policy={
            'conversation_id':self.b,'command_mode':'ask','memory_scope':b['memory_scope'],'memory_context_id':b['context_id']})
        self.assertTrue(result['procedure_reused'])
        self.assertEqual(result['memory_dependencies'],[a['memory_scope']])
        self.begin(self.a)
        rejected = self.commands.execute('recipe-b',approved=True)
        self.assertEqual(rejected['state'],'failed')
        self.assertEqual(rejected['error']['code'],'DISPATCH_REJECTED')
        self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0],0)

    def test_loopback_http_masks_forgotten_run_and_rejects_old_start(self):
        handler = type('MemoryConnectHandler',(AxxBridgeHandler,), {
            'connect':self.service,'provider':self.provider,'commands':self.commands,'chats':self.chats,
            'log_message':lambda *args:None})
        server = ThreadedHTTPServer(('127.0.0.1',0),handler)
        worker = threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        def request(method,route,body=None):
            headers = {'Authorization':'Bearer ' + server.host_token, 'Content-Type':'application/json'}
            data = json.dumps(body).encode() if body is not None else None
            query = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + '/axx-api/connect/' + route,
                                           headers=headers,data=data,method=method)
            with urllib.request.urlopen(query,timeout=3) as response:
                return json.load(response)
        try:
            body = self.body(self.a)
            body.pop('memory_context_id')
            self.assertEqual(request('POST','start',body)['memory_context_id'],body['conversation_id'])
            self.wait_started()
            self.notification('item/agentMessage/delta',delta='PRIVATE_HTTP')
            self.begin(self.a)
            projected = request('GET','run?request_id=run-a')
            self.assertTrue(projected['memory_forgotten'])
            self.assertNotIn('PRIVATE_HTTP',json.dumps(projected))
            with self.assertRaises(urllib.error.HTTPError) as raised:
                request('POST','start',body)
            self.assertEqual(raised.exception.code,400)
            self.assertEqual(json.load(raised.exception)['error']['code'],'MEMORY_SCOPE_CHANGED')
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_legacy_logical_chat_captures_opaque_context_before_unlink(self):
        a=self.chats.get(self.a)
        self.chats.mutate('save',{'id':self.a,'memory_scope':a['memory_scope'],'memory_context_id':a['context_id'],
            'messages':[{'id':'legacy-source','role':'user','status':'complete','text':'SOURCE_A','at':self.chats.clock()}]})
        self.chats.mutate('link',{'id':self.b,'source_id':self.a,'memory_scope':self.chats.get(self.b)['memory_scope']})
        b=self.chats.get(self.b)
        body={'request_id':'legacy-logical','conversation_id':self.b,'message':'Use the linked source'}
        run=self.provider.start(body)
        self.assertEqual(run['memory_context_id'],b['context_id'])
        self.assertEqual(run['conversation_id'],b['context_id'])
        self.assertEqual(self.provider.start(body)['memory_context_id'],b['context_id'])
        self.chats.mutate('unlink',{'id':self.b,'source_id':self.a,'memory_scope':b['memory_scope']})
        self.begin(self.a)
        self.assertTrue(self.provider.get('legacy-logical')['memory_forgotten'])
        with self.assertRaises(ProviderError):self.provider.start(body)

    def test_new_legacy_request_cannot_reclassify_a_forgotten_opaque_context(self):
        old=self.chats.get(self.a)['context_id']
        reference=self.begin(self.a);self.finish(self.a,reference)
        with self.assertRaises(ProviderError) as caught:
            self.provider.start({'request_id':'new-id-old-context','conversation_id':old,'message':'Use old context'})
        self.assertEqual(caught.exception.code,'MEMORY_SCOPE_CHANGED')
        self.assertIsNone(self.provider.db.execute('SELECT request_id FROM connect_runs WHERE request_id=?',('new-id-old-context',)).fetchone())

    def test_context_rotated_before_forgetting_cannot_resume_the_historical_thread(self):
        body=self.body(self.a)
        self.provider.start(body);self.wait_started()
        self.notification('turn/completed',turn={'id':'turn-test','status':'completed'})
        old=body['conversation_id']
        group=self.chats.mutate('group',{'title':'Moved group'})['id']
        self.chats.mutate('update',{'id':self.a,'group_id':group})
        reference=self.begin(self.a);self.finish(self.a,reference)
        with patch.object(self.provider,'_rpc',wraps=self.provider._rpc) as rpc,self.assertRaises(ProviderError) as caught:
            self.provider.start({'request_id':'new-id-historical-context','conversation_id':old,'message':'Resume old'})
        self.assertEqual(caught.exception.code,'MEMORY_SCOPE_CHANGED')
        rpc.assert_not_called()
        self.assertIsNone(self.provider.db.execute('SELECT request_id FROM connect_runs WHERE request_id=?',('new-id-historical-context',)).fetchone())

    def test_unused_rotated_context_cannot_become_a_legacy_namespace(self):
        old=self.chats.get(self.a)['context_id']
        group=self.chats.mutate('group',{'title':'Other group'})['id']
        self.chats.mutate('update',{'id':self.a,'group_id':group})
        with self.assertRaises(ProviderError) as caught:
            self.provider.start({'request_id':'unused-old-context','conversation_id':old,'message':'Use prior context'})
        self.assertEqual(caught.exception.code,'MEMORY_SCOPE_CHANGED')
        current=self.chats.get(self.a)
        run=self.provider.start({'request_id':'current-legacy-context','conversation_id':current['context_id'],'message':'Fresh context'})
        self.assertEqual(run['memory_scope'],current['memory_scope'])
        self.assertEqual(run['memory_context_id'],current['context_id'])

    def test_reassigned_opaque_context_cannot_resume_another_owners_thread(self):
        old=self.chats.get(self.a)['context_id']
        group=self.chats.mutate('group',{'title':'Moved A'})['id']
        self.chats.mutate('update',{'id':self.a,'group_id':group})
        other=self.chats.mutate('create',{'connect_id':old})['id']
        for body in ({'request_id':'reassigned-legacy','conversation_id':old,'message':'Use other owner'},
                     self.body(other,'reassigned-explicit')):
            with self.subTest(request=body['request_id']),self.assertRaises(ProviderError) as caught:
                self.provider.start(body)
            self.assertEqual(caught.exception.code,'MEMORY_SCOPE_CHANGED')


if __name__ == '__main__':
    unittest.main()
