"""Protected local Telegram account configuration."""
import json
import os
from pathlib import Path
import re
import tempfile
from contextlib import contextmanager

from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt

GRANTS = ('conversation', 'voice_notes', 'files', 'pc_commands', 'private_calls')


def account_path(data_dir=None):
    root = Path(data_dir) if data_dir is not None else Path(os.environ['LOCALAPPDATA']) / 'Axx'
    return root / 'telegram' / 'account.dpapi'


def validate_account(value):
    if not isinstance(value, dict) or set(value) - {'api_id', 'api_hash', 'session', 'account_id', 'owner_id', 'enabled', 'grants', 'voice'}:
        raise ValueError('Invalid Telegram account configuration')
    for key in ('api_id', 'account_id', 'owner_id'):
        if type(value.get(key)) is not int or value[key] <= 0:
            raise ValueError('Invalid Telegram account identifier')
    if value['owner_id'] == value['account_id']:
        raise ValueError('The owner must be a different Telegram account')
    if not isinstance(value.get('api_hash'), str) or not re.fullmatch(r'[0-9a-fA-F]{32}', value['api_hash']):
        raise ValueError('Invalid Telegram application hash')
    if not isinstance(value.get('session'), str) or not value['session']:
        raise ValueError('Missing Telegram session')
    if type(value.get('enabled')) is not bool:
        raise ValueError('Invalid Telegram enabled setting')
    grants = value.get('grants')
    if not isinstance(grants, dict) or set(grants) != set(GRANTS) or any(type(grants[k]) is not bool for k in GRANTS):
        raise ValueError('Invalid Telegram permissions')
    if 'voice' in value and (not isinstance(value['voice'], str) or len(value['voice']) > 160):
        raise ValueError('Invalid selected voice')
    return value.copy()


def _require_windows():
    if os.name != 'nt':
        raise RuntimeError('Telegram account protection requires Windows DPAPI')


@contextmanager
def _file_lease(target, error):
    _require_windows()
    import msvcrt
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError(error) from None
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def account_lease(data_dir=None):
    return _file_lease(account_path(data_dir).parent / 'session.lock', 'TELEGRAM_SESSION_IN_USE')


def load_account(data_dir=None):
    _require_windows()
    target = account_path(data_dir)
    return validate_account(json.loads(_dpapi_decrypt(target.read_bytes()).decode('utf-8')))


def save_account(value, data_dir=None, *, create_only=False):
    with _file_lease(account_path(data_dir).parent / 'config.lock', 'TELEGRAM_CONFIG_IN_USE'):
        _save_account(value, data_dir, create_only=create_only)


def update_permissions(enabled, grants, data_dir=None):
    with _file_lease(account_path(data_dir).parent / 'config.lock', 'TELEGRAM_CONFIG_IN_USE'):
        account = load_account(data_dir)
        account['enabled'] = enabled
        account['grants'] = grants
        _save_account(account, data_dir)


def _save_account(value, data_dir=None, *, create_only=False):
    _require_windows()
    raw = json.dumps(validate_account(value), ensure_ascii=True, allow_nan=False).encode('utf-8')
    encrypted = _dpapi_encrypt(raw)
    target = account_path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.telegram-', delete=False) as stream:
            name = stream.name
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        if create_only:
            os.link(name, target)
        else:
            os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
