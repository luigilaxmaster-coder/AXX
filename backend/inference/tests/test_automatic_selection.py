import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.inference.adapter import InferenceAdapter
from backend.inference.router import Router, UpstreamError, http_transport
from backend.inference import provider_settings


class AutomaticSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = patch.dict(os.environ, {'AUTO_TEST_KEY': 'offline-only'})
        self.key.start()
        self.addCleanup(self.key.stop)
        self.calls, self.responses = [], {}
        self.config = {'providers': [self.provider('a'), self.provider('b')]}

    def provider(self, name, **fields):
        return dict(name=name, model='model-' + name, base_url='https://' + name + '.example/v1',
                    api_key_env='AUTO_TEST_KEY', enabled=True, free_confirmed=True, billing_allowed=False,
                    cost_evidence='free_tier', route_kind='direct', context_window=32768,
                    capabilities=['text'], daily_attempt_limit=100, **fields)

    def adapter(self):
        def transport(provider, payload, timeout):
            self.calls.append((provider['name'], payload))
            result = self.responses.get(provider['name'], {'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]})
            if isinstance(result, Exception):
                raise result
            return copy.deepcopy(result)
        state = Path(self.tmp.name) / 'state.db'
        router = Router(self.config, state=state, transport=transport)
        adapter = InferenceAdapter(self.config, state, router_instance=router)
        self.addCleanup(adapter.close)
        return adapter

    def request(self, adapter, **fields):
        return adapter.route(dict(messages=[{'role': 'user', 'content': 'hello'}], selection_mode='automatic_free', **fields))

    def test_automatic_ignores_manual_pins_and_excludes_billing(self):
        self.config['providers'][0]['billing_allowed'] = True
        result = self.request(self.adapter(), model='model-a', provider_name='a')
        self.assertTrue(result['ok'], result)
        self.assertEqual([name for name, _ in self.calls], ['b'])
        self.assertNotIn('selection_mode', self.calls[0][1])

    def test_unknown_or_paid_cost_is_never_automatic(self):
        self.config['providers'][0]['cost_evidence'] = 'unknown'
        self.config['providers'][1]['cost_evidence'] = 'paid'
        result = self.request(self.adapter())
        self.assertFalse(result['ok'])
        self.assertIs(result['error']['upstream_attempted'], False)
        self.assertEqual(self.calls, [])

    def test_local_proxy_requires_explicit_downstream_free_evidence(self):
        self.config['providers'] = [dict(self.config['providers'][0], base_url='http://127.0.0.1:1234/v1',
                                         route_kind='proxy', cost_evidence='direct_local')]
        self.assertFalse(self.request(self.adapter())['ok'])
        self.assertEqual(self.calls, [])

    def test_explicit_direct_local_is_eligible_without_key(self):
        self.config['providers'] = [dict(self.config['providers'][0], base_url='http://127.0.0.1:1234/v1',
                                         route_kind='direct', cost_evidence='direct_local', api_key_env='MISSING_AUTO_KEY')]
        self.assertTrue(self.request(self.adapter())['ok'])

    def test_manual_preserves_billing_and_pinned_selection(self):
        self.config['providers'][0].update(billing_allowed=True, free_confirmed=False, cost_evidence='unknown')
        result = self.adapter().route({'model': 'model-a', 'provider_name': 'a', 'messages': [{'role': 'user', 'content': 'hi'}]})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['route']['model'], 'model-a')
        self.assertEqual([name for name, _ in self.calls], ['a'])

    def test_task_capabilities_and_context_are_hard_filters(self):
        self.config['providers'][0].update(context_window=1, task_priority={'vision': 0})
        self.config['providers'][1]['capabilities'] = ['text', 'vision']
        self.assertTrue(self.request(self.adapter(), task='vision')['ok'])
        self.assertEqual([name for name, _ in self.calls], ['b'])

    def test_unknown_context_and_missing_capability_are_ineligible(self):
        del self.config['providers'][0]['context_window']
        self.config['providers'][1]['capabilities'] = ['vision']
        self.assertFalse(self.request(self.adapter())['ok'])
        self.assertEqual(self.calls, [])

    def test_curated_task_priority_is_deterministic(self):
        self.config['providers'][0]['task_priority'] = {'plan': 80}
        self.config['providers'][1]['task_priority'] = {'plan': 10}
        self.assertTrue(self.request(self.adapter(), task='plan')['ok'])
        self.assertEqual([name for name, _ in self.calls], ['b'])

    def test_automatic_auth_failure_can_try_next_route(self):
        for status in (401, 403):
            with self.subTest(status=status):
                self.calls.clear()
                self.responses['a'] = UpstreamError(status)
                self.assertTrue(self.request(self.adapter())['ok'])
                self.assertEqual([name for name, _ in self.calls], ['a', 'b'])

    def test_policy_and_payment_stop_automatic_fallback(self):
        for error in (UpstreamError(403, is_policy=True), UpstreamError(402)):
            self.calls.clear()
            self.responses['a'] = error
            self.assertEqual(self.request(self.adapter())['error']['code'], 'UPSTREAM_POLICY')
            self.assertEqual([name for name, _ in self.calls], ['a'])

    def test_attempt_limit_survives_auth_fallback(self):
        self.config['max_attempts'] = 1
        self.responses['a'] = UpstreamError(401)
        result = self.request(self.adapter())
        self.assertFalse(result['ok'])
        self.assertIs(result['error']['upstream_attempted'], True)
        self.assertEqual([name for name, _ in self.calls], ['a'])

    def test_real_worker_capacity_error_proves_no_upstream_inference(self):
        adapter = InferenceAdapter({'providers': []}, Path(self.tmp.name) / 'empty.db')
        self.addCleanup(adapter.close)
        result = self.request(adapter)
        self.assertEqual(result['error']['code'], 'NO_PROVIDER_AVAILABLE')
        self.assertIs(result['error']['upstream_attempted'], False)
        adapter.conversation_locks['default'] = 'busy-fixture'
        result = self.request(adapter)
        self.assertEqual(result['error']['code'], 'BUSY')
        self.assertIs(result['error']['upstream_attempted'], False)

    def test_unknown_proxy_identity_never_invents_responder(self):
        self.config['providers'][0].update(route_kind='proxy', model='automatic')
        route = self.request(self.adapter())['route']
        self.assertEqual(route['provider'], 'a')
        self.assertIsNone(route['model'])
        self.assertIsNone(route['responder_model'])
        self.assertEqual(route['identity'], 'unverified_profile')
        self.assertEqual(route['configured_model'], 'automatic')

    def test_proxy_echoing_selection_alias_is_not_an_actual_model_identity(self):
        self.config['providers'][0].update(route_kind='proxy', model='auto/quality')
        self.responses['a'] = {'model': 'auto/quality', 'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]}
        route = self.request(self.adapter())['route']
        self.assertIsNone(route['responder_model'])
        self.assertEqual(route['identity'], 'unverified_profile')

    def test_freellmapi_requires_explicit_endpoint_and_stays_unverified(self):
        with self.assertRaises(ValueError):
            provider_settings.endpoint('', 'freellmapi')
        adapter = self.adapter()
        provider_settings.save({'provider': 'freellmapi', 'name': 'gateway', 'model': 'auto',
                                'base_url': 'http://127.0.0.1:19001/v1'}, adapter,
                               Path(self.tmp.name) / 'providers.json')
        provider = adapter.config['providers'][-1]
        self.assertEqual(provider['route_kind'], 'proxy')
        self.assertEqual(provider['cost_evidence'], 'unknown')
        self.assertFalse(adapter.get_status()['providers'][-1]['automatic_free_eligible'])

    def test_reported_identity_and_outcomes_remain_separate_from_http_metrics(self):
        self.responses['a'] = {'model': 'actual-model', 'provider': 'actual-provider',
                               'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]}
        adapter = self.adapter()
        route = self.request(adapter, task='plan')['route']
        self.assertEqual(route['responder_model'], 'actual-model')
        self.assertEqual(route['responder_provider'], 'actual-provider')
        self.assertEqual(route['identity'], 'reported')
        adapter.record_outcome(route, 'plan', 'failed')
        adapter.record_outcome(route, 'plan', 'failed')
        metrics = adapter.record_outcome(route, 'plan', 'user_confirmed')
        self.assertEqual(metrics['failed'], 1)
        self.assertEqual(metrics['user_confirmed'], 1)
        self.assertEqual(adapter.get_status()['providers'][0]['metrics']['successes'], 1)
        with self.assertRaises(ValueError):
            adapter.record_outcome(route, 'chat', 'succeeded')
        with self.assertRaises(ValueError):
            adapter.record_outcome(dict(route, profile_id='forged'), 'plan', 'succeeded')

    def test_observed_ranking_requires_five_real_task_outcomes(self):
        adapter = self.adapter()
        for _ in range(4):
            route = self.request(adapter)['route']
            self.assertEqual(route['provider'], 'a')
            adapter.record_outcome(route, 'chat', 'failed')
        route = self.request(adapter)['route']
        self.assertEqual(route['provider'], 'a')
        adapter.record_outcome(route, 'chat', 'failed')
        self.assertEqual(self.request(adapter)['route']['provider'], 'b')

    def test_invalid_selection_and_metadata_are_typed(self):
        adapter = self.adapter()
        result = adapter.route({'selection_mode': True, 'messages': [{'role': 'user', 'content': 'hello'}]})
        self.assertEqual(result['error']['code'], 'INVALID_REQUEST')
        for field, value in [('cost_evidence', True), ('route_kind', []), ('context_window', True),
                             ('task_priority', {'chat': True}), ('task_priority', {'bogus': 1})]:
            config = copy.deepcopy(self.config)
            config['providers'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                Router._validate_config(None, config)

    def test_provider_edits_preserve_account_limits_and_metadata(self):
        adapter = self.adapter()
        adapter.config['providers'][0].update(quota_scope_id='account', scope_limit=7, daily_attempt_limit=8,
                                              task_priority={'plan': 4})
        provider_settings.save({'provider': 'custom', 'name': 'a', 'model': 'model-a',
                                'base_url': 'https://a.example/v1'}, adapter, Path(self.tmp.name) / 'providers.json')
        provider = adapter.config['providers'][0]
        self.assertEqual(provider['quota_scope_id'], 'account')
        self.assertEqual(provider['scope_limit'], 7)
        self.assertEqual(provider['daily_attempt_limit'], 8)
        self.assertEqual(provider['cost_evidence'], 'free_tier')
        self.assertEqual(provider['task_priority'], {'plan': 4})
        public = provider_settings.public_entries(adapter.config)[0]
        self.assertEqual(public['context_window'], 32768)
        self.assertNotIn('api_key_env', public)

    def test_saved_local_proxy_is_not_automatic_by_address(self):
        adapter = self.adapter()
        provider_settings.save({'provider': 'compat', 'name': 'proxy', 'model': 'auto'}, adapter,
                               Path(self.tmp.name) / 'providers.json')
        provider = adapter.config['providers'][-1]
        self.assertEqual(provider['cost_evidence'], 'unknown')
        self.assertEqual(provider['route_kind'], 'unknown')

    def test_disabled_missing_key_and_shared_quota_are_filtered_before_ranking(self):
        self.config['providers'] += [self.provider('c'), self.provider('d')]
        self.config['providers'][0]['enabled'] = False
        self.config['providers'][1]['api_key_env'] = 'MISSING_AUTO_TEST_KEY'
        self.config['providers'][2].update(quota_scope_id='shared', scope_limit=1)
        self.config['providers'][3].update(quota_scope_id='shared', scope_limit=1)
        adapter = self.adapter()
        self.assertTrue(self.request(adapter)['ok'])
        self.assertFalse(self.request(adapter)['ok'])
        self.assertEqual([name for name, _ in self.calls], ['c'])
        self.assertFalse(any(p['automatic_free_eligible'] for p in adapter.get_status()['providers']))

    def test_image_context_budget_and_declared_tasks_are_required(self):
        self.config['providers'][0].update(capabilities=['text', 'vision'])
        self.config['providers'][1].update(capabilities=['text', 'vision'], image_context_tokens=8192, tasks=['vision'])
        adapter = self.adapter()
        result = adapter.route({'selection_mode': 'automatic_free', 'task': 'vision', 'messages': [
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aaaa'}}]}]})
        self.assertTrue(result['ok'], result)
        self.assertEqual([name for name, _ in self.calls], ['b'])
        self.assertEqual(self.calls[-1][1]['max_tokens'], 1024)

    def test_tool_capabilities_and_context_include_tool_definitions(self):
        self.config['providers'][1]['capabilities'] = ['text', 'tools']
        adapter = self.adapter()
        result = self.request(adapter, task='parameters', generation={'tools': [
            {'type': 'function', 'function': {'name': 'offline', 'parameters': {'type': 'object'}}}]})
        self.assertTrue(result['ok'], result)
        self.assertEqual([name for name, _ in self.calls], ['b'])

    def test_outcomes_persist_and_unverified_proxy_is_profile_attributed(self):
        adapter = self.adapter()
        route = self.request(adapter, task='repair')['route']
        self.assertEqual(route['attribution_id'], route['profile_id'])
        adapter.record_outcome(route, 'repair', 'succeeded')
        adapter.close()
        restored = self.adapter()
        counts = restored.record_outcome(route, 'repair', 'user_rejected')
        self.assertEqual(counts['succeeded'], 1)
        self.assertEqual(counts['user_rejected'], 1)
        for invalid in (None, 1, {}, 'http_success'):
            with self.assertRaises(ValueError):
                restored.record_outcome(route, 'repair', invalid)

    def test_new_model_does_not_inherit_cost_context_or_task_evidence(self):
        adapter = self.adapter()
        path = Path(self.tmp.name) / 'providers.json'
        provider_settings.save({'provider': 'custom', 'name': 'a', 'model': 'different',
                                'base_url': 'https://a.example/v1'}, adapter, path)
        provider = adapter.config['providers'][0]
        self.assertEqual(provider['cost_evidence'], 'unknown')
        self.assertNotIn('context_window', provider)
        self.assertEqual(provider['capabilities'], ['text'])
        self.assertFalse(adapter.get_status()['providers'][0]['automatic_free_eligible'])

    def test_invalid_provider_boolean_does_not_mutate_saved_configuration(self):
        adapter = self.adapter()
        before = copy.deepcopy(adapter.config)
        for field in ('enabled', 'free_confirmed', 'billing_allowed'):
            with self.assertRaises(ValueError):
                provider_settings.save({'provider': 'custom', 'name': 'a', 'model': 'model-a',
                                        'base_url': 'https://a.example/v1', field: 'true'}, adapter,
                                       Path(self.tmp.name) / 'providers.json')
        self.assertEqual(adapter.config, before)

    def test_actual_worker_persists_automatic_route_receipt_for_host_outcome(self):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                observed.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                response = json.dumps({'model': 'local-fixture', 'choices': [
                    {'message': {'role': 'assistant', 'content': 'local fixture response'}}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(response)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.config['providers'] = [dict(self.config['providers'][0], cost_evidence='direct_local',
                                         base_url=f'http://127.0.0.1:{server.server_port}/v1')]
        adapter = InferenceAdapter(self.config, Path(self.tmp.name) / 'worker.db')
        self.addCleanup(adapter.close)
        result = self.request(adapter, task='plan')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['route']['responder_model'], 'local-fixture')
        self.assertNotIn('selection_mode', observed[0])
        self.assertEqual(adapter.record_outcome(result['route'], 'plan', 'succeeded')['succeeded'], 1)

    def test_gateway_routed_header_reports_real_responder_not_profile_alias(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'model': 'auto:axx_plan', 'choices': [
            {'message': {'role': 'assistant', 'content': 'ok'}}]}).encode()
        response.__enter__.return_value.headers = {'X-Routed-Via': 'provider/model%2Factual'}
        with patch('backend.inference.router.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            result = http_transport(dict(self.config['providers'][0], kind='freellmapi'),
                                    {'messages': [{'role': 'user', 'content': 'hello'}]}, 1)
        self.assertEqual(result['model'], 'model/actual')
        self.assertEqual(result['provider'], 'provider')

    def gateway(self, limit=3):
        self.config['providers'][0].update(kind='freellmapi', route_kind='proxy', model='auto:axx_chat',
                                          gateway_profile_verified=True, gateway_attempt_limit=limit,
                                          gateway_free_model_ids=[1], gateway_timeout_ms=20000)

    def test_gateway_attempt_bound_uses_remaining_global_budget(self):
        self.gateway()
        self.responses['a'] = UpstreamError(503)
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 3}) as verify:
            result = self.request(self.adapter())
        self.assertFalse(result['ok'])
        self.assertEqual([name for name, _ in self.calls], ['a'])
        verify.assert_called_once()

    def test_bounded_gateway_failure_falls_back_to_next_verified_gateway(self):
        self.gateway(limit=1)
        self.config['providers'][1].update(kind='freellmapi',route_kind='proxy',model='auto:axx_chat',
            gateway_profile_verified=True,gateway_attempt_limit=1,gateway_free_model_ids=[2])
        self.responses['a']=UpstreamError(503)
        with patch('backend.inference.freellmapi.verify_provider',return_value={'gateway_attempt_limit':1}):
            result=self.request(self.adapter())
        self.assertTrue(result['ok'],result)
        self.assertEqual([name for name,_ in self.calls],['a','b'])
        self.assertEqual(result['route']['attempt_budget_used'],2)

    def test_gateway_live_policy_failure_blocks_traffic_and_uses_other_eligible_route(self):
        self.gateway()
        with patch('backend.inference.freellmapi.verify_provider', side_effect=ValueError('profile changed')):
            result = self.request(self.adapter())
        self.assertTrue(result['ok'], result)
        self.assertEqual([name for name, _ in self.calls], ['b'])

    def test_gateway_over_budget_is_filtered_and_unverified_flags_cannot_enable_it(self):
        self.gateway(limit=4)
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 4}):
            result = self.request(self.adapter())
        self.assertTrue(result['ok'])
        self.assertEqual([name for name, _ in self.calls], ['b'])
        self.calls.clear()
        self.config['providers'][0]['gateway_profile_verified'] = False
        with patch('backend.inference.freellmapi.verify_provider') as verify:
            self.assertTrue(self.request(self.adapter())['ok'])
            verify.assert_not_called()

    def test_gateway_cannot_follow_prior_attempt_when_remaining_budget_is_insufficient(self):
        self.gateway()
        self.config['providers'].reverse()
        self.responses['b'] = UpstreamError(401)
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 3}):
            result = self.request(self.adapter())
        self.assertFalse(result['ok'])
        self.assertEqual([name for name, _ in self.calls], ['b'])

    def test_gateway_route_distinguishes_outer_attempts_from_reserved_downstream_budget(self):
        self.gateway()
        with patch('backend.inference.freellmapi.verify_provider', return_value={'gateway_attempt_limit': 3}):
            route = self.request(self.adapter())['route']
        self.assertEqual(route['attempts'], 1)
        self.assertEqual(route['attempt_budget_used'], 3)

    def test_gateway_save_uses_live_verified_metadata_not_browser_flags(self):
        adapter = self.adapter()
        with patch('backend.inference.freellmapi.configure_gateway_credentials', return_value='AXX_API_DASHBOARD'), \
                patch('backend.inference.freellmapi.verify_provider', return_value={
                    'gateway_profile_verified': True, 'gateway_attempt_limit': 3, 'gateway_timeout_ms': 20000,
                    'context_window': 4096, 'capabilities': ['text']}):
            provider_settings.save({'provider': 'freellmapi', 'name': 'gateway', 'model': 'auto:axx_chat',
                                    'base_url': 'http://127.0.0.1:19001/v1', 'cost_evidence': 'free_tier',
                                    'free_confirmed': True, 'gateway_free_model_ids': [1],
                                    'gateway_attempt_limit': 1, 'gateway_dashboard_env': 'ATTACKER_CHOSEN_ENV'},
                                   adapter, Path(self.tmp.name) / 'providers.json')
        entry = adapter.config['providers'][-1]
        self.assertEqual(entry['gateway_attempt_limit'], 3)
        self.assertEqual(entry['gateway_dashboard_env'], 'AXX_API_DASHBOARD')
        self.assertNotIn('gateway_dashboard_env', provider_settings.public_entries(adapter.config)[-1])

    def test_gateway_local_address_does_not_replace_required_inference_key(self):
        self.gateway()
        self.config['providers'][0].update(base_url='http://127.0.0.1:19001/v1', api_key_env='MISSING_GATEWAY_KEY')
        adapter = self.adapter()
        self.assertEqual(adapter.get_status()['providers'][0]['state'], 'missing_key')
        with patch('backend.inference.freellmapi.verify_provider') as verify:
            self.assertTrue(self.request(adapter)['ok'])
            verify.assert_not_called()
        self.assertEqual([name for name, _ in self.calls], ['b'])

    def test_gateway_discovery_uses_filtered_catalog_helper(self):
        body = {'provider': 'freellmapi', 'base_url': 'http://127.0.0.1:19001/v1'}
        with patch('backend.inference.freellmapi.discover', return_value={'models': ['ready-model']}) as discover:
            self.assertEqual(provider_settings.discover(body, self.config), {'models': ['ready-model']})
            discover.assert_called_once_with(body, self.config)


if __name__ == '__main__':
    unittest.main()
