"""Plan adapters are read-only and never authorize inference or infer billing."""
import json
from pathlib import Path
import tempfile
import time
import unittest
import subprocess
import sys
from unittest.mock import patch
from contextlib import nullcontext

from backend.connect.subscriptions import statusline_snapshot, save_statusline, read_statusline, bridge_setup, claude_subscription
from backend.connect.tests.test_provider import ControlledProvider
from backend.connect.registry import tool_descriptors, validate
from backend.connect.mcp_server import LocalAxxClient


class SubscriptionTests(unittest.TestCase):
    def test_antigravity_official_statusline_projection_is_minimal(self):
        result = statusline_snapshot('antigravity', {'product': 'antigravity', 'plan_tier': 'Pro',
            'email': 'private', 'transcript_path': 'private', 'api_key': 'private',
            'quota': {'gemini-weekly': {'remaining_fraction': .72, 'reset_time': '2026-12-01T00:00:00Z'}}})
        self.assertEqual(result['plan'], 'Pro')
        self.assertEqual(result['windows'][0]['remaining_percent'], 72)
        self.assertEqual(result['verification'], 'client_report')
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('hours_remaining', result)

    def test_invalid_fraction_is_not_a_quota(self):
        for fraction in (True, float('nan'), float('inf'), -1, 1.01, '0.5', None):
            result = statusline_snapshot('antigravity', {'product': 'antigravity', 'quota': {'weekly': {'remaining_fraction': fraction}}})
            self.assertFalse(result['available'])
        with self.assertRaises(ValueError): statusline_snapshot('antigravity', {'product': 'other'})

    def test_atomic_snapshot_roundtrip_and_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {'product': 'antigravity', 'plan_tier': 'Ultra', 'quota': {'weekly': {'remaining_fraction': .4}}}
            save_statusline(directory, 'antigravity', payload)
            self.assertFalse(read_statusline(directory, 'antigravity')['stale'])
            with patch('backend.connect.subscriptions.time.time', return_value=time.time() + 360):
                self.assertTrue(read_statusline(directory, 'antigravity')['stale'])
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
            Path(directory, 'antigravity.json').write_text('{partial', encoding='utf-8')
            self.assertIsNone(read_statusline(directory, 'antigravity'))

    def test_claude_rate_limit_warning_is_not_balance(self):
        result = statusline_snapshot('claude', {'rate_limit_info': {'status': 'allowed'}})
        self.assertFalse(result['available'])
        result = statusline_snapshot('claude', {'rate_limits': {'five_hour': {'used_percentage': 25}}})
        self.assertEqual(result['windows'][0]['remaining_percent'], 75)

    def test_claude_missing_cli_is_unknown(self):
        with patch('backend.connect.subscriptions.claude_executable', return_value=None):
            result = claude_subscription()
        self.assertIsNone(result['plan'])
        self.assertFalse(result['available'])

    def test_setup_is_configuration_only_and_cwd_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            result = bridge_setup(directory, 'antigravity')
            self.assertIn('subscription-statusline.py', result['configuration']['statusLine']['command'])
            self.assertFalse(result['configured'])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_source_statusline_entrypoint_works_outside_repository(self):
        script = Path(__file__).resolve().parents[3] / 'scripts' / 'subscription-statusline.py'
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run([sys.executable, str(script), 'antigravity', '--state-dir', directory],
                input=json.dumps({'product': 'antigravity', 'plan_tier': 'Pro', 'email': 'private@example.invalid',
                                  'quota': {'weekly': {'remaining_fraction': .6}}}),
                text=True, capture_output=True, cwd=directory, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn('private', completed.stdout)
            self.assertEqual(read_statusline(directory, 'antigravity')['plan'], 'Pro')

    def test_codex_metadata_and_cache_never_start_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = ControlledProvider(None, Path(directory) / 'state.db', directory)
            try:
                first = provider.subscription_status('codex')
                second = provider.subscription_status('codex')
                self.assertEqual(first, second)
                self.assertEqual(first['connection'], 'connected')
                self.assertNotIn('email', json.dumps(first))
                self.assertFalse(any(method == 'turn/start' for method, *_ in provider.rpc_calls))
                provider.disconnect()
                self.assertEqual(provider.subscription_status('codex')['connection'], 'disconnected')
            finally: provider.close()

    def test_mcp_tools_are_bounded_and_read_only(self):
        descriptors = {tool['name']: tool for tool in tool_descriptors()}
        tool = descriptors['axx_subscription_status']
        validate(tool['inputSchema'], {'provider': 'claude'})
        with self.assertRaises(ValueError): validate(tool['inputSchema'], {'provider': 'other'})
        self.assertTrue(tool['annotations']['readOnlyHint'])

    def test_mcp_routes_subscription_tools_as_get_not_actions(self):
        class Client(LocalAxxClient):
            def _descriptor(self): return {'instance_id': 'fixture'}
            def _request(self, descriptor, method, route, body=None):
                self.last = (method, route)
                return {'instance_id': 'fixture'} if route.endswith('/status') else {'provider': 'claude'}
        client = Client()
        self.assertEqual(client.invoke('axx_subscription_status', {'provider': 'claude'}), {'provider': 'claude'})
        self.assertEqual(client.last, ('GET', '/axx-api/connect/subscriptions?provider=claude'))
        client.invoke('axx_subscription_bridge', {'provider': 'claude'})
        self.assertEqual(client.last, ('GET', '/axx-api/connect/subscriptions/setup?provider=claude'))

    def test_provider_dynamic_tools_have_real_read_handlers(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = ControlledProvider(None, Path(directory) / 'state.db', directory)
            try:
                with patch.object(provider, 'admission_guard', return_value=nullcontext):
                    result = provider._dispatch('axx_subscription_bridge', {'provider': 'antigravity'}, {}, 'read')
                self.assertFalse(result['configured'])
                self.assertIn('statusLine', result['configuration'])
            finally: provider.close()


if __name__ == '__main__': unittest.main()
