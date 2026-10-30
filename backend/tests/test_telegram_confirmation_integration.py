"""Windows DPAPI + real command and Telegram ledgers, with a simulated effect."""
import logging
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid
from urllib.parse import parse_qs, urlsplit

from backend.actions.executor import ActionExecutor
from backend.chat_store import ChatStore
from backend.commands import CommandService
from backend.telegram.config import GRANTS, account_path, save_account, set_confirmation_policy, update_permissions
from backend.telegram.bot_config import save_bot
from backend.telegram.miniapp import MiniAppFacade
from backend.telegram.service import TelegramService
from backend.tests.test_telegram_miniapp import signed


@unittest.skipUnless(os.name == 'nt', 'requires Windows DPAPI')
class TelegramConfirmationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.grants = {key: key in ('conversation', 'pc_commands') for key in GRANTS}
        self.account = {'api_id': 12345, 'api_hash': 'a' * 32, 'session': 'private-session-fixture',
                        'account_id': 10, 'owner_id': 20, 'enabled': True, 'grants': dict(self.grants)}
        save_account(self.account, self.root)
        set_confirmation_policy(True, self.root)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.chats = ChatStore(self.root / 'state.db')
        self.addCleanup(self.executor.close)
        self.addCleanup(self.commands.close)
        self.addCleanup(self.chats.close)
        self.service = TelegramService(self.root, self.chats, self.commands, Mock(), lambda: {})
        self.effect = {'state': 'succeeded', 'postconditions_passed': True,
                       'output': {'fixture': 'verified'}, 'evidence': {}, 'duration_ms': 1}

    def prepare(self, text='/comando axx.system.telemetry'):
        result = self.service.admit_miniapp(20, text, str(uuid.uuid4()))
        self.assertEqual(result['state'], 'awaiting_approval')
        return result['operation_id']

    def test_sequence_requires_a_fresh_approval_for_each_step(self):
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            first = self.prepare('abre calculadora y abre bloc de notas')
            effect.assert_not_called()
            token = self.service.review_operation(20, first)['token']
            result = self.service.decide_operation(20, token, 'confirm')
            self.assertEqual(effect.call_count, 1)
            second = result['next_operation_id']
            self.assertEqual(self.commands.get(second)['state'], 'awaiting_approval')
            replay = self.service.decide_operation(20, token, 'confirm')
            self.assertEqual(replay['next_operation_id'], second)
            self.assertEqual(effect.call_count, 1)
            result = self.service.decide_operation(20, self.service.review_operation(20, second)['token'], 'confirm')
            self.assertNotIn('next_operation_id', result)
            self.assertIn('Secuencia terminada', result['text'])
            self.assertEqual(effect.call_count, 2)
            self.service.adapter.route.assert_not_called()

    def test_denied_or_unverified_step_never_prepares_the_rest(self):
        for decision, effect_result in [('cancel', self.effect), ('confirm', dict(self.effect, postconditions_passed=False))]:
            with self.subTest(decision=decision), patch.object(self.executor, 'execute_action', return_value=effect_result):
                first = self.prepare('abre calculadora y abre bloc de notas')
                result = self.service.decide_operation(20, self.service.review_operation(20, first)['token'], decision)
                self.assertNotIn('next_operation_id', result)
                self.assertIn('Secuencia detenida', result['text'])

    def test_sequence_does_not_resume_after_service_restart(self):
        first = self.prepare('abre calculadora y abre bloc de notas')
        self.service = TelegramService(self.root, self.chats, self.commands, Mock(), lambda: {})
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            result = self.service.decide_operation(20, self.service.review_operation(20, first)['token'], 'confirm')
            self.assertNotIn('next_operation_id', result)
            effect.assert_called_once()

    def test_permission_change_after_first_effect_stops_sequence(self):
        first = self.prepare('abre calculadora y abre bloc de notas')
        def completed_effect(*args, **kwargs):
            update_permissions(True, dict(self.grants, pc_commands=False), self.root)
            return self.effect
        with patch.object(self.executor, 'execute_action', side_effect=completed_effect) as effect:
            result = self.service.decide_operation(20, self.service.review_operation(20, first)['token'], 'confirm')
            self.assertNotIn('next_operation_id', result)
            effect.assert_called_once()
            with self.service._db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM inbox').fetchone()[0], 1)

    def test_status_distinguishes_admission_from_a_verified_effect(self):
        first = self.prepare()
        self.assertEqual(self.service.status()['messages'], 'admitted')
        self.assertEqual(self.service.status()['pc_commands'], 'not_verified')
        with patch.object(self.executor, 'execute_action', return_value=self.effect):
            self.service.decide_operation(20, self.service.review_operation(20, first)['token'], 'confirm')
        self.assertEqual(self.service.status()['pc_commands'], 'verified_receipt')

    def test_incomplete_sequence_never_calls_provider_or_prepares_partial_effect(self):
        result = self.service.admit_miniapp(20, 'abre calculadora y crea un dragon', str(uuid.uuid4()))
        self.assertEqual(result['state'], 'blocked')
        self.assertIn('paso 2', result['text'])
        self.service.adapter.route.assert_not_called()

    def test_real_core_ledger_and_dpapi_confirm_exactly_once(self):
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            operation = self.prepare()
            effect.assert_not_called()
            review = self.service.review_operation(20, operation)
            self.assertTrue(review['can_confirm'])
            self.assertEqual(review['inputs'], {})
            effect.assert_not_called()
            result = self.service.decide_operation(20, review['token'], 'confirm')
            self.assertEqual(result['state'], 'succeeded')
            self.assertTrue(result['postconditions_passed'])
            self.assertEqual(self.commands.get(operation)['state'], 'succeeded')
            self.assertTrue(self.service.decide_operation(20, review['token'], 'confirm')['replayed'])
            effect.assert_called_once()

    def test_real_grant_change_after_review_blocks_effect(self):
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            operation = self.prepare()
            token = self.service.review_operation(20, operation)['token']
            update_permissions(True, dict(self.grants, pc_commands=False), self.root)
            with self.assertRaises(ValueError):
                self.service.decide_operation(20, token, 'confirm')
            effect.assert_not_called()

    def test_pc_command_confirmation_works_without_conversation_or_inference(self):
        update_permissions(True, dict(self.grants, conversation=False), self.root)
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            operation = self.prepare()
            review = self.service.review_operation(20, operation)
            self.assertTrue(review['can_confirm'])
            self.assertEqual(self.service.decide_operation(20, review['token'], 'confirm')['state'], 'succeeded')
            effect.assert_called_once()
        self.service.adapter.route.assert_not_called()

    def test_pc_command_without_conversation_and_confirmation_permission_is_blocked(self):
        update_permissions(True, dict(self.grants, conversation=False), self.root)
        set_confirmation_policy(False, self.root)
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            result = self.service.admit_miniapp(20, '/comando axx.system.telemetry', str(uuid.uuid4()))
            self.assertEqual(result['state'], 'blocked')
            effect.assert_not_called()
        self.service.adapter.route.assert_not_called()

    def test_policy_revoked_during_resolution_cannot_fall_back_to_auto_execution(self):
        update_permissions(True, dict(self.grants, conversation=False), self.root)
        resolve = self.commands.resolve
        def revoke_during_resolution(*args, **kwargs):
            result = resolve(*args, **kwargs)
            set_confirmation_policy(False, self.root)
            return result
        with patch.object(self.commands, 'resolve', side_effect=revoke_during_resolution), \
             patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            result = self.service.admit_miniapp(20, '/comando axx.system.telemetry', str(uuid.uuid4()))
            self.assertEqual(result['state'], 'blocked')
            effect.assert_not_called()
        self.service.adapter.route.assert_not_called()

    def test_policy_reenable_invalidates_old_token(self):
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            operation = self.prepare()
            token = self.service.review_operation(20, operation)['token']
            set_confirmation_policy(False, self.root)
            set_confirmation_policy(True, self.root)
            with self.assertRaises(ValueError):
                self.service.decide_operation(20, token, 'confirm')
            effect.assert_not_called()
            new_token = self.service.review_operation(20, operation)['token']
            self.assertNotEqual(new_token, token)
            self.assertEqual(self.service.decide_operation(20, new_token, 'confirm')['state'], 'succeeded')
            effect.assert_called_once()

    def test_pc_reserved_command_cannot_receive_remote_token(self):
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            operation = self.prepare('/comando axx.shell.cmd {"script":"echo fixture"}')
            review = self.service.review_operation(20, operation)
            self.assertFalse(review['can_confirm'])
            self.assertNotIn('token', review)
            self.assertTrue(review['reason'])
            effect.assert_not_called()

    def test_policy_update_preserves_account_bytes_and_does_not_log_secrets(self):
        before = account_path(self.root).read_bytes()
        records = []
        class Capture(logging.Handler):
            def emit(self, record): records.append(record.getMessage())
        handler = Capture()
        logging.getLogger().addHandler(handler)
        try:
            set_confirmation_policy(False, self.root)
            set_confirmation_policy(True, self.root)
        finally:
            logging.getLogger().removeHandler(handler)
        self.assertEqual(account_path(self.root).read_bytes(), before)
        self.assertNotIn(self.account['session'], '\n'.join(records))
        self.assertNotIn(self.account['api_hash'], '\n'.join(records))

    def test_miniapp_http_pair_review_decision_and_replay(self):
        token = '12345:' + 'a' * 35
        origin = 'https://example.org'
        save_bot({'token': token, 'enabled': True, 'public_url': origin}, self.root)
        facade = MiniAppFacade(self.root, self.service)
        port = facade.start()
        self.addCleanup(facade.close)

        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                headers = dict(headers or {})
                if body is not None:
                    headers['Content-Type'] = 'application/json'
                connection.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                cookies = response.msg.get_all('Set-Cookie') or []
                return response.status, cookies, json.loads(response.read())
            finally:
                connection.close()

        pairing = facade.pairing.create_pairing(self.account, 'FixtureBot')
        pairing_token = parse_qs(urlsplit(pairing['url']).query)['start'][0]
        code, cookies, session = request('POST', '/api/session',
            {'init_data': signed(owner=20, token=token), 'pairing_token': pairing_token}, {'Origin': origin})
        self.assertEqual(code, 200)
        headers = {'Origin': origin, 'Cookie': '; '.join(cookie.split(';')[0] for cookie in cookies)}
        csrf = session['csrf']
        with patch.object(self.executor, 'execute_action', return_value=self.effect) as effect:
            code, _, admission = request('POST', '/api/chat',
                {'text': '/comando axx.system.telemetry', 'request_id': str(uuid.uuid4()), 'csrf': csrf}, headers)
            self.assertEqual((code, admission['state']), (200, 'awaiting_approval'))
            operation = admission['operation_id']
            code, _, activity = request('GET', '/api/activity', headers={'Cookie': headers['Cookie']})
            self.assertEqual(code, 200)
            self.assertTrue(any(item['id'] == operation for item in activity['items']))
            code, _, review = request('POST', '/api/review', {'operation_id': operation, 'csrf': csrf}, headers)
            self.assertEqual(code, 200)
            self.assertTrue(review['can_confirm'])
            decision = {'token': review['token'], 'decision': 'confirm', 'csrf': csrf}
            self.assertEqual(request('POST', '/api/decision', dict(decision, csrf='wrong'), headers)[0], 403)
            effect.assert_not_called()
            code, _, result = request('POST', '/api/decision', decision, headers)
            self.assertEqual((code, result['state'], result['postconditions_passed']), (200, 'succeeded', True))
            code, _, replay = request('POST', '/api/decision', decision, headers)
            self.assertEqual((code, replay['state']), (200, 'succeeded'))
            effect.assert_called_once()


if __name__ == '__main__':
    unittest.main()
