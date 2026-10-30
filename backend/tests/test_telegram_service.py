import copy
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import Mock, patch

from backend.chat_store import ChatStore
from backend.telegram.service import TelegramService


class TelegramServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.chats = ChatStore(Path(self.temp.name) / 'state.db')
        self.addCleanup(self.chats.close)
        self.account = {'account_id': 10, 'owner_id': 20, 'enabled': True,
                        'grants': {'conversation': True, 'pc_commands': True}}
        self.load = patch('backend.telegram.service.load_account', side_effect=lambda _: copy.deepcopy(self.account))
        self.load.start()
        self.addCleanup(self.load.stop)
        self.commands = Mock()
        self.commands.resolve.return_value = {'match': 'none'}
        self.commands.prepare.return_value = {'state': 'prepared'}
        self.commands.execute.return_value = {'state': 'succeeded', 'postconditions_passed': True, 'output': 'ok'}
        self.adapter = Mock()
        self.adapter.route.return_value = {'ok': True, 'message': {'content': 'respuesta'}}
        self.preferences = {'provider': 'bridge', 'model': 'selected', 'provider_name': 'selected-provider', 'selection_mode': 'manual'}
        self.service = TelegramService(self.temp.name, self.chats, self.commands, self.adapter, lambda: self.preferences)

    def body(self, text='hola', message=1, **kwargs):
        return {'account_id': 10, 'peer_id': 20, 'message_id': message,
                'sent_at': time.time(), 'kind': 'text', 'text': text, **kwargs}

    def command(self):
        self.commands.resolve.return_value = {'match': 'exact', 'command_id': 'allowed', 'inputs': {}}

    def inbox_count(self):
        with self.service._db() as db:
            return db.execute('SELECT count(*) FROM inbox').fetchone()[0]

    def test_invalid_identity_or_disabled_rejected_before_admission(self):
        for body in (self.body(peer_id=21), self.body(account_id=11), self.body(peer_id=True)):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.service.admit(body)
        self.account['enabled'] = False
        with self.assertRaises(ValueError):
            self.service.admit(self.body())
        self.assertEqual(self.inbox_count(), 0)
        self.commands.resolve.assert_not_called()
        self.adapter.route.assert_not_called()

    def test_duplicate_request_never_repeats_command_or_conversation(self):
        self.command()
        body = self.body('/accion')
        first = self.service.admit(body)
        self.assertEqual(first['state'], 'succeeded')
        self.assertEqual(self.service.admit(body), first)
        self.commands.prepare.assert_called_once()
        self.commands.execute.assert_called_once()
        self.adapter.route.assert_not_called()
        self.commands.resolve.return_value = {'match': 'none'}
        text = self.body('hola', message=2)
        self.assertEqual(self.service.admit(text)['state'], 'succeeded')
        self.service.admit(text)
        self.adapter.route.assert_called_once()

    def test_expired_input_never_dispatches(self):
        self.command()
        result = self.service.admit(self.body('/accion', sent_at=time.time()-121))
        self.assertEqual(result['state'], 'expired')
        self.commands.resolve.assert_not_called()
        self.commands.execute.assert_not_called()
        self.adapter.route.assert_not_called()

    def test_pending_approval_never_executes_and_uses_persisted_mode(self):
        self.command()
        self.commands.prepare.return_value = {'state': 'awaiting_approval'}
        result = self.service.admit(self.body('/accion'))
        self.assertEqual(result['state'], 'awaiting_approval')
        self.assertEqual(self.commands.prepare.call_args.kwargs['command_mode'], 'ask')
        self.commands.execute.assert_not_called()

    def test_revoked_grant_between_prepare_and_execute_cancels(self):
        self.command()
        def prepare(*args, **kwargs):
            self.account['grants']['pc_commands'] = False
            return {'state': 'prepared'}
        self.commands.prepare.side_effect = prepare
        result = self.service.admit(self.body('/accion'))
        self.assertEqual(result['state'], 'blocked')
        self.commands.cancel.assert_called_once()
        self.commands.execute.assert_not_called()

    def test_unknown_request_is_never_replayed_after_restart(self):
        self.command()
        self.commands.execute.side_effect = RuntimeError('uncertain')
        body = self.body('/accion')
        self.assertEqual(self.service.admit(body)['state'], 'unknown')
        restarted = TelegramService(self.temp.name, self.chats, self.commands, self.adapter, lambda: self.preferences)
        self.assertEqual(restarted.admit(body)['state'], 'unknown')
        self.commands.execute.assert_called_once()

    def test_inflight_request_is_unknown_after_restart_without_replay(self):
        self.command()
        body = self.body('/accion')
        self.service.admit(body)
        with self.service._db() as db:
            db.execute("UPDATE inbox SET state='running', response=NULL")
        restarted = TelegramService(self.temp.name, self.chats, self.commands, self.adapter, lambda: self.preferences)
        self.assertEqual(restarted.admit(body)['state'], 'unknown')
        self.commands.execute.assert_called_once()

    def test_control_priority_while_busy_and_cross_account_operation_rejected(self):
        self.command()
        first = self.service.admit(self.body('/accion'))
        operation = first['operation_id']
        self.account.update(account_id=30, owner_id=40)
        cancel = self.body('/cancelar '+operation, account_id=30, peer_id=40, message=2)
        with self.service.lock:
            self.assertEqual(self.service.admit(cancel)['state'], 'blocked')
        self.commands.cancel.assert_not_called()

    def test_cancel_priority_works_for_owner_but_rejects_stale_control(self):
        self.command()
        operation = self.service.admit(self.body('/accion'))['operation_id']
        with self.service.lock:
            stale = self.body('/cancelar '+operation, message=2, sent_at=time.time()-121)
            self.assertEqual(self.service.admit(stale)['state'], 'expired')
            self.commands.cancel.assert_not_called()
            fresh = self.body('/cancelar '+operation, message=3)
            self.assertEqual(self.service.admit(fresh)['state'], 'cancel_requested')
            self.adapter.cancel.assert_called_once_with(operation)
        self.commands.cancel.assert_called_once_with(operation)

    def test_selected_unsupported_provider_has_no_fallback(self):
        self.preferences['provider'] = 'chatgpt'
        self.assertEqual(self.service.admit(self.body())['state'], 'blocked')
        self.adapter.route.assert_not_called()

    def test_incomplete_manual_selection_does_not_route(self):
        for index, field in enumerate(('model', 'provider_name'), 1):
            with self.subTest(field=field):
                self.preferences = {'provider': 'bridge', 'model': 'selected',
                                    'provider_name': 'selected-provider', 'selection_mode': 'manual'}
                self.preferences[field] = ''
                self.assertEqual(self.service.admit(self.body(message=index))['state'], 'blocked')
        self.adapter.route.assert_not_called()

    def test_cancel_rechecks_grant_after_initial_admission(self):
        self.command()
        operation = self.service.admit(self.body('/accion'))['operation_id']
        original = copy.deepcopy(self.account)
        revoked = copy.deepcopy(self.account)
        revoked['grants']['pc_commands'] = False
        with patch.object(self.service, '_authorize', side_effect=[original, revoked]):
            result = self.service.admit(self.body('/cancelar '+operation, message=2))
        self.assertEqual(result['state'], 'blocked')
        self.commands.cancel.assert_not_called()

    def test_bot_and_account_events_are_isolated_but_share_owner_conversation(self):
        first = self.service.admit(self.body('from account', message=1))
        bot = {'peer_id': 20, 'event_id': 0, 'text': 'from bot', 'sent_at': time.time()}
        second = self.service.admit_bot(bot)
        self.assertEqual(first['state'], 'succeeded')
        self.assertEqual(second['state'], 'succeeded')
        self.assertEqual(self.inbox_count(), 2)
        self.assertEqual(self.adapter.route.call_count, 2)
        ids = [call.args[0]['conversation_id'] for call in self.adapter.route.call_args_list]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(self.service.admit_bot(bot), second)
        self.assertEqual(self.adapter.route.call_count, 2)

    def test_bot_wrong_owner_and_extra_approval_are_rejected(self):
        body = {'peer_id': 21, 'event_id': 1, 'text': '/accion', 'sent_at': time.time()}
        with self.assertRaises(ValueError):
            self.service.admit_bot(body)
        body['peer_id'] = 20
        body['approved'] = True
        with self.assertRaises(ValueError):
            self.service.admit_bot(body)
        self.assertEqual(self.inbox_count(), 0)
        self.commands.resolve.assert_not_called()
        self.commands.execute.assert_not_called()

    def test_miniapp_request_dedup_and_wrong_owner_rejected(self):
        request_id = str(uuid.uuid4())
        result = self.service.admit_miniapp(20, 'hola', request_id)
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(self.service.admit_miniapp(20, 'hola', request_id), result)
        self.adapter.route.assert_called_once()
        with self.assertRaises(ValueError):
            self.service.admit_miniapp(21, 'hola', str(uuid.uuid4()))
        with self.assertRaises(TypeError):
            self.service.admit_miniapp(20, 'hola', str(uuid.uuid4()), approved=True)
        self.assertEqual(self.inbox_count(), 1)

    def test_diagnostics_and_history_do_not_create_conversations(self):
        self.preferences = {}
        state = self.service.diagnostics(20)
        self.assertEqual(state['conversation']['reason_code'], 'SELECTED_PROVIDER_NOT_SYNCED')
        self.assertIsNone(state['conversation']['model'])
        self.assertEqual(self.service.history(20), {'messages': [], 'has_more': False})
        self.assertEqual(self.chats.list()['conversations'], [])
        with self.assertRaises(ValueError):
            self.service.history(21)

    def test_history_requires_grant_and_remains_owner_bound(self):
        self.service.admit(self.body('private from owner'))
        history = self.service.history(20)
        self.assertTrue(any(item['text'] == 'private from owner' for item in history['messages']))
        self.assertTrue(all(set(item) <= {'id','role','text','status','at'} for item in history['messages']))
        self.account['grants']['conversation'] = False
        with self.assertRaises(ValueError):
            self.service.history(20)
        self.account.update(account_id=30, owner_id=40)
        self.account['grants']['conversation'] = True
        self.assertEqual(self.service.history(40), {'messages': [], 'has_more': False})

    def test_activity_cancel_only_owned_permitted_commands(self):
        self.command()
        self.commands.prepare.return_value = {'state': 'awaiting_approval'}
        operation = self.service.admit(self.body('/accion'))['operation_id']
        self.commands.get.return_value = {'operation_id': operation, 'state': 'awaiting_approval', 'command_id': 'allowed', 'secret': 'private'}
        item = self.service.activity(20)['items'][0]
        self.assertTrue(item['can_cancel'])
        self.assertNotIn('secret', item)
        with self.assertRaises(ValueError):
            self.service.cancel_operation(21, operation)
        with self.assertRaises(ValueError):
            self.service.cancel_operation(20, str(uuid.uuid4()))
        self.commands.cancel.assert_not_called()
        self.account['grants']['pc_commands'] = False
        with self.assertRaises(ValueError):
            self.service.cancel_operation(20, operation)
        self.commands.cancel.assert_not_called()
        self.account['grants']['pc_commands'] = True
        self.assertEqual(self.service.cancel_operation(20, operation), {'state':'cancel_requested'})
        self.commands.cancel.assert_called_once_with(operation)

    def test_conversation_history_is_separate_between_accounts(self):
        self.service.admit(self.body('secreto primera cuenta'))
        self.account.update(account_id=30, owner_id=40)
        self.service.admit(self.body('segunda cuenta', account_id=30, peer_id=40))
        request = self.adapter.route.call_args.args[0]
        self.assertNotIn('secreto primera cuenta', str(request['messages']))
        self.assertIn('segunda cuenta', str(request['messages']))


if __name__ == '__main__':
    unittest.main()
