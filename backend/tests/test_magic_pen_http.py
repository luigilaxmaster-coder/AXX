"""Private loopback contract; fixture pixels are not a desktop capture test."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch
import urllib.request
import urllib.error
from PIL import Image
from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.magic_pen import MagicPenService
from backend.presentation_plan import output_schema


class MagicPenHTTPTests(unittest.TestCase):
    def test_spatial_readiness_and_session_routes_are_local_and_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            class Adapter:
                config = {'allow_paid': False, 'providers': [{'name': 'fixture', 'model': 'claude-opus-4-6',
                    'protocol': 'anthropic', 'enabled': True, 'free_confirmed': True, 'capabilities': ['vision']}]}
                def __init__(self): self.calls = []
                def route(self, request):
                    self.calls.append(request)
                    plan = {'schema_version': '1.0', 'kind': 'presentation', 'title': 'Figura', 'summary': 'Una pieza azul.',
                        'fidelity': 'conceptual', 'steps': [
                            {'id': 's1', 'title': 'Pieza', 'body': 'Rectángulo azul.', 'narration': 'La pieza azul.', 'basis': 'observed'},
                            {'id': 's2', 'title': 'Contexto', 'body': 'Está dentro de la selección.', 'narration': 'Vemos el contexto.', 'basis': 'inferred'}]}
                    return {'ok': True, 'message': {'content': json.dumps(plan)},
                            'route': {'provider_name': 'fixture', 'model': 'claude-opus-4-6'}}
                def cancel(self, request_id): return True

            adapter = Adapter()
            pen = MagicPenService(root, adapter)
            doc = pen.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'fixture'})
            pen.save({'id': doc['id'], 'expected_revision': 1, 'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]}, 'strokes': []})
            handler = type('SpatialHandler', (AxxBridgeHandler,), {'magic_pen': pen})
            server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def request(method, path, body=None):
                data = json.dumps(body).encode() if body is not None else None
                req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', data=data, method=method,
                    headers={'Authorization': 'Bearer ' + server.host_token, **({'Content-Type': 'application/json'} if data is not None else {})})
                with opener.open(req, timeout=5) as response: return json.load(response)

            try:
                readiness = request('GET', '/axx-api/feature-readiness?feature_id=spatial_intelligence')
                self.assertEqual(readiness['status'], 'not_verified')
                self.assertEqual(adapter.calls, [], 'Readiness GET must not make an upstream inference')
                verified = request('POST', '/axx-api/feature-readiness/verify',
                    {'feature_id': 'spatial_intelligence', 'provider': 'fixture', 'model': 'claude-opus-4-6', 'effort': 'auto'})
                self.assertEqual((verified['state'], verified['provider'], verified['model']), ('ready', 'fixture', 'claude-opus-4-6'))
                self.assertEqual(adapter.calls[0]['generation']['output_schema'], output_schema('presentation'))
                self.assertEqual(adapter.calls[0]['generation']['effort'], 'medium')
                self.assertIn('image_url', adapter.calls[0]['messages'][1]['content'][1])
                readiness = request('GET', '/axx-api/feature-readiness?feature_id=spatial_intelligence')
                self.assertEqual(readiness['status'], 'ready')

                started = request('POST', '/axx-api/spatial/session/start', {'id': doc['id'], 'revision': 2,
                    'question': 'Explica la pieza.', 'provider': 'fixture', 'model': 'claude-opus-4-6',
                    'selection_mode': 'manual', 'effort': 'auto', 'request_id': uuid.uuid4().hex})
                self.assertEqual(started['state'], 'running')
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    result = request('POST', '/axx-api/spatial/session/get', {'id': doc['id'], 'query_id': started['id']})
                    if result['state'] != 'running': break
                    time.sleep(.01)
                self.assertEqual(result['state'], 'completed', result.get('error'))
                self.assertEqual(result['presentation']['title'], 'Figura')
                self.assertEqual(adapter.calls[1]['generation']['output_schema'], output_schema('presentation'))
            finally:
                pen.close(); server.shutdown(); server.server_close(); thread.join(2)

    def test_authorization_revision_and_export_errors(self):
        with tempfile.TemporaryDirectory() as root:
            pen = MagicPenService(Path(root))
            doc = pen.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'fixture'})
            handler = type('Handler', (AxxBridgeHandler,), {'magic_pen': pen})
            server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def request(op, body, authorized=True):
                headers = {'Content-Type': 'application/json'}
                if authorized:
                    headers['Authorization'] = 'Bearer ' + server.host_token
                req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/axx-api/pen/{op}',
                    data=json.dumps(body).encode(), headers=headers)
                try:
                    with opener.open(req) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as response:
                    with response:
                        return response.code, json.load(response)
            try:
                self.assertEqual(request('get', {'id': doc['id']}, False)[0], 401)
                self.assertEqual(request('get', {'id': doc['id']})[0], 200)
                self.assertEqual(request('get', {'id': '../outside'})[0], 400)
                edit = {'id': doc['id'], 'expected_revision': 1, 'selection': None, 'strokes': []}
                self.assertEqual(request('save', edit)[0], 200)
                self.assertEqual(request('save', edit)[0], 400)
                output = {'id': doc['id'], 'revision': 2, 'kind': 'original', 'directory': root, 'name': 'output'}
                self.assertTrue(request('export', output)[1]['verified'])
                status, body = request('export', output)
                self.assertEqual(status, 409)
                self.assertEqual(body['error']['code'], 'FILE_EXISTS')
                status, body = request('guide_check', {'id': doc['id'], 'query_id': 'a' * 32, 'step_id': 'g1', 'phase': 'target'})
                self.assertEqual(status, 400)
                self.assertIn('La consulta no existe', json.dumps(body, ensure_ascii=False), 'guide_check reaches MagicPenService')
                self.assertEqual(request('guide_check', {'id': doc['id']}, False)[0], 401)
            finally:
                pen.close()
                server.shutdown()
                server.server_close()
                thread.join(2)

    @contextmanager
    def host(self, adapter=None):
        with tempfile.TemporaryDirectory() as root:
            pen = MagicPenService(root, adapter)
            doc = pen.acquire(Image.new('RGB', (200, 100), 'white'), {'id': 'fixture'})
            pen.save({'id': doc['id'], 'expected_revision': 1, 'selection': {'shape': 'rect', 'bounds': [5, 5, 60, 60]}, 'strokes': []})
            handler = type('PenHandler', (AxxBridgeHandler,), {'magic_pen': pen})
            server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def request(operation, body, authorized=True):
                headers = {'Content-Type': 'application/json'}
                if authorized: headers['Authorization'] = 'Bearer ' + server.host_token
                req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/axx-api/pen/{operation}',
                                             data=json.dumps(body).encode(), headers=headers)
                try:
                    with opener.open(req, timeout=5) as response: return response.status, json.load(response)
                except urllib.error.HTTPError as response:
                    with response: return response.code, json.load(response)
            try:
                yield pen, doc, request
            finally:
                pen.close(); server.shutdown(); server.server_close(); thread.join(2)

    def test_async_auth_snapshot_idempotency_and_cancel_http(self):
        entered, release = threading.Event(), threading.Event()
        class Adapter:
            config = {'providers': [{'name': 'fixture', 'model': 'visual', 'enabled': True, 'free_confirmed': True, 'capabilities': ['vision']}]}
            calls = []
            def route(self, request):
                self.calls.append(request); entered.set(); release.wait(3)
                return {'ok': True, 'message': {'content': 'late fixture'}}
            def cancel(self, request_id): release.set(); return True
        adapter = Adapter()
        with self.host(adapter) as (pen, doc, request):
            body = {'id': doc['id'], 'revision': 2, 'question': 'fixture', 'provider': 'fixture', 'model': 'visual',
                    'selection_mode': 'manual', 'request_id': uuid.uuid4().hex}
            self.assertEqual(request('start', body, False)[0], 401)
            self.assertEqual(adapter.calls, [])
            started_at = time.monotonic()
            status, query = request('start', body)
            self.assertEqual(status, 200); self.assertEqual(query['state'], 'running')
            self.assertLess(time.monotonic() - started_at, 1)
            self.assertTrue(entered.wait(2))
            ref = {'id': doc['id'], 'query_id': query['id']}
            self.assertEqual(request('query', ref)[1]['state'], 'running')
            self.assertEqual(request('start', body)[1]['id'], query['id'])
            self.assertEqual(request('start', body | {'question': 'changed'})[0], 400)
            self.assertEqual(request('start', body | {'request_id': uuid.uuid4().hex})[0], 400)
            self.assertEqual(request('cancel', ref, False)[0], 401)
            self.assertEqual(request('cancel', ref)[1]['state'], 'cancelled')
            with pen.condition: pen.condition.wait_for(lambda: pen.processing is None, timeout=3)
            done = request('query', ref)[1]
            self.assertEqual(done['state'], 'cancelled'); self.assertNotIn('response', done)
            self.assertEqual(len(adapter.calls), 1)

    def test_cancel_before_start_and_capture_omits_preview_http(self):
        with self.host() as (pen, doc, request):
            request_id = uuid.uuid4().hex
            ref = {'id': doc['id'], 'query_id': request_id}
            self.assertEqual(request('cancel', ref)[1]['state'], 'cancelled')
            self.assertEqual(request('start', {'id': doc['id'], 'revision': 2, 'question': 'cancelled', 'request_id': request_id})[1]['state'], 'cancelled')
            self.assertIn('preview', request('get', {'id': doc['id']})[1])
            monitor = {'id': 'fixture', 'x': 0, 'y': 0, 'width': 200, 'height': 100}
            with patch('backend.magic_pen.monitors', return_value=[monitor]), patch('backend.magic_pen.ImageGrab.grab', return_value=Image.new('RGB', (200, 100), 'white')):
                status, captured = request('capture', {'monitor': 'fixture'})
            self.assertEqual(status, 200); self.assertNotIn('preview', captured)


if __name__ == '__main__':
    unittest.main()
