"""DPAPI-protected configuration for the separate Telegram bot."""
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt
from backend.telegram.config import _file_lease, _require_windows, account_path


def bot_path(data_dir=None):
    return account_path(data_dir).parent / 'bot.dpapi'


def validate_bot(value):
    if not isinstance(value, dict) or not {'token', 'enabled', 'public_url'} <= set(value) or set(value) - {'token', 'enabled', 'public_url', 'username'}:
        raise ValueError('Invalid bot configuration')
    if not isinstance(value['token'], str) or not re.fullmatch(r'[0-9]{5,15}:[A-Za-z0-9_-]{25,100}', value['token']):
        raise ValueError('Invalid bot token')
    if type(value['enabled']) is not bool or not isinstance(value['public_url'], str):
        raise ValueError('Invalid bot settings')
    if 'username' in value and (not isinstance(value['username'], str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', value['username'])):
        raise ValueError('Invalid bot username')
    if value['public_url']:
        try:
            url = urlsplit(value['public_url'])
            host = url.hostname or ''
            try:
                ipaddress.ip_address(host)
                raise ValueError('IP address is not permitted')
            except ValueError as exc:
                if str(exc) == 'IP address is not permitted':
                    raise
            if (url.scheme != 'https' or not re.fullmatch(r'[a-zA-Z0-9.-]+', host)
                    or '.' not in host or host.endswith(('.local', '.localhost', '.invalid', '.test', '.example'))
                    or url.username or url.password or url.port not in (None, 443)
                    or url.fragment or len(value['public_url']) > 2048):
                raise ValueError('Invalid public HTTPS URL')
        except ValueError:
            raise ValueError('Invalid public HTTPS URL') from None
    return value.copy()


def load_bot(data_dir=None):
    _require_windows()
    raw = bot_path(data_dir).read_bytes()
    if len(raw) > 16384:
        raise ValueError('Invalid bot configuration')
    return validate_bot(json.loads(_dpapi_decrypt(raw).decode('utf-8')))


def save_bot(value, data_dir=None):
    _require_windows()
    raw = _dpapi_encrypt(json.dumps(validate_bot(value), ensure_ascii=True).encode('utf-8'))
    target = bot_path(data_dir)
    with _file_lease(target.with_suffix('.lock'), 'TELEGRAM_BOT_CONFIG_IN_USE'):
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.bot-', delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
