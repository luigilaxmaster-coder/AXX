"""PC-only Telegram management over real local HTTP with isolated fixtures."""
import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from backend.server import AxxBridgeHandler, ThreadedHTTPServer
from backend.telegram.config import GRANTS
from backend.telegram.desktop import DesktopTelegram
from backend.telegram.miniapp import MiniAppFacade


ACCOUNT = {'account_id': 11, 'owner_id': 22, 'enabled': True, 'session': 'session-fixture',
           'grants': {key: key == 'conversation' for key in GRANTS}}


class DesktopHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = Mock()
        self.manager.data_dir = self.tmp.name
        self.manager.status.return_value = {'account': {'configured': True}}
        self.manager.pause.return_value = {'state': 'paused'}
        self.manager.update_permissions.return_value = {'state': 'saved'}
        self.manager.validate_permissions.side_effect = DesktopTelegram.validate_permissions
        self.pairing = Mock()
        handler = type('DesktopTelegramHandler', (AxxBridgeHandler,),
                       {'telegram_desktop': self.manager, 'telegram_pairing': self.pairing})
        self.server = ThreadedHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        patcher = patch('backend.telegram.http_api.load_account', return_value=ACCOUNT)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_host_auth_and_browser_origin_block_management(self):
        path = '/axx-api/telegram/desktop/status'
        self.assertEqual(self.request('GET', path, auth=False)[0], 401)
        self.assertEqual(self.request('GET', path, origin='https://attacker.example')[0], 403)
        self.assertEqual(self.request('GET', path, host='attacker.example')[0], 403)
        self.manager.status.assert_not_called()
        self.assertEqual(self.request('GET', path)[0], 200)
        self.manager.status.assert_called_once()

    def test_invalid_bodies_cannot_revoke_or_change_permissions(self):
        self.assertEqual(self.request('POST', '/axx-api/telegram/desktop/pause', {'unexpected': True})[0], 400)
        self.assertEqual(self.request('POST', '/axx-api/telegram/desktop/update_permissions',
                                      {'enabled': True, 'grants': {'conversation': True}, 'approved': True})[0], 400)
        self.pairing.revoke_all.assert_not_called()
        self.manager.pause.assert_not_called()
        self.manager.update_permissions.assert_not_called()

    def test_pause_and_grant_change_revoke_existing_bindings_first(self):
        operations = []
        self.pairing.revoke_all.side_effect = lambda _account: operations.append('revoke')
        self.manager.pause.side_effect = lambda: operations.append('pause') or {'state': 'paused'}
        self.manager.update_permissions.side_effect = lambda _body: operations.append('permissions') or {'state': 'saved'}
        self.assertEqual(self.request('POST', '/axx-api/telegram/desktop/pause', {})[0], 200)
        body = {'enabled': True, 'grants': dict(ACCOUNT['grants'])}
        self.assertEqual(self.request('POST', '/axx-api/telegram/desktop/update_permissions', body)[0], 200)
        self.assertEqual(operations, ['revoke', 'pause', 'permissions'])
        body['grants']['conversation'] = not body['grants']['conversation']
        self.assertEqual(self.request('POST', '/axx-api/telegram/desktop/update_permissions', body)[0], 200)
        self.assertEqual(operations, ['revoke', 'pause', 'permissions', 'revoke', 'permissions'])

    def test_miniapp_does_not_expose_desktop_admin_route(self):
        bot = {'enabled': True, 'token': 'fixture', 'public_url': 'https://miniapp.example.org/'}
        with patch('backend.telegram.bot_config.load_bot', return_value=bot), \
             patch('backend.telegram.miniapp.load_account', return_value=ACCOUNT):
            facade = MiniAppFacade(self.tmp.name, Mock())
            port = facade.start()
            try:
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                conn.request('GET', '/axx-api/telegram/desktop/status')
                response = conn.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                conn.close()
            finally:
                facade.close()


if __name__ == '__main__':
    unittest.main()
