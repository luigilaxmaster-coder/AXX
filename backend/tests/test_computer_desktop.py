"""Desktop scope and real image math with synthetic windows; never injects input."""
from contextlib import nullcontext
import unittest
import io
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
        with patch.object(cu.uia,'read_window_content',return_value=self.observed),patch.object(cu.vision,'capture',return_value=after),patch.object(cu,'execute_action',return_value={'success':True}) as action:
            result=cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'],self.executor.workspace_root,self.cancelled,self.executor)
        self.assertTrue(result.success,result.error);action.assert_called_once();self.assertFalse(result.output['goal_verified']);self.assertIsNone(self.grant['shot'])

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
