import http.server
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from backend import model_ranking as mr

VERIFIED = {'vision': 'verificado', 'json_estricto': 'verificado', 'scene_3d': 'verificado', 'diagram_2d': 'verificado', 'explicacion': 'verificado'}
UNTESTED = {c: 'sin_datos' for c in mr.WEIGHTS}


def row(name, model, aptitude):
    return {'name': name, 'model': model, 'protocol': 'openai', 'spatial_3d': aptitude.get('scene_3d') == 'verificado', 'aptitude': aptitude, 'efforts': []}


class ScoringTests(unittest.TestCase):
    def test_a_measured_3d_result_outranks_a_better_reputed_model_nobody_tested(self):
        ranking = mr.build([row('axx1', 'claude-haiku-5-5', VERIFIED), row('big', 'claude-opus-5-5', UNTESTED)])
        order = [e['model'] for e in ranking['entries']]
        self.assertLess(order.index('claude-haiku-5-5'), order.index('claude-opus-5-5'))
        by = {e['model']: e for e in ranking['entries']}
        self.assertEqual(by['claude-haiku-5-5']['status'], 'apto_3d')
        self.assertIn('Medido en este equipo', by['claude-haiku-5-5']['basis'])
        self.assertLessEqual(by['claude-opus-5-5']['score'], 50)  # the prior alone can never reach a verified score
        self.assertIn('Orientativo', by['claude-opus-5-5']['basis'])

    def test_a_failed_aptitude_test_is_shown_as_2d_only_and_ranks_below_a_verified_one(self):
        failed = dict(UNTESTED, vision='verificado', scene_3d='no_soportado', diagram_2d='verificado')
        by = {e['model']: e for e in mr.build([row('a', 'gemma4:31b', failed), row('b', 'claude-sonnet-5-5', VERIFIED)])['entries']}
        self.assertEqual(by['gemma4:31b']['status'], 'solo_2d')
        self.assertEqual(by['gemma4:31b']['tasks']['no_apto'], ['3D'])
        self.assertLess(by['gemma4:31b']['score'], by['claude-sonnet-5-5']['score'])

    def test_recommendations_fill_the_list_only_with_models_that_are_not_already_connected(self):
        ranking = mr.build([row('axx1', 'claude-sonnet-5-5', VERIFIED)])
        recommended = [e for e in ranking['entries'] if e['status'] == 'recomendado']
        self.assertNotIn('claude-sonnet-5-5', [e['model'] for e in recommended])
        self.assertTrue({'claude-opus-5-5', 'gpt-6.1-sol'} <= {e['model'] for e in recommended})
        self.assertTrue(all(e['action']['type'] == 'connect' and e['action']['text'] for e in recommended))
        self.assertEqual([e['rank'] for e in ranking['entries']], list(range(1, len(ranking['entries']) + 1)))
        self.assertEqual(ranking['reference_date'], mr.REFERENCE_DATE)

    def test_the_codex_subscription_is_labelled_for_people_and_selectable_by_its_real_key(self):
        entry = next(e for e in mr.build([row('@codex', 'gpt-6.1-sol', dict(UNTESTED, vision='verificado'))])['entries'] if e['status'] != 'recomendado')
        self.assertEqual((entry['provider'], entry['connection'], entry['action']), ('ChatGPT/Codex', '@codex', {'type': 'select', 'key': '@codex::gpt-6.1-sol'}))


class SourcesTests(unittest.TestCase):
    def test_installed_ollama_vision_models_are_offered_but_never_connected_and_text_only_ones_are_left_out(self):
        ollama = {'available': True, 'base_url': 'http://127.0.0.1:11434', 'message': '', 'models': [
            {'name': 'llama3.2-vision:11b', 'vision': True, 'configured_as': None}, {'name': 'qwen2.5:3b', 'vision': False, 'configured_as': None},
            {'name': 'llava:13b', 'vision': True, 'configured_as': 'ollama-local'}]}
        ranking = mr.build([row('ollama-local', 'llava:13b', dict(UNTESTED, vision='declarado'))], ollama=ollama)
        models = [e['model'] for e in ranking['entries']]
        self.assertEqual(models.count('llava:13b'), 1)  # already connected: not duplicated
        self.assertNotIn('qwen2.5:3b', models)
        installed = next(e for e in ranking['entries'] if e['model'] == 'llama3.2-vision:11b' and e['status'] == 'instalado')
        self.assertIn('no lo conecta solo', installed['action']['text'])
        self.assertEqual(installed['tasks']['declarado'], ['visión'])  # a declaration, not a measurement
        self.assertNotIn('llama3.2-vision:11b', [e['model'] for e in ranking['entries'] if e['status'] == 'recomendado'])

    def test_an_unreachable_ollama_is_reported_honestly(self):
        ranking = mr.build([], ollama={'available': False, 'models': [], 'message': 'Ollama no disponible en http://127.0.0.1:11434 (sin conexión).'})
        source = next(s for s in ranking['sources'] if s['name'] == 'Ollama local')
        self.assertEqual(source['state'], 'unavailable')
        self.assertIn('no disponible', source['message'])


class GatherTests(unittest.TestCase):
    config = {'providers': [
        {'name': 'axx1', 'kind': 'anthropic', 'base_url': 'https://api.anthropic.com/v1', 'protocol': 'anthropic', 'enabled': True},
        {'name': 'axxx3', 'kind': 'ollama_cloud', 'base_url': 'https://ollama.com/v1', 'protocol': 'openai', 'enabled': True},
        {'name': 'gw', 'kind': 'freellmapi', 'base_url': 'http://127.0.0.1:9/v1', 'protocol': 'openai', 'enabled': True},
        {'name': 'off', 'kind': 'openai', 'base_url': 'https://api.openai.com/v1', 'protocol': 'openai', 'enabled': False},
        {'name': 'legacy', 'kind': None, 'base_url': 'http://x/v1', 'enabled': True}]}
    capabilities = {'vision': [row('axx1', 'claude-sonnet-5-5', VERIFIED)], 'codex_vision': []}

    def test_without_refresh_nothing_is_asked_over_the_network(self):
        calls = []
        result = mr.gather(self.capabilities, self.config, refresh=False, discover_fn=lambda *a: calls.append(a), ollama_fn=lambda *a: calls.append(a), ollama_url='x')
        self.assertEqual(calls, [])
        self.assertFalse(result['refreshed'])

    def test_refresh_reads_only_catalogs_of_saved_enabled_connections_and_one_failure_does_not_hide_the_others(self):
        asked = []

        def discover(body, config):
            asked.append(body['name'])
            if body['name'] == 'axx1':
                return {'models': ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-3-old', 'text-embedding-x']}
            raise ValueError('No se pudo consultar el catálogo (HTTP 401). Revisa dirección y clave.')
        result = mr.gather(self.capabilities, self.config, refresh=True, discover_fn=discover,
                           ollama_fn=lambda url: {'available': False, 'models': [], 'message': 'Ollama no disponible.'}, ollama_url='http://127.0.0.1:11434')
        self.assertEqual(asked, ['axx1', 'axxx3'])  # no gateway, no disabled connection, no connection without a kind
        self.assertTrue(result['refreshed'])
        account = [e for e in result['entries'] if e['status'] == 'en_cuenta']
        self.assertEqual([e['model'] for e in account], ['claude-opus-5-5'])  # sonnet is already connected; old/irrelevant models are not listed
        self.assertEqual(len([e for e in result['entries'] if e['model'] == 'claude-opus-5-5']), 1)  # the account entry replaces the generic recommendation
        names = {s['name']: s for s in result['sources']}
        self.assertEqual(names['Catálogo de axxx3']['state'], 'unavailable')
        self.assertIn('401', names['Catálogo de axxx3']['message'])
        self.assertEqual(names['Catálogo de axx1']['state'], 'ok')
        self.assertNotIn('text-embedding-x', json.dumps(result))  # models without any relevance for this function are not listed
        self.assertNotIn('sk-', json.dumps(result))

    def test_a_catalog_model_is_marked_as_in_the_account_and_needs_the_owner_to_connect_it(self):
        discover = lambda body, config: {'models': ['claude-haiku-5-5']}
        result = mr.gather(self.capabilities, self.config, refresh=True, discover_fn=discover, ollama_fn=lambda url: {'available': False, 'models': [], 'message': ''}, ollama_url='x')
        haiku = next(e for e in result['entries'] if e['model'] == 'claude-haiku-5-5')
        self.assertEqual(haiku['status'], 'en_cuenta')
        self.assertIn('AXX no lo activa solo', haiku['action']['text'])


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
            with opener.open(request, timeout=15) as response:
                return json.load(response)
        return get

    def test_the_route_ranks_without_network_by_default_and_adds_local_ollama_models_on_refresh(self):
        simulated = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Local)
        threading.Thread(target=simulated.serve_forever, daemon=True).start()
        self.addCleanup(simulated.shutdown); self.addCleanup(simulated.server_close)
        get = self.start(f'http://127.0.0.1:{simulated.server_port}')
        quick = get('/axx-api/model-ranking')
        self.assertFalse(quick['refreshed'])
        self.assertTrue(quick['entries'])
        self.assertNotIn('llama3.2-vision:11b', [e['model'] for e in quick['entries'] if e['status'] == 'instalado'])
        fresh = get('/axx-api/model-ranking?refresh=1')
        self.assertTrue(fresh['refreshed'])
        installed = [e for e in fresh['entries'] if e['status'] == 'instalado']
        self.assertEqual([e['model'] for e in installed], ['llama3.2-vision:11b'])
        self.assertEqual(next(s for s in fresh['sources'] if s['name'] == 'Ollama local')['state'], 'ok')

    def test_unknown_or_malformed_queries_are_rejected(self):
        get = self.start('http://127.0.0.1:9')
        for query in ('?refresh=2', '?x=1', '?refresh=1&refresh=1'):
            with self.subTest(query=query), self.assertRaises(urllib.error.HTTPError) as caught:
                get('/axx-api/model-ranking' + query)
            self.assertEqual(caught.exception.code, 400)


if __name__ == '__main__':
    unittest.main()
