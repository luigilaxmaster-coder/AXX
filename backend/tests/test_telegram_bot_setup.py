"""Offline tests for the local bot configuration workflow."""
import unittest
from unittest.mock import patch

from backend.telegram.bot import BotApiError
from backend.telegram.bot_setup import configure, diagnostic, discover_url


TOKEN = '123456:' + 'a' * 35
BOT = {'token': TOKEN, 'enabled': True, 'public_url': ''}
ACCOUNT = {'owner_id': 22, 'enabled': True}


class BotSetupTests(unittest.TestCase):
    def test_tailscale_prefill_requires_online_status(self):
        with patch('backend.telegram.bot_setup.tailscale_status', return_value={
                'BackendState': 'Running', 'Self': {'Online': True, 'DNSName': 'axx.tailnet.ts.net.'}}):
            self.assertEqual(discover_url(), 'https://axx.tailnet.ts.net/')
        with patch('backend.telegram.bot_setup.tailscale_status', side_effect=RuntimeError('private details')):
            self.assertEqual(discover_url(), '')

    def test_configures_owner_menu_and_preserves_existing_token(self):
        calls = []
        def request(token, method, body):
            calls.append((token, method, body))
            return {'is_bot': True} if method == 'getMe' else True
        with patch('backend.telegram.bot_setup.load_bot', return_value=BOT), \
             patch('backend.telegram.bot_setup.load_account', return_value=ACCOUNT), \
             patch('backend.telegram.bot_setup.bot_request', side_effect=request), \
             patch('backend.telegram.bot_setup.save_bot') as save:
            result = configure('', 'https://axx.tailnet.ts.net/', True, 'state')
        self.assertTrue(result['menu_configured'])
        self.assertEqual([c[1] for c in calls], ['getMe', 'setChatMenuButton', 'setMyCommands'])
        self.assertEqual(calls[1][2]['chat_id'], 22)
        self.assertEqual(calls[2][2]['scope'], {'type': 'chat', 'chat_id': 22})
        self.assertEqual(save.call_args.args[0]['token'], TOKEN)

    def test_invalid_identity_never_saves(self):
        with patch('backend.telegram.bot_setup.load_account', return_value=ACCOUNT), \
             patch('backend.telegram.bot_setup.bot_request', return_value={'is_bot': False}), \
             patch('backend.telegram.bot_setup.save_bot') as save:
            with self.assertRaises(BotApiError):
                configure(TOKEN, '', True, 'state')
            save.assert_not_called()

    def test_menu_failure_preserves_valid_token_and_returns_safe_diagnostic(self):
        def request(_token, method, _body):
            if method == 'getMe':
                return {'is_bot': True}
            raise BotApiError('OWNER_CHAT_NOT_STARTED')
        with patch('backend.telegram.bot_setup.load_account', return_value=ACCOUNT), \
             patch('backend.telegram.bot_setup.bot_request', side_effect=request), \
             patch('backend.telegram.bot_setup.save_bot') as save:
            result = configure(TOKEN, 'https://axx.tailnet.ts.net/', True, 'state')
        self.assertTrue(result['local_saved'])
        self.assertFalse(result['menu_configured'])
        self.assertEqual(result['error_code'], 'OWNER_CHAT_NOT_STARTED')
        self.assertIn('/start', diagnostic(result['error_code']))
        self.assertEqual(save.call_args.args[0]['token'], TOKEN)
        self.assertNotIn(TOKEN, str(result))

    def test_empty_url_skips_remote_menu(self):
        with patch('backend.telegram.bot_setup.load_account', return_value=ACCOUNT), \
             patch('backend.telegram.bot_setup.bot_request', return_value={'is_bot': True}) as request, \
             patch('backend.telegram.bot_setup.save_bot'):
            result = configure(TOKEN, '', False, 'state')
        self.assertFalse(result['menu_configured'])
        request.assert_called_once_with(TOKEN, 'getMe', {})


if __name__ == '__main__':
    unittest.main()
