import http.server
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from backend import market_catalog as mc
from backend import model_ranking as mr

NOW = 1_800_000_000.0
DAY = 86400
VERIFIED = {c: 'verificado' for c in ('vision', 'json_estricto', 'scene_3d', 'diagram_2d', 'explicacion')}
UNTESTED = {c: 'sin_datos' for c in ('vision', 'json_estricto', 'scene_3d', 'diagram_2d', 'explicacion')}


def or_item(model_id, *, age_days=30, out_usd=0.00001, in_usd=0.000002, modalities=('text', 'image'), supported=('structured_outputs', 'response_format', 'reasoning'),
            max_out=128000, context=1_000_000, reasoning=True, expiration=None):
    return {'id': model_id, 'name': model_id, 'created': NOW - age_days * DAY, 'context_length': context, 'expiration_date': expiration,
            'architecture': {'input_modalities': list(modalities)}, 'supported_parameters': list(supported),
            'top_provider': {'max_completion_tokens': max_out}, 'pricing': {'prompt': str(in_usd), 'completion': str(out_usd)},
            'reasoning': {'mandatory': False} if reasoning else None}


OPENROUTER = {'data': [
    or_item('anthropic/claude-sonnet-5.5'), or_item('anthropic/claude-opus-5.5', out_usd=0.00002), or_item('anthropic/claude-opus-5.5:batch'),
    or_item('qwen/qwen3.8-max-prime', out_usd=0.000012), or_item('meta/old-vision', age_days=900, out_usd=0.0000005, supported=(), max_out=2048, context=32000, reasoning=False),
    or_item('acme/text-only', modalities=('text',)), or_item('acme/going-away', expiration='2026-12-01'), or_item('~openai/alias'),
    or_item('nvidia/free-vl:free', out_usd=0, in_usd=0), {'id': 5}, 'junk']}
OLLAMA = {'models': [
    {'name': 'gemma4:31b', 'capabilities': ['completion', 'vision', 'tools'], 'details': {'parameter_size': '32682372656'}, 'modified_at': '2026-10-01T00:00:00Z'},
    {'name': 'kimi-k3.1-pro', 'capabilities': ['vision', 'thinking'], 'details': {'parameter_size': '2812000000000'}, 'modified_at': '2026-11-04T08:00:00-08:00'},
    {'name': 'gpt-oss:120b', 'capabilities': ['completion', 'tools'], 'details': {'parameter_size': '120B'}, 'modified_at': '2025-08-05T00:00:00Z'}, 'junk']}


def row(name, model, aptitude):
    return {'name': name, 'model': model, 'protocol': 'openai', 'spatial_3d': aptitude.get('scene_3d') == 'verificado', 'aptitude': aptitude, 'efforts': []}


class MarketCatalogTests(unittest.TestCase):
    def test_only_current_vision_models_are_kept_and_duplicates_aliases_and_retiring_ones_are_dropped(self):
        ids = [m['id'] for m in mc.openrouter_models(OPENROUTER, NOW)]
        self.assertIn('anthropic/claude-sonnet-5.5', ids)
        for dropped in ('anthropic/claude-opus-5.5:batch', 'acme/text-only', 'acme/going-away', '~openai/alias'):
            self.assertNotIn(dropped, ids)
        self.assertEqual(mc.openrouter_models({}, NOW), [])
        self.assertEqual(mc.openrouter_models('junk', NOW), [])

    def test_the_score_is_computed_from_published_fields_and_explains_itself(self):
        by = {m['id']: m for m in mc.openrouter_models(OPENROUTER, NOW)}
        strong, weak = by['anthropic/claude-opus-5.5'], by['meta/old-vision']
        self.assertGreater(strong['score'], weak['score'])
        self.assertTrue(any('JSON estricta' in r for r in strong['reasons']))
        self.assertTrue(any('lanzado hace 30 días' in r for r in strong['reasons']))
        self.assertFalse(any('JSON estricta' in r for r in weak['reasons']))  # that model does not publish structured outputs
        self.assertLessEqual(strong['score'], 100)
        self.assertTrue(by['nvidia/free-vl:free']['free'])
        newer, older = mc.market_score({'created': NOW - 30 * DAY}, NOW), mc.market_score({'created': NOW - 800 * DAY}, NOW)
        self.assertGreater(newer['score'], older['score'])

    def test_the_score_never_depends_on_the_name(self):
        base = or_item('a/model')
        renamed = or_item('anthropic/claude-sonnet-5.5')
        self.assertEqual(mc.openrouter_models({'data': [base]}, NOW)[0]['score'], mc.openrouter_models({'data': [renamed]}, NOW)[0]['score'])

    def test_ollama_cloud_keeps_vision_models_only_and_uses_their_declared_size(self):
        found = {m['id']: m for m in mc.ollama_cloud_models(OLLAMA, NOW)}
        self.assertEqual(set(found), {'gemma4:31b', 'kimi-k3.1-pro'})
        self.assertGreater(found['kimi-k3.1-pro']['parameters_b'], found['gemma4:31b']['parameters_b'])
        self.assertTrue(found['kimi-k3.1-pro']['reasoning'])
        self.assertTrue(any('parámetros' in r for r in found['gemma4:31b']['reasons']))

    def test_one_failing_catalogue_never_hides_the_other(self):
        def fetch(url):
            if url == mc.OPENROUTER_URL:
                raise urllib.error.URLError('sin red')
            return OLLAMA
        market = mc.load_market(now=NOW, fetch=fetch)
        states = {s['name']: s['state'] for s in market['sources']}
        self.assertEqual(states, {'OpenRouter': 'unavailable', 'Ollama Cloud': 'ok'})
        self.assertEqual({m['source'] for m in market['models']}, {'ollama_cloud'})


class RankingTests(unittest.TestCase):
    def market(self):
        return {'models': mc.openrouter_models(OPENROUTER, NOW) + mc.ollama_cloud_models(OLLAMA, NOW), 'sources': [{'name': 'OpenRouter', 'state': 'ok', 'message': 'x'}], 'at': int(NOW)}

    def build(self, rows=(), **kw):
        return mr.build(list(rows), market=kw.pop('market', self.market()), clock=lambda: NOW, **kw)

    def test_the_ranking_is_made_of_the_models_that_exist_today_not_only_the_ones_you_can_use(self):
        result = self.build()
        models = [e['model'] for e in result['entries']]
        self.assertIn('anthropic/claude-opus-5.5', models)
        self.assertTrue(all(e['status'] == 'configurable' for e in result['entries']))
        self.assertEqual([e['rank'] for e in result['entries']], list(range(1, len(result['entries']) + 1)))
        self.assertEqual([e['score'] for e in result['entries']], sorted((e['score'] for e in result['entries']), reverse=True))

    def test_a_connected_model_is_merged_with_its_market_entry_and_measured_evidence_moves_it(self):
        rows = [row('axx1', 'claude-sonnet-5-5', VERIFIED), row('axxx3', 'gemma4:31b', dict(UNTESTED, scene_3d='no_soportado', vision='verificado'))]
        result = self.build(rows, connections=[{'name': 'axx1', 'kind': 'anthropic'}, {'name': 'axxx3', 'kind': 'ollama_cloud'}])
        by = {e['model']: e for e in result['entries']}
        sonnet, gemma = by['claude-sonnet-5-5'], by['gemma4:31b']
        self.assertEqual((sonnet['status'], sonnet['kind']), ('apto_3d', 'anthropic'))
        self.assertEqual(sonnet['action'], {'type': 'select', 'key': 'axx1::claude-sonnet-5-5'})
        self.assertIsNotNone(sonnet['market']['market_rank'])  # "Mercado #n de N" from the public data
        self.assertTrue(any('prueba de 3D superada' in r for r in sonnet['reasons']))
        self.assertEqual(gemma['status'], 'solo_2d')
        self.assertTrue(any('falló la prueba de 3D' in r for r in gemma['reasons']))
        self.assertEqual([e['model'] for e in result['entries']].count('claude-sonnet-5-5'), 1)  # not duplicated as "configurable"
        self.assertNotIn('anthropic/claude-sonnet-5.5', [e['model'] for e in result['entries']])

    def test_a_connected_model_the_catalogues_do_not_list_starts_neutral_and_says_so(self):
        entry = next(e for e in self.build([row('@codex', 'gpt-6.1-sol', VERIFIED)])['entries'] if e['model'] == 'gpt-6.1-sol')
        self.assertEqual((entry['provider'], entry['status']), ('ChatGPT/Codex', 'apto_3d'))
        self.assertIsNone(entry['market'])
        self.assertTrue(any('sin datos públicos' in r for r in entry['reasons']))

    def test_every_unconnected_model_offers_prefilled_forms_and_never_a_key(self):
        entries = {e['model']: e for e in self.build(connections=[{'name': 'axx1', 'kind': 'anthropic'}])['entries']}
        opus = entries['anthropic/claude-opus-5.5']
        kinds = [o['kind'] for o in opus['action']['options']]
        self.assertEqual(kinds, ['anthropic', 'openrouter'])  # the company's own API first, one OpenRouter key as the alternative
        native = opus['action']['options'][0]
        self.assertEqual((native['model'], native['vision'], native['has_connection_kind']), ('claude-opus-5-5', True, True))
        self.assertEqual(opus['action']['options'][1]['model'], 'anthropic/claude-opus-5.5')
        qwen = entries['qwen/qwen3.8-max-prime']
        self.assertEqual([o['kind'] for o in qwen['action']['options']], ['openrouter'])  # no native kind: only the aggregator
        cloud = entries['kimi-k3.1-pro']
        self.assertEqual(cloud['action']['options'][0]['kind'], 'ollama_cloud')
        for entry in entries.values():
            for option in entry['action']['options']:
                self.assertFalse({'key', 'api_key', 'token'} & set(option))

    def test_a_model_offered_by_a_catalogue_of_the_account_is_flagged(self):
        result = self.build(discovered=[{'connection': 'axx1', 'ok': True, 'models': ['claude-opus-5-5', 'x']}])
        opus = next(e for e in result['entries'] if e['model'] == 'anthropic/claude-opus-5.5')
        self.assertTrue(opus['in_account'])
        self.assertIn('Tu cuenta ya lo ofrece', opus['action']['note'])

    def test_installed_ollama_vision_models_are_offered_and_text_only_ones_left_out(self):
        ollama = {'available': True, 'base_url': 'http://127.0.0.1:11434', 'message': '', 'models': [
            {'name': 'llava:13b', 'vision': True, 'configured_as': None}, {'name': 'qwen2.5:3b', 'vision': False, 'configured_as': None},
            {'name': 'gemma4:31b', 'vision': True, 'configured_as': 'ollama-local'}]}
        result = self.build([row('ollama-local', 'gemma4:31b', UNTESTED)], ollama=ollama)
        installed = [e for e in result['entries'] if e['status'] == 'instalado']
        self.assertEqual([e['model'] for e in installed], ['llava:13b'])
        self.assertEqual(installed[0]['action']['options'][0]['kind'], 'ollama')
        self.assertNotIn('qwen2.5:3b', [e['model'] for e in result['entries']])

    def test_without_a_market_the_ranking_says_how_to_load_it(self):
        result = mr.build([row('axx1', 'claude-sonnet-5-5', VERIFIED)], market=None, clock=lambda: NOW)
        self.assertEqual(len(result['entries']), 1)
        self.assertTrue(any('Actualizar ranking' in s['message'] for s in result['sources']))

    def test_the_list_is_bounded_and_keeps_every_connected_model(self):
        many = {'models': [{'id': f'x/m{i}', 'model': f'm{i}', 'company': 'x', 'source': 'openrouter', 'score': 50 + (i % 40), 'reasons': [], 'created': NOW} for i in range(200)], 'sources': []}
        result = mr.build([row('a', 'zzz-local', UNTESTED)], market=many, clock=lambda: NOW)
        self.assertLessEqual(len(result['entries']), mr.MAX_ENTRIES)
        self.assertIn('zzz-local', [e['model'] for e in result['entries']])

    def test_names_are_compared_the_way_providers_spell_them(self):
        self.assertEqual(mr.norm('claude-sonnet-5-5'), mr.norm('claude-sonnet-5.5'))
        self.assertEqual(mr.norm('google/gemini-4-argon:free'.split('/')[1]), 'gemini-4-argon')


class GatherTests(unittest.TestCase):
    config = {'providers': [
        {'name': 'axx1', 'kind': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'protocol': 'anthropic', 'enabled': True},
        {'name': 'axxx3', 'kind': 'ollama_cloud', 'base_url': 'https://ollama.com/v1', 'protocol': 'openai', 'enabled': True},
        {'name': 'gw', 'kind': 'freellmapi', 'base_url': 'http://127.0.0.1:9/v1', 'enabled': True},
        {'name': 'off', 'kind': 'openai', 'base_url': 'https://api.openai.com/v1', 'enabled': False}, {'name': 'legacy', 'kind': None, 'base_url': 'x', 'enabled': True}]}
    capabilities = {'vision': [row('axx1', 'claude-sonnet-5-5', VERIFIED)], 'codex_vision': []}

    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.cache = Path(temp.name) / 'market-cache.json'
        self.market_calls = 0

    def market_fn(self):
        self.market_calls += 1
        return {'models': mc.openrouter_models(OPENROUTER, NOW), 'sources': [{'name': 'OpenRouter', 'state': 'ok', 'message': 'ok'}], 'at': int(NOW)}

    def gather(self, refresh, discover=None, market_fn=None):
        return mr.gather(self.capabilities, self.config, refresh=refresh, discover_fn=discover or (lambda body, cfg: {'models': ['claude-opus-5-5']}),
                         ollama_fn=lambda url: {'available': False, 'models': [], 'message': 'Ollama no disponible.', 'base_url': url}, ollama_url='http://127.0.0.1:11434',
                         market_fn=market_fn or self.market_fn, cache_path=self.cache, clock=lambda: NOW)

    def test_without_refresh_nothing_is_downloaded_and_the_last_market_is_reused(self):
        first = self.gather(False)
        self.assertEqual((self.market_calls, first['refreshed']), (0, False))
        self.assertFalse(any(e['status'] == 'configurable' for e in first['entries']))  # nothing cached yet
        self.gather(True)
        self.assertTrue(self.cache.is_file())
        again = self.gather(False)
        self.assertEqual(self.market_calls, 1)
        self.assertTrue(any(e['status'] == 'configurable' for e in again['entries']))

    def test_refresh_reads_only_saved_enabled_connections_and_reports_each_failure_without_hiding_the_rest(self):
        asked = []

        def discover(body, config):
            asked.append(body['name'])
            if body['name'] == 'axxx3':
                raise ValueError('No se pudo consultar el catálogo (HTTP 401).')
            return {'models': ['claude-opus-5-5']}
        result = self.gather(True, discover=discover)
        self.assertEqual(asked, ['axx1', 'axxx3'])
        states = {s['name']: s for s in result['sources']}
        self.assertEqual(states['Catálogo de axx1']['state'], 'ok')
        self.assertEqual(states['Catálogo de axxx3']['state'], 'unavailable')
        self.assertIn('401', states['Catálogo de axxx3']['message'])
        self.assertTrue(result['refreshed'])

    def test_when_the_network_fails_the_cached_market_still_ranks(self):
        self.gather(True)
        down = lambda: {'models': [], 'sources': [{'name': 'OpenRouter', 'state': 'unavailable', 'message': 'sin red'}], 'at': int(NOW)}
        result = self.gather(True, market_fn=down)
        self.assertTrue(any(e['status'] == 'configurable' for e in result['entries']))
        self.assertTrue(any(s['state'] == 'unavailable' and s['name'] == 'OpenRouter' for s in result['sources']))


class _Local(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, payload):
        raw = json.dumps(payload).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        self._send({'models': [{'name': 'llama3.2-vision:11b'}, {'name': 'qwen2.5:3b'}]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self._send({'capabilities': ['completion', 'vision'], 'details': {'family': 'llama', 'parameter_size': '11B'}})


class RankingRouteTests(unittest.TestCase):
    def start(self, base_url):
        from backend.magic_pen import MagicPenService
        from backend.server import AxxBridgeHandler, ThreadedHTTPServer
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        pen = MagicPenService(Path(temp.name)); self.addCleanup(pen.close)

        class Adapter:
            config = {'allow_paid': False, 'providers': [{'name': 'ollama-local', 'kind': 'ollama', 'model': 'qwen2.5:3b', 'protocol': 'openai', 'enabled': True,
                                                          'base_url': base_url + '/v1', 'free_confirmed': True, 'capabilities': ['text']}]}
        handler = type('H', (AxxBridgeHandler,), {'magic_pen': pen, 'adapter': Adapter()})
        server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown); self.addCleanup(server.server_close)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(path):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', headers={'Authorization': 'Bearer ' + server.host_token})
            with opener.open(request, timeout=20) as response:
                return json.load(response)

        def post(path, body):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', data=json.dumps(body).encode(), method='POST',
                                             headers={'Authorization': 'Bearer ' + server.host_token, 'Content-Type': 'application/json'})
            with opener.open(request, timeout=15) as response:
                return json.load(response)
        self.post, self.pen = post, pen
        return get

    def test_the_route_ranks_the_market_after_a_refresh_and_never_touches_the_network_otherwise(self):
        simulated = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Local)
        threading.Thread(target=simulated.serve_forever, daemon=True).start()
        self.addCleanup(simulated.shutdown); self.addCleanup(simulated.server_close)
        get = self.start(f'http://127.0.0.1:{simulated.server_port}')
        calls = []

        def fetch(url):
            calls.append(url)
            return OPENROUTER if url == mc.OPENROUTER_URL else OLLAMA
        with patch.object(mc, 'fetch_json', fetch):
            quick = get('/axx-api/model-ranking')
            self.assertEqual((quick['refreshed'], calls), (False, []))
            fresh = get('/axx-api/model-ranking?refresh=1')
            self.assertEqual(sorted(calls), sorted([mc.OPENROUTER_URL, mc.OLLAMA_CLOUD_URL]))
            self.assertTrue(fresh['refreshed'])
            self.assertTrue(any(e['status'] == 'configurable' for e in fresh['entries']))
            self.assertEqual([e['model'] for e in fresh['entries'] if e['status'] == 'instalado'], ['llama3.2-vision:11b'])
            again = get('/axx-api/model-ranking')
            self.assertEqual(len(calls), 2)  # the second quick read used the cache written by the refresh
            self.assertTrue(any(e['status'] == 'configurable' for e in again['entries']))

    def test_unknown_or_malformed_queries_are_rejected(self):
        get = self.start('http://127.0.0.1:9')
        for query in ('?refresh=2', '?x=1', '?refresh=1&refresh=1'):
            with self.subTest(query=query), self.assertRaises(urllib.error.HTTPError) as caught:
                get('/axx-api/model-ranking' + query)
            self.assertEqual(caught.exception.code, 400)

    def test_the_owner_can_read_change_and_restart_the_budget_and_nothing_else_is_accepted(self):
        self.start('http://127.0.0.1:9')
        self.assertEqual(self.post('/axx-api/pen/budget', {})['limit_usd'], 5.0)
        self.assertEqual(self.post('/axx-api/pen/budget', {'limit_usd': 12})['limit_usd'], 12.0)
        self.pen.budget.record({'name': 'axx1', 'kind': 'anthropic', 'billing_allowed': True}, {'input_tokens': 1000, 'output_tokens': 1000})
        self.assertGreater(self.post('/axx-api/pen/budget', {})['spent_usd'], 0)
        self.assertEqual(self.post('/axx-api/pen/budget', {'reset': True})['spent_usd'], 0)
        for bad in ({'limit_usd': -3}, {'limit_usd': 'mucho'}, {'reset': 'si'}, {'prices': 1}):
            with self.subTest(bad=bad), self.assertRaises(urllib.error.HTTPError) as caught:
                self.post('/axx-api/pen/budget', bad)
            self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
