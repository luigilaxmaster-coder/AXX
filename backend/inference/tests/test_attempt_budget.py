"""Per-request upstream budgets constrain real router dispatches using offline transports."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.inference.adapter import InferenceAdapter, worker_main
from backend.inference.router import Router, RequestError, StateError, UpstreamError


class AttemptBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = patch.dict(os.environ, {'BUDGET_TEST_KEY': 'offline-fixture'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.calls, self.responses, self.serial = [], {}, 0
        self.config = {'allow_paid': False, 'max_attempts': 3,
                       'providers': [self.provider('a'), self.provider('b')]}

    @staticmethod
    def provider(name, **overrides):
        return dict(name=name, model='model-' + name, base_url='https://' + name + '.example/v1',
            api_key_env='BUDGET_TEST_KEY', enabled=True, free_confirmed=True, billing_allowed=False,
            cost_evidence='free_tier', route_kind='direct', context_window=32768,
            capabilities=['text'], daily_attempt_limit=100, **overrides)

    def transport(self, provider, payload, timeout):
        self.calls.append((provider['name'], copy.deepcopy(payload)))
        result = self.responses.get(provider['name'], {'choices': [{'message': {'role': 'assistant', 'content': 'local fixture'}}]})
        if isinstance(result, Exception): raise result
        return copy.deepcopy(result)

    def adapter(self, *, injected=True):
        self.serial += 1
        state = Path(self.temp.name) / (str(self.serial) + '.db')
        router = Router(copy.deepcopy(self.config), state=state, transport=self.transport) if injected else None
        adapter = InferenceAdapter(copy.deepcopy(self.config), state, router_instance=router)
        self.addCleanup(adapter.close)
        return adapter

    @staticmethod
    def request(**fields):
        return {'messages': [{'role': 'user', 'content': 'synthetic budget trial'}],
                'selection_mode': 'automatic_free'} | fields

    def gateway(self, *, bound=2):
        return dict(self.provider('gateway'), kind='freellmapi', route_kind='proxy', model='auto:axx_chat',
            gateway_profile_verified=True, gateway_attempt_limit=bound, gateway_free_model_ids=[1])

    def test_one_attempt_never_fails_over_but_legacy_requests_still_do(self):
        self.responses['a'] = UpstreamError(500)
        for mode in ('manual', 'automatic_free'):
            with self.subTest(mode=mode):
                self.calls.clear()
                limited = self.adapter().route(self.request(selection_mode=mode, upstream_attempt_budget=1))
                self.assertFalse(limited['ok'], limited)
                self.assertEqual([name for name, _ in self.calls], ['a'])
                self.assertEqual(limited['error']['upstream_attempts'], 1)
                self.assertEqual(limited['error']['attempt_budget_used'], 1)
                self.calls.clear()
                legacy = self.adapter().route(self.request(selection_mode=mode))
                self.assertTrue(legacy['ok'], legacy)
                self.assertEqual([name for name, _ in self.calls], ['a', 'b'])
                self.assertEqual(legacy['route']['upstream_attempts'], 2)
                self.assertEqual(legacy['route']['attempt_budget_used'], 2)
        self.assertEqual(self.config['max_attempts'], 3)

    def test_request_cannot_raise_configured_attempt_limit(self):
        self.config['max_attempts'] = 1
        self.responses['a'] = UpstreamError(500)
        result = self.adapter().route(self.request(upstream_attempt_budget=10))
        self.assertFalse(result['ok'])
        self.assertEqual([name for name, _ in self.calls], ['a'])
        self.assertEqual(result['error']['attempt_budget_used'], 1)

    def test_invalid_budget_is_rejected_before_any_router_or_worker_call(self):
        adapter = self.adapter(injected=False)
        for budget in (0, -1, True, False, None, '1', 1.0, 11):
            with self.subTest(budget=budget), patch.object(adapter, '_worker_result') as worker:
                result = adapter.route(self.request(upstream_attempt_budget=budget))
                self.assertEqual(result['error']['code'], 'INVALID_REQUEST')
                self.assertIs(result['error']['upstream_attempted'], False)
                self.assertEqual(result['error']['upstream_attempts'], 0)
                self.assertEqual(result['error']['attempt_budget_used'], 0)
                self.assertFalse(adapter.active_requests)
                worker.assert_not_called()
                with self.assertRaises(RequestError) as caught:
                    adapter.router.chat({'messages': [{'role': 'user', 'content': 'trial'}], 'axx_attempt_budget': budget})
                self.assertEqual(caught.exception.upstream_attempts, 0)
                self.assertEqual(caught.exception.attempt_budget_used, 0)
        self.assertEqual(self.calls, [])

    def test_gateway_live_bound_excludes_route_over_one_attempt_even_when_manually_pinned(self):
        self.config['providers'] = [self.gateway(bound=1)]
        for mode in ('manual', 'automatic_free'):
            with self.subTest(mode=mode), patch('backend.inference.freellmapi.verify_provider',
                    return_value={'gateway_attempt_limit': 2}) as verify:
                result = self.adapter().route(self.request(selection_mode=mode, model='auto:axx_chat',
                    provider_name='gateway', upstream_attempt_budget=1))
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['error']['upstream_attempts'], 0)
                self.assertEqual(result['error']['attempt_budget_used'], 0)
                verify.assert_called_once()
        self.assertEqual(self.calls, [])

    def test_bounded_gateway_reports_outer_dispatch_and_conservative_downstream_cost(self):
        self.config['providers'] = [self.gateway()]
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 2}):
            result = self.adapter().route(self.request(upstream_attempt_budget=2))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['upstream_attempts'], 1)
        self.assertEqual(result['attempt_budget_used'], 2)
        self.assertEqual(result['route']['attempts'], 1)
        self.assertEqual(result['route']['attempt_budget_used'], 2)
        self.assertNotIn('axx_attempt_budget', self.calls[0][1])
        self.assertNotIn('upstream_attempt_budget', self.calls[0][1])

    def test_gateway_cannot_spend_more_than_remaining_request_budget(self):
        self.config['providers'] = [self.provider('a'), self.gateway(), self.provider('c')]
        self.responses['a'] = UpstreamError(500)
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 2}):
            result = self.adapter().route(self.request(upstream_attempt_budget=2))
        self.assertTrue(result['ok'], result)
        self.assertEqual([name for name, _ in self.calls], ['a', 'c'])
        self.assertEqual(result['upstream_attempts'], 2)
        self.assertEqual(result['attempt_budget_used'], 2)

    def test_unknown_proxy_fanout_cannot_borrow_a_direct_route_attempt_bound(self):
        self.config['providers'] = [dict(self.provider('proxy'), route_kind='proxy')]
        limited = self.adapter().route(self.request(upstream_attempt_budget=1))
        self.assertFalse(limited['ok'])
        self.assertEqual(limited['error']['attempt_budget_used'], 0)
        self.assertEqual(self.calls, [])
        legacy = self.adapter().route(self.request())
        self.assertTrue(legacy['ok'], legacy)
        self.assertEqual([name for name, _ in self.calls], ['proxy'])

    def test_candidate_route_honors_budget_instead_of_using_a_sibling_failover(self):
        self.config['providers'][0] = self.gateway()
        adapter = self.adapter()
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 2}):
            result = adapter.route_candidate(self.request(upstream_attempt_budget=1), 'gateway')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['attempt_budget_used'], 0)
        self.assertEqual(self.calls, [])

    def test_worker_request_and_error_preserve_budget_without_global_config_mutation(self):
        adapter = self.adapter(injected=False)
        captured = []
        def worker(active, request):
            captured.append(copy.deepcopy(request))
            return {'ok': False, 'error': {'code': 'UPSTREAM_TEMPORARY', 'message': 'offline failure', 'retryable': True,
                'upstream_attempted': True, 'upstream_attempts': 1, 'attempt_budget_used': 1}}
        with patch.object(adapter, '_worker_result', side_effect=worker):
            result = adapter.route(self.request(upstream_attempt_budget=1))
        self.assertEqual(captured[0]['axx_attempt_budget'], 1)
        self.assertNotIn('upstream_attempt_budget', captured[0])
        self.assertEqual(result['error']['upstream_attempts'], 1)
        self.assertEqual(result['error']['attempt_budget_used'], 1)
        self.assertEqual(adapter.config['max_attempts'], 3)
        self.assertEqual(adapter.router.max_attempts, 3)

    def test_worker_main_enforces_forwarded_budget_with_actual_offline_router(self):
        self.responses['a'] = UpstreamError(500)
        request = {'messages': [{'role': 'user', 'content': 'trial'}], 'selection_mode': 'automatic_free', 'axx_attempt_budget': 1}
        stdin = SimpleNamespace(buffer=io.BytesIO(json.dumps({'config': self.config, 'request': request}).encode()))
        stdout = SimpleNamespace(buffer=io.BytesIO())
        def router(config, state): return Router(config, state=state, transport=self.transport)
        with patch('backend.inference.adapter.sys.stdin', stdin), patch('backend.inference.adapter.sys.stdout', stdout), \
                patch('backend.inference.adapter.Router', side_effect=router):
            code = worker_main(str(Path(self.temp.name) / 'worker.db'))
        result = json.loads(stdout.buffer.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual([name for name, _ in self.calls], ['a'])
        self.assertEqual(result['error']['upstream_attempts'], 1)
        self.assertEqual(result['error']['attempt_budget_used'], 1)
        self.assertNotIn('axx_attempt_budget', self.calls[0][1])

    def test_unknown_worker_failure_never_claims_zero_upstream(self):
        adapter = self.adapter(injected=False)
        with patch.object(adapter, '_worker_result', return_value={'ok': False, 'error': {
                'code': 'PROCESS_FAILURE', 'message': 'worker receipt missing'}}):
            result = adapter.route(self.request(upstream_attempt_budget=1))
        self.assertNotIn('upstream_attempts', result['error'])
        self.assertNotIn('attempt_budget_used', result['error'])
        self.assertNotIn('upstream_attempted', result['error'])

    def test_late_cancellation_discards_content_but_keeps_consumed_attempt(self):
        adapter = self.adapter()
        def cancel(provider, payload, timeout):
            adapter.cancel('cancel-consumed')
            return {'choices': [{'message': {'role': 'assistant', 'content': 'discarded synthetic content'}}]}
        adapter.router.transport = cancel
        result = adapter.route(self.request(request_id='cancel-consumed', upstream_attempt_budget=1))
        self.assertEqual(result['error']['code'], 'CANCELLED')
        self.assertEqual(result['error']['upstream_attempts'], 1)
        self.assertEqual(result['error']['attempt_budget_used'], 1)
        self.assertNotIn('message', result)

    def test_post_dispatch_policy_and_state_errors_keep_consumed_attempt(self):
        self.responses['a'] = UpstreamError(403, is_policy=True)
        result = self.adapter().route(self.request(upstream_attempt_budget=1))
        self.assertEqual(result['error']['code'], 'UPSTREAM_POLICY')
        self.assertEqual(result['error']['upstream_attempts'], 1)
        self.responses.clear()
        adapter = self.adapter()
        with patch.object(adapter.router, '_record', side_effect=StateError('local receipt failed')):
            result = adapter.route(self.request(upstream_attempt_budget=1))
        self.assertEqual(result['error']['code'], 'STATE_UNAVAILABLE')
        self.assertEqual(result['error']['upstream_attempts'], 1)
        self.assertEqual(result['error']['attempt_budget_used'], 1)


if __name__ == '__main__': unittest.main()
