import json
import os
from pathlib import Path
import time
import subprocess
import threading
import unittest
from unittest.mock import patch, MagicMock

from backend.actions import windows_automation as automation


class WindowsAutomationTests(unittest.TestCase):
    def test_clipboard_reader_uses_cancellable_worker_and_validates_bounds(self):
        snapshot = {'success':True,'sequence_number':7,'text':'ensayo','available':True}
        cancelled = threading.Event()
        with patch.object(automation, '_uia', return_value=snapshot) as worker:
            self.assertEqual(automation.read_clipboard_text(max_characters=10, cancelled=cancelled),
                             {'sequence_number':7,'text':'ensayo','available':True})
            worker.assert_called_once_with({'operation':'clipboard','max_characters':10},cancelled=cancelled,timeout=5)
        for maximum in (True,0,100001,'8192'):
            with self.subTest(maximum=maximum), patch.object(automation,'_uia') as worker, self.assertRaises(ValueError):
                automation.read_clipboard_text(max_characters=maximum)
            worker.assert_not_called()
        for bad in ({'sequence_number':True}, {'sequence_number':-1}, {'available':False}, {'text':42}, {'text':'x'*11}):
            with self.subTest(bad=bad), patch.object(automation,'_uia',return_value=snapshot|bad), self.assertRaises(ValueError):
                automation.read_clipboard_text(max_characters=10)

    @unittest.skipUnless(os.name == 'nt', 'Requires the packaged Windows worker path')
    def test_clipboard_worker_is_killed_on_cancel_without_reading_a_real_clipboard(self):
        cancelled = threading.Event()
        class Worker:
            returncode = None
            killed = False
            def communicate(self, input=None, timeout=None):
                if self.killed:return b'',b''
                cancelled.set()
                raise subprocess.TimeoutExpired('powershell',timeout)
            def kill(self):self.killed=True
        worker = Worker()
        with patch.object(automation.subprocess,'Popen',return_value=worker), \
                patch.object(automation,'observe_geometry',side_effect=AssertionError('Clipboard must not inspect a window')), \
                self.assertRaisesRegex(ValueError,'cancelada'):
            automation.read_clipboard_text(cancelled=cancelled)
        self.assertTrue(worker.killed)

    @unittest.skipUnless(os.name == 'nt', 'Compiles the actual Windows reader; never reads the clipboard')
    def test_actual_clipboard_decoder_handles_untrusted_bytes_without_native_read(self):
        source = Path(automation.__file__).with_name('uia_worker.ps1').read_text(encoding='utf8')
        definition = source.split("Add-Type -TypeDefinition @'\n",1)[1].split("\n'@",1)[0]
        cases = [([65,0,0,0],1,'A'), ([0,0],1,''), ([61,216,0,222,0,0],2,'😀'),
                 ([0,216,0,0],2,None), ([65,0],1,None), ([65,0,0],2,None), ([65,0,0,0],0,None),
                 ([65,0,66,0,0,0],1,None)]
        request = {'source':definition, 'cases':[{'bytes':raw,'maximum':maximum} for raw,maximum,_ in cases],
                   'path':str(Path(automation.__file__).with_name('uia_worker.ps1'))}
        script = '''$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $r=[Console]::In.ReadToEnd() | ConvertFrom-Json;
$tokens=$null; $errors=$null; [void][Management.Automation.Language.Parser]::ParseFile($r.path,[ref]$tokens,[ref]$errors);
if ($errors.Count) { throw 'Invalid packaged worker syntax' }; Add-Type -TypeDefinition $r.source;
$answers=@(foreach ($c in $r.cases) { try { @{ok=$true;text=[AxxClipboardRead]::Decode([byte[]]$c.bytes,[int]$c.maximum)} } catch { @{ok=$false;text=$null} } });
[Console]::Out.Write((ConvertTo-Json -InputObject $answers -Compress))'''
        process = subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',script],
                                 input=json.dumps(request).encode(),capture_output=True,timeout=20,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(process.returncode,0,process.stderr.decode(errors='replace'))
        answers = json.loads(process.stdout.decode('utf-8-sig'))
        self.assertEqual([(row['ok'],row['text']) for row in answers],[(expected is not None,expected) for _,_,expected in cases])

    def test_metadata_only_enumeration_never_reads_window_titles(self):
        user = MagicMock()
        user.GetForegroundWindow.return_value = 42
        user.IsWindowVisible.return_value = True
        user.GetWindowTextLengthW.side_effect = AssertionError('Title observation was not authorized')
        user.GetWindowTextW.side_effect = AssertionError('Title observation was not authorized')
        user.GetWindowThreadProcessId.side_effect = lambda hwnd, out: setattr(out._obj, 'value', 7) or 1
        user.GetClassNameW.side_effect = lambda hwnd, out, size: setattr(out, 'value', 'Fixture') or 7
        user.EnumWindows.side_effect = lambda callback, value: callback(42, value)
        with patch.object(automation, '_windows_api', return_value=(user, MagicMock())):
            rows = automation.list_windows(include_titles=False)
        self.assertEqual(rows, [{'window_id':42,'pid':7,'title':'','class_name':'Fixture','foreground':True}])
        user.GetWindowTextW.assert_not_called()
        user.GetWindowTextLengthW.assert_not_called()

    def test_read_value_binds_one_fresh_metadata_control_without_page_content(self):
        control_id = 'a' * 64
        observed = {'window_title': 'Owned browser fixture', 'truncated': False,
            'controls': [{'control_id': control_id, 'name': 'Address bar', 'enabled': True,
                          'offscreen': False, 'supports_value_pattern': True, 'value': ''}],
            'observation': {'process_started': '123456', 'window_bounds': {'x': 0, 'y': 0, 'width': 100, 'height': 100},
                            'completed_monotonic': time.monotonic()}}
        answer = {'success': True, 'verification': 'uia_control_value_observed', 'window_id': 12, 'pid': 45,
                  'control_id': control_id, 'process_started': '123456', 'value': 'https://example.com/'}
        with patch.object(automation, 'get_observation', return_value=observed) as lookup, \
                patch.object(automation, '_uia', return_value=answer) as worker:
            result = automation.read_control_value(12, 45, control_id, 'owned-observation')
        self.assertEqual(result['value'], answer['value'])
        lookup.assert_called_once_with('owned-observation', 12, 45)
        payload = worker.call_args.args[0]
        self.assertEqual(payload['operation'], 'read_value')
        self.assertEqual(payload['control_id'], control_id)
        self.assertEqual(payload['expected_process_started'], '123456')
        self.assertEqual(payload['expected_name'], 'Address bar')
        self.assertNotIn('value', payload)
        for change in [{'truncated': True}, {'controls': observed['controls'] * 2},
                       {'controls': [dict(observed['controls'][0], offscreen=True)]}]:
            with self.subTest(change=change), patch.object(automation, 'get_observation', return_value=observed | change), \
                    patch.object(automation, '_uia') as worker, self.assertRaises(ValueError):
                automation.read_control_value(12, 45, control_id, 'owned-observation')
            worker.assert_not_called()
        with patch.object(automation, 'get_observation', return_value=observed), \
                patch.object(automation, '_uia', return_value=dict(answer, process_started='replacement')), \
                self.assertRaises(ValueError):
            automation.read_control_value(12, 45, control_id, 'owned-observation')

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

        worker = Worker()
        with patch.object(automation.os, 'name', 'nt'), \
             patch.object(automation, 'observe_geometry', return_value={}), \
             patch.object(automation.subprocess, 'Popen', return_value=worker), \
             patch.object(automation.time, 'monotonic', side_effect=[0, 0, 0, 16]):
            with self.assertRaisesRegex(ValueError, 'verifica la ventana antes de reintentar'):
                automation.inspect_controls(12, 45)
        self.assertTrue(worker.killed)

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
             patch.object(automation, 'observe_geometry', return_value={}), \
             patch.object(automation.subprocess, 'Popen', return_value=worker):
            with self.assertRaisesRegex(ValueError, 'cancelada'):
                automation.inspect_controls(12, 45, cancelled=cancelled)
        self.assertTrue(worker.killed)
        self.assertEqual(worker.calls, 2)


if __name__ == '__main__':
    unittest.main()
