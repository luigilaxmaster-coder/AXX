"""Real loopback HTTP checks around the Telegram service boundary."""
import http.client
import json
import threading
import unittest
from unittest.mock import Mock, patch

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

    def test_port_in_use_preserves_socket_error(self):
        with self.assertRaises(OSError):
            ThreadedHTTPServer(('127.0.0.1', self.server.server_port), AxxBridgeHandler)

    def test_native_core_bound_tracks_actual_server_lifecycle(self):
        with patch.dict('os.environ', {'AXX_HOST_TOKEN': 'fixture-token-' * 4}):
            server = ThreadedHTTPServer(('127.0.0.1', 0), AxxBridgeHandler)
        self.assertFalse(server.core_bound())
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            self.assertTrue(server.serving.wait(2))
            self.assertTrue(server.core_bound())
            server.shutdown()
            worker.join(2)
            self.assertFalse(server.core_bound())
        finally:
            server.server_close()

    def test_rejected_post_bodies_are_drained_without_dispatch(self):
        payload = {'peer_id': 22, 'operation_id': 'x' * 5000}
        for _ in range(30):
            code, _ = self.request('POST', '/axx-api/telegram/review', payload, origin='https://attacker.example')
            self.assertEqual(code, 403)
        self.telegram.review_operation.assert_not_called()

    def test_status_requires_native_token(self):
        code, _ = self.request('GET', '/axx-api/telegram/status', auth=False)
        self.assertEqual(code, 401)
        self.telegram.status.assert_not_called()
        code, value = self.request('GET', '/axx-api/telegram/status')
        self.assertEqual(code, 200)
        self.assertEqual(value, {'state': 'unavailable', 'capabilities': {}})
        self.telegram.status.assert_called_once_with()

    def test_confirmation_routes_require_native_auth_and_exact_payload(self):
        review = '/axx-api/telegram/review'
        body = {'peer_id': 22, 'operation_id': '00000000-0000-4000-8000-000000000001'}
        self.telegram.review_operation.return_value = {'can_confirm': False}
        self.assertEqual(self.request('POST', review, body, auth=False)[0], 401)
        self.assertEqual(self.request('POST', review, body, origin='https://untrusted.example')[0], 403)
        self.assertEqual(self.request('POST', review, dict(body, approved=True))[0], 400)
        self.assertEqual(self.request('POST', review, dict(body, peer_id=True))[0], 400)
        self.telegram.review_operation.assert_not_called()
        self.assertEqual(self.request('POST', review, body)[0], 200)
        self.telegram.review_operation.assert_called_once_with(22, body['operation_id'])
        self.telegram.decide_operation.return_value = {'state': 'unknown'}
        self.assertEqual(self.request('POST', '/axx-api/telegram/decision',
                                      {'peer_id': 22, 'token': 'x' * 32, 'decision': 'confirm'})[0], 200)
        self.telegram.decide_operation.assert_called_once_with(22, 'x' * 32, 'confirm')

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
