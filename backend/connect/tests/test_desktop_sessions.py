"""Offline contracts. No account, model request, desktop or paid-use claim."""
import json
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.connect.provider import ProviderError
from backend.connect.session_transport import codex_usage, claude_usage, quota_window, claude_sessions, run_claude_session
from backend.connect.tests.test_provider import ControlledProvider


class DesktopSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.provider = ControlledProvider(None, Path(self.tmp.name)/'state.db', self.tmp.name)
        self.provider.selected_model = 'keep-model'
        self.original_request = self.provider._request
        def request(method, params=None, timeout=20):
            if method == 'thread/list':
                return {'data': [{'id': 'existing', 'name': 'Existing session', 'cwd': self.tmp.name,
                                 'model': 'gpt-6.1-sol', 'status': {'type': 'idle'}}]}
            if method == 'thread/read':
                return {'thread': {'id': 'existing', 'cwd': self.tmp.name, 'model': 'gpt-6.1-sol', 'status': {'type': 'idle'}}}
            if method == 'thread/resume':
                self.provider.rpc_calls.append((method, params))
                return {'thread': {'id': 'existing'}, 'model': 'gpt-6.1-sol', 'modelProvider': 'openai'}
            return self.original_request(method, params, timeout)
        self.provider._request = request

    def tearDown(self):
        self.provider.close(); self.tmp.cleanup()

    def test_quotas_preserve_actual_windows_and_never_turn_percent_into_hours(self):
        snapshot = codex_usage({'ordinaryUsageAllowed': True, 'rateLimits': {
            'primary': {'usedPercent': 25, 'windowDurationMins': 300, 'resetsAt': 2000000000},
            'secondary': {'usedPercent': 90, 'windowDurationMins': 10080}}})
        self.assertEqual([w['remaining_percent'] for w in snapshot['windows']], [75, 10])
        self.assertEqual([w['window_minutes'] for w in snapshot['windows']], [300, 10080])
        self.assertNotIn('hours_remaining', snapshot)
        self.assertFalse(codex_usage({'rateLimits': {}})['available'])

    def test_invalid_quota_is_unknown_and_claude_warning_is_not_a_balance(self):
        for value in (True, float('nan'), float('inf'), -1, 101, '50', None):
            self.assertIsNone(quota_window({'usedPercent': value}))
        self.assertFalse(claude_usage({'rate_limit_info': {'status': 'allowed'}})['available'])
        self.assertEqual(claude_usage({'rate_limits': {'five_hour': {'used_percentage': 10}}})['windows'][0]['remaining_percent'], 90)

    def test_codex_discovery_only_projects_metadata(self):
        data = self.provider.desktop_sessions('codex')
        self.assertEqual(data['sessions'][0]['id'], 'existing')
        self.assertNotIn('turns', data['sessions'][0])
        self.assertNotIn('account', data)

    def test_resume_real_thread_without_replacing_active_axx_model_or_saved_thread_settings(self):
        run = self.provider.start_desktop_session({'provider': 'codex', 'session_id': 'existing',
                                                  'request_id': 'direct-1', 'message': 'A question'})
        for _ in range(200):
            state = self.provider.get(run['request_id'])
            if state.get('turn_id') or state['state'] in ('failed', 'unknown'): break
            time.sleep(.005)
        self.assertEqual(state.get('thread_id'), 'existing', state.get('error'))
        self.assertIn(('thread/resume', {'threadId': 'existing'}), self.provider.rpc_calls)
        self.assertEqual(self.provider.selected_model, 'keep-model')
        self.provider._notification({'method': 'turn/completed', 'params': {'threadId': 'existing', 'turn': {'id': 'turn-test', 'status': 'completed'}}})
        self.assertEqual(self.provider.get('direct-1')['state'], 'completed')
        self.assertIsNone(self.provider.verified_model, 'External chat must not change AXX model verification')

    def test_invalid_provider_path_and_occupied_target_are_rejected_before_send(self):
        for value in ('../session', '', 'a'*161):
            with self.assertRaises(ProviderError):
                self.provider.start_desktop_session({'provider': 'codex', 'session_id': value, 'request_id': 'bad', 'message': 'x'})
        self.provider._request = lambda method, params=None, timeout=20: {'thread': {'id': 'existing', 'cwd': self.tmp.name, 'model': 'gpt-6.1-sol', 'status': {'type': 'active'}}} if method == 'thread/read' else self.original_request(method, params, timeout)
        with self.assertRaisesRegex(ProviderError, 'trabajando'):
            self.provider.start_desktop_session({'provider': 'codex', 'session_id': 'existing', 'request_id': 'busy', 'message': 'x'})
        self.assertFalse(self.provider.live)

    def test_claude_discovery_reads_only_bounded_local_metadata(self):
        root = Path(self.tmp.name)/'projects'; project = root/'encoded'; project.mkdir(parents=True)
        (project/'session-id.jsonl').write_text(json.dumps({'type': 'user', 'cwd': self.tmp.name, 'message': {'content': 'PRIVATE BODY'}})+'\n'+json.dumps({'type': 'custom-title', 'customTitle': 'Local chat'}), encoding='utf-8')
        with patch('backend.connect.session_transport.claude_executable', return_value='claude.exe'):
            result = claude_sessions(root)
        self.assertEqual(result['sessions'][0]['title'], 'Local chat')
        self.assertNotIn('PRIVATE BODY', json.dumps(result))

    def test_antigravity_is_explicitly_unavailable_and_never_redirects(self):
        self.assertFalse(self.provider.desktop_sessions('antigravity')['available'])
        with self.assertRaises(ProviderError):
            self.provider.start_desktop_session({'provider': 'antigravity', 'session_id': 'external', 'request_id': 'none', 'message': 'x'})
        self.assertFalse(self.provider.live)

    def test_claude_adapter_shares_existing_run_events_and_does_not_touch_codex_settings(self):
        self.provider.local_enabled = False  # Codex opt-out is not a Claude logout.
        def respond(target, message, cancel, deadline, emit, usage_update):
            emit('Answer'); usage_update(claude_usage({'rate_limits': {'seven_day': {'used_percentage': 40}}})); return 'Answer'
        with patch('backend.connect.session_transport.claude_sessions', return_value={'sessions': [{'id': 'claude-id', 'project': self.tmp.name}]}), patch('backend.connect.session_transport.run_claude_session', side_effect=respond):
            self.provider.start_desktop_session({'provider': 'claude', 'session_id': 'claude-id', 'request_id': 'claude-1', 'message': 'Question'})
            for _ in range(100):
                result = self.provider.get('claude-1')
                if result['state'] in ('completed', 'failed'): break
                time.sleep(.005)
        self.assertEqual(result['state'], 'completed', result.get('error'))
        self.assertEqual(result['response'], 'Answer')
        self.assertEqual(self.provider.selected_model, 'keep-model')
        self.assertEqual(self.provider.session_usage('claude')['windows'][0]['remaining_percent'], 60)

    def test_claude_transport_passes_prompt_through_stdin_and_disables_tools_hooks_and_shell(self):
        import threading
        class Input(io.BytesIO):
            def close(self):
                if not self.closed: self.captured = self.getvalue()
                super().close()
        class Process:
            def __init__(self):
                self.stdin = Input(); self.stderr = io.BytesIO()
                self.stdout = io.BytesIO((json.dumps({'type': 'stream_event', 'event': {'delta': {'type': 'text_delta', 'text': 'answer'}}})+'\n'+json.dumps({'type': 'result', 'session_id': 'safe-id', 'result': 'answer', 'is_error': False})+'\n').encode())
            def poll(self): return 0
            def wait(self, timeout=None): return 0
        process = Process(); deltas = []
        with patch('backend.connect.session_transport.claude_executable', return_value='C:/cli/claude.exe'), patch('backend.connect.session_transport.subprocess.Popen', return_value=process) as spawn:
            response = run_claude_session({'session_id': 'safe-id', 'cwd': self.tmp.name}, 'literal $(prompt) `text`', threading.Event(), time.monotonic()+3, deltas.append, lambda _: None)
        self.assertEqual(response, 'answer')
        args, kwargs = spawn.call_args
        self.assertFalse(kwargs['shell'])
        self.assertIn('--tools', args[0]); self.assertEqual(args[0][args[0].index('--tools')+1], '')
        self.assertNotIn('literal $(prompt) `text`', args[0])
        self.assertEqual(process.stdin.captured.decode(), 'literal $(prompt) `text`')
        self.assertIn('{"disableAllHooks":true}', args[0])
        self.assertNotIn('--dangerously-skip-permissions', args[0])


if __name__ == '__main__': unittest.main()
