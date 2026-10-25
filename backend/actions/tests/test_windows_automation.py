import json
import subprocess
import threading
import unittest
from unittest.mock import patch

from backend.actions import windows_automation as automation


class WindowsAutomationTests(unittest.TestCase):
    def test_worker_proves_rejection_before_write_is_not_uncertain(self):
        class Worker:
            returncode=2
            def communicate(self,input=None,timeout=None):
                return b'{"success":false,"effect_started":false,"error":"focus lost"}',b'focus lost'
        with patch.object(automation.os,'name','nt'),patch.object(automation.subprocess,'Popen',return_value=Worker()):
            with self.assertRaises(ValueError) as caught:automation.set_control_value(12,45,'a'*64,'test')
        self.assertNotIsInstance(caught.exception,automation.UncertainEffect)

    def test_foreground_observation_requires_target_title(self):
        snapshots = [
            [{'window_id': 101, 'pid': 9, 'title': 'Other app', 'foreground': True}],
            [{'window_id': 202, 'pid': 10, 'title': 'Untitled - Notepad', 'foreground': True}],
        ]
        with patch.object(automation, 'list_windows', side_effect=snapshots), patch.object(automation.time, 'sleep'):
            result = automation.observe_foreground('Bloc de notas', timeout=1,
                aliases=('Notepad',), before=[{'window_id': 101}])
        self.assertTrue(result['window_observed'])
        self.assertTrue(result['foreground_verified'])
        self.assertTrue(result['ready_for_action'])
        self.assertEqual(result['window']['window_id'], 202)

    def test_new_unrelated_foreground_window_is_not_ready_for_action(self):
        with patch.object(automation, 'list_windows', return_value=[
            {'window_id': 202, 'pid': 10, 'title': 'Other app', 'foreground': True}]), patch.object(automation.time, 'sleep'):
            result = automation.observe_foreground('Notepad', timeout=0,
                before=[{'window_id': 101}])
        self.assertFalse(result['window_observed'])
        self.assertFalse(result['foreground_verified'])
        self.assertFalse(result['ready_for_action'])

    def test_unique_background_app_is_observed_and_focused(self):
        background={'window_id':202,'pid':10,'title':'cerebrum - Obsidian','foreground':False}
        foreground={**background,'foreground':True}
        with patch.object(automation,'list_windows',side_effect=[[background],[foreground]]), \
             patch.object(automation,'focus_window') as focus:
            result=automation.observe_foreground('Obsidian',timeout=0,before=[{'window_id':101}],control=object())
        focus.assert_called_once()
        self.assertTrue(result['window_observed'])
        self.assertTrue(result['foreground_verified'])
        self.assertTrue(result['ready_for_action'])

    def test_ambiguous_background_windows_are_not_focused(self):
        windows=[{'window_id':n,'pid':n,'title':'Obsidian','foreground':False} for n in (201,202)]
        with patch.object(automation,'list_windows',return_value=windows), patch.object(automation,'focus_window') as focus:
            result=automation.observe_foreground('Obsidian',timeout=0,control=object())
        focus.assert_not_called()
        self.assertFalse(result['ready_for_action'])

    def test_focus_denial_keeps_visible_window_receipt_without_readiness(self):
        window={'window_id':202,'pid':10,'title':'Obsidian','foreground':False}
        with patch.object(automation,'list_windows',return_value=[window]), \
             patch.object(automation,'focus_window',side_effect=ValueError('Windows negó el foco')):
            result=automation.observe_foreground('Obsidian',timeout=0,control=object())
        self.assertTrue(result['window_observed'])
        self.assertFalse(result['ready_for_action'])
        self.assertEqual(result['verification'],'visible_window_observation')

    def test_set_value_uses_fixed_mta_worker_and_json_not_script_input(self):
        control_id = 'a' * 64
        response = {'success': True, 'window_id': 12, 'pid': 45, 'control_id': control_id,
                    'value_sha256': 'a' * 64, 'value_length': 4, 'verification': 'uia_value_readback'}
        class Worker:
            returncode = 0
            def communicate(self, input=None, timeout=None):
                self.input = input
                return json.dumps(response).encode(), b''
            def kill(self): pass

        worker = Worker()
        with patch.object(automation.os, 'name', 'nt'), patch.object(automation.subprocess, 'Popen', return_value=worker) as popen:
            result = automation.set_control_value(12, 45, control_id, 'test')
        command = popen.call_args.args[0]
        self.assertLess(sum(map(len, command)), 2048)
        self.assertTrue(popen.call_args.kwargs['env']['AXX_UIA_WORKER'].endswith('uia_worker.ps1'))
        self.assertNotIn('AXX_HOST_TOKEN', popen.call_args.kwargs['env'])
        self.assertIn('-MTA', command)
        self.assertIn('-EncodedCommand', command)
        self.assertNotIn('test', command)
        self.assertEqual(json.loads(worker.input), {'operation':'set_value','window_id':12,'pid':45,
                         'control_id':control_id,'value':'test','expected_title':None})
        self.assertEqual(result['verification'], 'uia_value_readback')

    def test_set_value_rejects_invalid_text_before_worker(self):
        with self.assertRaises(ValueError):
            automation.set_control_value(12, 45, 'a' * 64, 'bad\x00value')
        with self.assertRaises(ValueError):
            automation.set_control_value(12, 45, '', 'valid')

    def test_uia_timeout_is_uncertain_and_reported_for_reconciliation(self):
        class Worker:
            returncode = None
            def communicate(self, input=None, timeout=None):
                if self.killed:
                    return b'', b''
                raise subprocess.TimeoutExpired('powershell', timeout)
            killed = False
            def kill(self): self.killed = True

        with patch.object(automation.os, 'name', 'nt'), \
             patch.object(automation.subprocess, 'Popen', return_value=Worker()), \
             patch.object(automation, 'UIA_TIMEOUT_SECONDS', 0.01):
            with self.assertRaisesRegex(ValueError, 'verifica la ventana antes de reintentar'):
                automation.inspect_controls(12, 45)

    def test_uia_cancellation_terminates_worker_promptly(self):
        cancelled = threading.Event()

        class Worker:
            returncode = None
            killed = False
            calls = 0
            def communicate(self, input=None, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    cancelled.set()
                    raise subprocess.TimeoutExpired('powershell', timeout)
                return b'', b''
            def kill(self): self.killed = True

        worker = Worker()
        with patch.object(automation.os, 'name', 'nt'), \
             patch.object(automation.subprocess, 'Popen', return_value=worker):
            with self.assertRaisesRegex(ValueError, 'cancelada'):
                automation.inspect_controls(12, 45, cancelled=cancelled)
        self.assertTrue(worker.killed)
        self.assertEqual(worker.calls, 2)


if __name__ == '__main__':
    unittest.main()
