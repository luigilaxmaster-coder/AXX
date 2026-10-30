"""Offline local setup contracts; no Telegram authentication or live account."""
import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.telegram.config import GRANTS
from backend.telegram.desktop import DesktopTelegram


APP = {'api_id': 12345, 'api_hash': 'a' * 32, 'owner_id': 22}
ACCOUNT = {**APP, 'account_id': 11, 'session': 'private-session-fixture', 'enabled': True,
           'grants': {key: key == 'pc_commands' for key in GRANTS}}


class DesktopTelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = DesktopTelegram(self.temp.name)
        self.addCleanup(self.manager.stop_reconcile.set)

    def test_status_never_returns_credentials(self):
        bot = {'token': 'sensitive-token-fixture', 'enabled': True, 'public_url': 'https://example.org/', 'username': 'bot_name'}
        with patch('backend.telegram.desktop.load_account', return_value=ACCOUNT), \
             patch('backend.telegram.desktop.load_bot', return_value=bot):
            status = self.manager.status()
        encoded = json.dumps(status)
        self.assertNotIn('private-session-fixture', encoded)
        self.assertNotIn('sensitive-token-fixture', encoded)
        self.assertNotIn(APP['api_hash'], encoded)
        self.assertTrue(status['account']['configured'])
        self.assertTrue(status['account']['grants']['pc_commands'])

    def test_configure_app_validates_and_uses_protected_storage(self):
        with patch('backend.telegram.desktop.load_account', side_effect=FileNotFoundError), \
             patch('backend.telegram.desktop._dpapi_encrypt', side_effect=lambda raw: b'encrypted:' + raw):
            self.assertEqual(self.manager.configure_app(APP), {'state': 'saved'})
        self.assertTrue((Path(self.temp.name) / 'telegram' / 'app.dpapi').read_bytes().startswith(b'encrypted:'))
        for change in ({'owner_id': 0}, {'api_id': True}, {'api_hash': 'short'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.configure_app({**APP, **change})

    def test_bot_configuration_runs_in_background_and_returns_no_token(self):
        result = {'local_saved': True, 'account_enabled': True, 'menu_configured': False,
                  'error_code': 'OWNER_CHAT_NOT_STARTED', 'retry_after': 0}
        with patch('backend.telegram.desktop.configure_bot_remote', return_value=result):
            self.assertEqual(self.manager.configure_bot({'token': 'fixture-secret', 'enabled': True, 'public_url': ''}), {'state': 'running'})
            for _ in range(100):
                if self.manager.bot_job['state'] != 'running':
                    break
                threading_event.wait(.005)
        self.assertEqual(self.manager.bot_job['error_code'], 'OWNER_CHAT_NOT_STARTED')
        self.assertNotIn('fixture-secret', str(self.manager.bot_job))

    def test_invalid_permissions_rejected(self):
        with self.assertRaises(ValueError):
            self.manager.update_permissions({'enabled': True, 'grants': {'conversation': True}})

    def test_pause_resume_preserve_grants_and_toggle_authorization(self):
        self.manager.service = Mock()
        account = dict(ACCOUNT, grants=dict(ACCOUNT['grants']))
        with patch('backend.telegram.desktop._file_lease', return_value=nullcontext()), \
             patch('backend.telegram.desktop.load_account', side_effect=lambda _: dict(account, grants=dict(account['grants']))), \
             patch('backend.telegram.desktop._save_account') as save:
            self.assertEqual(self.manager.pause()['state'], 'paused')
            disabled = save.call_args.args[0]
            self.assertFalse(disabled['enabled'])
            self.assertEqual(disabled['grants'], ACCOUNT['grants'])
            self.assertEqual(self.manager.resume()['state'], 'start_requested')
            enabled = save.call_args.args[0]
            self.assertTrue(enabled['enabled'])
            self.assertEqual(enabled['grants'], ACCOUNT['grants'])
        self.manager.service.close.assert_called_once()
        self.manager.service.start.assert_called_once()
        self.manager.service.start_bot.assert_called_once()

    def test_reconcile_waits_for_qr_and_respects_disabled_and_closed(self):
        self.manager.service = Mock()
        self.manager.facade = Mock()
        with patch('backend.telegram.desktop.load_account', return_value={**ACCOUNT, 'enabled': False}):
            self.manager.reconcile()
        self.manager.service.start.assert_not_called()
        self.manager.qr = {'state': 'waiting_qr'}
        with patch('backend.telegram.desktop.load_account', return_value=ACCOUNT):
            self.manager.reconcile()
        self.manager.service.start.assert_not_called()
        self.manager.qr = {'state': 'saved'}
        with patch('backend.telegram.desktop.load_account', return_value=ACCOUNT):
            self.manager.reconcile()
        self.manager.service.start.assert_called_once()
        self.manager.service.start_bot.assert_called_once()
        self.manager.facade.start.assert_called_once_with(port=6451)
        self.manager.closed = True
        with patch('backend.telegram.desktop.load_account', return_value=ACCOUNT):
            self.manager.reconcile()
        self.manager.service.start.assert_called_once()

    def test_reconcile_continues_after_account_start_failure(self):
        self.manager.service = Mock()
        self.manager.service.start.side_effect = OSError('sensitive-fixture')
        self.manager.facade = Mock()
        with patch('backend.telegram.desktop.load_account', return_value=ACCOUNT), self.assertLogs('axx.telegram.desktop', level='DEBUG') as logs:
            self.manager.reconcile()
        self.assertIn('account: OSError', logs.output[0])
        self.assertNotIn('sensitive-fixture', str(logs.output))
        self.manager.service.start_bot.assert_called_once()
        self.manager.facade.start.assert_called_once_with(port=6451)

    def test_save_permissions_reconciles_and_disable_stops(self):
        self.manager.service = Mock()
        self.manager.reconcile = Mock()
        with patch('backend.telegram.desktop.update_permissions') as update:
            self.manager.update_permissions({'enabled': False, 'grants': ACCOUNT['grants']})
        update.assert_called_once()
        self.manager.service.close.assert_called_once()
        self.manager.reconcile.assert_called_once()

    def test_bot_setup_reconciles_after_background_completion(self):
        self.manager.reconcile = Mock()
        with patch('backend.telegram.desktop.configure_bot_remote', return_value={'local_saved': True}):
            self.manager.configure_bot({'token': 'fixture', 'enabled': True, 'public_url': ''})
            self.manager.bot_thread.join(2)
        self.manager.reconcile.assert_called_once()

    def test_qr_completion_and_failure_reconcile_only_after_login_returns(self):
        self.manager.reconcile = Mock()
        async def finish(_):
            self.manager._qr_state('saved')
        with patch.object(self.manager, '_qr_login', side_effect=finish):
            self.manager._qr_thread(APP)
        self.assertEqual(self.manager.qr['state'], 'saved')
        self.manager.reconcile.assert_called_once()
        self.manager.reconcile.reset_mock()
        async def fail(_):
            raise ValueError('ACCOUNT_MISMATCH')
        with patch.object(self.manager, '_qr_login', side_effect=fail):
            self.manager._qr_thread(APP)
        self.assertEqual(self.manager.qr['state'], 'failed')
        self.manager.reconcile.assert_called_once()

    def test_close_removes_qr_and_does_not_modify_configuration(self):
        self.manager.service = Mock()
        self.manager.qr = {'state': 'waiting_qr', 'image': 'sensitive-qr-fixture'}
        with patch('backend.telegram.desktop._save_account') as save:
            self.manager.close()
        self.assertEqual(self.manager.qr, {'state': 'closed'})
        self.assertEqual(self.manager.bot_job, {'state': 'closed'})
        self.assertTrue(self.manager.cancel_requested)
        self.manager.service.close.assert_called_once()
        save.assert_not_called()


threading_event = threading.Event()


class DesktopQRTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_factor_remains_local_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = DesktopTelegram(directory)
            errors = ModuleType('telethon.errors')
            errors.SessionPasswordNeededError = type('SessionPasswordNeededError', (Exception,), {})
            errors.PasswordHashInvalidError = type('PasswordHashInvalidError', (Exception,), {})
            client = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(),
                qr_login=AsyncMock(return_value=SimpleNamespace(url='tg://login?token=fixture',
                    expires=datetime.now(timezone.utc) + timedelta(seconds=60),
                    wait=AsyncMock(side_effect=errors.SessionPasswordNeededError()))),
                sign_in=AsyncMock(), get_me=AsyncMock(return_value=SimpleNamespace(id=11, bot=False)),
                session=SimpleNamespace(save=lambda: 'new-session'))
            telethon = ModuleType('telethon'); telethon.TelegramClient = lambda *args: client
            sessions = ModuleType('telethon.sessions'); sessions.StringSession = lambda: None
            with patch.dict('sys.modules', {'telethon': telethon, 'telethon.errors': errors, 'telethon.sessions': sessions}), \
                 patch('backend.telegram.desktop.account_lease', return_value=nullcontext()), \
                 patch('backend.telegram.desktop._file_lease', return_value=nullcontext()), \
                 patch('backend.telegram.desktop.load_account', return_value=ACCOUNT), \
                 patch('backend.telegram.desktop.pairing_qr_base64', return_value='fixture-image'), \
                 patch('backend.telegram.desktop._save_account'):
                task = asyncio.create_task(manager._qr_login(APP))
                for _ in range(100):
                    if manager.qr['state'] == 'password_required':
                        break
                    await asyncio.sleep(.005)
                self.assertEqual(manager.password({'password': 'private-password-fixture'}), {'state': 'verifying'})
                await task
                self.assertNotIn('private-password-fixture', str(manager.qr))
                client.sign_in.assert_awaited_once_with(password='private-password-fixture')
                client.disconnect.assert_awaited_once()

    async def test_qr_preserves_grants_and_rejects_another_account(self):
        for account_id, valid in ((11, True), (33, False)):
            with self.subTest(account_id=account_id), tempfile.TemporaryDirectory() as directory:
                manager = DesktopTelegram(directory)
                client = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(),
                    qr_login=AsyncMock(return_value=SimpleNamespace(url='tg://login?token=fixture',
                        expires=datetime.now(timezone.utc) + timedelta(seconds=60), wait=AsyncMock())),
                    get_me=AsyncMock(return_value=SimpleNamespace(id=account_id, bot=False)),
                    session=SimpleNamespace(save=lambda: 'new-session'))
                telethon = ModuleType('telethon'); telethon.TelegramClient = lambda *args: client
                errors = ModuleType('telethon.errors')
                errors.SessionPasswordNeededError = type('SessionPasswordNeededError', (Exception,), {})
                errors.PasswordHashInvalidError = type('PasswordHashInvalidError', (Exception,), {})
                sessions = ModuleType('telethon.sessions'); sessions.StringSession = lambda: None
                with patch.dict('sys.modules', {'telethon': telethon, 'telethon.errors': errors, 'telethon.sessions': sessions}), \
                     patch('backend.telegram.desktop.account_lease', return_value=nullcontext()), \
                     patch('backend.telegram.desktop._file_lease', return_value=nullcontext()), \
                     patch('backend.telegram.desktop.load_account', return_value=ACCOUNT), \
                     patch('backend.telegram.desktop.pairing_qr_base64', return_value='fixture-image'), \
                     patch('backend.telegram.desktop._save_account') as save:
                    if valid:
                        await manager._qr_login(APP)
                        self.assertEqual(manager.qr['state'], 'saved')
                        self.assertEqual(save.call_args.args[0]['grants'], ACCOUNT['grants'])
                        self.assertTrue(save.call_args.args[0]['enabled'])
                    else:
                        with self.assertRaisesRegex(ValueError, 'ACCOUNT_MISMATCH'):
                            await manager._qr_login(APP)
                        save.assert_not_called()
                    client.disconnect.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
