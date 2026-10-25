"""Desktop dispatch regression: user commands reach tools, not inference."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import ANY, patch
from contextlib import nullcontext
from types import SimpleNamespace
import hashlib

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService, ApprovalRequired


class DesktopCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.executor = ActionExecutor(Path(self.tmp.name) / 'state.db', Path(self.tmp.name) / 'artifacts')
        self.addCleanup(self.executor.close)
        self.service = CommandService(self.executor)
        self.addCleanup(self.service.close)

    def test_spanish_requests_resolve_with_exact_parameters(self):
        cases = [
            ('abre YouTube', 'axx.desktop.open_url', {'url': 'https://www.youtube.com/'}),
            ('¿Puedes abrir YouTube por favor?', 'axx.desktop.open_url', {'url': 'https://www.youtube.com/'}),
            ('Axx, abre la calculadora', 'axx.desktop.open_app', {'app': 'calculator'}),
            ('abre https://example.com/AbC?q=Hola', 'axx.desktop.open_url', {'url': 'https://example.com/AbC?q=Hola'}),
            ('busca gatos y perros en YouTube', 'axx.desktop.search', {'query': 'gatos y perros', 'engine': 'youtube'}),
            ('busca en Google clima La Paz', 'axx.desktop.search', {'query': 'clima La Paz', 'engine': 'google'}),
            ('/powershell Get-Date', 'axx.shell.powershell', {'script': 'Get-Date'}),
            ('/cmd echo hola', 'axx.shell.cmd', {'script': 'echo hola'}),
        ]
        for text, command, inputs in cases:
            with self.subTest(text=text):
                result = self.service.resolve(text)
                self.assertEqual(result.get('command_id'), command)
                self.assertEqual(result['inputs'], inputs)
        for text in ('cómo abrir YouTube', 'no abras YouTube', 'resume: abre YouTube', 'abre calculadora && whoami'):
            self.assertNotEqual(self.service.resolve(text).get('match'), 'exact')

    def test_spotify_commands_never_become_youtube_searches(self):
        for text in ('pausa Spotify', 'siguiente en Spotify'):
            with self.subTest(text=text):
                result = self.service.resolve(text, source='voice')
                self.assertEqual(result['match'], 'unsupported')
                self.assertNotIn('youtube', str(result).lower())
        self.assertEqual(self.service.resolve('Reproduce la canción en Spotify.', source='voice'),
                         {'match':'exact','command_id':'axx.desktop.spotify.play','inputs':{}})
        search = self.service.resolve('Busca Bachata Rosa en Spotify', source='voice')
        self.assertEqual(search['command_id'], 'axx.desktop.open_url')
        self.assertEqual(search['inputs']['url'], 'https://open.spotify.com/search/Bachata%20Rosa')

    def test_spotify_play_invokes_observed_button_and_checks_pause_readback(self):
        def controls(name):
            return {'truncated': True, 'controls': [
                {'control_type':'ControlType.Button','enabled':True,'offscreen':False,'name':'Anterior','bounds':{'x':100,'y':100,'width':40,'height':40}},
                {'control_type':'ControlType.Button','enabled':True,'offscreen':False,'name':name,'control_id':'a'*64,'bounds':{'x':150,'y':100,'width':40,'height':40}},
                {'control_type':'ControlType.Button','enabled':True,'offscreen':False,'name':'Siguiente','bounds':{'x':200,'y':100,'width':40,'height':40}}]}
        control=SimpleNamespace(is_set=lambda:False)
        self.executor.input_control=SimpleNamespace(automation=lambda cancelled:nullcontext(control))
        with patch('backend.actions.windows_automation.list_windows',return_value=[{'window_id':18,'pid':45,'title':'Spotify Premium'}]), \
             patch('backend.actions.windows_automation.process_name',return_value='spotify.exe'), \
             patch('backend.actions.windows_automation.focus_window'), \
             patch('backend.actions.windows_automation.inspect_controls',side_effect=[controls('Reproducir'),controls('Pausa')]), \
             patch('backend.actions.windows_automation.invoke_control') as invoke, \
             patch('backend.actions.desktop.time.sleep'):
            pending=self.service.prepare('axx.desktop.spotify.play',{},source='voice')
            receipt=self.service.execute(pending['operation_id'])
        self.assertEqual(receipt['state'],'succeeded')
        self.assertTrue(receipt['postconditions_passed'])
        invoke.assert_called_once()

    def test_spotify_play_waits_for_a_new_window_to_expose_its_controls(self):
        empty={'truncated':False,'controls':[]}
        buttons={'truncated':False,'controls':[
            {'control_type':'ControlType.Button','enabled':True,'offscreen':False,'name':'Anterior','bounds':{'x':100,'y':100,'width':40,'height':40}},
            {'control_type':'ControlType.Button','enabled':True,'offscreen':False,'name':'Pausa','control_id':'a'*64,'bounds':{'x':150,'y':100,'width':40,'height':40}},
            {'control_type':'ControlType.Button','enabled':True,'offscreen':False,'name':'Siguiente','bounds':{'x':200,'y':100,'width':40,'height':40}}]}
        control=SimpleNamespace(is_set=lambda:False)
        self.executor.input_control=SimpleNamespace(automation=lambda cancelled:nullcontext(control))
        with patch('backend.actions.windows_automation.list_windows',return_value=[{'window_id':18,'pid':45,'title':'Spotify'}]), \
             patch('backend.actions.windows_automation.process_name',return_value='spotify.exe'), \
             patch('backend.actions.windows_automation.focus_window'), \
             patch('backend.actions.windows_automation.inspect_controls',side_effect=[empty,buttons]) as inspect, \
             patch('backend.actions.desktop.time.sleep'):
            pending=self.service.prepare('axx.desktop.spotify.play',{},source='voice')
            receipt=self.service.execute(pending['operation_id'])
        self.assertEqual(receipt['state'],'succeeded')
        self.assertEqual(inspect.call_count,2)

    def test_explicit_pointer_position_is_typed_and_read_back(self):
        result = self.service.resolve('mueve el mouse a x 500 y 400', source='voice')
        self.assertEqual(result, {'match': 'exact', 'command_id': 'axx.desktop.pointer.move', 'inputs': {'x': 500, 'y': 400}})
        with self.assertRaises(ValueError):
            self.service.prepare('axx.desktop.pointer.move', {'x': '500', 'y': 400})
        control = SimpleNamespace(move_absolute=lambda x, y: {'x': x, 'y': y, 'confirmed': True}, is_set=lambda: False)
        owner = SimpleNamespace(automation=lambda cancelled: nullcontext(control))
        self.executor.input_control = owner
        pending = self.service.prepare(result['command_id'], result['inputs'], source='voice')
        receipt = self.service.execute(pending['operation_id'])
        self.assertEqual(receipt['state'], 'succeeded')
        self.assertEqual(receipt['evidence']['verification'], 'cursor_readback')

    def test_first_video_pointer_uses_observed_youtube_control(self):
        window={'window_id':18,'pid':45,'title':'Resultados - YouTube - Google Chrome'}
        with patch('backend.actions.windows_automation.list_windows',return_value=[window]):
            resolved=self.service.resolve('pon el mouse sobre el primer vídeo',source='voice')
            mistaken=self.service.resolve('con el mouse sobre el primer vídeo',source='voice')
        self.assertEqual(resolved['command_id'],'axx.desktop.pointer.first_video')
        self.assertEqual(mistaken,resolved)
        moves=[]
        control=SimpleNamespace(is_set=lambda:False,focus=lambda hwnd,pid:moves.append(('focus',hwnd,pid)),
                                move_absolute=lambda x,y:(moves.append(('move',x,y)) or {'x':x,'y':y,'confirmed':True}))
        self.executor.input_control=SimpleNamespace(automation=lambda cancelled:nullcontext(control))
        observed={'truncated':False,'links':[{'control_id':'a'*64,'title':'Primer video','video_id':'12345678901'}],
                  'controls':[{'control_id':'a'*64,'offscreen':False,'bounds':{'x':100,'y':200,'width':80,'height':40}}]}
        with patch('backend.actions.windows_automation.read_window_content',return_value=observed), \
             patch('backend.actions.windows_automation.focus_window',side_effect=lambda hwnd,pid,control:moves.append(('focus',hwnd,pid))):
            pending=self.service.prepare(resolved['command_id'],resolved['inputs'],source='voice')
            receipt=self.service.execute(pending['operation_id'])
        self.assertEqual(receipt['state'],'succeeded')
        self.assertEqual(moves,[('focus',18,45),('move',140,220)])
        self.assertEqual(receipt['output']['video_id'],'12345678901')

    def test_url_dispatch_is_typed_and_idempotent(self):
        with patch('os.startfile', create=True) as launch:
            pending = self.service.prepare('axx.desktop.open_url', {'url': 'https://www.youtube.com/'})
            result = self.service.execute(pending['operation_id'])
            self.assertEqual(result['state'], 'succeeded')
            self.assertEqual(result['evidence']['verification'], 'os_handoff')
            self.assertTrue(self.service.execute(pending['operation_id'])['replayed'])
            launch.assert_called_once_with('https://www.youtube.com/')

    def test_reject_unsafe_urls_and_unknown_apps(self):
        for url in ('file:///C:/Windows', 'javascript:alert(1)', 'https://user:pass@example.com', 'https://example.com/\ncalc'):
            with self.assertRaises(ValueError):
                self.service.prepare('axx.desktop.open_url', {'url': url})
        with self.assertRaises(ValueError):
            self.service.prepare('axx.desktop.open_app', {'app': 'calc & whoami'})

    def test_window_capabilities_are_typed_and_writes_require_bound_approval(self):
        with self.assertRaises(ValueError):
            self.service.prepare('axx.desktop.window.set_value', {
                'window_id': 'not-a-hwnd', 'pid': 45, 'control_id': 'a' * 64, 'value': 'hello'})
        with self.assertRaises(ValueError):
            self.service.prepare('axx.desktop.window.set_value', {
                'window_id': '0x12', 'pid': True, 'control_id': 'a' * 64, 'value': 'hello'})
        pending = self.service.prepare('axx.desktop.window.set_value', {
            'window_id': '0x12', 'pid': 45, 'control_id': 'a' * 64, 'value': 'hello'})
        self.assertEqual(pending['state'], 'awaiting_approval')
        with self.assertRaises(ApprovalRequired):
            self.service.execute(pending['operation_id'])
        self.service.cancel(pending['operation_id'])

    def test_window_observation_and_focus_use_verified_readbacks(self):
        with patch('backend.actions.windows_automation.list_windows', return_value=[
                {'window_id': 18, 'pid': 45, 'title': 'Notepad', 'class_name': 'Notepad', 'foreground': True}]), \
             patch('backend.actions.windows_automation.inspect_controls', return_value={
                'success': True, 'window_id': 18, 'pid': 45, 'controls': [], 'count': 0,
                'truncated': False, 'verification': 'uia_control_tree_observed'}):
            listed = self.service.prepare('axx.desktop.list_windows', {})
            listed = self.service.execute(listed['operation_id'])
            self.assertEqual(listed['state'], 'succeeded')
            self.assertEqual(listed['output']['windows'][0]['pid'], 45)
            inspected = self.service.prepare('axx.desktop.window.inspect', {'window_id': '12', 'pid': 45})
            inspected = self.service.execute(inspected['operation_id'])
            self.assertEqual(inspected['state'], 'succeeded')
            self.assertTrue(inspected['postconditions_passed'])

    def test_close_request_resolves_one_observed_window_and_checks_disappearance(self):
        observed = [{'window_id': 18, 'pid': 45, 'title': 'Spotify', 'class_name': 'Chrome_WidgetWin_1', 'foreground': True}]
        with patch('backend.actions.windows_automation.list_windows', return_value=observed), \
             patch('backend.actions.windows_automation.process_name', return_value='spotify.exe'):
            resolved = self.service.resolve('Axx, cierra Spotify', source='voice')
        self.assertEqual(resolved['command_id'], 'axx.desktop.window.close')
        self.assertEqual(resolved['inputs'], {'window_id': '12', 'pid': 45})
        with patch('backend.actions.windows_automation.list_windows', return_value=observed), \
             patch('backend.actions.windows_automation.process_name', return_value='spotify.exe'):
            self.assertEqual(self.service.resolve('cierra la aplicación Spotify')['command_id'], 'axx.desktop.window.close')
        with patch('backend.actions.windows_automation.close_window', return_value={'closed': True, 'window_id': 18, 'pid': 45}):
            prepared = self.service.prepare(resolved['command_id'], resolved['inputs'], source='voice')
            result = self.service.execute(prepared['operation_id'])
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(result['evidence']['verification'], 'window_disappeared')

    def test_close_request_does_not_guess_between_windows(self):
        windows = [{'window_id': n, 'pid': n, 'title': 'Spotify', 'class_name': 'App', 'foreground': False} for n in (18, 19)]
        with patch('backend.actions.windows_automation.list_windows', return_value=windows), \
             patch('backend.actions.windows_automation.process_name', return_value='spotify.exe'):
            self.assertEqual(self.service.resolve('cierra Spotify')['match'], 'ambiguous')

    def test_spoken_open_me_uses_observed_app_inventory(self):
        with patch('backend.actions.windows_apps.find_app', return_value=[{'name': 'Obsidian', 'app_id': 'md.obsidian'}]):
            self.assertEqual(self.service.resolve('puedes abrirme mi obsedia', source='voice')['inputs'], {'app_id': 'md.obsidian'})

    def test_window_value_readback_is_hashed_and_only_succeeds_after_approval(self):
        self.executor.input_control = SimpleNamespace(automation=lambda event: nullcontext(event))
        digest = hashlib.sha256(b'hello').hexdigest()
        with patch('backend.actions.windows_automation.set_control_value', return_value={
                'success': True, 'window_id': 18, 'pid': 45, 'control_id': 'a' * 64,
                'value_sha256': digest, 'value_length': 5, 'verification': 'uia_value_readback'}) as set_value:
            pending = self.service.prepare('axx.desktop.window.set_value', {
                'window_id': '12', 'pid': 45, 'control_id': 'a' * 64, 'value': 'hello'})
            self.assertEqual(pending['state'], 'awaiting_approval')
            result = self.service.execute(pending['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(result['evidence']['value_sha256'], digest)
        set_value.assert_called_once_with(18, 45, 'a' * 64, 'hello', cancelled=ANY)

    def test_powershell_requires_approval_and_cannot_be_voice(self):
        with self.assertRaises(ValueError):
            self.service.prepare('axx.shell.powershell', {'script': 'Get-Date'}, 'voice')
        pending = self.service.prepare('axx.shell.powershell', {'script': "Write-Output 'hola'"})
        self.assertEqual(pending['state'], 'awaiting_approval')
        with self.assertRaises(ApprovalRequired):
            self.service.execute(pending['operation_id'])
        self.service.cancel(pending['operation_id'])
        self.assertEqual(self.service.execute(pending['operation_id'], True)['state'], 'cancelled')

    @unittest.skipUnless(os.name == 'nt', 'Windows CMD integration')
    def test_cmd_requires_approval_and_returns_real_exit_code(self):
        with self.assertRaises(ValueError):
            self.service.prepare('axx.shell.cmd', {'script': 'echo hola'}, 'voice')
        pending = self.service.prepare('axx.shell.cmd', {'script': 'echo AXX_CMD_OK'})
        with self.assertRaises(ApprovalRequired):
            self.service.execute(pending['operation_id'])
        result = self.service.execute(pending['operation_id'], True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertIn('AXX_CMD_OK', result['output']['stdout'])
        self.assertEqual(result['evidence']['exit_code'], 0)
        accented = self.service.prepare('axx.shell.cmd', {'script': 'echo hola áxx'})
        accented_result = self.service.execute(accented['operation_id'], True)
        self.assertEqual(accented_result['state'], 'succeeded', accented_result)
        self.assertIn('hola áxx', accented_result['output']['stdout'])

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell integration')
    def test_real_powershell_output_and_error(self):
        for script, state in [("Write-Output 'hola áxx'", 'succeeded'), ("throw 'fixture failure'", 'failed')]:
            pending = self.service.prepare('axx.shell.powershell', {'script': script})
            result = self.service.execute(pending['operation_id'], True)
            self.assertEqual(result['state'], state, result)
            if state == 'succeeded':
                self.assertIn('hola áxx', result['output']['stdout'])
            else:
                self.assertIn('fixture failure', result['output']['stderr'])

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell integration')
    def test_shell_timeout_output_bound_and_filtered_environment(self):
        cases = [('Start-Sleep -Seconds 20', .15, 'superó el límite'),
                 ("Write-Output ('x' * 150000)", 10, '64 KiB'),
                 ("Write-Output $env:AXX_TEST_SECRET", 10, None)]
        for script, timeout, error in cases:
            with self.subTest(script=script), patch('backend.actions.desktop.SHELL_TIMEOUT', timeout), patch.dict(os.environ, {'AXX_TEST_SECRET': 'PRIVATE-FIXTURE'}):
                pending = self.service.prepare('axx.shell.powershell', {'script': script})
                result = self.service.execute(pending['operation_id'], True)
                if error:
                    self.assertEqual(result['state'], 'failed')
                    self.assertIn(error, result['error']['message'])
                self.assertLessEqual(len(result['output']['stdout'].encode('utf-8')), 65536)
                self.assertNotIn('PRIVATE-FIXTURE', result['output']['stdout'])

    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell integration')
    def test_cancel_running_powershell(self):
        pending = self.service.prepare('axx.shell.powershell', {'script': "Set-Content -LiteralPath 'running.txt' -Value $PID; Start-Sleep -Seconds 30"})
        results = []
        thread = threading.Thread(target=lambda: results.append(self.service.execute(pending['operation_id'], True)))
        thread.start()
        try:
            deadline = time.monotonic() + 5
            marker = self.executor.workspace_root / 'running.txt'
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(marker.exists(), 'Real PowerShell did not start')
            self.service.cancel(pending['operation_id'])
            thread.join(6)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results[0]['state'], 'cancelled', results)
        finally:
            self.service.cancel(pending['operation_id'])
            thread.join(35)
