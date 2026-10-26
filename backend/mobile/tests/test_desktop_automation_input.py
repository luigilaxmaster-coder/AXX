import copy
import ctypes as C
from ctypes import wintypes as W
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from backend.actions import desktop_input as desktop
from backend.actions.windows_automation import UncertainEffect
from backend.mobile.control import AutomationLease, RemoteControl
from backend.mobile.windows_input import WindowsInput


def observation():
    return {'window_title':'Fixture', 'observation': {
        'window_id':42, 'pid':7, 'process_started':'123',
        'completed_monotonic':time.monotonic(), 'focus_hwnd':99,
        'window_bounds':{'x':-200, 'y':0, 'width':200, 'height':150},
        'monitors':[{'id':'left','x':-300,'y':0,'width':300,'height':300}],
    }}


class Lease:
    def __init__(self): self.calls=[]; self.cancelled=False
    def is_set(self): return self.cancelled
    def wait(self, _): return self.cancelled
    def targeted(self, target, kind, values=()):
        self.calls.append((kind, values))
        return {'confirmed':True, 'x':values[0], 'y':values[1]} if kind=='move_absolute' else {'checked':True}


class DesktopInputTests(unittest.TestCase):
    def inputs(self, action='click', **kwargs):
        return dict(observation_id='observed',window_id=42,pid=7,action=action,**kwargs)

    def test_literal_unicode_and_application_hotkeys_are_bounded(self):
        desktop.validate_action(self.inputs('type_text',text='Texto literal: 1,20 m 👋'))
        desktop.validate_action(self.inputs('hotkey',keys=['Control','Shift','S']))
        for value in (self.inputs('type_text',text='x'*513),self.inputs('type_text',text='bad\0'),
                      self.inputs('hotkey',keys=['Meta','R']),self.inputs('hotkey',keys=['Alt','Tab']),
                      self.inputs('hotkey',keys=['Control','Alt','Delete']),self.inputs('hotkey',keys=['Control']),
                      self.inputs('click',x=True,y=0),self.inputs('click',x=1,y=0,shell='anything')):
            with self.assertRaises(ValueError): desktop.validate_action(value)

    @patch.object(desktop.windows,'get_observation')
    def test_click_delivery_is_not_verified_application_effect(self, get):
        get.return_value=observation(); control=Lease()
        result=desktop.execute_action(self.inputs(x=-100,y=50),control)
        self.assertEqual(result['output']['effect_status'],'unknown')
        self.assertTrue(result['evidence']['reconciliation_required'])
        self.assertEqual([c[0] for c in control.calls],['check','move_absolute','events','events'])
        self.assertFalse(control.calls[-1][1][0]['down'])

    @patch.object(desktop.windows,'get_observation')
    def test_only_move_reports_cursor_readback(self, get):
        get.return_value=observation()
        result=desktop.execute_action(self.inputs('move',x=-100,y=50),Lease())
        self.assertEqual(result['output']['effect_status'],'confirmed')
        self.assertEqual(result['evidence']['verification'],'cursor_readback')

    @patch.object(desktop.windows,'get_observation')
    def test_expired_token_never_reaches_broker(self, get):
        get.side_effect=ValueError('expired');control=Lease()
        with self.assertRaises(ValueError):desktop.execute_action(self.inputs(x=-100,y=50),control)
        self.assertFalse(control.calls)

    @patch.object(desktop.windows,'get_observation')
    def test_drag_outside_target_is_rejected_before_mouse_down(self, get):
        get.return_value=observation();control=Lease()
        with self.assertRaises(ValueError):desktop.execute_action(self.inputs('drag',x=-100,y=50,to_x=10,to_y=70),control)
        self.assertFalse(control.calls)

    @patch.object(desktop.windows,'get_observation')
    def test_interruption_mid_drag_never_completes_or_retries(self, get):
        get.return_value=observation();control=Lease()
        control.wait=lambda _:setattr(control,'cancelled',True) or True
        with self.assertRaises(UncertainEffect):desktop.execute_action(self.inputs('drag',x=-100,y=50,to_x=-50,to_y=70),control)
        self.assertEqual(sum(kind=='move_absolute' for kind,_ in control.calls),2)

    @patch.object(desktop.windows,'get_observation')
    def test_hotkey_releases_in_reverse_order(self, get):
        get.return_value=observation();control=Lease()
        desktop.execute_action(self.inputs('hotkey',keys=['Control','Shift','S']),control)
        self.assertEqual([(e['key'],e['down']) for e in control.calls[-1][1]],
                         [('Control',True),('Shift',True),('S',True),('S',False),('Shift',False),('Control',False)])

    @patch.object(desktop.windows,'get_observation')
    def test_unicode_chunks_yield_and_stop_after_physical_cancellation(self, get):
        get.return_value=observation();control=Lease();send=control.targeted
        def targeted(target,kind,values=()):
            result=send(target,kind,values)
            if kind=='events':control.cancelled=True
            return result
        control.targeted=targeted
        with self.assertRaises(UncertainEffect):desktop.execute_action(self.inputs('type_text',text='👋'*64),control)
        sent=[values for kind,values in control.calls if kind=='events']
        self.assertEqual(len(sent),1);self.assertEqual(sent[0][0]['text'],'👋'*32)


class TargetGuardTests(unittest.TestCase):
    def setUp(self):
        self.target=observation();self.user=MagicMock();self.kernel=MagicMock()
        self.user.GetWindowThreadProcessId.side_effect=lambda _,out:setattr(out._obj,'value',7) or 1
        self.user.IsWindow.return_value=True;self.user.IsWindowVisible.return_value=True
        self.user.IsIconic.return_value=False;self.user.GetForegroundWindow.return_value=42
        self.user.GetWindowTextW.side_effect=lambda _,out,n:setattr(out,'value','Fixture') or 7
        def rect(_, out):
            out._obj.left=-200;out._obj.top=0;out._obj.right=0;out._obj.bottom=150;return True
        self.user.GetWindowRect.side_effect=rect
        self.user.WindowFromPoint.return_value=42;self.user.GetAncestor.return_value=42
        self.user.GetGUIThreadInfo.side_effect=lambda _,out:setattr(out._obj,'focus',99) or True
        for mock in (patch.object(desktop.windows,'_windows_api',return_value=(self.user,self.kernel)),
                     patch.object(desktop,'_interactive_session'),patch.object(desktop,'_process_identity',return_value='123'),
                     patch('backend.magic_pen.monitors',return_value=self.target['observation']['monitors'])):
            mock.start();self.addCleanup(mock.stop)

    def test_negative_monitor_coordinates_are_validated(self):
        desktop.verify_target(self.target,point=(-100,50),keyboard=True)
        with self.assertRaisesRegex(ValueError,'fuera'):desktop.verify_target(self.target,point=(10,50))

    def test_foreground_change_and_occlusion_prevent_dispatch(self):
        self.user.GetForegroundWindow.return_value=43
        with self.assertRaisesRegex(ValueError,'foco'):desktop.verify_target(self.target)
        self.user.GetForegroundWindow.return_value=42;self.user.GetAncestor.return_value=43
        with self.assertRaisesRegex(ValueError,'cubierto'):desktop.verify_target(self.target,point=(-100,50))

    def test_focus_document_process_and_geometry_changes_are_rejected(self):
        for field,value,regex in [('focus_hwnd',98,'control'),('process_started','other','identidad'),
                                 ('completed_monotonic',time.monotonic()-16,'caduc')]:
            target=copy.deepcopy(self.target);target['observation'][field]=value
            with self.assertRaisesRegex(ValueError,regex):desktop.verify_target(target,keyboard=True)
        target=copy.deepcopy(self.target);target['window_title']='Another document'
        with self.assertRaisesRegex(ValueError,'documento'):desktop.verify_target(target)
        target=copy.deepcopy(self.target);target['observation']['window_bounds']['width']=201
        with self.assertRaisesRegex(ValueError,'geometr'):desktop.verify_target(target)

    def test_locked_session_and_integrity_failure_propagate(self):
        with patch.object(desktop,'_interactive_session',side_effect=ValueError('locked')):
            with self.assertRaisesRegex(ValueError,'locked'):desktop.verify_target(self.target)
        with patch.object(desktop,'_process_identity',side_effect=ValueError('UIPI')):
            with self.assertRaisesRegex(ValueError,'UIPI'):desktop.verify_target(self.target)


class BrokerTests(unittest.TestCase):
    def native(self):
        native=WindowsInput.__new__(WindowsInput)
        native._check=MagicMock();native._send=MagicMock();native.user=MagicMock()
        native.user.GetCursorPos.side_effect=lambda p:setattr(p._obj,'x',-100) or setattr(p._obj,'y',50) or True
        native.held_keys=set();native.held_buttons=set();native.pulse_at=0
        return native

    def test_native_guard_precedes_each_packet_and_blocks_on_focus_loss(self):
        native=self.native()
        events=[{'type':'key','key':'Control','down':True},{'type':'key','key':'A','down':True}]
        with patch.object(desktop,'verify_target',side_effect=[None,None,ValueError('focus changed')]):
            with self.assertRaisesRegex(ValueError,'focus changed'):
                native._execute('targeted',('lease',observation(),'events',events))
        self.assertEqual(native._send.call_count,1)
        self.assertEqual(native.held_keys,{'Control'})

    def test_failed_release_keeps_owned_key_for_final_cleanup(self):
        native=self.native();native.held_keys={'Control'};native._send.side_effect=ValueError('partial')
        with self.assertRaises(ValueError):native._execute('events',('lease',[{'type':'key','key':'Control','down':False}]))
        self.assertEqual(native.held_keys,{'Control'})

    def test_cancelled_lease_does_not_queue_more_input(self):
        native=MagicMock();native.abort=threading.Event();native.lease='lease'
        cancelled=threading.Event();lease=AutomationLease(native,'lease',cancelled);cancelled.set()
        with self.assertRaises(ValueError):lease.targeted(observation(),'check')
        native.targeted.assert_not_called()

    def test_automation_cleanup_releases_held_input_after_error(self):
        native=MagicMock();native.abort=threading.Event();native.active=False;native.lease=''
        native.status.return_value={'active':False,'reason':'idle'}
        def grant(lease,ttl,source):native.lease=lease;native.active=True
        native.grant.side_effect=grant
        control=RemoteControl(MagicMock(),native)
        with self.assertRaises(ValueError):
            with control.automation(threading.Event()):raise ValueError('target changed')
        native.cancel.assert_called_once_with('released')


if __name__=='__main__':unittest.main()
