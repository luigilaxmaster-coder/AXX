"""Diagnostic receipts retain failure stages and redact configured credentials."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('provider_diagnostics', Path(__file__).with_name('verify-recovery-providers.py'))
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class ProviderDiagnosticTests(unittest.TestCase):
    def test_rejected_http_is_reachable_but_transport_failure_is_separate(self):
        url = 'https://example.invalid/v1'
        with patch.object(diagnostics.urllib.request, 'urlopen', side_effect=diagnostics.urllib.error.HTTPError(url, 401, 'Unauthorized', {}, None)):
            self.assertEqual(diagnostics.endpoint_state(url), 'ACCESSIBLE')
        with patch.object(diagnostics.urllib.request, 'urlopen', side_effect=diagnostics.urllib.error.URLError('refused')):
            self.assertEqual(diagnostics.endpoint_state(url), 'UNREACHABLE_AT_PROBE')

    def test_redaction_and_failure_categories(self):
        diagnostics.SECRETS[:] = ['private-test-value']
        self.addCleanup(diagnostics.SECRETS.clear)
        self.assertNotIn('private-test-value', str(diagnostics.failure(ValueError('HTTP 402 private-test-value'))))
        self.assertEqual(diagnostics.failure(ValueError('HTTP 402'))['reason'], 'BILLING_REQUIRED')
        self.assertEqual(diagnostics.failure(ValueError('HTTP 503 high demand'))['reason'], 'PROVIDER_UNAVAILABLE')
        error = RuntimeError('local transport')
        error.code = 'RPC_TIMEOUT'
        self.assertEqual(diagnostics.failure(error)['reason'], 'LOCAL_RPC_TIMEOUT')

    def test_trace_preserves_requested_and_effective_route(self):
        result = {'ok': True, 'route': {'model': 'effective'}, 'message': {'content': 'OK'}}
        owner = types.SimpleNamespace(route=lambda request: result)
        attempts, saves = [], []
        diagnostics.trace_calls(owner, 'route', attempts, lambda: saves.append(True))
        self.assertIs(owner.route({'task': 'vision', 'model': 'requested', 'deadline_ms': 70000}), result)
        self.assertEqual(attempts[0]['model_requested'], 'requested')
        self.assertEqual(attempts[0]['route']['model'], 'effective')
        self.assertEqual(attempts[0]['response'], 'OK')
        self.assertEqual(len(saves), 1)


if __name__ == '__main__':
    unittest.main()
