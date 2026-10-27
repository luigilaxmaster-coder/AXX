import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from backend.inference import freellmapi as gateway


BASE = 'http://127.0.0.1:3001/v1'


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = gateway.FreeLLMAPIService(self.root)
        self.models = [{'id': 7, 'platform': 'groq', 'modelId': 'fixture', 'contextWindow': 8192,
                        'enabled': True, 'supportsVision': True, 'supportsTools': True,
                        'intelligenceRank': 1, 'speedRank': 2}]
        self.profiles = [{'id': 4, 'name': 'axx_plan', 'type': 'custom', 'auto_include_new_models': 0}]
        self.members = {4: [{'model_db_id': 7, 'enabled': True}]}
        self.calls = []
        self.guard = 3
        self.keys = []
        self.group_extra_ids = []
        self.ready = {'id': 'fixture', 'owned_by': 'groq', 'available': True, 'execution_status': 'ready', 'context_window': 8192}

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def request(self, base, path, key='', body=None, method=None, timeout=5):
        self.calls.append((path, body, method))
        if path == '/api/auth/status':
            return {'authenticated': key == 'dashboard-secret'}
        if path == '/v1/models?execution_status=ready':
            return {'data': [{'id': 'auto', 'available': True}, {'id': 'auto:axx_plan', 'available': True}, self.ready]}
        if path == '/api/models':
            return copy.deepcopy(self.models)
        if path == '/api/settings/guardrails':
            if method == 'PUT':
                self.guard = body['maxConsecutiveUpstreamFails']
            return {'maxConsecutiveUpstreamFails': self.guard}
        if path == '/api/keys':
            if method == 'POST':
                self.keys.append({'platform': body['platform'], 'enabled': True, 'keyless': True})
                return {'id': 1}
            return copy.deepcopy(self.keys)
        if path == '/api/settings/version':
            return {'version': gateway.VERSION}
        if path == '/api/fallback' or path.startswith('/api/fallback?profile='):
            return [{'canonicalId': m.get('canonical', 'fixture'), 'modelDbId': m['id']} for m in self.models] + [
                {'canonicalId': 'fixture', 'modelDbId': i} for i in self.group_extra_ids]
        if path == '/api/profiles':
            if method == 'POST':
                profile = {'id': len(self.profiles) + 10, 'name': body['name'], 'type': 'custom', 'auto_include_new_models': 0}
                self.profiles.append(profile)
                self.members[profile['id']] = []
                return dict(profile)
            return copy.deepcopy(self.profiles)
        if path.startswith('/api/profiles/'):
            ident = int(path.split('/')[3])
            if path.endswith('/models'):
                return copy.deepcopy(self.members[ident])
            if path.endswith('/reorder'):
                self.members[ident] = [{'model_db_id': r['modelDbId'], 'enabled': r['enabled']} for r in body]
                return {'success': True}
        if path == '/api/keys/custom':
            return {'modelDbId': 7, 'maskedKey': 'must-not-return'}
        if path == '/api/models/7' and method == 'PATCH':
            return {'success': True}
        raise AssertionError(path)

    def provider(self):
        return {'model': 'auto:axx_plan', 'base_url': BASE, 'gateway_free_model_ids': [7],
                'gateway_dashboard_env': 'TEST_GATEWAY_SESSION', 'api_key_env': 'TEST_GATEWAY_KEY'}

    def test_catalog_separates_synthetic_even_when_available_true(self):
        with patch.object(gateway, '_request', side_effect=self.request):
            result = gateway.discover({'base_url': BASE, 'api_key': 'secret'})
        self.assertEqual(result['models'], ['fixture'])
        self.assertEqual(len(result['routing_entries']), 2)
        self.assertFalse(result['free_verified'])
        self.assertNotIn('secret', json.dumps(result))

    def test_changed_endpoint_never_receives_saved_credentials(self):
        config = {'providers': [{'name': 'g', 'base_url': BASE, 'api_key_env': 'TEST_KEY', 'gateway_dashboard_env': 'TEST_ADMIN'}]}
        with patch.dict(os.environ, {'TEST_KEY': 'api-secret', 'TEST_ADMIN': 'admin-secret'}):
            same = gateway._connection({'name': 'g', 'base_url': BASE}, config)
            changed = gateway._connection({'name': 'g', 'base_url': 'http://127.0.0.1:3002/v1'}, config)
        self.assertEqual(same[1:], ('api-secret', 'admin-secret'))
        self.assertEqual(changed[1:], ('', ''))

    def test_profile_live_validation_minimum_context_and_member_intersection(self):
        self.models.append({**self.models[0], 'id': 8, 'modelId': 'second', 'contextWindow': 4096, 'supportsTools': False})
        self.members[4].append({'model_db_id': 8, 'enabled': True})
        provider = self.provider()
        provider['gateway_free_model_ids'].append(8)
        with patch.object(gateway, '_request', side_effect=self.request), patch.dict(os.environ, {'TEST_GATEWAY_SESSION': 'dashboard-secret'}):
            result = gateway.verify_provider(provider, timeout=.5)
        self.assertEqual(result['context_window'], 4096)
        self.assertEqual(result['capabilities'], ['text', 'vision'])
        self.assertEqual(result['gateway_attempt_limit'], 3)
        self.assertTrue(result['gateway_profile_verified'])

    def test_unconfirmed_new_members_auto_backfill_and_disabled_guard_are_rejected(self):
        with patch.object(gateway, '_request', side_effect=self.request), patch.dict(os.environ, {'TEST_GATEWAY_SESSION': 'dashboard-secret'}):
            self.members[4].append({'model_db_id': 999, 'enabled': True})
            with self.assertRaises(ValueError): gateway.verify_provider(self.provider())
            self.members[4].pop()
            self.profiles[0]['auto_include_new_models'] = 1
            with self.assertRaises(ValueError): gateway.verify_provider(self.provider())
            self.profiles[0]['auto_include_new_models'] = 0
            self.guard = 0
            with self.assertRaises(ValueError): gateway.verify_provider(self.provider())

    def test_unified_or_exhausted_catalog_does_not_prove_member_ready(self):
        with patch.object(gateway, '_request', side_effect=self.request), patch.dict(os.environ, {'TEST_GATEWAY_SESSION': 'dashboard-secret'}):
            self.ready['owned_by'] = 'freellmapi'
            self.group_extra_ids = [999]
            with self.assertRaises(ValueError): gateway.verify_provider(self.provider())
            self.group_extra_ids = []
            self.ready['execution_status'] = 'exhausted'
            with self.assertRaises(ValueError): gateway.verify_provider(self.provider())

    def test_catalog_change_retries_whole_profile_validation_once(self):
        changed = False
        def request(base, path, *args, **kwargs):
            nonlocal changed
            result = self.request(base, path, *args, **kwargs)
            if path == '/api/models' and not changed:
                self.models.append({**self.models[0], 'id': 8, 'modelId': 'other', 'canonical': 'unrelated'})
                changed = True
            return result
        with patch.object(gateway, '_request', side_effect=request):
            result = gateway._profile_metadata(BASE, '', '', 'axx_plan', {7}, .5)
        self.assertTrue(result['gateway_profile_verified'])
        self.assertEqual(result['gateway_member_ids'], [7])
        self.assertEqual(sum(path == '/api/settings/version' for path, _, _ in self.calls), 2)
        self.assertEqual(sum(path == '/api/profiles/4/models' for path, _, _ in self.calls), 2)

    def test_stable_incomplete_map_is_rejected_without_retry(self):
        self.group_extra_ids = [999]
        with patch.object(gateway, '_request', side_effect=self.request):
            with self.assertRaisesRegex(ValueError, 'mapa completo'):
                gateway._profile_metadata(BASE, '', '', 'axx_plan', {7}, .5)
        self.assertEqual(sum(path == '/api/settings/version' for path, _, _ in self.calls), 1)

    def test_catalog_retry_rechecks_free_members_and_rejects_new_unapproved_member(self):
        changed = False
        def request(base, path, *args, **kwargs):
            nonlocal changed
            result = self.request(base, path, *args, **kwargs)
            if path == '/api/models' and not changed:
                self.models.append({**self.models[0], 'id': 8, 'modelId': 'other', 'canonical': 'unrelated'})
                self.members[4].append({'model_db_id': 8, 'enabled': True})
                changed = True
            return result
        with patch.object(gateway, '_request', side_effect=request):
            with self.assertRaisesRegex(ValueError, 'gratuidad confirmada'):
                gateway._profile_metadata(BASE, '', '', 'axx_plan', {7}, .5)
        self.assertEqual(sum(path == '/api/profiles/4/models' for path, _, _ in self.calls), 2)

    def test_continuously_changing_catalog_stops_after_one_retry(self):
        def request(base, path, *args, **kwargs):
            result = self.request(base, path, *args, **kwargs)
            if path == '/api/models':
                self.models.append({**self.models[0], 'id': len(self.models) + 8, 'canonical': 'unrelated'})
            return result
        with patch.object(gateway, '_request', side_effect=request):
            with self.assertRaisesRegex(ValueError, 'cambió durante'):
                gateway._profile_metadata(BASE, '', '', 'axx_plan', {7}, .5)
        self.assertEqual(sum(path == '/api/settings/version' for path, _, _ in self.calls), 2)

    def test_external_profile_ownership_persists_and_does_not_overwrite_existing(self):
        body = {'base_url': BASE, 'dashboard_token': 'dashboard-secret', 'create': True, 'gateway_free_model_ids': [7]}
        with patch.object(gateway, '_request', side_effect=self.request):
            result = self.service.profiles(body)
            self.assertEqual(len(result['profiles']), 7)
            self.assertFalse(any(p == '/api/profiles/4/reorder' for p, _, _ in self.calls))
            self.service.close()
            self.service = gateway.FreeLLMAPIService(self.root)
            self.calls.clear()
            result = self.service.profiles(body)
        self.assertEqual(len(self.profiles), 7)
        self.assertEqual(sum(p.endswith('/reorder') for p, _, _ in self.calls), 6)
        writing = next(p for p in result['profiles'] if p['task'] == 'writing')
        self.assertEqual(writing['provider_fields']['tasks'], ['writing', 'translation'])

    def test_profile_catalog_marks_group_readiness_without_claiming_free_or_member_readiness(self):
        body = {'base_url': BASE, 'dashboard_token': 'dashboard-secret'}
        with patch.object(gateway, '_request', side_effect=self.request):
            ready = self.service.profiles(body)['models'][0]
            self.ready['execution_status'] = 'exhausted'
            exhausted = self.service.profiles(body)['models'][0]
        self.assertTrue(ready['group_ready'])
        self.assertEqual(ready['canonical_id'], 'fixture')
        self.assertEqual(ready['group_member_ids'], [7])
        self.assertFalse(exhausted['group_ready'])
        self.assertNotIn('ready', ready)
        self.assertNotIn('free_confirmed', ready)

    def test_evaluation_isolates_one_group_and_never_rewrites_existing_profile(self):
        self.models.append({**self.models[0], 'id': 8, 'canonical': 'other', 'modelId': 'other'})
        self.members[4].append({'model_db_id': 8, 'enabled': True})
        provider = {**self.provider(), 'gateway_free_model_ids': [7, 8]}
        before = copy.deepcopy(self.members[4])
        with patch.object(gateway, '_request', side_effect=self.request), patch.dict(os.environ, {'TEST_GATEWAY_SESSION': 'dashboard-secret'}):
            evaluation = gateway.evaluation_provider(provider, [7], 'plan')
            self.assertTrue(evaluation['model'].startswith('auto:axx_e_l_'))
            self.assertEqual(evaluation['gateway_free_model_ids'], [7])
            self.assertEqual(gateway.verify_provider(evaluation)['gateway_member_ids'], [7])
            self.calls.clear()
            gateway.evaluation_provider(provider, [7], 'plan')
            self.assertFalse(any(p.endswith('/reorder') for p, _, _ in self.calls))
            self.members[evaluation['gateway_profile_id']].append({'model_db_id': 8, 'enabled': True})
            self.calls.clear()
            with self.assertRaises(ValueError): gateway.evaluation_provider(provider, [7], 'plan')
            self.assertFalse(any(p.endswith('/reorder') for p, _, _ in self.calls))
            with self.assertRaises(ValueError): gateway.evaluation_provider(provider, [7, 8], 'plan')
            with self.assertRaises(ValueError): gateway.evaluation_provider(provider, [999], 'plan')
        self.assertEqual(self.members[4], before)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_dashboard_secret_persisted_and_reused_by_endpoint_not_profile_name(self):
        with patch.object(gateway, '_request', side_effect=self.request):
            env = gateway.configure_gateway_credentials({'base_url': BASE, 'dashboard_token': 'dashboard-secret'}, self.root / 'router.json', 'plan')
            reused = gateway.configure_gateway_credentials({'base_url': BASE}, self.root / 'router.json', 'chat')
        try:
            self.assertEqual(env, reused)
            data = (self.root / 'credentials' / (env + '.bin')).read_bytes()
            self.assertNotIn(b'dashboard-secret', data)
        finally:
            os.environ.pop(env, None)

    def test_external_close_never_terminates_an_unowned_process(self):
        with patch.object(gateway, 'terminate_process_tree') as terminate:
            self.service.state['base_url'] = BASE
            self.service.close()
            terminate.assert_not_called()

    def test_explicit_import_only_confirmed_free_selected_model_no_inference(self):
        source = {'name': 'selected', 'kind': 'custom', 'base_url': 'https://fixture.example/v1', 'model': 'fixture',
                  'enabled': True, 'free_confirmed': True, 'billing_allowed': False, 'cost_evidence': 'free_tier',
                  'context_window': 8192, 'api_key_env': 'TEST_SOURCE_KEY', 'capabilities': ['text']}
        body = {'source_name': 'selected', 'base_url': BASE, 'dashboard_token': 'dashboard-secret'}
        with patch.object(gateway, '_request', side_effect=self.request), patch.dict(os.environ, {'TEST_SOURCE_KEY': 'upstream-secret'}):
            result = self.service.import_provider(body, {'providers': [source]})
            self.assertEqual(result['model_ids'], [7])
            self.assertNotIn('secret', json.dumps(result))
            self.assertNotIn('maskedKey', result)
            self.assertFalse(any('completions' in p or 'probe' in p for p, _, _ in self.calls))
            source['billing_allowed'] = True
            self.calls.clear()
            with self.assertRaises(ValueError): self.service.import_provider(body, {'providers': [source]})
            self.assertEqual(self.calls, [])

    def test_managed_blank_ui_credentials_are_filled_server_side(self):
        class Running:
            def poll(self): return None
        self.service.process = Running()
        self.service.state['base_url'] = BASE
        self.service.api_key, self.service.dashboard = 'api-secret', 'dashboard-secret'
        try:
            result = self.service._body({'base_url': BASE, 'api_key': '', 'dashboard_token': ''})
            self.assertEqual(result['api_key'], 'api-secret')
            self.assertEqual(result['dashboard_token'], 'dashboard-secret')
        finally:
            self.service.process = None

    def test_keyless_catalog_excludes_paid_and_keeps_anonymous_ovh_pricing_separate(self):
        free = {'id': 'model:free', 'isFree': True, 'pricing': {'prompt': '0', 'completion': '0'},
                'architecture': {'output_modalities': ['text']}, 'context_length': 4096}
        paid = {**free, 'id': 'paid:free', 'pricing': {'prompt': '.01', 'completion': '0'}}
        self.assertEqual([m['id'] for m in gateway._anonymous_models('kilo', {'data': [free, paid]})], ['model:free'])
        ovh = {**paid, 'id': 'Mistral-Small-fixture', 'max_completion_tokens': 1024}
        self.assertEqual(gateway._anonymous_models('ovh', {'data': [ovh]}), [ovh])

    def test_keyless_bootstrap_stages_verified_routes_reuses_evidence_and_blocks_personal_accounts(self):
        self.models[0].update(platform='kilo', modelId='fixture:free')
        self.service.state['base_url'] = BASE
        self.service.api_key, self.service.dashboard = 'api-secret', 'dashboard-secret'
        catalog = {'data': [{'id': 'fixture:free', 'isFree': True, 'pricing': {'prompt': '0', 'completion': '0'},
                              'architecture': {'output_modalities': ['text']}, 'context_length': 8192}]}
        def anonymous(platform, body=None, timeout=25):
            if body is not None:
                return {'model': 'fixture:free', 'choices': [{'message': {'content': 'OK'}}]}
            return catalog if platform == 'kilo' else {'data': []}
        with patch.object(self.service, 'provision'), patch.object(self.service, 'start'), \
                patch.object(gateway, '_request', side_effect=self.request), \
                patch.object(gateway, '_anonymous_request', side_effect=anonymous) as public, \
                patch.object(gateway, '_dpapi_encrypt', side_effect=lambda raw: raw), \
                patch.object(gateway, 'configure_gateway_credentials', return_value='TEST_GATEWAY_SESSION'), \
                patch.dict(os.environ, {'TEST_GATEWAY_SESSION': 'dashboard-secret'}):
            result = self.service.bootstrap_keyless()
            self.assertEqual(len(result['providers']), 1)
            provider = result['providers'][0]
            self.assertTrue(provider['candidate_only'])
            self.assertFalse(provider['allow_sensitive'])
            self.assertEqual(provider['gateway_attempt_limit'], 1)
            self.assertEqual(provider['daily_attempt_limit'], 200)
            public.reset_mock()
            self.assertTrue(self.service.bootstrap_keyless()['reused'])
            public.assert_not_called()
            self.keys.append({'platform': 'kilo', 'keyless': False, 'enabled': True})
            with self.assertRaises(ValueError): gateway.verify_provider(provider)
        self.service.api_key = self.service.dashboard = ''

    def test_cancel_before_bootstrap_never_provisions_or_restarts(self):
        self.service.cancel_bootstrap()
        with patch.object(self.service, 'provision') as provision, patch.object(self.service, 'start') as start:
            with self.assertRaises(ValueError): self.service.bootstrap_keyless()
        provision.assert_not_called()
        start.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows managed startup')
    def test_managed_cold_start_authenticates_after_twenty_seconds_and_stops_at_forty(self):
        source = self.root / 'owned-node'
        entry = source / 'server/dist/index.js'
        entry.parent.mkdir(parents=True)
        entry.write_text('// Never executed: process creation is mocked.')
        node = source / 'node.exe'
        node.touch()
        marker = self.root / 'managed-install.json'
        marker.write_text(json.dumps({'commit': gateway.COMMIT, 'source_dir': str(source),
                                      'node_executable': str(node)}))

        class Running:
            stopped = False
            def poll(self): return 0 if self.stopped else None
            def wait(self, timeout=None): return self.poll()

        for available_after in (25, None):
            with self.subTest(available_after=available_after):
                clock = [0.0]
                process = Running()
                service = gateway.FreeLLMAPIService(self.root / ('late' if available_after else 'expired'))
                def request(base, path, key='', body=None, method=None, timeout=5):
                    if path == '/api/auth/login':
                        if available_after is None or clock[0] < available_after:
                            raise ValueError('Owned gateway is not ready')
                        return {'token': 'dashboard-secret'}
                    if path == '/api/settings/api-key':
                        self.assertEqual(key, 'dashboard-secret')
                        return {'apiKey': 'api-secret'}
                    return self.request(base, path, key, body, method, timeout)
                with patch.object(gateway, 'installation_path', return_value=marker), \
                        patch.object(gateway, 'spawn_managed_process', return_value=(process, None)) as spawn, \
                        patch.object(gateway, 'terminate_process_tree', side_effect=lambda p, _: setattr(p, 'stopped', True)), \
                        patch.object(gateway, '_request', side_effect=request), \
                        patch.object(gateway, 'configure_gateway_credentials') as persist, \
                        patch.object(gateway.time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(gateway.time, 'sleep', side_effect=lambda delay: clock.__setitem__(0, clock[0]+delay)):
                    try:
                        if available_after:
                            result = service.start()
                            self.assertTrue(result['connected'])
                            self.assertGreater(clock[0], 20)
                            self.assertLess(clock[0], 40)
                            self.assertEqual((service.dashboard, service.api_key), ('dashboard-secret', 'api-secret'))
                            persist.assert_called_once()
                        else:
                            with self.assertRaisesRegex(ValueError, 'cuarenta segundos'):
                                service.start()
                            self.assertGreaterEqual(clock[0], 40)
                            self.assertLess(clock[0], 40.21)
                            self.assertTrue(process.stopped)
                            self.assertIsNone(service.process)
                            self.assertEqual((service.dashboard, service.api_key), ('', ''))
                            persist.assert_not_called()
                        spawn.assert_called_once()
                    finally:
                        service.close()


@unittest.skipUnless(os.name == 'nt' and gateway.installation_path().is_file(), 'Optional installed Windows gateway smoke')
class NativeGatewayTests(unittest.TestCase):
    def test_real_managed_gateway_profile_creation_restart_and_fixed_port(self):
        class Fixture(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def respond(self, value):
                raw = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_GET(self):
                self.respond({'object': 'list', 'data': [{'id': 'axx-integration-fixture', 'object': 'model'}]})
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.respond({'id': 'fixture-response', 'object': 'chat.completion', 'model': 'axx-integration-fixture',
                              'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'fixture-ok'}}],
                              'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream.shutdown)
        install = json.loads(gateway.installation_path().read_text(encoding='utf-8-sig'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'freellmapi-install.json'
            marker.write_text(json.dumps(install))
            with patch.object(gateway, 'installation_path', return_value=marker):
                service = gateway.FreeLLMAPIService(root / 'state')
                try:
                    first = service.start()
                    self.assertTrue(first['connected'])
                    self.assertEqual(first['ownership'], 'managed')
                    self.assertEqual(first['ready_count'], 0)
                    other = gateway.FreeLLMAPIService(root / 'state')
                    try:
                        with self.assertRaisesRegex(ValueError, 'Otra instancia'):
                            other.start()
                    finally:
                        other.close()
                    self.assertTrue(service.status()['connected'])
                    profiles = service.profiles({'create': True, 'gateway_free_model_ids': []})
                    self.assertEqual(len(profiles['profiles']), 7)
                    self.assertTrue(all(p['exists'] and not p['verified'] for p in profiles['profiles']))
                    source = {'name': 'local fixture', 'kind': 'custom', 'base_url': f'http://127.0.0.1:{upstream.server_port}/v1',
                              'model': 'axx-integration-fixture', 'context_window': 4096, 'capabilities': ['text'],
                              'enabled': True, 'auth_optional': True, 'route_kind': 'direct', 'free_confirmed': True,
                              'billing_allowed': False, 'cost_evidence': 'direct_local'}
                    imported = service.import_provider({'source_name': 'local fixture'}, {'providers': [source]})
                    profiles = service.profiles({'create': True, 'gateway_free_model_ids': imported['model_ids']})
                    ready_models = [m for m in profiles['models'] if m['group_ready']]
                    self.assertEqual([m['id'] for m in ready_models], imported['model_ids'])
                    plan = next(p for p in profiles['profiles'] if p['task'] == 'plan')
                    self.assertTrue(plan['verified'], (plan, service.discover({})))
                    answer = gateway._request(service.state['base_url'], '/v1/chat/completions', service.api_key,
                                              {'model': 'auto:axx_plan', 'messages': [{'role': 'user', 'content': 'fixture request'}],
                                               'max_tokens': 16}, timeout=10)
                    self.assertEqual(answer['choices'][0]['message']['content'], 'fixture-ok')
                    second_source = {**source, 'name': 'second local fixture', 'model': 'second-fixture'}
                    second_import = service.import_provider({'source_name': second_source['name']}, {'providers': [second_source]})
                    both_ids = imported['model_ids'] + second_import['model_ids']
                    mixed = service.profiles({'create': True, 'gateway_free_model_ids': both_ids})
                    normal = next(p for p in mixed['profiles'] if p['task'] == 'plan')['provider_fields']
                    self.assertEqual(set(normal['gateway_member_ids']), set(both_ids))
                    provider = {**normal, 'base_url': service.state['base_url'], 'gateway_free_model_ids': both_ids,
                                'api_key_env': 'TEST_EVAL_API', 'gateway_dashboard_env': 'TEST_EVAL_DASHBOARD'}
                    with patch.dict(os.environ, {'TEST_EVAL_API': service.api_key, 'TEST_EVAL_DASHBOARD': service.dashboard}):
                        isolated = gateway.evaluation_provider(provider, imported['model_ids'], 'plan')
                        self.assertEqual(gateway.verify_provider(isolated)['gateway_member_ids'], imported['model_ids'])
                        answer = gateway._request(service.state['base_url'], '/v1/chat/completions', service.api_key,
                                                  {'model': isolated['model'], 'messages': [{'role': 'user', 'content': 'fixture evaluation'}],
                                                   'max_tokens': 16}, timeout=10)
                        self.assertEqual(answer['choices'][0]['message']['content'], 'fixture-ok')
                    original = gateway._request(service.state['base_url'], f"/api/profiles/{normal['gateway_profile_id']}/models", service.dashboard)
                    self.assertEqual({m['model_db_id'] for m in original if m['enabled']}, set(both_ids))
                    port = service.state['port']
                    service.close()
                    service = gateway.FreeLLMAPIService(root / 'state')
                    second = service.reconnect()
                    self.assertTrue(second['connected'])
                    self.assertEqual(service.state['port'], port)
                    service.stop()
                    self.assertFalse(service.state['enabled'])
                finally:
                    service.close()


if __name__ == '__main__':
    unittest.main()
