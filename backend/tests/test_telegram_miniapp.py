import hashlib
import hmac
import http.client
import json
import sys
import time
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode
import uuid

from backend.telegram.miniapp import MiniAppFacade, validate_init_data

TOKEN = '12345:fixture-token'
ORIGIN = 'https://example.invalid'


def signed(owner=7, timestamp=None, token=TOKEN):
    values = {'auth_date': str(int(time.time()) if timestamp is None else timestamp),
              'user': json.dumps({'id': owner}, separators=(',', ':')),
              'query_id': 'fixture'}
    check = '\n'.join(k+'='+values[k] for k in sorted(values)).encode()
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    values['hash'] = hmac.new(secret, check, hashlib.sha256).hexdigest()
    return urlencode(values)


class MiniAppTests(unittest.TestCase):
    def setUp(self):
        self.account = {'account_id': 3, 'owner_id': 7, 'enabled': True}
        self.bot = {'token': TOKEN, 'enabled': True, 'public_url': ORIGIN}
        module = types.ModuleType('backend.telegram.bot_config')
        module.load_bot = lambda _: self.bot.copy()
        self.modules = patch.dict(sys.modules, {'backend.telegram.bot_config': module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.account_patch = patch('backend.telegram.miniapp.load_account', side_effect=lambda _: self.account.copy())
        self.account_patch.start()
        self.addCleanup(self.account_patch.stop)
        self.service = Mock()
        self.service.appearance = None
        self.service.status.return_value = {'state': 'configured', 'messages': 'not_verified', 'secret': 'never-expose'}
        self.service.admit_miniapp.return_value = {'state': 'succeeded', 'text': 'ok', 'secret': 'never-expose'}
        self.facade = MiniAppFacade(None, self.service)
        self.port = self.facade.start()
        self.addCleanup(self.facade.close)

    def request(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        try:
            raw = json.dumps(data).encode() if data is not None else None
            headers = dict(headers or {})
            if raw is not None:
                headers['Content-Type'] = 'application/json'
            conn.request(method, path, body=raw, headers=headers)
            res = conn.getresponse()
            return res.status, dict(res.getheaders()), json.loads(res.read())
        finally:
            conn.close()

    def session(self):
        status, headers, body = self.request('POST', '/api/session', {'init_data': signed()}, {'Origin': ORIGIN})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('Secure', cookie)
        self.assertIn('SameSite=Strict', cookie)
        return cookie.split(';')[0], body['csrf']

    def test_init_signature_expiry_identity_and_duplicates(self):
        self.assertTrue(validate_init_data(signed(), TOKEN, 7))
        for value in (signed(owner=8), signed(timestamp=int(time.time())-301),
                      signed(timestamp=int(time.time())+31), signed(token='wrong'), signed()+'&user=x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_init_data(value, TOKEN, 7)

    def test_session_replay_blocked_and_wrong_origin_rejected(self):
        init = signed()
        status, headers, body = self.request('POST', '/api/session', {'init_data': init}, {'Origin': ORIGIN})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        status, _, resumed = self.request('POST', '/api/session', {'init_data': init}, {'Origin': ORIGIN, 'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(resumed['csrf'], body['csrf'])
        self.assertEqual(self.request('POST', '/api/session', {'init_data': init}, {'Origin': ORIGIN})[0], 403)
        self.assertEqual(self.request('POST', '/api/session', {'init_data': signed()}, {'Origin': 'https://evil.invalid'})[0], 403)

    def test_status_and_chat_are_session_bound_and_sanitized(self):
        self.assertEqual(self.request('GET', '/api/state')[0], 403)
        cookie, csrf = self.session()
        status, _, data = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertNotIn('secret', data)
        payload = {'text': 'hola', 'request_id': str(uuid.uuid4()), 'csrf': csrf}
        headers = {'Cookie': cookie, 'Origin': ORIGIN}
        status, _, data = self.request('POST', '/api/chat', payload, headers)
        self.assertEqual(status, 200)
        self.assertEqual(data, {'state': 'succeeded', 'text': 'ok'})
        self.service.admit_miniapp.assert_called_once_with(7, 'hola', payload['request_id'])
        payload['approved'] = True
        self.assertEqual(self.request('POST', '/api/chat', payload, headers)[0], 403)
        self.service.admit_miniapp.assert_called_once()

    def test_appearance_comes_only_from_local_snapshot(self):
        self.service.appearance = lambda: {'settings': {}, 'studio': {}, 'camera': {}, 'finish': {}}
        cookie, _ = self.session()
        status, _, data = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(data['appearance'], self.service.appearance())
        self.service.appearance = lambda: None
        self.assertIsNone(self.request('GET', '/api/state', headers={'Cookie': cookie})[2]['appearance'])

    def test_revocation_wrong_csrf_and_account_change_fail_closed(self):
        cookie, csrf = self.session()
        payload = {'text': 'hola', 'request_id': str(uuid.uuid4()), 'csrf': csrf+'x'}
        headers = {'Cookie': cookie, 'Origin': ORIGIN}
        self.assertEqual(self.request('POST', '/api/chat', payload, headers)[0], 403)
        self.account['owner_id'] = 8
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': cookie})[0], 403)
        self.account['enabled'] = False
        self.assertEqual(self.request('GET', '/api/state', headers={'Cookie': cookie})[0], 403)
        self.service.admit_miniapp.assert_not_called()


if __name__ == '__main__':
    unittest.main()
