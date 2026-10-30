import hashlib
import hmac
import http.client
import json
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode, urlsplit, parse_qs
import uuid

from backend.telegram.miniapp import MiniAppFacade, validate_init_data

TOKEN = '12345:fixture-token'
ORIGIN = 'https://example.invalid'


def signed(owner=7, timestamp=None, token=TOKEN, start_param=None, query_id='fixture'):
    values = {'auth_date': str(int(time.time()) if timestamp is None else timestamp),
              'user': json.dumps({'id': owner}, separators=(',', ':')),
              'query_id': query_id}
    if start_param is not None:
        values['start_param'] = start_param
    check = '\n'.join(k+'='+values[k] for k in sorted(values)).encode()
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    values['hash'] = hmac.new(secret, check, hashlib.sha256).hexdigest()
    return urlencode(values)


class MiniAppTests(unittest.TestCase):
    def setUp(self):
        self.account = {'account_id': 3, 'owner_id': 7, 'enabled': True, 'session':'fixture'}
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
        self.service.diagnostics.return_value = {'permissions': {}, 'conversation': {}, 'connection': {}, 'observed_at': 0}
        self.service.status.return_value = {'state': 'configured', 'messages': 'not_verified', 'secret': 'never-expose'}
        self.service.admit_miniapp.return_value = {'state': 'succeeded', 'text': 'ok', 'secret': 'never-expose'}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.facade = MiniAppFacade(self.temp.name, self.service)
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
            response_headers = dict(res.getheaders())
            response_headers['Cookies'] = res.msg.get_all('Set-Cookie') or []
            return res.status, response_headers, json.loads(res.read())
        finally:
            conn.close()

    def pairing_init(self):
        value = self.facade.pairing.create_pairing(self.account, 'FixtureBot')
        return parse_qs(urlsplit(value['url']).query)['start'][0]

    def session(self):
        status, headers, body = self.request('POST', '/api/session', {'init_data': signed(), 'pairing_token': self.pairing_init()}, {'Origin': ORIGIN})
        self.assertEqual(status, 200)
        cookies = headers['Cookies']
        self.assertEqual(len(cookies), 2)
        for cookie in cookies:
            self.assertIn('HttpOnly', cookie)
            self.assertIn('Secure', cookie)
            self.assertIn('SameSite=Strict', cookie)
        return '; '.join(cookie.split(';')[0] for cookie in cookies), body['csrf']

    def test_init_signature_expiry_identity_and_duplicates(self):
        self.assertTrue(validate_init_data(signed(), TOKEN, 7))
        for value in (signed(owner=8), signed(timestamp=int(time.time())-301),
                      signed(timestamp=int(time.time())+31), signed(token='wrong'), signed()+'&user=x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_init_data(value, TOKEN, 7)

    def test_session_replay_blocked_and_wrong_origin_rejected(self):
        pair_token = self.pairing_init()
        init = signed()
        status, headers, body = self.request('POST', '/api/session', {'init_data': init, 'pairing_token': pair_token}, {'Origin': ORIGIN})
        self.assertEqual(status, 200)
        cookie = '; '.join(c.split(';')[0] for c in headers['Cookies'])
        status, _, resumed = self.request('POST', '/api/session', {'init_data': init}, {'Origin': ORIGIN, 'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(resumed['csrf'], body['csrf'])
        self.assertEqual(self.request('POST', '/api/session', {'init_data': init, 'pairing_token': pair_token}, {'Origin': ORIGIN})[0], 401)
        self.assertEqual(self.request('POST', '/api/session', {'init_data': signed()}, {'Origin': 'https://evil.invalid'})[0], 403)

    def test_status_and_chat_are_session_bound_and_sanitized(self):
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
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
        self.assertEqual(self.request('POST', '/api/chat', payload, headers)[0], 400)
        self.service.admit_miniapp.assert_called_once()

    def test_appearance_comes_only_from_local_snapshot(self):
        self.service.appearance = lambda: {'settings': {}, 'studio': {}, 'camera': {}, 'finish': {}}
        cookie, _ = self.session()
        status, _, data = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        self.assertEqual(data['appearance'], self.service.appearance())
        self.service.appearance = lambda: None
        self.assertIsNone(self.request('GET', '/api/state', headers={'Cookie': cookie})[2]['appearance'])

    def test_activity_history_and_cancel_require_session_and_csrf(self):
        self.service.activity.return_value = {'items': []}
        self.service.history.return_value = {'messages': [], 'has_more': False}
        self.service.cancel_operation.return_value = {'state': 'cancel_requested', 'secret': 'not sent'}
        for route in ('/api/activity', '/api/history'):
            self.assertEqual(self.request('GET', route)[0], 401)
        cookie, csrf = self.session()
        for route in ('/api/activity', '/api/history'):
            self.assertEqual(self.request('GET', route, headers={'Cookie': cookie})[0], 200)
        operation = str(uuid.uuid4())
        payload = {'operation_id': operation, 'csrf': csrf}
        headers = {'Cookie': cookie, 'Origin': ORIGIN}
        self.assertEqual(self.request('POST', '/api/cancel', {**payload, 'csrf': 'wrong'}, headers)[0], 403)
        self.assertEqual(self.request('POST', '/api/cancel', {**payload, 'approved': True}, headers)[0], 400)
        self.service.cancel_operation.assert_not_called()
        status, _, result = self.request('POST', '/api/cancel', payload, headers)
        self.assertEqual((status, result), (200, {'state':'cancel_requested'}))
        self.service.cancel_operation.assert_called_once_with(7, operation)

    def test_safe_error_codes_distinguish_session_and_core_failure(self):
        status, _, result = self.request('GET', '/api/state')
        self.assertEqual((status, result['error']), (401, 'AUTH_REQUIRED'))
        cookie, _ = self.session()
        session_key = cookie.split(';', 1)[0].split('=', 1)[1]
        self.facade.sessions[session_key]['until'] = time.time() - 1
        status, _, result = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual((status, result['error']), (401, 'SESSION_EXPIRED'))
        self.facade.used.clear()
        cookie, _ = self.session()
        self.service.diagnostics.side_effect = RuntimeError('secret marker')
        status, _, result = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual((status, result['error']), (503, 'CORE_UNAVAILABLE'))
        self.assertNotIn('secret marker', str(result))

    def test_pairing_token_without_verified_owner_cannot_bind(self):
        pair_token = self.pairing_init()
        for invalid in (signed(owner=8), signed(token='wrong')):
            status, _, result = self.request('POST', '/api/session', {'init_data':invalid, 'pairing_token':pair_token}, {'Origin':ORIGIN})
            self.assertEqual((status, result['error']), (401, 'AUTH_REQUIRED'))
            self.assertTrue(self.facade.pairing.pending(self.account, pair_token))
        self.assertEqual(self.request('POST', '/api/session', {'init_data':signed(), 'pairing_token':pair_token}, {'Origin':ORIGIN})[0], 200)
        self.assertFalse(self.facade.pairing.pending(self.account, pair_token))

    def test_reused_init_does_not_consume_a_new_pairing(self):
        init = signed(query_id='first')
        first_token = self.pairing_init()
        status, _, _ = self.request('POST', '/api/session', {'init_data':init, 'pairing_token':first_token}, {'Origin':ORIGIN})
        self.assertEqual(status, 200)
        next_token = self.pairing_init()
        status, _, result = self.request('POST', '/api/session', {'init_data':init, 'pairing_token':next_token}, {'Origin':ORIGIN})
        self.assertEqual((status, result['error']), (401, 'AUTH_REQUIRED'))
        self.assertTrue(self.facade.pairing.pending(self.account, next_token))
        status, _, _ = self.request('POST', '/api/session', {'init_data':signed(query_id='fresh'), 'pairing_token':next_token}, {'Origin':ORIGIN})
        self.assertEqual(status, 200)
        self.assertFalse(self.facade.pairing.pending(self.account, next_token))

    def test_existing_bond_can_open_without_new_qr(self):
        cookie, _ = self.session()
        bond = next(part.strip() for part in cookie.split(';') if part.strip().startswith('__Host-axx_telegram_bond='))
        status, headers, body = self.request('POST', '/api/session', {'init_data': signed(query_id='reopen')}, {'Origin': ORIGIN, 'Cookie': bond})
        self.assertEqual(status, 200)
        self.assertIn('csrf', body)
        self.assertEqual(len(headers['Cookies']), 1)

    def test_signed_owner_needs_pc_qr_and_revocation_ends_session(self):
        status, _, result = self.request('POST', '/api/session', {'init_data': signed()}, {'Origin': ORIGIN})
        self.assertEqual((status, result['error']), (403, 'PAIRING_REQUIRED'))
        cookie, _ = self.session()
        binding = self.facade.pairing.status(self.account)['bindings'][0]['id']
        self.assertTrue(self.facade.pairing.revoke(self.account, binding))
        status, _, result = self.request('GET', '/api/state', headers={'Cookie': cookie})
        self.assertEqual((status, result['error']), (403, 'PAIRING_REQUIRED'))

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
