"""Authenticated loopback contracts over isolated stores and a synthetic adapter."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import Mock, patch

from backend.actions.executor import ActionExecutor
from backend.action_learning import ActionLearning
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class MemoryHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.executor=ActionExecutor(root/'state.db',root/'artifacts')
        self.commands=CommandService(self.executor)
        self.adapter=Mock()
        self.adapter.route.side_effect=lambda envelope:{'ok':True,'request_id':envelope.get('request_id','synthetic'),
            'message':{'content':'SYNTHETIC_RESPONSE'},'route':{'provider':'synthetic'}}
        self.learning=ActionLearning(self.commands,self.adapter);self.commands.learning=self.learning
        self.chats=ChatStore(self.executor.db_path);self.provider=Mock()
        handler=type('MemoryHandler',(AxxBridgeHandler,),{'executor':self.executor,'commands':self.commands,
            'learning':self.learning,'chats':self.chats,'adapter':self.adapter,'provider':self.provider})
        self.server=ThreadedHTTPServer(('127.0.0.1',0),handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.a=self.chats.mutate('create',{'title':'Synthetic A'})['id']
        self.b=self.chats.mutate('create',{'title':'Synthetic B'})['id']

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)
        self.chats.close();self.learning.close();self.commands.close();self.executor.close();self.temp.cleanup()

    def request(self,route,body=None,auth=True):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/axx-api/'+route,
            data=json.dumps(body,allow_nan=False).encode() if body is not None else None,
            headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+self.server.host_token} if auth else {})})
        try:
            with urllib.request.urlopen(req,timeout=10) as response:return response.status,response.read(),response.headers
        except urllib.error.HTTPError as error:
            with error:return error.code,error.read(),error.headers

    def json(self,route,body=None,**kwargs):
        code,raw,_=self.request(route,body,**kwargs);return code,json.loads(raw)

    def scope(self,task):
        chat=self.chats.get(task)
        return {'memory_scope':copy.deepcopy(chat['memory_scope']),'memory_context_id':chat['connect_id']}

    def forget(self,task,operation):
        code,preview=self.json('learning/memory-preview',{'text':'olvida lo que aprendiste de esta sesión',
            'task_id':task,'project_id':'','operation_id':operation,**self.scope(task)})
        self.assertEqual(code,200,preview);self.assertEqual(preview['status'],'ready')
        body={'change':preview['change'],'review_hash':preview['review_hash'],'confirmed':True}
        code,result=self.json('learning/memory-apply',body)
        self.assertEqual(code,200,result);self.assertEqual(result['state'],'applied')
        return body,result

    def chat_body(self,task,**extra):
        identity=self.scope(task)
        return {'model':'synthetic','messages':[{'role':'user','content':'SYNTHETIC_PRIVATE_A'}],
            'conversation_id':identity['memory_context_id'],**identity,**extra}

    def test_memory_routes_auth_strict_hash_idempotence_and_history_opt_in(self):
        identity=self.scope(self.a)
        self.chats.mutate('save',{'id':self.a,**identity,'messages':[{'id':'old-a','role':'user',
            'text':'SYNTHETIC_HISTORY_ONLY','status':'complete','at':self.chats.clock()}]})
        preview={'text':'olvida lo que aprendiste de esta sesión','task_id':self.a,'operation_id':'http-forget',**identity}
        self.assertEqual(self.json('learning/memory-preview',preview,auth=False)[0],401)
        self.assertEqual(self.json('learning/memory-preview',preview|{'grant':True})[0],400)
        self.assertEqual(self.json('learning/memory-apply',{'change':{},'review_hash':'x','confirmed':1})[0],400)
        body,result=self.forget(self.a,'http-forget')
        self.assertEqual(self.json('learning/memory-apply',body)[1],result)
        self.assertEqual(self.json('learning/memory-apply',body|{'review_hash':'0'*64})[0],400)
        normal=self.json('chat/conversations?id='+self.a)[1]
        self.assertEqual(normal['messages'],[]);self.assertNotIn('history_messages',normal)
        manual=self.json('chat/conversations?id='+self.a+'&include_history=true')[1]
        self.assertEqual(manual['history_messages'][0]['text'],'SYNTHETIC_HISTORY_ONLY')
        for query in ('include_history=true','id='+self.a+'&include_history=1','id='+self.a+'&include_history=true&include_history=false'):
            self.assertEqual(self.json('chat/conversations?'+query)[0],400)
        self.assertEqual(self.executor.list_operations(),[])

    def test_chat_guards_metadata_is_not_an_upstream_envelope(self):
        body=self.chat_body(self.a)
        code,result=self.json('chat',body)
        self.assertEqual(code,200,result)
        envelope=self.adapter.route.call_args.args[0]
        self.assertNotIn('memory_scope',envelope);self.assertNotIn('memory_context_id',envelope)
        self.assertEqual(envelope['conversation_id'],body['conversation_id'])
        for invalid in (body|{'memory_scope':{'task_id':self.b,'generation':0}},
                        body|{'memory_scope':{'task_id':self.a,'generation':True}},
                        body|{'memory_scope':body['memory_scope']|{'extra':1}},
                        body|{'conversation_id':self.a},
                        {key:value for key,value in body.items() if key!='conversation_id'}):
            before=self.adapter.route.call_count
            self.assertEqual(self.json('chat',invalid)[0],400)
            self.assertEqual(self.adapter.route.call_count,before)
        self.forget(self.a,'guard-forget')
        before=self.adapter.route.call_count
        self.assertEqual(self.json('chat',body)[0],400)
        self.assertEqual(self.json('chat',{'model':'synthetic','messages':body['messages']})[0],400)
        self.assertEqual(self.adapter.route.call_count,before)
        self.assertEqual(self.json('chat',self.chat_body(self.a))[0],200)

    def test_chat_late_json_and_sse_are_rejected_after_forget(self):
        for stream in (False,True):
            with self.subTest(stream=stream):
                entered=threading.Event();release=threading.Event();holder={}
                def route(envelope):
                    holder['envelope']=copy.deepcopy(envelope);entered.set()
                    if not release.wait(5):raise RuntimeError('fixture release missing')
                    return {'ok':True,'request_id':'late','message':{'content':'SYNTHETIC_LATE_PRIVATE'}}
                self.adapter.route.side_effect=route
                body=self.chat_body(self.a,stream=stream)
                worker=threading.Thread(target=lambda:holder.update(response=self.request('chat',body)))
                worker.start();self.assertTrue(entered.wait(3))
                try:self.forget(self.a,'late-'+str(stream))
                finally:release.set();worker.join(5)
                self.assertFalse(worker.is_alive());code,raw,headers=holder['response']
                self.assertEqual(code,400,raw);self.assertNotIn(b'SYNTHETIC_LATE_PRIVATE',raw)
                self.assertNotIn('text/event-stream',headers.get('Content-Type',''))
                self.assertEqual(holder['envelope']['conversation_id'],body['conversation_id'])

    def test_linked_a_forget_invalidates_b_context_even_when_b_generation_stays(self):
        self.chats.mutate('save',{'id':self.a,**self.scope(self.a),'messages':[{'id':'a','role':'user','text':'SYNTHETIC_LINK_A','at':self.chats.clock(),'status':'complete'}]})
        self.chats.mutate('save',{'id':self.b,**self.scope(self.b),'messages':[{'id':'b','role':'user','text':'KEEP_OWN_B','at':self.chats.clock(),'status':'complete'}]})
        self.chats.mutate('link',{'id':self.b,'source_id':self.a,**self.scope(self.b)})
        body=self.chat_body(self.b);old=self.scope(self.b)
        def route(_envelope):
            self.forget(self.a,'linked-forget')
            return {'ok':True,'request_id':'linked','message':{'content':'SYNTHETIC_LINKED_LATE'}}
        self.adapter.route.side_effect=route
        code,raw,_=self.request('chat',body)
        self.assertEqual(code,400,raw);self.assertNotIn(b'SYNTHETIC_LINKED_LATE',raw)
        current=self.scope(self.b)
        self.assertEqual(current['memory_scope'],old['memory_scope'])
        self.assertNotEqual(current['memory_context_id'],old['memory_context_id'])
        self.assertEqual(self.chats.get(self.b)['messages'][0]['text'],'KEEP_OWN_B')
        before=self.adapter.route.call_count;self.assertEqual(self.json('chat',body)[0],400)
        self.assertEqual(self.adapter.route.call_count,before)

    def test_legacy_chat_retains_admitted_source_after_unlink_and_forget(self):
        self.chats.mutate('save',{'id':self.a,**self.scope(self.a),'messages':[{'id':'source-a','role':'user',
            'text':'SYNTHETIC_SOURCE_A','at':self.chats.clock(),'status':'complete'}]})
        self.chats.mutate('link',{'id':self.b,'source_id':self.a,**self.scope(self.b)})
        entered,release=threading.Event(),threading.Event();holder={}
        def route(_envelope):
            entered.set()
            if not release.wait(8):raise RuntimeError('controlled release missing')
            return {'ok':True,'request_id':'unlinked-late','message':{'content':'SYNTHETIC_UNLINKED_LATE_A'}}
        self.adapter.route.side_effect=route
        body={'model':'synthetic','conversation_id':self.b,'messages':[{'role':'user','content':'Use the linked reference'}]}
        worker=threading.Thread(target=lambda:holder.update(response=self.request('chat',body)));worker.start()
        try:
            self.assertTrue(entered.wait(4))
            self.chats.mutate('unlink',{'id':self.b,'source_id':self.a,**self.scope(self.b)})
            self.forget(self.a,'unlinked-source')
        finally:release.set();worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(holder['response'][0],400,holder['response'][1])
        self.assertNotIn(b'SYNTHETIC_UNLINKED_LATE_A',holder['response'][1])
    def test_learning_and_workshop_forward_fixed_metadata_outside_definitions(self):
        identity=self.scope(self.a)
        with patch.object(self.learning,'compose',return_value={'state':'awaiting_approval'}) as compose:
            code,result=self.json('learning/compose',{'text':'Synthetic','parts':[],**identity})
            self.assertEqual(code,200,result)
            self.assertEqual(compose.call_args.kwargs['conversation_id'],self.a)
            self.assertEqual(compose.call_args.kwargs['memory_scope'],identity['memory_scope'])
            self.assertEqual(compose.call_args.kwargs['memory_context_id'],identity['memory_context_id'])
        with patch.object(self.learning,'configure',return_value={'id':'synthetic'}) as configure:
            self.assertEqual(self.json('learning/configure',{'id':'synthetic','changes':{'favorite':True},**identity})[0],200)
            self.assertEqual(configure.call_args.args[1],{'favorite':True})
            self.assertEqual(configure.call_args.kwargs,identity)
            self.forget(self.a,'old-config')
            configure.reset_mock()
            self.assertEqual(self.json('learning/configure',{'id':'synthetic','changes':{'favorite':False},**identity})[0],400)
            configure.assert_not_called()
        workshop=Mock();workshop.create.return_value={'state':'draft'};self.server.RequestHandlerClass.workshop=workshop
        definition={'kind':'synthetic'};fresh=self.scope(self.a)
        self.assertEqual(self.json('capabilities/create',{'definition':definition,'project_id':'p',**fresh})[0],200)
        self.assertEqual(workshop.create.call_args.args[0],definition)
        self.assertEqual(workshop.create.call_args.kwargs,fresh)

    def legacy_memory(self):
        memory=Mock();memory.forget_task.return_value={'quarantined':0}
        memory.ai_memory.status.return_value={'available':True,'backend':'synthetic'}
        memory.ai_memory.query_recipes.return_value=[{'id':'synthetic'}]
        memory.ai_memory.read_recipe_page.return_value='SYNTHETIC_PAGE'
        memory.register_recipe.return_value.to_dict.return_value={'id':'synthetic','status':'verified'}
        self.server.RequestHandlerClass.memory=memory
        return memory

    def test_legacy_memory_routes_forward_only_captured_pair_and_drop_late_page(self):
        memory=self.legacy_memory();identity=self.scope(self.a)
        self.assertEqual(self.json('memory/query',{'query':'synthetic',**identity})[0],200)
        memory.ai_memory.query_recipes.assert_called_once_with('synthetic',**identity)
        self.assertEqual(self.json('memory/read',{'recipe_id':'synthetic',**identity})[0],200)
        memory.ai_memory.read_recipe_page.assert_called_once_with('synthetic',**identity)
        self.assertEqual(self.json('memory/query',{'query':'synthetic',**identity,'grant':True})[0],400)
        def delayed(_key,**kwargs):
            self.assertEqual(kwargs,identity);self.forget(self.a,'legacy-late')
            return 'SYNTHETIC_FORGOTTEN_PAGE'
        memory.ai_memory.read_recipe_page.side_effect=delayed
        code,raw,_=self.request('memory/read',{'recipe_id':'synthetic',**identity})
        self.assertEqual(code,400,raw);self.assertNotIn(b'SYNTHETIC_FORGOTTEN_PAGE',raw)

    def test_recipe_promotion_uses_receipt_origin_never_a_fresh_client_relabel(self):
        memory=self.legacy_memory()
        legacy={'state':'succeeded','postconditions_passed':True,'tool_name':'file_artifact_writer',
            'inputs':{'path':'synthetic-old.txt','content':'SYNTHETIC_OLD'}}
        body={'id':'legacy','intent_key':'legacy','operation_id':'unattributed-old',**self.scope(self.a)}
        with patch.object(self.executor,'get_operation',return_value=legacy):
            self.assertEqual(self.json('recipes/register',body)[0],200)
            self.assertNotIn('memory_scope',memory.register_recipe.call_args.kwargs)
            self.assertNotIn('memory_context_id',memory.register_recipe.call_args.kwargs)
            self.forget(self.a,'legacy-promotion')
            memory.register_recipe.reset_mock()
            self.assertEqual(self.json('recipes/register',body|self.scope(self.a))[0],400)
            memory.register_recipe.assert_not_called()
        identity=self.scope(self.b)
        plan=self.commands.prepare('axx.artifact.write',{'path':'b.txt','content':'SYNTHETIC_B'},
            conversation_id=self.b,**identity)
        done=self.commands.execute(plan['operation_id'],approved=True)
        self.assertEqual(done['state'],'succeeded',done)
        body={'id':'known-b','intent_key':'known-b','operation_id':done['action_operation_id'],**identity}
        self.assertEqual(self.json('recipes/register',body)[0],200)
        self.assertEqual(memory.register_recipe.call_args.kwargs['memory_scope'],identity['memory_scope'])
        self.assertEqual(memory.register_recipe.call_args.kwargs['memory_context_id'],identity['memory_context_id'])
        self.forget(self.b,'known-promotion');memory.register_recipe.reset_mock()
        self.assertEqual(self.json('recipes/register',body|self.scope(self.b))[0],400)
        memory.register_recipe.assert_not_called()
        self.assertEqual((self.executor.workspace_root/'b.txt').read_text(),'SYNTHETIC_B')

    def test_recipe_http_promotion_and_preparation_preserve_transitive_original_dependencies(self):
        with ProceduralMemory(self.executor.db_path) as memory:
            self.server.RequestHandlerClass.memory=memory
            a,b=self.scope(self.a),self.scope(self.b)
            dependency=a['memory_scope']|{'context_id':a['memory_context_id']}
            plan=self.commands.prepare('axx.artifact.write',{'path':'derived-b.txt','content':'SYNTHETIC_A_TO_B'},
                conversation_id=self.b,**b,_memory_dependencies=[dependency])
            done=self.commands.execute(plan['operation_id'],approved=True)
            self.assertEqual(done['state'],'succeeded',done)
            body={'id':'derived-b','intent_key':'derived-b','operation_id':done['action_operation_id'],**b}
            self.assertEqual(self.json('recipes/register',body|{'memory_dependencies':[]})[0],400)
            code,registered=self.json('recipes/register',body)
            self.assertEqual(code,200,registered)
            self.assertEqual(registered['recipe']['memory_dependencies'],[dependency])
            # Another current user context may request B; B's original context remains a dependency.
            prepare={'intent_key':'derived-b','inputs':{'path':'never-written.txt','content':'SYNTHETIC_SUFFIX'},**a}
            code,pending=self.json('recipes/prepare',prepare)
            self.assertEqual(code,200,pending)
            self.assertEqual(pending['memory_scope'],a['memory_scope'])
            self.assertEqual(pending['memory_context_id'],a['memory_context_id'])
            self.assertIn(dependency,pending['memory_dependencies'])
            self.assertIn(b['memory_scope'],pending['memory_dependencies'])
            self.assertFalse(self.commands.db.execute('SELECT 1 FROM chat_links').fetchone())
            self.forget(self.a,'http-forget-transitive-recipe')
            self.assertIsNone(memory.find_recipe('derived-b'))
            blocked=self.commands.execute(pending['operation_id'],approved=True)
            self.assertNotEqual(blocked['state'],'succeeded',blocked)
            self.assertFalse((self.executor.workspace_root/'never-written.txt').exists())
            self.assertEqual((self.executor.workspace_root/'derived-b.txt').read_text(),'SYNTHETIC_A_TO_B')

    def test_independent_recipe_b_survives_real_causal_context_rotation_but_old_request_does_not(self):
        with ProceduralMemory(self.executor.db_path) as memory:
            self.server.RequestHandlerClass.memory=memory
            original=self.scope(self.b)
            recipe=memory.register_recipe('independent-b','independent-b',
                [{'tool':'system_telemetry','args':{}}],{},**original)
            for task,text in ((self.a,'SYNTHETIC_A'),(self.b,'KEEP_OWN_B')):
                self.chats.mutate('save',{'id':task,**self.scope(task),'messages':[
                    {'id':task+'-user','role':'user','text':text,'at':self.chats.clock(),'status':'complete'}]})
            self.chats.mutate('link',{'id':self.b,'source_id':self.a,**self.scope(self.b)})
            old=self.scope(self.b)
            self.forget(self.a,'forget-linked-a-keep-recipe-b')
            fresh=self.scope(self.b)
            self.assertEqual(fresh['memory_scope'],old['memory_scope'])
            self.assertNotEqual(fresh['memory_context_id'],old['memory_context_id'])
            self.assertEqual(memory.find_recipe('independent-b').to_dict(),recipe.to_dict())
            with patch.object(self.executor,'execute_action',return_value={'state':'succeeded'}) as effect:
                self.assertEqual(self.json('recipes/execute',{'intent_key':'independent-b',**old})[0],400)
                effect.assert_not_called()
                code,result=self.json('recipes/execute',{'intent_key':'independent-b',**fresh})
                self.assertEqual(code,200,result);self.assertEqual(result['outcome'],'succeeded')
                effect.assert_called_once()
            code,pending=self.json('recipes/prepare',{'intent_key':'independent-b',**fresh})
            self.assertEqual(code,200,pending)
            self.assertIn(original['memory_scope'],pending['memory_dependencies'])
            self.assertEqual(pending['memory_context_id'],fresh['memory_context_id'])
            self.assertEqual(self.chats.get(self.b)['messages'][0]['text'],'KEEP_OWN_B')


if __name__=='__main__':unittest.main()
