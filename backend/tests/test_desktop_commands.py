"""Desktop dispatch regression: user commands reach tools, not inference."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

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
