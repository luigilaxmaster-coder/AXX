"""Offline contracts for owner-bound, one-use Telegram command confirmations."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch

from backend.chat_store import ChatStore
from backend.telegram.service import TelegramService


class TelegramConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.chats = ChatStore(Path(self.temp.name) / 'state.db')
        self.addCleanup(self.chats.close)
        self.account = {'account_id': 10, 'owner_id': 20, 'session': 'session-fixture', 'enabled': True,
                        'grants': {'conversation': True, 'pc_commands': True}}
        self.policy = {'enabled': True}
        self.fingerprint = 'snapshot-1'
        for name, fn in [('load_account', lambda _: copy.deepcopy(self.account)),
                         ('confirmation_policy', lambda _: dict(self.policy)),
                         ('confirmation_fingerprint', lambda _: self.fingerprint + '|' + self.account['session'] + '|' + str(self.policy['enabled']))]:
            patcher = patch('backend.telegram.service.' + name, side_effect=fn, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.commands = Mock()
        self.adapter = Mock()
        self.service = TelegramService(self.temp.name, self.chats, self.commands, self.adapter, lambda: {})
        self.operation = str(uuid.uuid4())
        self.preview = {'operation_id': self.operation, 'title': 'Operación de prueba',
                        'description': 'Ejecutar la operación revisada', 'risk': 'medium',
                        'inputs': {'name': 'fixture'}, 'plan_hash': 'a' * 64,
                        'expires_at': time.time() + 120, 'state': 'awaiting_approval', 'eligible': True, 'reason': None}
        self.commands.remote_review.side_effect = lambda _id: copy.deepcopy(self.preview)
        def confirm(_id, _plan_hash, authorization_check):
            authorization_check()
            return {'state': 'succeeded', 'operation_id': self.operation,
                    'output': 'ok', 'postconditions_passed': True}
        self.commands.confirm_remote.side_effect = confirm
        with self.service._db() as db:
            db.execute('INSERT INTO inbox(id,state,response,operation_id,created,account,peer) VALUES(?,?,?,?,?,?,?)',
                       (self.operation, 'awaiting_approval', None, self.operation, time.time(), 10, 20))

    def review(self):
        result = self.service.review_operation(20, self.operation)
        self.assertTrue(result['can_confirm'])
        self.assertEqual(result['plan_hash'], 'a' * 64)
        self.assertEqual(result['inputs'], {'name': 'fixture'})
        self.assertIsInstance(result['token'], str)
        return result

    def blocked_decision(self, owner, token):
        try:
            result = self.service.decide_operation(owner, token, 'confirm')
        except ValueError:
            return
        self.assertIn(result['state'], {'blocked', 'expired', 'failed', 'unknown'})

    def test_review_and_confirmation_use_authoritative_hash_once(self):
        reviewed = self.review()
        result = self.service.decide_operation(20, reviewed['token'], 'confirm')
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        call = self.commands.confirm_remote.call_args
        self.assertEqual(call.args[:2], (self.operation, self.preview['plan_hash']))
        self.assertTrue(callable(call.kwargs['authorization_check']))
        repeat = self.service.decide_operation(20, reviewed['token'], 'confirm')
        self.assertTrue(repeat.get('replayed'))
        self.commands.confirm_remote.assert_called_once()

    def test_disabled_policy_or_grant_never_issues_confirmation_token(self):
        self.policy['enabled'] = False
        result = self.service.review_operation(20, self.operation)
        self.assertFalse(result['can_confirm'])
        self.assertNotIn('token', result)
        self.policy['enabled'] = True
        self.account['grants']['pc_commands'] = False
        try:
            result = self.service.review_operation(20, self.operation)
        except ValueError:
            pass
        else:
            self.assertFalse(result['can_confirm'])
            self.assertNotIn('token', result)
        self.commands.confirm_remote.assert_not_called()

    def test_wrong_owner_and_unknown_operation_are_rejected(self):
        reviewed = self.review()
        self.blocked_decision(21, reviewed['token'])
        with self.assertRaises(ValueError):
            self.service.review_operation(20, str(uuid.uuid4()))
        self.commands.confirm_remote.assert_not_called()

    def test_new_review_invalidates_previous_token(self):
        old = self.review()['token']
        new = self.review()['token']
        self.assertNotEqual(old, new)
        self.blocked_decision(20, old)
        self.assertEqual(self.service.decide_operation(20, new, 'confirm')['state'], 'succeeded')
        self.commands.confirm_remote.assert_called_once()

    def test_changed_authoritative_plan_cannot_dispatch(self):
        token = self.review()['token']
        self.preview['plan_hash'] = 'b' * 64
        self.blocked_decision(20, token)
        self.commands.confirm_remote.assert_not_called()

    def test_dispatch_callback_rechecks_permission(self):
        token = self.review()['token']
        effects = []
        def revoked(_id, _hash, authorization_check):
            self.account['grants']['pc_commands'] = False
            authorization_check()
            effects.append('executed')
        self.commands.confirm_remote.side_effect = revoked
        result = self.service.decide_operation(20, token, 'confirm')
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(effects, [])

    def test_dispatch_callback_rejects_token_that_expires_after_claim(self):
        now = time.time()
        self.preview['expires_at'] = now + 300
        with patch('backend.telegram.service.time.time', return_value=now):
            token = self.review()['token']
            effects = []
            def late(_id, _hash, authorization_check):
                with patch('backend.telegram.service.time.time', return_value=now + 121):
                    authorization_check()
                    effects.append('executed')
            self.commands.confirm_remote.side_effect = late
            result = self.service.decide_operation(20, token, 'confirm')
        self.assertIn(result['state'], {'unknown', 'expired', 'failed', 'blocked'})
        self.assertEqual(effects, [])

    def test_revocation_and_session_or_policy_changes_invalidate_token(self):
        for mutation in ('disable', 'owner', 'account', 'session', 'grant', 'policy', 'revision'):
            with self.subTest(mutation=mutation):
                self.operation = str(uuid.uuid4())
                self.preview['operation_id'] = self.operation
                with self.service._db() as db:
                    db.execute('INSERT INTO inbox(id,state,response,operation_id,created,account,peer) VALUES(?,?,?,?,?,?,?)',
                               (self.operation, 'awaiting_approval', None, self.operation, time.time(), 10, 20))
                self.account.update(account_id=10, owner_id=20, session='session-fixture', enabled=True)
                self.account['grants']['pc_commands'] = True
                self.policy['enabled'] = True
                self.fingerprint = 'snapshot-1'
                token = self.review()['token']
                if mutation == 'disable': self.account['enabled'] = False
                elif mutation == 'owner': self.account['owner_id'] = 21
                elif mutation == 'account': self.account['account_id'] = 11
                elif mutation == 'session': self.account['session'] = 'different-session'
                elif mutation == 'grant': self.account['grants']['pc_commands'] = False
                elif mutation == 'policy': self.policy['enabled'] = False
                else: self.fingerprint = 'snapshot-2'
                self.blocked_decision(20, token)
        self.commands.confirm_remote.assert_not_called()

    def test_expired_token_and_ineligible_preview_cannot_dispatch(self):
        token = self.review()['token']
        with patch('backend.telegram.service.time.time', return_value=time.time() + 121):
            self.blocked_decision(20, token)
        self.preview.update(eligible=False, reason='Esta operación requiere revisión local.')
        result = self.service.review_operation(20, self.operation)
        self.assertFalse(result['can_confirm'])
        self.assertNotIn('token', result)
        self.assertTrue(result['reason'])
        self.commands.confirm_remote.assert_not_called()

    def test_uncertain_execution_and_concurrent_replay_never_dispatch_twice(self):
        token = self.review()['token']
        entered, release = threading.Event(), threading.Event()
        result = {}
        def execute(_id, _hash, authorization_check):
            authorization_check()
            entered.set()
            release.wait(3)
            raise RuntimeError('uncertain private details')
        self.commands.confirm_remote.side_effect = execute
        def run():
            try: result['value'] = self.service.decide_operation(20, token, 'confirm')
            except Exception as exc: result['error'] = exc
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(3))
        try:
            self.blocked_decision(20, token)
        finally:
            release.set()
            worker.join(3)
        self.blocked_decision(20, token)
        self.commands.confirm_remote.assert_called_once()

    def test_token_never_appears_in_inbox_or_activity(self):
        token = self.review()['token']
        with self.service._db() as db:
            dump = '\n'.join(db.iterdump())
        self.assertNotIn(token, dump)
        self.assertNotIn(token, json.dumps(self.service.activity(20)))

    def test_unknown_result_is_not_redispatched_after_restart(self):
        token = self.review()['token']
        self.commands.confirm_remote.side_effect = RuntimeError('uncertain')
        try:
            self.service.decide_operation(20, token, 'confirm')
        except (ValueError, RuntimeError):
            pass
        self.service = TelegramService(self.temp.name, self.chats, self.commands, self.adapter, lambda: {})
        self.blocked_decision(20, token)
        self.commands.confirm_remote.assert_called_once()

    def test_restart_expires_pending_nonce_and_fresh_review_allows_new_one(self):
        old_token = self.review()['token']
        self.service = TelegramService(self.temp.name, self.chats, self.commands, self.adapter, lambda: {})
        self.blocked_decision(20, old_token)
        self.commands.confirm_remote.assert_not_called()
        new_token = self.review()['token']
        self.assertNotEqual(old_token, new_token)
        self.assertEqual(self.service.decide_operation(20, new_token, 'confirm')['state'], 'succeeded')
        self.commands.confirm_remote.assert_called_once()

    def test_cancel_decision_never_dispatches_the_operation(self):
        token = self.review()['token']
        self.commands.cancel.return_value = {'state': 'cancelled', 'operation_id': self.operation}
        result = self.service.decide_operation(20, token, 'cancel')
        self.assertIn(result['state'], {'cancelled', 'cancel_requested'})
        self.commands.confirm_remote.assert_not_called()

    def test_cancel_does_not_claim_completed_or_running_operation_was_cancelled(self):
        for state in ('running', 'succeeded'):
            with self.subTest(state=state):
                self.operation = str(uuid.uuid4())
                self.preview['operation_id'] = self.operation
                with self.service._db() as db:
                    db.execute('INSERT INTO inbox(id,state,response,operation_id,created,account,peer) VALUES(?,?,?,?,?,?,?)',
                               (self.operation, 'awaiting_approval', None, self.operation, time.time(), 10, 20))
                token = self.review()['token']
                self.commands.cancel.return_value = {'state': state, 'operation_id': self.operation,
                                                     'postconditions_passed': state == 'succeeded'}
                result = self.service.decide_operation(20, token, 'cancel')
                self.assertNotEqual(result['state'], 'cancelled')
                if state == 'succeeded':
                    self.assertEqual(result['state'], 'succeeded')
                    self.assertTrue(result['postconditions_passed'])
                else:
                    self.assertIn(result['state'], {'running', 'cancel_requested', 'unknown'})
        self.commands.confirm_remote.assert_not_called()


if __name__ == '__main__':
    unittest.main()
