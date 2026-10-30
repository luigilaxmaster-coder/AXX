"""Native-host-only local Telegram setup. No network is started on import."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt
from backend.mobile.pairing_qr import pairing_qr_base64
from backend.telegram.bot_config import load_bot
from backend.telegram.bot_setup import configure as configure_bot_remote
from backend.telegram.config import GRANTS, _file_lease, _save_account, account_lease, account_path, load_account, update_permissions, confirmation_policy, set_confirmation_policy

LOG = logging.getLogger('axx.telegram.desktop')


class DesktopTelegram:
    def __init__(self, data_dir, telegram_service=None):
        self.data_dir = Path(data_dir)
        self.service = telegram_service
        self.lock = threading.RLock()
        self.qr = {'state': 'idle'}
        self.bot_job = {'state': 'idle'}
        self.loop = self.task = self.password_future = None
        self.cancel_requested = False
        self.qr_thread = self.bot_thread = None
        self.closed = False
        self.facade = None
        self.stop_reconcile = threading.Event()
        self.reconcile_thread = threading.Thread(target=self._reconcile_loop, daemon=True, name='axx-telegram-reconcile')
        self.reconcile_thread.start()

    def _reconcile_loop(self):
        while not self.stop_reconcile.wait(10):
            self.reconcile()

    def reconcile(self):
        from backend.telegram.miniapp import MiniAppError
        with self.lock:
            if self.closed or not self.service or self.qr['state'] in ('starting', 'waiting_qr', 'password_required', 'verifying'):
                return
            try:
                if not load_account(self.data_dir)['enabled']:
                    return
            except (OSError, ValueError, RuntimeError):
                return
            for component, action in (('account', self.service.start), ('bot', self.service.start_bot),
                                      ('miniapp', lambda: self.facade.start(port=6451) if self.facade else None)):
                try:
                    action()
                except (OSError, ValueError, RuntimeError, ImportError, MiniAppError) as error:
                    LOG.debug('Telegram reconcile %s: %s', component, type(error).__name__)

    @property
    def app_path(self):
        return self.data_dir / 'telegram' / 'app.dpapi'

    def _app(self):
        try:
            raw = self.app_path.read_bytes()
            if len(raw) > 16384:
                raise ValueError('Invalid local configuration')
            return self._validate_app(json.loads(_dpapi_decrypt(raw)))
        except FileNotFoundError:
            account = load_account(self.data_dir)
            return {key: account[key] for key in ('api_id', 'api_hash', 'owner_id')}

    @staticmethod
    def _validate_app(body):
        if not isinstance(body, dict) or set(body) != {'api_id', 'api_hash', 'owner_id'}:
            raise ValueError('Invalid configuration')
        if (type(body['api_id']) is not int or not 0 < body['api_id'] <= 2147483647
                or type(body['owner_id']) is not int or not 0 < body['owner_id'] <= 9223372036854775807
                or not isinstance(body['api_hash'], str) or not re.fullmatch(r'[0-9a-fA-F]{32}', body['api_hash'])):
            raise ValueError('Invalid configuration')
        return body.copy()

    def configure_app(self, body):
        value = self._validate_app(body)
        try:
            account = load_account(self.data_dir)
        except FileNotFoundError:
            account = None
        if account and value['owner_id'] != account['owner_id']:
            raise ValueError('OWNER_MISMATCH')
        encrypted = _dpapi_encrypt(json.dumps(value).encode())
        target = self.app_path
        with _file_lease(target.with_suffix('.lock'), 'TELEGRAM_APP_CONFIG_IN_USE'):
            name = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.app-', delete=False) as stream:
                    name = stream.name
                    stream.write(encrypted)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, target)
            finally:
                if name and os.path.exists(name):
                    os.unlink(name)
        return {'state': 'saved'}

    def status(self):
        try:
            account = load_account(self.data_dir)
        except (OSError, ValueError, RuntimeError):
            account = None
        try:
            bot = load_bot(self.data_dir)
        except (OSError, ValueError, RuntimeError):
            bot = None
        try:
            self._app()
            app_configured = True
        except (OSError, ValueError, RuntimeError, KeyError):
            app_configured = False
        with self.lock:
            qr = dict(self.qr)
            bot_job = dict(self.bot_job)
        if qr.get('expires_at') and time.time() >= qr['expires_at']:
            qr.pop('image', None)
        return {'app_configured': app_configured, 'remote_confirmations': confirmation_policy(self.data_dir)['enabled'],
                'account': {'configured': bool(account), 'enabled': bool(account and account['enabled']),
                            'owner_id': account['owner_id'] if account else None,
                            'grants': dict(account['grants']) if account else {key: False for key in GRANTS}},
                'bot': {'configured': bool(bot), 'enabled': bool(bot and bot['enabled']),
                        'public_url': bot['public_url'] if bot else '', 'username': bot.get('username') if bot else None},
                'qr': qr, 'bot_job': bot_job}

    def _qr_state(self, state, **fields):
        with self.lock:
            self.qr = {'state': 'closed'} if self.closed else {'state': state, **fields}

    def start_qr(self, body=None):
        if body not in (None, {}):
            raise ValueError('Invalid QR request')
        app = self._app()
        with self.lock:
            if self.closed:
                raise ValueError('SERVICE_CLOSED')
            if self.qr['state'] in ('starting', 'waiting_qr', 'password_required', 'verifying'):
                raise ValueError('QR_LOGIN_IN_PROGRESS')
            self.cancel_requested = False
            self.qr = {'state': 'starting'}
            self.qr_thread = threading.Thread(target=self._qr_thread, args=(app,), daemon=True, name='axx-telegram-qr')
            self.qr_thread.start()
        return {'state': 'starting'}

    def _qr_thread(self, app):
        try:
            asyncio.run(self._qr_login(app))
        except asyncio.CancelledError:
            self._qr_state('cancelled')
        except Exception as exc:
            code = str(exc) if isinstance(exc, ValueError) and str(exc) in {'OWNER_MISMATCH', 'ACCOUNT_MISMATCH', 'BOT_ACCOUNT'} else 'QR_LOGIN_FAILED'
            self._qr_state('failed', code=code)
        finally:
            with self.lock:
                self.loop = self.task = self.password_future = None
            self.reconcile()

    async def _qr_login(self, app):
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError
        from telethon.sessions import StringSession
        with self.lock:
            self.loop, self.task = asyncio.get_running_loop(), asyncio.current_task()
            if self.cancel_requested:
                raise asyncio.CancelledError()
        if self.service and getattr(self.service, 'process', None) is not None:
            if not callable(getattr(self.service, 'pause_account', None)):
                raise ValueError('ACCOUNT_WORKER_ACTIVE')
            self.service.pause_account()
        with account_lease(self.data_dir):
            client = TelegramClient(StringSession(), app['api_id'], app['api_hash'])
            try:
                await client.connect()
                qr = await client.qr_login()
                expiry = min(time.time() + 110, qr.expires.timestamp())
                image = pairing_qr_base64(qr.url)
                self._qr_state('waiting_qr', image=image, expires_at=expiry)
                try:
                    await asyncio.wait_for(qr.wait(), timeout=max(0.1, expiry-time.time()))
                except SessionPasswordNeededError:
                    while True:
                        future = asyncio.get_running_loop().create_future()
                        with self.lock:
                            self.password_future = future
                        self._qr_state('password_required')
                        password = await asyncio.wait_for(future, timeout=110)
                        self._qr_state('verifying')
                        try:
                            await client.sign_in(password=password)
                            break
                        except PasswordHashInvalidError:
                            continue
                        finally:
                            password = None
                me = await client.get_me()
                if not me or type(getattr(me, 'id', None)) is not int or me.id <= 0:
                    raise ValueError('ACCOUNT_UNAVAILABLE')
                if getattr(me, 'bot', False):
                    raise ValueError('BOT_ACCOUNT')
                if me.id == app['owner_id']:
                    raise ValueError('OWNER_MISMATCH')
                target = account_path(self.data_dir)
                with _file_lease(target.parent / 'config.lock', 'TELEGRAM_CONFIG_IN_USE'):
                    try:
                        existing = load_account(self.data_dir)
                    except FileNotFoundError:
                        existing = None
                    if existing and existing['account_id'] != me.id:
                        raise ValueError('ACCOUNT_MISMATCH')
                    if existing and existing['owner_id'] != app['owner_id']:
                        raise ValueError('OWNER_MISMATCH')
                    saved = dict(existing) if existing else {'enabled': False, 'grants': {key: key == 'conversation' for key in GRANTS}}
                    saved.update(api_id=app['api_id'], api_hash=app['api_hash'], owner_id=app['owner_id'],
                                 account_id=me.id, session=client.session.save())
                    _save_account(saved, self.data_dir, create_only=existing is None)
                self._qr_state('saved')
            finally:
                await client.disconnect()

    def password(self, body):
        if not isinstance(body, dict) or set(body) != {'password'} or not isinstance(body['password'], str) or not 1 <= len(body['password']) <= 1024:
            raise ValueError('Invalid password')
        with self.lock:
            if self.qr['state'] != 'password_required' or not self.loop or not self.password_future:
                raise ValueError('PASSWORD_NOT_REQUIRED')
            future, loop = self.password_future, self.loop
            self.qr = {'state': 'verifying'}
        def submit():
            if not future.done():
                future.set_result(body['password'])
        loop.call_soon_threadsafe(submit)
        return {'state': 'verifying'}

    def cancel(self):
        with self.lock:
            loop, task, state = self.loop, self.task, self.qr['state']
            if state in ('starting', 'waiting_qr', 'password_required', 'verifying'):
                self.cancel_requested = True
        if loop and task:
            loop.call_soon_threadsafe(task.cancel)
        return {'state': 'cancellation_requested' if state in ('starting', 'waiting_qr', 'password_required', 'verifying') else state}

    def configure_bot(self, body):
        if not isinstance(body, dict) or set(body) != {'token', 'enabled', 'public_url'} or not isinstance(body['token'], str) or type(body['enabled']) is not bool or not isinstance(body['public_url'], str):
            raise ValueError('Invalid bot configuration')
        with self.lock:
            if self.closed:
                raise ValueError('SERVICE_CLOSED')
            if self.bot_job['state'] == 'running':
                raise ValueError('BOT_SETUP_IN_PROGRESS')
            self.bot_job = {'state': 'running'}
        def work():
            try:
                result = configure_bot_remote(body['token'], body['public_url'], body['enabled'], self.data_dir)
                value = {'state': 'saved', **result}
            except Exception as exc:
                from backend.telegram.bot import BotApiError
                from backend.telegram.bot_setup import safe_code
                value = {'state': 'failed', 'code': safe_code(exc.code) if isinstance(exc, BotApiError) else 'SETUP_ERROR'}
            with self.lock:
                self.bot_job = {'state': 'closed'} if self.closed else value
            self.reconcile()
        with self.lock:
            if self.closed:
                self.bot_job = {'state': 'cancelled'}
                raise ValueError('SERVICE_CLOSED')
            self.bot_thread = threading.Thread(target=work, daemon=True, name='axx-telegram-bot-setup')
            self.bot_thread.start()
        return {'state': 'running'}

    @staticmethod
    def validate_permissions(body):
        if not isinstance(body, dict) or set(body) != {'enabled', 'grants'} or type(body['enabled']) is not bool or not isinstance(body['grants'], dict) or set(body['grants']) != set(GRANTS) or any(type(body['grants'][key]) is not bool for key in GRANTS):
            raise ValueError('Invalid permissions')
        return {'enabled': body['enabled'], 'grants': dict(body['grants'])}

    def configure_confirmations(self, body):
        if not isinstance(body, dict) or set(body) != {'enabled'} or type(body['enabled']) is not bool:
            raise ValueError('Invalid confirmation permission')
        return set_confirmation_policy(body['enabled'], self.data_dir)

    def update_permissions(self, body):
        value = self.validate_permissions(body)
        with self.lock:
            update_permissions(value['enabled'], value['grants'], self.data_dir)
            if not value['enabled'] and self.service:
                self.service.close()
        self.reconcile()
        return {'state': 'saved'}

    def pause(self):
        if not self.service:
            raise ValueError('SERVICE_UNAVAILABLE')
        self.cancel()
        with self.lock:
            self._set_enabled(False)
            self.service.close()
        return {'state': 'paused'}

    def resume(self):
        if not self.service:
            raise ValueError('SERVICE_UNAVAILABLE')
        with self.lock:
            self._set_enabled(True)
        self.reconcile()
        return {'state': 'start_requested'}

    def _set_enabled(self, enabled):
        target = account_path(self.data_dir)
        with _file_lease(target.parent / 'config.lock', 'TELEGRAM_CONFIG_IN_USE'):
            account = load_account(self.data_dir)
            account['enabled'] = enabled
            _save_account(account, self.data_dir)

    def close(self):
        with self.lock:
            self.closed = True
            self.stop_reconcile.set()
            qr_thread, bot_thread = self.qr_thread, self.bot_thread
        self.cancel()
        if self.service:
            self.service.close()
        if self.reconcile_thread is not threading.current_thread():
            self.reconcile_thread.join(5)
        for worker, timeout in ((qr_thread, 5), (bot_thread, 50)):
            if worker and worker is not threading.current_thread():
                worker.join(timeout)
        with self.lock:
            self.qr = {'state': 'closed'}
            self.bot_job = {'state': 'closed'}
