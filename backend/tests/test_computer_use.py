"""Scope, idempotency, image isolation and real journal policy for visual tools."""
import copy
import hashlib
from contextlib import nullcontext
import json
import io
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend import computer_use as cu
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.connect.service import ConnectService
from backend.connect.registry import tool_descriptors


class ComputerUseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.executor=ActionExecutor(root/'state.db',root/'artifacts');self.commands=CommandService(self.executor)
        self.service=cu.ComputerUse(self.commands);self.executor.computer_use=self.service
        self.cancelled=threading.Event();self.commands.cancel_events.update(gesture=self.cancelled,observe=self.cancelled)
        self.executor.input_control=SimpleNamespace(automation=lambda event:nullcontext(event))
        self.connect=ConnectService(self.commands,None)
        self.run={'request_id':'run-one','conversation_id':'chat-one','_cancel':threading.Event(),
                  '_deadline':time.monotonic()+70,'account_fingerprint':'account-one'}
        self.patches=[patch.object(cu.uia,'process_name',return_value='fixture.exe'),
                      patch.object(cu.uia,'process_started',return_value='birth'),
                      patch.object(cu.uia,'list_windows',return_value=[{'window_id':10,'pid':20,'title':'Fixture'}]),
                      patch.object(cu.uia,'focus_window')]
        self.patches.extend([patch.object(cu.vision,'_interactive_session'),patch.object(cu.uia,'_windows_api',return_value=(None,None))])
        for item in self.patches:item.start()
        self.service.begin('chat-one',10,20,image_authorized=True,allow_input=True)
        self.grant=self.service.grants['chat-one']
        row={'control_id':'button','name':'Apply','enabled':True,'offscreen':False,'bounds':{'x':20,'y':20,'width':100,'height':30}}
        self.observed={'controls':[row],'window_title':'Fixture','focused_control_id':'button',
            'observation':{'observation_id':'snapshot','window_bounds':{'x':10,'y':10,'width':300,'height':200},
                           'monitors':[],'process_started':'birth'}}
        self.shot={'id':'snapshot','at':time.monotonic(),'observed':self.observed,'hash':'frame','jpeg':b'private-image','width':300,'height':200}
        self.grant['shot']=self.shot
    def tearDown(self):
        self.service.close();self.connect.close();self.commands.close();self.executor.close()
        for item in self.patches:item.stop()
        self.temp.cleanup()
    def admit(self,kind='act',**changes):
        args={'operation_id':'gesture','action':'click','control_id':'button','observation_id':'snapshot','expected':{'name':'Done'}} if kind=='act' else {'operation_id':'observe'}
        args.update(changes);return self.service.admit('axx_computer_'+kind,args,self.run)
    def execute(self,**changes):
        prepared=self.admit(**changes)
        control=SimpleNamespace(is_set=lambda:False,wait=lambda seconds:False)
        self.executor.input_control=SimpleNamespace(automation=lambda event:nullcontext(control))
        with patch.object(cu.uia,'focus_window'),patch.object(cu.uia,'read_window_content',side_effect=[self.observed,self.observed,{'controls':[{'name':'Done'}]}]),patch.object(cu,'execute_action',return_value={'success':True}) as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        return result,action
    def test_status_stop_do_not_require_an_existing_grant(self):
        self.service.end('chat-one');self.assertFalse(self.service.admit('axx_computer_status',{},self.run)['active'])
        self.assertFalse(self.service.admit('axx_computer_stop',{},self.run)['active'])
    def test_explicit_consent_and_observed_instance_required(self):
        for args in ({},{'image_authorized':True}):
            with self.assertRaises(ValueError):self.service.begin('chat-two',10,20,**args)
        with patch.object(cu.uia,'process_name',return_value='powershell.exe'):
            with self.assertRaises(ValueError):self.service.begin('chat-two',10,20,image_authorized=True,allow_input=True)
        with patch.object(cu.uia,'process_started',return_value='different'):
            with self.assertRaises(ValueError):self.admit()
    def test_account_and_chat_bound(self):
        self.admit();self.run['account_fingerprint']='different'
        with self.assertRaises(ValueError):self.admit(operation_id='other')
        self.run['conversation_id']='chat-two'
        with self.assertRaises(ValueError):self.admit()
    def test_single_use_and_stable_idempotency(self):
        prepared=self.admit();self.assertEqual(prepared,self.admit())
        self.service.claim(prepared['inputs']['ticket'],'act',self.cancelled)
        with self.assertRaises(ValueError):self.service.claim(prepared['inputs']['ticket'],'act',self.cancelled)
        with self.assertRaises(ValueError):self.admit(action='double_click')
        with self.assertRaises(ValueError):self.service.admit('axx_computer_observe',{'operation_id':'gesture'},self.run)
    def test_revocation_cancels_claim_and_releases_image_and_tickets(self):
        prepared=self.admit();_,_,event=self.service.claim(prepared['inputs']['ticket'],'act',self.cancelled)
        self.service.end('chat-one');self.assertTrue(event.is_set());self.assertIsNone(self.grant['shot']);self.assertFalse(self.service.admissions)
    def test_foreign_worker_cannot_consume_an_admitted_ticket(self):
        prepared=self.admit()
        with self.assertRaisesRegex(ValueError,'esta operación'):
            self.service.claim(prepared['inputs']['ticket'],'act',threading.Event())
        self.assertFalse(self.service.admissions[prepared['inputs']['ticket']]['claimed'])
        self.service.claim(prepared['inputs']['ticket'],'act',self.cancelled)

    def test_parent_cancellation_and_deadline(self):
        prepared=self.admit();self.run['_cancel'].set()
        with self.assertRaises(ValueError):self.service.claim(prepared['inputs']['ticket'],'act',self.cancelled)
        self.run['_cancel'].clear();self.grant['deadline']=time.monotonic()-1
        with self.assertRaises(ValueError):self.admit(operation_id='later')
    def test_images_only_return_to_own_run_and_fresh_snapshot(self):
        prepared=self.admit('observe');result=prepared|{'state':'succeeded','output':{'observation_id':'snapshot'}}
        self.assertEqual(self.service.image_content(result,self.run)[0]['type'],'inputImage')
        self.assertEqual(self.service.image_content(result,self.run|{'request_id':'other'}),[])
        self.assertNotIn('private-image',json.dumps(prepared));self.shot['at']-=61
        self.assertEqual(self.service.image_content(result,self.run),[])
    def test_mouse_click_requires_postcondition_and_stale_snapshot_rejected(self):
        result,action=self.execute(expected=None);self.assertFalse(result.success);action.assert_not_called()
        self.service.admissions.clear();result,action=self.execute(observation_id='old');self.assertFalse(result.success);action.assert_not_called()
    def test_verified_control_gesture(self):
        result,action=self.execute();self.assertTrue(result.success,result.error)
        self.assertEqual(action.call_args.args[0]['x'],70);self.assertEqual(result.evidence['verification'],'computer_expected_control')
    def test_already_satisfied_does_not_dispatch(self):
        self.observed['controls'].append({'name':'Done'})
        result,action=self.execute();self.assertTrue(result.success);self.assertFalse(result.output['dispatched']);action.assert_not_called()
    def test_changed_control_rejects_before_dispatch(self):
        self.grant['shot']=copy.deepcopy(self.shot);self.observed['controls'][0]['name']='Destroy'
        result,action=self.execute();self.assertFalse(result.success);action.assert_not_called()
    def test_outside_image_and_changed_frame_rejected(self):
        for shot,x in ((dict(self.shot,hash='different'),1),(self.shot,301)):
            self.service.admissions.clear()
            with patch.object(self.service,'_observe',return_value=(shot,{})):
                result,action=self.execute(control_id=None,x=x,y=5)
            self.assertFalse(result.success);action.assert_not_called()
    def test_observation_failure_is_visible_and_success_clears_it(self):
        prepared=self.admit('observe')
        with patch.object(self.service,'_observe',side_effect=ValueError('UI Automation excedió el límite')):
            result=cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertFalse(result.success);self.assertFalse(result.evidence['effect_uncertain'])
        self.assertEqual(self.service.status('chat-one')['last_error'],'UI Automation excedió el límite')
        self.commands.cancel_events['next-observe']=self.cancelled
        prepared=self.admit('observe',operation_id='next-observe')
        with patch.object(self.service,'_observe',return_value=(self.shot,{'observation_id':'snapshot'})):
            result=cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertTrue(result.success);self.assertIsNone(self.service.status('chat-one')['last_error'])
    def test_uncertain_delivery_blocks_followup(self):
        prepared=self.admit();control=SimpleNamespace(is_set=lambda:False,wait=lambda seconds:False)
        self.executor.input_control=SimpleNamespace(automation=lambda event:nullcontext(control))
        with patch.object(cu.uia,'focus_window'),patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu,'execute_action',side_effect=cu.uia.UncertainEffect('partial')):
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertTrue(result.evidence['effect_uncertain']);self.assertEqual(self.grant['blocked'],'gesture')
        with self.assertRaises(ValueError):self.admit(operation_id='retry')
        self.admit('observe')
    def test_wrappers_only_exposed_to_context_aware_provider(self):
        self.assertNotIn('axx_computer_act',{r['name'] for r in tool_descriptors()})
        self.assertIn('axx_computer_act',{r['name'] for r in tool_descriptors(computer=True)})
    def test_real_connect_executor_journal_observation_without_image_storage(self):
        prepared=self.admit('observe')
        with patch.object(self.service,'_observe',return_value=(self.shot,{'observation_id':'snapshot'})):
            result=self.connect.dispatch('axx_execute_action',prepared,'run-one','call-one')
        self.assertEqual(result['state'],'succeeded',result);self.assertTrue(result['postconditions_passed'])
        self.assertEqual(len(self.service.image_content(result,self.run)),1)
        self.assertNotIn('private-image',json.dumps(self.commands.operations()))
        replay=self.connect.dispatch('axx_execute_action',prepared,'run-one','call-one')
        self.assertTrue(replay['replayed'])

    def test_capture_matches_physical_window_and_rejects_changed_geometry(self):
        from PIL import Image
        buffer=io.BytesIO();Image.new('RGB',(300,200),'white').save(buffer,format='JPEG')
        captured={'window_bounds':dict(self.observed['observation']['window_bounds']),'jpeg':cu.base64.b64encode(buffer.getvalue()).decode()}
        geometry={k:self.observed['observation'][k] for k in ('window_bounds','monitors')}
        with patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu.uia,'capture_window',return_value=captured),patch.object(cu.uia,'observe_geometry',return_value=geometry):
            shot,result=self.service._observe(self.grant,threading.Event())
            self.assertEqual((shot['width'],shot['height']),(300,200));self.assertNotIn('jpeg',result)
            self.assertEqual(result['image_sha256'],hashlib.sha256(buffer.getvalue()).hexdigest())
            captured['window_bounds']['width']=301
            with self.assertRaisesRegex(ValueError,'geometría'):self.service._observe(self.grant,threading.Event())

    def test_authenticated_http_binds_ui_chat_to_provider_and_stop(self):
        from backend.chat_store import ChatStore
        from backend.server import AxxBridgeHandler,ThreadedHTTPServer
        import urllib.error,urllib.request
        chats=ChatStore(self.executor.db_path);chat=chats.mutate('create',{'title':'Fixture'})['id']
        handler=type('ComputerHandler',(AxxBridgeHandler,),dict(chats=chats,commands=self.commands,computer_use=self.service))
        server=ThreadedHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(action,body,authorized=True):
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/axx-api/computer/'+action,
                data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+server.host_token,'Content-Type':'application/json'} if authorized else {})
            with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
        try:
            body={'conversation_id':chat,'window_id':10,'pid':20,'image_authorized':True,'allow_input':True}
            with self.assertRaises(urllib.error.HTTPError):request('begin',body,False)
            self.assertTrue(request('begin',body)['active'])
            self.assertIn(chats.get(chat)['connect_id'],self.service.grants)
            self.assertFalse(request('stop',{'conversation_id':chat})['active'])
            desktop={'conversation_id':chat,'scope':'desktop','image_authorized':True,'allow_input':True}
            result=request('begin',desktop);self.assertTrue(result['active']);self.assertEqual(result['scope'],'desktop');self.assertIsNone(result['window_id'])
            with self.assertRaises(urllib.error.HTTPError):request('begin',dict(desktop,window_id=10,pid=20))
            self.assertFalse(request('stop',{'conversation_id':chat})['active'])
        finally:server.shutdown();server.server_close();thread.join(2);chats.close()


if __name__=='__main__':unittest.main()
