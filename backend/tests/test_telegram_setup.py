import asyncio
from concurrent.futures import Future
from pathlib import Path
import queue
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.telegram.setup import Setup, SetupError, setup_error


SessionPasswordNeededError = type('SessionPasswordNeededError', (Exception,), {})
PasswordHashInvalidError = type('PasswordHashInvalidError', (Exception,), {})
PhoneCodeExpiredError = type('PhoneCodeExpiredError', (Exception,), {})
FloodWaitError = type('FloodWaitError', (Exception,), {})


class TelegramSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.obj = Setup.__new__(Setup)
        self.obj.pending = (1, 'a' * 32, '+12025550123', 99)
        self.obj.code_hash = 'code-hash'
        self.obj.need_password = False
        self.obj.lease = None
        self.obj.client = SimpleNamespace(sign_in=AsyncMock(),
            get_me=AsyncMock(return_value=SimpleNamespace(id=42, bot=False)),
            disconnect=AsyncMock(), session=SimpleNamespace(save=Mock(return_value='session-secret')))
        errors = ModuleType('telethon.errors')
        errors.SessionPasswordNeededError = SessionPasswordNeededError
        telethon = ModuleType('telethon')
        telethon.errors = errors
        modules = patch.dict(sys.modules, {'telethon': telethon, 'telethon.errors': errors})
        modules.start()
        self.addCleanup(modules.stop)
        self.path_patch = patch('backend.telegram.setup.account_path', return_value=Path(self.temp.name) / 'account.dpapi')
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.save_patch = patch('backend.telegram.setup.save_account')
        self.save = self.save_patch.start()
        self.addCleanup(self.save_patch.stop)

    def test_login_without_two_factor_password(self):
        client = self.obj.client
        asyncio.run(self.obj._sign_in('12345', '', {'conversation': True}, False))
        client.sign_in.assert_awaited_once_with(phone='+12025550123', code='12345', phone_code_hash='code-hash')
        self.assertEqual(self.save.call_args.args[0]['account_id'], 42)
        self.assertFalse(self.save.call_args.args[0]['enabled'])
        client.disconnect.assert_awaited_once()

    def test_two_factor_request_then_invalid_password_and_recovery(self):
        client = self.obj.client
        client.sign_in.side_effect = [SessionPasswordNeededError('private marker'),
                                      PasswordHashInvalidError('private marker'), None]
        with self.assertRaisesRegex(SetupError, 'TWO_FACTOR_REQUIRED'):
            asyncio.run(self.obj._sign_in('12345', '', {'conversation': True}, False))
        self.assertTrue(self.obj.need_password)
        self.assertEqual(self.obj.code_hash, 'code-hash')
        with self.assertRaises(PasswordHashInvalidError):
            asyncio.run(self.obj._sign_in('', 'bad-password', {'conversation': True}, False))
        self.assertTrue(self.obj.need_password)
        self.assertEqual(self.obj.code_hash, 'code-hash')
        self.save.assert_not_called()
        asyncio.run(self.obj._sign_in('', 'correct-password', {'conversation': True}, False))
        self.assertEqual(client.sign_in.await_count, 3)
        self.save.assert_called_once()

    def test_bot_account_is_never_saved(self):
        self.obj.client.get_me.return_value = SimpleNamespace(id=42, bot=True)
        with self.assertRaisesRegex(SetupError, 'BOT_ACCOUNT'):
            asyncio.run(self.obj._sign_in('12345', '', {'conversation': True}, False))
        self.save.assert_not_called()

    def test_error_messages_do_not_echo_exception_details(self):
        for error in (ValueError('private marker'), PasswordHashInvalidError('private marker'),
                      SetupError('private marker'), OSError('private marker')):
            with self.subTest(error=type(error).__name__):
                code, message, wait = setup_error(error)
                self.assertNotIn('private marker', code + message)
                self.assertEqual(wait, 0)
        self.assertEqual(setup_error(PasswordHashInvalidError('private marker'))[0], 'PASSWORD_HASH_INVALID')

    def poll(self, error, now=100):
        self.obj.closed = False
        self.obj.busy = True
        self.obj.existing = False
        self.obj.retry_at = 0
        self.obj.stage = 'Inicio'
        self.obj.root = Mock()
        self.obj.status = Mock()
        self.obj.password_label = Mock()
        self.obj.fields = {'password': Mock()}
        self.obj.send_button = Mock()
        self.obj.sign_button = Mock()
        self.obj.save_button = Mock()
        self.obj.events = queue.Queue()
        future = Future()
        future.set_exception(error)
        self.obj.events.put((future, Mock()))
        with patch('backend.telegram.setup.time.monotonic', return_value=now):
            self.obj._poll()

    def test_code_expired_resets_login_state(self):
        self.obj.need_password = True
        self.poll(PhoneCodeExpiredError('private marker'))
        self.assertIsNone(self.obj.code_hash)
        self.assertFalse(self.obj.need_password)
        self.obj.sign_button.configure.assert_called_with(state='disabled')
        self.assertNotIn('private marker', str(self.obj.status.set.call_args))

    def test_flood_wait_disables_retry_until_deadline(self):
        error = FloodWaitError('private marker')
        error.seconds = 30
        self.poll(error)
        self.assertEqual(self.obj.retry_at, 130)
        self.obj.send_button.configure.assert_called_with(state='disabled')
        self.obj.sign_button.configure.assert_called_with(state='disabled')
        with patch('backend.telegram.setup.time.monotonic', return_value=129):
            self.obj.send_code()
            self.obj.sign_in()
        self.save.assert_not_called()
        with patch('backend.telegram.setup.time.monotonic', return_value=130):
            self.obj._poll()
        self.obj.send_button.configure.assert_called_with(state='normal')
        self.obj.sign_button.configure.assert_called_with(state='normal')
        self.assertNotIn('private marker', str(self.obj.status.set.call_args))


if __name__ == '__main__':
    unittest.main()
