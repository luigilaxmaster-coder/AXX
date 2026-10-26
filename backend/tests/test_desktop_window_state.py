from contextlib import nullcontext
import copy
import threading
import unittest
from unittest.mock import MagicMock,patch

from backend.actions import desktop_window_state as window
from backend.actions.windows_automation import UncertainEffect


class WindowStateTests(unittest.TestCase):
    def setUp(self):
        self.bounds={'x':-200,'y':0,'width':200,'height':150}
        self.monitors=[{'id':'left','x':-500,'y':0,'width':500,'height':500}]
        self.state={'window_id':42,'pid':7,'process_started':'123','bounds':self.bounds,
                    'minimized':False,'maximized':False,'monitors':self.monitors}
        self.target={'window_title':'Fixture','observation':{'window_id':42,'pid':7,'process_started':'123',
                     'window_bounds':self.bounds,'monitors':self.monitors,'minimized':False}}
        self.user=MagicMock();self.kernel=MagicMock();self.control=MagicMock()
        self.control.is_set.return_value=False;self.control.wait.return_value=False
        for mock in (patch.object(window.windows,'get_observation',return_value=self.target),
                     patch.object(window.windows,'_windows_api',return_value=(self.user,self.kernel)),
                     patch('backend.magic_pen.physical_dpi_context',return_value=nullcontext())):
            mock.start();self.addCleanup(mock.stop)

    def inputs(self,action,**kw):return dict(observation_id='seen',window_id=42,pid=7,action=action,**kw)

    def test_schema_rejects_extra_fields_boolean_geometry_and_close(self):
        for args in (self.inputs('close'),self.inputs('restore',bounds=self.bounds),
                     self.inputs('move_resize',bounds=self.bounds|{'width':True}),self.inputs('move_resize',bounds=self.bounds|{'x':1.5})):
            with self.assertRaises(ValueError):window.validate_action(args)

    def test_monitor_intersection_keeps_top_edge_reachable(self):
        self.assertTrue(window._reachable(self.bounds,self.monitors))
        self.assertFalse(window._reachable(self.bounds|{'x':1},self.monitors))
        self.assertFalse(window._reachable(self.bounds|{'y':-200},self.monitors))

    @patch.object(window,'_state')
    def test_move_resize_uses_physical_geometry_and_readback(self,state):
        desired=self.bounds|{'x':-300,'width':250}
        state.side_effect=[self.state,self.state,self.state|{'bounds':desired}]
        result=window.execute_action(self.inputs('move_resize',bounds=desired),self.control)
        self.assertTrue(result['success']);self.assertEqual(result['output']['bounds'],desired)
        self.assertEqual(result['evidence']['verification'],'window_state_readback')
        self.assertTrue(self.user.SetWindowPos.call_args.args[-1]&0x4000)
        self.assertTrue(self.user.SetWindowPos.call_args.args[-1]&0x10)

    @patch.object(window,'_state')
    def test_minimize_and_restore_use_state_readback(self,state):
        for action,first,last,show in [('minimize',self.state,self.state|{'minimized':True},7),
                                      ('restore',self.state|{'minimized':True},self.state,1),
                                      ('maximize',self.state,self.state|{'maximized':True},3)]:
            state.side_effect=[first,first,last]
            result=window.execute_action(self.inputs(action),self.control)
            self.assertEqual(result['output']['effect_status'],'confirmed')
            self.user.ShowWindowAsync.assert_called_with(42,show)

    @patch.object(window,'_state')
    def test_desired_state_is_not_dispatched_again(self,state):
        state.return_value=self.state|{'minimized':True}
        result=window.execute_action(self.inputs('minimize'),self.control)
        self.assertEqual(result['output']['dispatch_status'],'not_delivered')
        self.user.ShowWindowAsync.assert_not_called()

    @patch.object(window,'_state')
    def test_maximized_move_or_invisible_position_rejected_before_dispatch(self,state):
        state.return_value=self.state|{'maximized':True}
        with self.assertRaises(ValueError):window.execute_action(self.inputs('move_resize',bounds=self.bounds),self.control)
        state.return_value=self.state
        with self.assertRaises(ValueError):window.execute_action(self.inputs('move_resize',bounds=self.bounds|{'x':2000}),self.control)
        self.user.SetWindowPos.assert_not_called()

    @patch.object(window,'_state')
    def test_cancel_before_dispatch_has_no_effect(self,state):
        self.control.is_set.return_value=True
        with self.assertRaises(ValueError):window.execute_action(self.inputs('minimize'),self.control)
        state.assert_not_called();self.user.ShowWindowAsync.assert_not_called()

    @patch.object(window,'_state')
    def test_identity_failure_after_dispatch_remains_unknown(self,state):
        state.side_effect=[self.state,self.state,ValueError('new process')]
        with self.assertRaises(UncertainEffect):window.execute_action(self.inputs('minimize'),self.control)
        self.assertEqual(self.user.ShowWindowAsync.call_count,1)

    @patch.object(window,'_state')
    def test_cancel_after_dispatch_does_not_claim_rollback(self,state):
        state.return_value=self.state;self.control.is_set.side_effect=[False,False,False,True]
        with self.assertRaises(UncertainEffect):window.execute_action(self.inputs('minimize'),self.control)
        self.assertEqual(self.user.ShowWindowAsync.call_count,1)

    def test_tool_requires_runtime_owner(self):
        tool=window.WindowStateTool()
        self.assertFalse(tool.execute_with_runtime(self.inputs('minimize'),None,threading.Event(),object()).success)


class WindowIdentityTests(unittest.TestCase):
    setUp=WindowStateTests.setUp
    def test_identity_and_geometry_are_revalidated(self):
        self.user.GetWindowThreadProcessId.side_effect=lambda _,out:setattr(out._obj,'value',7) or 1
        self.user.IsWindow.return_value=True;self.user.IsWindowVisible.return_value=True
        self.user.GetAncestor.return_value=42;self.user.GetShellWindow.return_value=100;self.user.GetDesktopWindow.return_value=101
        self.user.GetWindowTextW.side_effect=lambda _,out,size:setattr(out,'value','Fixture') or 7
        self.user.IsZoomed.return_value=False
        with patch.object(window,'_interactive_session'),patch.object(window,'_process_identity',return_value='123'),patch.object(window.windows,'observe_geometry',return_value={'window_bounds':self.bounds,'monitors':self.monitors,'minimized':False}):
            self.assertEqual(window._state(self.user,self.kernel,self.target,before=True)['bounds'],self.bounds)
            changed=copy.deepcopy(self.target);changed['observation']['window_bounds']['width']=220
            with self.assertRaisesRegex(ValueError,'cambió'):window._state(self.user,self.kernel,changed,before=True)
            changed=copy.deepcopy(self.target);changed['observation']['process_started']='other'
            with self.assertRaisesRegex(ValueError,'identidad'):window._state(self.user,self.kernel,changed)
            self.user.GetAncestor.return_value=99
            with self.assertRaisesRegex(ValueError,'superior'):window._state(self.user,self.kernel,self.target)


class MinimizedObservationTests(unittest.TestCase):
    @patch.object(window,'_process_identity',return_value='123')
    @patch.object(window,'_state')
    @patch.object(window.windows,'observe_geometry')
    @patch.object(window.windows,'_windows_api')
    def test_minimized_geometry_has_bindable_token_without_ui_claim(self,api,geometry,state,birth):
        user=MagicMock();api.return_value=(user,MagicMock())
        user.GetWindowTextW.side_effect=lambda _,out,n:setattr(out,'value','Minimized fixture') or 1
        geometry.return_value={'window_bounds':{'x':-32000,'y':-32000,'width':160,'height':28},
                               'monitors':[{'id':'primary','x':0,'y':0,'width':1920,'height':1080}],
                               'minimized':True,'focus_hwnd':None,'foreground_window_id':99}
        state.return_value={'window_id':42,'pid':7,'minimized':True}
        result=window.observe_window_state(42,7)
        self.assertEqual(result['quality'],'geometry_only')
        self.assertEqual(result['controls'],[])
        self.assertEqual(result['ui_content_status'],'not_observed')
        resolved=window.windows.get_observation(result['observation_id'],42,7)
        self.assertTrue(resolved['observation']['minimized'])
        self.assertEqual(resolved['observation']['process_started'],'123')

    @patch.object(window.windows,'_remember_observation')
    @patch.object(window,'_state',side_effect=ValueError('window changed'))
    @patch.object(window,'_process_identity',return_value='123')
    @patch.object(window.windows,'observe_geometry',return_value={'window_bounds':{},'monitors':[]})
    @patch.object(window.windows,'_windows_api',return_value=(MagicMock(),MagicMock()))
    def test_changed_window_is_not_cached(self,*mocks):
        with self.assertRaises(ValueError):window.observe_window_state(42,7)
        mocks[-1].assert_not_called()

    def test_cancelled_observation_never_calls_windows(self):
        cancelled=threading.Event();cancelled.set()
        with patch.object(window.windows,'_windows_api') as api:
            with self.assertRaises(ValueError):window.observe_window_state(42,7,cancelled)
            api.assert_not_called()


if __name__=='__main__':unittest.main()
