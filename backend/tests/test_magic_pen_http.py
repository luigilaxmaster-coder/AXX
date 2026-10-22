"""Private loopback contract; fixture pixels are not a desktop capture test."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
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
                server.shutdown()
                server.server_close()
                thread.join(2)


if __name__ == '__main__':
    unittest.main()
