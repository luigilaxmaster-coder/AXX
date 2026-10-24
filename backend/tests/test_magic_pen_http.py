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


class MagicPenHTTPTests(unittest.TestCase):
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
