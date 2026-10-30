"""Offline transport and authorization contracts for the Telegram bot."""
import json
import io
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from backend.telegram.bot import BotApiError, BotWorker, allowed, bot_request, menu
from backend.telegram.bot_config import load_bot, save_bot, validate_bot


BOT = {'token': '123456:' + 'a' * 35, 'enabled': True, 'public_url': ''}
ACCOUNT = {'owner_id': 22, 'account_id': 11, 'enabled': True, 'grants': {'conversation': True}}


def message(update_id=1, owner=22, text='hola'):
    return {'update_id': update_id, 'message': {'chat': {'id': owner, 'type': 'private'},
        'from': {'id': owner, 'is_bot': False}, 'date': 100, 'text': text}}


class BotConfigTests(unittest.TestCase):
    def test_http_errors_are_classified_without_exposing_url_or_description(self):
        scenarios = [(401, 'unauthorized', 'TOKEN_REJECTED'), (400, 'Bad Request: chat not found', 'OWNER_CHAT_NOT_STARTED'),
                     (400, 'Bad Request: web app URL invalid', 'MINIAPP_URL_REJECTED'),
                     (403, 'Forbidden', 'OWNER_BLOCKED_BOT'), (429, 'Too Many Requests', 'RATE_LIMITED')]
        for status, description, code in scenarios:
            with self.subTest(status=status, code=code):
                raw = json.dumps({'description': description + ' PRIVATE', 'parameters': {'retry_after': 12}}).encode()
                error = urllib.error.HTTPError('https://example.test/PRIVATE', status, 'PRIVATE', {}, io.BytesIO(raw))
                with patch('backend.telegram.bot.urllib.request.build_opener') as build:
                    build.return_value.open.side_effect = error
                    with self.assertRaises(BotApiError) as raised:
                        bot_request(BOT['token'], 'getMe', {})
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn('PRIVATE', str(raised.exception))
                self.assertNotIn(BOT['token'], str(raised.exception))
                if status == 429:
                    self.assertEqual(raised.exception.retry_after, 12)

    def test_https_public_url_validation(self):
        for url in ('http://example.com', 'https://127.0.0.1/', 'https://localhost/',
                    'https://name:pass@example.com/', 'https://example.com:8080/', 'https://site.local/'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_bot(dict(BOT, public_url=url))
        self.assertEqual(validate_bot(dict(BOT, public_url='https://axx.example.org/app'))['public_url'], 'https://axx.example.org/app')
        self.assertEqual(validate_bot(dict(BOT, username='VerifiedBot'))['username'], 'VerifiedBot')
        with self.assertRaises(ValueError):
            validate_bot(dict(BOT, username='https://other.example/'))

    def test_config_roundtrip_with_protection_injected(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch('backend.telegram.bot_config._dpapi_encrypt', side_effect=lambda x: b'protected:' + x), \
             patch('backend.telegram.bot_config._dpapi_decrypt', side_effect=lambda x: x.removeprefix(b'protected:')):
            save_bot(BOT, directory)
            self.assertEqual(load_bot(directory), BOT)
            self.assertTrue((Path(directory) / 'telegram' / 'bot.dpapi').read_bytes().startswith(b'protected:'))


class BotWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, side_effect in [('load_bot', lambda _: BOT.copy()), ('load_account', lambda _: ACCOUNT.copy()),
                                  ('_dpapi_encrypt', lambda x: x), ('_dpapi_decrypt', lambda x: x)]:
            p = patch('backend.telegram.bot.' + name, side_effect=side_effect)
            p.start()
            self.addCleanup(p.stop)
        self.worker = BotWorker(self.temp.name, 'unused')
        self.addCleanup(self.worker.close)

    def test_owner_only_forward_reply_group_and_bot_blocked(self):
        self.assertTrue(allowed(message(), 22))
        wrong = message(owner=23)
        forwarded = message(); forwarded['message']['forward_origin'] = {'type': 'user'}
        reply = message(); reply['message']['reply_to_message'] = {'text': 'quoted'}
        group = message(); group['message']['chat']['type'] = 'group'
        bot = message(); bot['message']['from']['is_bot'] = True
        for item in (wrong, forwarded, reply, group, bot):
            self.assertFalse(allowed(item, 22))

    def test_menus_include_webapp_only_when_configured(self):
        self.assertNotIn('web_app', json.dumps(menu('')))
        self.assertIn('web_app', json.dumps(menu('https://axx.example.org/')))

    def test_status_permissions_and_help_use_plain_language_without_raw_json(self):
        requests = []
        state = {'worker_running': True, 'messages': 'not_verified', 'voice_notes': 'not_implemented',
                 'files': 'not_implemented', 'pc_commands': 'not_verified', 'private_calls': 'not_verified'}
        with patch('backend.telegram.bot.bot_request', side_effect=lambda _t, method, data, **kw: requests.append(data)), \
             patch('backend.telegram.bot.local_request', return_value=state):
            for index, choice in enumerate(('status', 'permissions', 'help'), 1):
                item = message(index)
                self.worker.process(index, {'update_id': index, 'callback_query': {
                    'id': str(index), 'from': item['message']['from'], 'message': item['message'], 'data': choice}})
        self.assertEqual(len(requests), 3)
        self.assertIn('Notas de voz: En preparación', requests[0]['text'])
        self.assertIn('Conversar por texto: Permitido', requests[1]['text'])
        self.assertIn('Toca Abrir Axx', requests[2]['text'])
        for data in requests:
            self.assertNotIn('{', data['text'])
            self.assertNotIn('private_calls', data['text'])
            self.assertNotIn('not_implemented', data['text'])

    def test_input_is_persisted_before_offset_and_no_replay_after_unknown(self):
        self.worker.persist([message()])
        self.assertEqual(self.worker.offset(), 2)
        with self.worker.db() as db:
            db.execute("UPDATE updates SET state='running' WHERE id=1")
        second = BotWorker(self.temp.name, 'unused')
        self.addCleanup(second.close)
        with second.db() as db:
            self.assertEqual(db.execute('SELECT state FROM updates').fetchone()[0], 'unknown')
        second.pump()
        self.assertFalse(second.tasks)

    def test_start_menu_owner_only_and_routes_normal_text(self):
        requests = []
        with patch('backend.telegram.bot.bot_request', side_effect=lambda _t, method, data, **kw: requests.append((method, data))), \
             patch('backend.telegram.bot.local_request', return_value={'state': 'succeeded', 'text': 'respuesta'}) as local:
            self.worker.persist([message(1, text='/start'), message(2, owner=23), message(3)])
            for item in (message(1, text='/start'), message(2, owner=23), message(3)):
                self.worker.process(item['update_id'], item)
        self.assertEqual([r[1]['chat_id'] for r in requests], [22, 22])
        self.assertEqual(local.call_args.args[1], '/axx-api/telegram/bot-input')
        self.assertEqual(local.call_args.args[2]['event_id'], 3)
        with self.worker.db() as db:
            self.assertEqual([row[0] for row in db.execute('SELECT state FROM updates ORDER BY id')], ['done'] * 3)

    def test_revocation_prevents_send(self):
        with patch('backend.telegram.bot.load_bot', return_value=dict(BOT, enabled=False)), \
             patch('backend.telegram.bot.bot_request') as request:
            self.worker.process(1, message(text='/start'))
            request.assert_not_called()

    def test_pairing_link_is_sent_only_for_authorized_owner_and_pending_token(self):
        param = 'axx_' + 'x' * 43
        update = message(text='/start ' + param)
        configured = dict(BOT, public_url='https://axx.example.org/')
        with patch('backend.telegram.bot.load_bot', return_value=configured), \
             patch('backend.telegram.bot.PairingStore') as store, \
             patch('backend.telegram.bot.bot_request') as request:
            store.return_value.pending.return_value = True
            self.worker.process(1, update)
            body = request.call_args.args[2]
            self.assertEqual(body['chat_id'], 22)
            self.assertEqual(body['reply_markup']['inline_keyboard'][0][0]['web_app']['url'],
                             'https://axx.example.org/#pairing=' + param)
            store.return_value.pending.assert_called_once_with(ACCOUNT, param)
            request.reset_mock(); store.reset_mock()
            self.worker.process(2, message(owner=23, text='/start ' + param))
            request.assert_not_called()
            store.assert_not_called()

    def test_expired_and_invalid_pairing_does_not_expose_token(self):
        param = 'axx_' + 'x' * 43
        with patch('backend.telegram.bot.load_bot', return_value=dict(BOT, public_url='https://axx.example.org/')), \
             patch('backend.telegram.bot.PairingStore') as store, \
             patch('backend.telegram.bot.bot_request') as request:
            store.return_value.pending.return_value = False
            self.worker.process(1, message(text='/start ' + param))
            self.assertNotIn(param, str(request.call_args))
            request.reset_mock()
            self.worker.process(2, message(text='/start https://attacker.example/'))
            self.assertNotIn('attacker.example', str(request.call_args))

    def test_result_delivery_failure_becomes_unknown(self):
        self.worker.persist([message()])
        with patch('backend.telegram.bot.local_request', return_value={'text': 'ok'}), \
             patch('backend.telegram.bot.bot_request', side_effect=RuntimeError('failed')):
            self.worker.process(1, message())
        with self.worker.db() as db:
            self.assertEqual(db.execute('SELECT state FROM updates').fetchone()[0], 'unknown')


if __name__ == '__main__':
    unittest.main()
