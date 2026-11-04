"""Capability table, aptitude test verdicts, Ollama detection and honest 3D eligibility."""
import copy
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path

from backend.ollama_models import detect
from backend.provider_capabilities import CapabilityTable
from backend.tests.test_presentation_plan import MagicPenPresentationTests, plan

SEES = 'Se ven una figura roja y un círculo azul en la imagen.'


def piece(ident, label, shape, color, x):
    return {'id': ident, 'label': label, 'shape': shape, 'size': [1, 1, 1], 'position': [x, 0, 0], 'color': color}


def answer(*, scene=True, sees=True):
    p = plan(scene={'fidelity': 'conceptual', 'objects': [piece('o1', 'Rectángulo', 'box', '#d33b36', 0), piece('o2', 'Círculo', 'sphere', '#2878c8', 1.1)]}) if scene else plan()
    p['steps'][0]['body'] = SEES if sees else 'Una escena con dos formas simples sobre fondo claro.'
    p['steps'][1]['body'] = 'El círculo queda a la derecha del rectángulo y no se tocan entre sí.'
    if not sees:  # grey pieces too: nothing in the answer proves the image was looked at
        for item in (p.get('scene') or {}).get('objects', []):
            item['color'] = '#888888'
    return p


class CapabilityTableTests(unittest.TestCase):
    def test_levels_never_overwrite_a_real_result_and_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'caps.json'
            table = CapabilityTable(path)
            self.assertEqual(table.summary('c', 'm'), {k: 'sin_datos' for k in ('vision', 'json_estricto', 'scene_3d', 'diagram_2d', 'explicacion')})
            table.declare('c', 'm', 'vision', 'Declarada en la configuración.')
            self.assertEqual(table.level('c', 'm', 'vision'), 'declarado')
            table.verify('c', 'm', 'vision', True, 'Describió las figuras.')
            table.declare('c', 'm', 'vision', 'otra vez')  # a claim must not downgrade a verified result
            self.assertEqual(table.level('c', 'm', 'vision'), 'verificado')
            table.verify('c', 'm', 'scene_3d', False, 'Sin escena', mode='json_2d')
            self.assertEqual(CapabilityTable(path).summary('c', 'm')['scene_3d'], 'no_soportado')  # persisted
            self.assertEqual(CapabilityTable(path).get('c', 'm')['scene_3d']['mode'], 'json_2d')

    def test_unknown_capabilities_and_bad_keys_are_rejected_and_names_prove_nothing(self):
        table = CapabilityTable()
        for call in (lambda: table.level('c', 'm', 'telepatia'), lambda: table.declare('', 'm', 'vision', 'x'), lambda: table.verify('c', 'x' * 201, 'vision', True, 'x')):
            with self.assertRaises(ValueError): call()
        for model in ('claude-opus-5-5', 'gpt-6.1-sol', 'llava:13b'):  # famous names without a test or a declaration have no data
            self.assertEqual(set(table.summary('c', model).values()), {'sin_datos'})


class AptitudeTests(MagicPenPresentationTests):
    def verify(self, reply, model='visual-model'):
        self.replies.append(json.dumps(reply) if isinstance(reply, dict) else reply)
        return self.service.verify_spatial({'provider': 'fixture', 'model': model, 'effort': 'auto'})

    def test_a_valid_3d_answer_makes_the_model_apt_for_3d_and_stores_every_capability(self):
        result = self.verify(answer())
        self.assertEqual(result['verdict'], 'apto_3d')
        self.assertEqual(result['capabilities'], {k: 'verificado' for k in ('vision', 'json_estricto', 'scene_3d', 'diagram_2d', 'explicacion')})
        self.assertTrue(self.service.capabilities()['vision'][0]['spatial_3d'])
        reduced = self.adapter.calls[-1]['messages'][0]['content']
        from backend.presentation_plan import PLAN_CONTRACT
        self.assertIn('Describe lo que ves en la imagen', reduced)
        self.assertLess(reduced.count('COMPONENTES DEL CATÁLOGO'), 1)  # the reduced contract, not the full one
        self.assertEqual(len(self.adapter.calls), 1)  # one call, never automatic retries

    def test_a_json_answer_without_a_scene_is_apt_for_2d_only_and_3d_is_switched_off_with_the_reason(self):
        result = self.verify(answer(scene=False))
        self.assertEqual(result['verdict'], 'apto_2d')
        self.assertIn('3D', result['reason'])
        row = self.service.capabilities()['vision'][0]
        self.assertFalse(row['spatial_3d'])  # a real test beats the protocol default
        self.assertEqual(row['aptitude']['scene_3d'], 'no_soportado')
        self.assertEqual(row['aptitude']['diagram_2d'], 'verificado')

    def test_plain_prose_is_apt_as_text_and_uses_the_local_diagram_path(self):
        result = self.verify('La figura roja es un rectángulo. El círculo azul está a su derecha. Ambas figuras están separadas y tienen colores distintos.')
        self.assertEqual(result['verdict'], 'apto_2d')
        self.assertTrue(result['text_diagram'])
        self.assertEqual(self.service.caps.level('fixture', 'visual-model', 'json_estricto'), 'no_soportado')

    def test_a_model_that_does_not_describe_the_figures_is_not_apt_and_the_reason_is_shown(self):
        with self.assertRaises(ValueError) as caught:
            self.verify(answer(sees=False))
        self.assertIn('no parece ver la imagen', str(caught.exception))
        self.assertEqual(self.service.caps.level('fixture', 'visual-model', 'vision'), 'no_soportado')
        self.assertEqual(self.service.capabilities()['vision'][0]['aptitude']['vision'], 'no_soportado')

    def test_configured_vision_is_a_declaration_not_a_verification(self):
        self.assertEqual(self.service.capabilities()['vision'][0]['aptitude']['vision'], 'declarado')
        self.assertEqual(self.service.capabilities()['vision'][0]['aptitude']['scene_3d'], 'sin_datos')

    def test_an_openai_compatible_model_that_passes_3d_is_used_like_claude_but_without_a_schema(self):
        local = self.adapter.config['providers'][0]
        local.update(model='llava-local', protocol='openai')
        self.assertFalse(self.service.capabilities()['vision'][0]['spatial_3d'])  # no data: 3D is not assumed for this protocol
        self.assertEqual(self.verify(answer(), model='llava-local')['verdict'], 'apto_3d')
        self.assertNotIn('output_schema', self.adapter.calls[-1]['generation'])  # the route cannot take a JSON schema
        self.assertTrue(self.service.capabilities()['vision'][0]['spatial_3d'])
        self.replies.append(json.dumps(answer()))
        started = self.ask(format='presentation', model='llava-local')
        self.assertEqual(started['state'], 'completed', started.get('error'))
        self.assertIn('scene', started['presentation'])  # 3D scene kept for a verified model
        self.assertNotIn('output_schema', self.adapter.calls[-1]['generation'])

    def test_codex_keeps_its_strict_schema_and_the_new_component_fields_are_accepted(self):
        from backend.presentation_plan import output_schema, _strict_schema
        strict = output_schema('presentation', strict=True)
        item = strict['properties']['scene']['anyOf'][0]['properties']['objects']['items']
        for field in ('component', 'scale', 'group', 'material', 'param', 'shape', 'size'):
            self.assertIn(field, item['properties'])
            self.assertIn(field, item['required'])  # strict mode lists every property; optional ones are nullable
        self.assertEqual({'anyOf': [{'type': 'string'}, {'type': 'null'}]}, item['properties']['component'])


class _Ollama(http.server.BaseHTTPRequestHandler):
    models = {'llava:13b': ['completion', 'vision'], 'qwen2.5:3b': ['completion', 'tools'], 'old-model': None}
    hits = []

    def log_message(self, *args): pass

    def reply(self, status, data):
        raw = json.dumps(data).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        _Ollama.hits.append(self.path)
        if self.path == '/api/tags':
            self.reply(200, {'models': [{'name': n} for n in self.models]})
        elif self.path == '/redirect':
            self.send_response(302); self.send_header('Location', 'http://example.com/'); self.end_headers()
        else:
            self.reply(404, {})

    def do_POST(self):
        _Ollama.hits.append(self.path)
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        caps = self.models.get(body['model'], [])
        shown = {'details': {'family': 'llama', 'parameter_size': '13B'}}
        if caps is not None:
            shown['capabilities'] = caps
        self.reply(200, shown)


class UsageNormalizationTests(unittest.TestCase):
    def test_every_provider_usage_shape_becomes_the_same_four_counters(self):
        from backend.inference.adapter import normalize_usage
        self.assertEqual(normalize_usage({'input_tokens': 337, 'output_tokens': 2994, 'cache_read_input_tokens': 7445, 'cache_creation_input_tokens': 0, 'x': 1}),
                         {'input_tokens': 337, 'output_tokens': 2994, 'cache_read_input_tokens': 7445, 'cache_creation_input_tokens': 0})
        self.assertEqual(normalize_usage({'prompt_tokens': 904, 'completion_tokens': 332, 'total_tokens': 1236, 'prompt_tokens_details': {'cached_tokens': 400}}),
                         {'input_tokens': 504, 'output_tokens': 332, 'cache_read_input_tokens': 400})
        for bad in (None, 'x', [], {'input_tokens': -1, 'output_tokens': True}):
            self.assertEqual(normalize_usage(bad), {})


class OllamaDetectionTests(unittest.TestCase):
    def serve(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Ollama)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown); self.addCleanup(server.server_close)
        return f'http://127.0.0.1:{server.server_port}'

    def test_installed_models_and_their_declared_capabilities_are_listed_read_only(self):
        _Ollama.hits.clear()
        result = detect(self.serve())
        self.assertTrue(result['available'])
        by_name = {m['name']: m for m in result['models']}
        self.assertTrue(by_name['llava:13b']['vision'] and by_name['llava:13b']['declared'])
        self.assertFalse(by_name['qwen2.5:3b']['vision'])
        self.assertFalse(by_name['old-model']['declared'])  # an Ollama that reports nothing is not treated as "no vision" or "vision"
        self.assertEqual(sorted(set(_Ollama.hits)), ['/api/show', '/api/tags'])  # nothing is run or pulled

    def test_an_unreachable_ollama_says_it_is_unavailable_and_remote_hosts_are_refused(self):
        down = detect('http://127.0.0.1:9', timeout=1)
        self.assertFalse(down['available'])
        self.assertIn('Ollama no disponible', down['message'])
        for remote in ('https://ollama.com', 'http://8.8.8.8:11434', 'ftp://127.0.0.1'):
            with self.subTest(remote=remote), self.assertRaises(ValueError): detect(remote)

    def test_vision_models_become_candidates_only_after_an_explicit_connection_and_a_passing_aptitude_test(self):
        table = CapabilityTable()
        found = {m['name']: m for m in detect(self.serve())['models']}
        if found['llava:13b']['vision']:
            table.declare('ollama-local', 'llava:13b', 'vision', 'Ollama /api/show')
        self.assertEqual(table.level('ollama-local', 'llava:13b', 'vision'), 'declarado')
        self.assertEqual(table.level('ollama-local', 'llava:13b', 'scene_3d'), None)  # declared vision does not make it apt for 3D


class OllamaRouteTests(unittest.TestCase):
    def start(self, base_url):
        import urllib.request
        from PIL import Image
        from backend.magic_pen import MagicPenService
        from backend.server import AxxBridgeHandler, ThreadedHTTPServer
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        pen = MagicPenService(Path(temp.name)); self.addCleanup(pen.close)

        class Adapter:
            config = {'allow_paid': False, 'providers': [{'name': 'ollama-local', 'kind': 'ollama', 'model': 'llava:13b', 'protocol': 'openai', 'enabled': True,
                                                          'base_url': base_url + '/v1', 'free_confirmed': True, 'capabilities': ['text']}]}
        handler = type('H', (AxxBridgeHandler,), {'magic_pen': pen, 'adapter': Adapter()})
        server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown); self.addCleanup(server.server_close)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(path):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', headers={'Authorization': 'Bearer ' + server.host_token})
            with opener.open(request, timeout=10) as response:
                return json.load(response)
        return pen, get

    def test_the_route_lists_models_and_records_only_what_ollama_declares_for_saved_connections(self):
        simulated = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Ollama)
        threading.Thread(target=simulated.serve_forever, daemon=True).start()
        self.addCleanup(simulated.shutdown); self.addCleanup(simulated.server_close)
        pen, get = self.start(f'http://127.0.0.1:{simulated.server_port}')
        result = get('/axx-api/ollama/models')
        self.assertTrue(result['available'])
        by_name = {m['name']: m for m in result['models']}
        self.assertEqual(by_name['llava:13b']['configured_as'], 'ollama-local')
        self.assertIsNone(by_name['qwen2.5:3b']['configured_as'])  # detected but never saved: not offered, nothing recorded
        self.assertEqual(pen.caps.level('ollama-local', 'llava:13b', 'vision'), 'declarado')
        self.assertIsNone(pen.caps.level('ollama-local', 'llava:13b', 'scene_3d'))  # a declaration never grants 3D
        self.assertEqual(by_name['llava:13b']['aptitude']['vision'], 'declarado')

    def test_without_ollama_the_route_answers_unavailable_instead_of_a_generic_error(self):
        _, get = self.start('http://127.0.0.1:9')
        result = get('/axx-api/ollama/models')
        self.assertFalse(result['available'])
        self.assertIn('Ollama no disponible', result['message'])


if __name__ == '__main__':
    unittest.main()
