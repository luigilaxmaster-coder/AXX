"""Real loopback HTTP checks around the Telegram service boundary."""
import http.client
import json
import threading
import unittest
from unittest.mock import Mock

from backend.server import AxxBridgeHandler, ThreadedHTTPServer


class TelegramHTTPTests(unittest.TestCase):
    def setUp(self):
        self.telegram = Mock()
        self.telegram.status.return_value = {'state': 'unavailable', 'capabilities': {}}
        self.telegram.admit.return_value = {'state': 'succeeded', 'text': 'ok'}
        handler = type('TelegramHandler', (AxxBridgeHandler,), {'telegram': self.telegram})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None, *, auth=True, origin=None, host=None):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.server.host_token
        if origin:
            headers['Origin'] = origin
        if host:
            headers['Host'] = host
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_status_requires_native_token(self):
        code, _ = self.request('GET', '/axx-api/telegram/status', auth=False)
        self.assertEqual(code, 401)
        self.telegram.status.assert_not_called()
        code, value = self.request('GET', '/axx-api/telegram/status')
        self.assertEqual(code, 200)
        self.assertEqual(value, {'state': 'unavailable', 'capabilities': {}})
        self.telegram.status.assert_called_once_with()

    def test_input_blocks_unauthorized_origin_and_host_before_admission(self):
        payload = {'account_id': 11, 'peer_id': 22, 'message_id': 1, 'sent_at': 1,
                   'kind': 'text', 'text': 'hola'}
        path = '/axx-api/telegram/input'
        for options, expected in [({'auth': False}, 401), ({'origin': 'https://other.example'}, 403),
                                  ({'host': 'other.example'}, 403)]:
            with self.subTest(options=options):
                self.assertEqual(self.request('POST', path, payload, **options)[0], expected)
                self.telegram.admit.assert_not_called()
        code, value = self.request('POST', path, payload)
        self.assertEqual(code, 200)
        self.assertEqual(value, {'state': 'succeeded', 'text': 'ok'})
        self.telegram.admit.assert_called_once_with(payload)


if __name__ == '__main__':
    unittest.main()
