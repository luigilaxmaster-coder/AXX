"""Desktop scope and real image math with synthetic windows; never injects input."""
from contextlib import nullcontext
import unittest
import io
import copy
import threading
import time
from unittest.mock import patch

from PIL import Image, ImageDraw
from backend import computer_use as cu
from backend.tests import test_computer_use as fixture


def shot(image, observed, bounds):
    buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=70)
    return {'id':'snapshot','jpeg':buffer.getvalue(),'width':image.width,'height':image.height,'image_bounds':dict(bounds),
            'at':time.monotonic(),'observed':observed,'overview':False}


class DesktopComputerTests(unittest.TestCase):
    setUp=fixture.ComputerUseTests.setUp
    tearDown=fixture.ComputerUseTests.tearDown
    admit=fixture.ComputerUseTests.admit
    def test_desktop_consent_scope_and_cross_application_observation(self):
        for kwargs in ({},{'image_authorized':True},{'image_authorized':True,'allow_input':True,'window_id':10}):
            with self.assertRaises(ValueError):self.service.begin('chat-two',scope='desktop',**kwargs)
        self.service.begin('chat-two',scope='desktop',image_authorized=True,allow_input=True)
        self.assertFalse(self.service.status('chat-one')['active'])
        self.run['conversation_id']='chat-two';grant=self.service.grants['chat-two']
        self.assertEqual(self.service.status('chat-two')['scope'],'desktop');self.assertIsNone(grant['pid'])
        rows=[{'window_id':10,'pid':20,'title':'Browser','foreground':True},{'window_id':11,'pid':21,'title':'Editor'}]
        with patch.object(cu.uia,'list_windows',return_value=rows),patch.object(self.service,'_observe',return_value=(self.shot,{'observation_id':'snapshot'})) as observe:
            first=self.admit('observe');result=cu.TOOLS['computer_use_observe'].execute_with_runtime(first['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertTrue(result.success,result.error);self.assertEqual(grant['window_id'],10);self.assertTrue(observe.call_args.kwargs['overview'])
            self.commands.cancel_events['second-app']=self.cancelled
            second=self.admit('observe',operation_id='second-app',window_id=11,pid=21)
            result=cu.TOOLS['computer_use_observe'].execute_with_runtime(second['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertTrue(result.success,result.error);self.assertEqual(grant['window_id'],11);self.assertFalse(observe.call_args.kwargs['overview'])
            self.assertEqual(self.service.status('chat-two')['target_title'],'Editor')
            with patch.object(cu.uia,'process_name',return_value='powershell.exe'):
                with self.assertRaises(ValueError):self.service._target(grant,{'window_id':10,'pid':20})

    def test_window_scope_cannot_expand_or_use_malformed_target(self):
        for args in ({'window_id':11,'pid':21},{'window_id':True,'pid':20}):
            with self.assertRaises(ValueError):self.service._target(self.grant,args)
        self.assertEqual(self.grant['window_id'],10)

    def test_failed_observation_of_second_app_invalidates_first_app_image(self):
        self.service.begin('chat-two',scope='desktop',image_authorized=True,allow_input=True);self.run['conversation_id']='chat-two'
        grant=self.service.grants['chat-two'];rows=[{'window_id':10,'pid':20,'title':'A'},{'window_id':11,'pid':21,'title':'B'}]
        with patch.object(cu.uia,'list_windows',return_value=rows),patch.object(self.service,'_observe',side_effect=[(self.shot,{}),ValueError('Capture B failed')]):
            a=self.admit('observe',window_id=10,pid=20);result=cu.TOOLS['computer_use_observe'].execute_with_runtime(a['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertTrue(result.success,result.error);self.assertIsNotNone(grant['shot'])
            self.commands.cancel_events['observe-b']=self.cancelled;b=self.admit('observe',operation_id='observe-b',window_id=11,pid=21)
            result=cu.TOOLS['computer_use_observe'].execute_with_runtime(b['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertFalse(result.success);self.assertEqual(grant['window_id'],11);self.assertIsNone(grant['shot'])
            for action,extra in (('hotkey',{'keys':['Control','L']}),('type_text',{'text':'hey'})):
                self.service.admissions.clear();prepared=self.admit(action=action,control_id=None,**extra)
                with patch.object(cu,'execute_action') as send,patch.object(cu.uia,'inspect_focused_control') as focused:
                    result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
                self.assertFalse(result.success);send.assert_not_called();focused.assert_not_called()

    def test_same_image_id_with_foreign_window_pid_or_birth_never_dispatches(self):
        for key,value in (('window_id',11),('pid',21),('process_started','different')):
            self.service.admissions.clear();self.grant['shot']=copy.deepcopy(self.shot);self.grant['shot']['observed']['observation'][key]=value
            prepared=self.admit(action='type_text',control_id=None,text='hey')
            with patch.object(cu,'execute_action') as send,patch.object(cu.uia,'inspect_focused_control') as focused:
                result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertFalse(result.success);send.assert_not_called();focused.assert_not_called()

    def test_parallel_observe_or_act_cannot_retarget_and_stop_stays_available(self):
        self.grant['work'].acquire();self.grant['phase']='observing'
        try:
            prepared=self.admit('observe')
            with patch.object(self.service,'_target') as target,patch.object(cu,'execute_action') as send:
                result=cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertFalse(result.success);self.assertIn('COMPUTER_BUSY',result.error);target.assert_not_called();send.assert_not_called();self.assertEqual(self.grant['phase'],'observing')
            self.assertFalse(self.service.end('chat-one')['active'])
        finally:self.grant['work'].release()

    def test_typing_verifies_focused_field_without_walking_the_application(self):
        before=copy.deepcopy(self.observed);before.update(focused_control_id='editor',focused_only=True,truncated=True)
        before['controls']=[{'control_id':'editor','name':'Editor','value':'','enabled':True,'offscreen':False,'control_type':'ControlType.Document','read_only':False}]
        after=copy.deepcopy(before);after['controls'][0]['value']='hey'
        prepared=self.admit(action='type_text',control_id=None,text='hey',expected={'name':'Editor','value':'hey','focused':True})
        control=type('Control',(),{'is_set':lambda _:False,'wait':lambda _,seconds:False})();self.executor.input_control.automation=lambda event:nullcontext(control)
        with patch.object(cu.uia,'read_window_content',side_effect=AssertionError('Must not traverse whole app')) as tree,patch.object(cu.uia,'inspect_focused_control',side_effect=[before,after]) as focused,patch.object(cu,'execute_action',return_value={'success':True}) as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertTrue(result.success,result.error);tree.assert_not_called();self.assertEqual(focused.call_count,2);self.assertEqual(action.call_args.args[0]['text'],'hey')

    def test_readonly_or_unknown_focused_field_never_receives_text(self):
        for readonly,offscreen in ((True,False),(None,False),(False,True)):
            self.service.admissions.clear()
            focused=copy.deepcopy(self.observed);focused['focused_control_id']='editor'
            focused['controls']=[{'control_id':'editor','name':'Editor','enabled':True,'offscreen':offscreen,'control_type':'ControlType.Document','read_only':readonly}]
            prepared=self.admit(action='type_text',control_id=None,text='hey',expected={'name':'Done'})
            with patch.object(cu.uia,'inspect_focused_control',return_value=focused),patch.object(cu,'execute_action') as action:
                result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
            self.assertFalse(result.success);action.assert_not_called()

    def test_partial_focused_probe_cannot_claim_global_presence_or_absence(self):
        observed={'truncated':True,'focused_only':True,'focused_control_id':'editor','controls':[{'control_id':'editor','name':'Editor','value':'hey'}]}
        self.assertTrue(cu.predicate(observed,{'name':'Editor','value':'hey','focused':True}))
        observed['controls'][0]['value_truncated']=True
        for present in (True,False):self.assertFalse(cu.predicate(observed,{'name':'Editor','value':'hey','focused':True,'present':present}))
        observed['controls'][0]['value_truncated']=False;observed['controls'][0]['value']=None
        for present in (True,False):self.assertFalse(cu.predicate(observed,{'name':'Editor','value':'hey','focused':True,'present':present}))
        observed['controls'][0]['value']='hey'
        self.assertFalse(cu.predicate(observed,{'name':'Editor'}));self.assertFalse(cu.predicate(observed,{'name':'Elsewhere','present':False}))
        observed['focused_only']=False;self.assertFalse(cu.predicate(observed,{'name':'Elsewhere','present':False,'focused':True}))

    def test_focused_probe_validates_identity_and_has_short_deadline(self):
        with patch.object(cu.uia,'_uia',return_value={}) as call:
            cu.uia.inspect_focused_control(10,20)
            self.assertEqual(call.call_args.args[0]['operation'],'focused_edit');self.assertEqual(call.call_args.kwargs['timeout'],3)
            for a,b in ((True,20),(10,False),(0,20)):
                with self.assertRaises(ValueError):cu.uia.inspect_focused_control(a,b)

    def test_unrelated_animation_is_allowed_but_changed_target_and_resize_are_rejected(self):
        image=Image.new('RGB',(300,200),'white');old=shot(image,self.observed,{'x':10,'y':10,'width':300,'height':200})
        ImageDraw.Draw(image).rectangle((220,140,290,190),fill='blue');other=shot(image,self.observed,old['image_bounds'])
        self.assertTrue(cu.vision.same_target(old,other,30,30))
        ImageDraw.Draw(image).rectangle((20,20,40,40),fill='black');changed=shot(image,self.observed,old['image_bounds'])
        self.assertFalse(cu.vision.same_target(old,changed,30,30));changed['image_bounds']['x']=11
        self.assertFalse(cu.vision.same_target(old,changed,100,100))
        with self.assertRaises(ValueError):cu.vision.same_target(old,other,-1,10)

    def test_visual_postcondition_and_consumed_observation_do_not_certify_goal(self):
        bounds=self.observed['observation']['window_bounds'];old=shot(Image.new('RGB',(300,200),'white'),self.observed,dict(bounds));self.grant['shot']=old
        image=Image.new('RGB',(300,200),'white');ImageDraw.Draw(image).rectangle((10,10,90,90),fill='blue');after=shot(image,self.observed,dict(bounds))
        prepared=self.admit(expected={'region_changed':[10,10,100,100]})
        control=type('Control',(),{'is_set':lambda _:False,'wait':lambda _,seconds:False})()
        self.executor.input_control.automation=lambda event:nullcontext(control)
        with patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu.vision,'capture',side_effect=[old,after]),patch.object(cu,'execute_action',return_value={'success':True}) as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertTrue(result.success,result.error);action.assert_called_once();self.assertFalse(result.output['goal_verified']);self.assertIsNone(self.grant['shot'])

    def test_visual_change_before_dispatch_does_not_verify_the_gesture(self):
        bounds=self.observed['observation']['window_bounds'];old=shot(Image.new('RGB',(300,200),'white'),self.observed,bounds);self.grant['shot']=old
        baseline=shot(Image.new('RGB',(300,200),'blue'),self.observed,bounds);clock=[time.monotonic()]
        def wait(seconds):clock[0]+=seconds;return False
        control=type('Control',(),{'is_set':lambda _:False,'wait':lambda _,seconds:wait(seconds)})();self.executor.input_control.automation=lambda event:nullcontext(control)
        prepared=self.admit(expected={'region_changed':[10,10,100,100]})
        with patch.object(cu.time,'monotonic',side_effect=lambda:clock[0]),patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu.vision,'capture',return_value=baseline),patch.object(cu,'execute_action',return_value={'success':True}) as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertFalse(result.success);self.assertTrue(result.evidence['effect_uncertain']);action.assert_called_once();self.assertEqual(self.grant['blocked'],'gesture')

    def test_changed_visual_baseline_geometry_aborts_before_input(self):
        bounds=self.observed['observation']['window_bounds'];old=shot(Image.new('RGB',(300,200),'white'),self.observed,bounds);self.grant['shot']=old
        baseline=copy.deepcopy(old);baseline['image_bounds']['x']+=1
        prepared=self.admit(expected={'region_changed':[10,10,100,100]})
        with patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu.vision,'capture',return_value=baseline),patch.object(cu,'execute_action') as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertFalse(result.success);self.assertFalse(result.evidence['effect_uncertain']);action.assert_not_called()

    def test_input_guard_rejection_does_not_claim_an_unknown_effect(self):
        prepared=self.admit()
        with patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu,'execute_action',side_effect=ValueError('Target lost focus before dispatch')):
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertFalse(result.success);self.assertFalse(result.evidence['effect_uncertain']);self.assertIsNone(self.grant['blocked'])

    def test_full_desktop_coordinate_transform_keeps_negative_monitor_origin(self):
        bounds={'x':-300,'y':-100,'width':1200,'height':400};old=shot(Image.new('RGB',(1200,400),'white'),self.observed,bounds);old['overview']=True;self.grant['shot']=old
        control=type('Control',(),{'is_set':lambda _:False,'wait':lambda _,seconds:False})();self.executor.input_control.automation=lambda event:nullcontext(control)
        prepared=self.admit(action='move',control_id=None,x=350,y=150,expected=None)
        with patch.object(self.service,'_observe',return_value=(old,{})),patch.object(cu,'execute_action',return_value={'success':True,'evidence':{'verification':'cursor_readback'}}) as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertTrue(result.success,result.error);self.assertEqual((action.call_args.args[0]['x'],action.call_args.args[0]['y']),(50,50))

    def test_uia_timeout_still_returns_an_identified_real_image(self):
        geometry={**self.observed['observation'],'minimized':False};image=Image.new('RGB',(300,200),'white');value=shot(image,self.observed,geometry['window_bounds'])
        captured={'window_bounds':geometry['window_bounds'],'jpeg':cu.base64.b64encode(value['jpeg']).decode()}
        with patch.object(cu.uia,'observe_geometry',return_value=geometry),patch.object(cu.uia,'read_window_content',side_effect=ValueError('UI Automation excedió el límite')),patch.object(cu.uia,'capture_window',return_value=captured):
            frame,output=self.service._observe(self.grant,threading.Event())
        self.assertTrue(output['accessibility_warning']);self.assertEqual(output['controls'],[]);self.assertTrue(output['truncated']);self.assertTrue(frame['jpeg'])
        self.assertEqual(cu.uia.get_observation(frame['id'],10,20)['observation']['source'],'windows_visual')

    def test_overview_has_physical_bounds_and_masks_protected_surface(self):
        bounds={'x':-300,'y':-100,'width':1200,'height':400};identity={**self.observed['observation'],'monitors':[{'id':'left','x':-300,'y':-100,'width':600,'height':400},{'id':'right','x':300,'y':-100,'width':600,'height':400}]}
        protected={'window_id':99,'pid':99};box={'x':-200,'y':0,'width':100,'height':100}
        def geometry(hwnd):return {'window_bounds':box} if hwnd==99 else identity
        with patch.object(cu.uia,'observe_geometry',side_effect=geometry),patch.object(cu.vision,'physical_dpi_context',return_value=nullcontext()),patch.object(cu.vision.ImageGrab,'grab',return_value=Image.new('RGB',(1200,400),'white')) as grab:
            frame=cu.vision.capture(self.grant,identity,threading.Event(),overview=True,hidden=[protected])
        self.assertEqual(frame['image_bounds'],bounds);self.assertEqual(grab.call_args.kwargs['bbox'],(-300,-100,900,300))
        with Image.open(io.BytesIO(frame['jpeg'])) as im:self.assertLess(max(im.getpixel((150,150))),10)

    def test_physical_cancellation_revokes_the_session(self):
        prepared=self.admit('observe');error=ValueError('physical stop');error.input_cancelled=True
        with patch.object(self.service,'_observe',side_effect=error):
            result=cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertFalse(result.success);self.assertFalse(self.service.status('chat-one')['active'])
