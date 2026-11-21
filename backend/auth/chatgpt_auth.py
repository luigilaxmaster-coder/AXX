"""DPAPI helpers and inert compatibility facade for the retired Axx OAuth flow.

Codex App Server owns ChatGPT login. Existing credential files are left untouched.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

# Windows DPAPI structures
class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]

def _dpapi_encrypt(data: bytes) -> bytes:
    if os.name != 'nt':
        return data
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), 'axx_token', None, None, None, 0, ctypes.byref(blob_out)):
        raise RuntimeError('CryptProtectData failed')
    res = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return res

def _dpapi_decrypt(data: bytes) -> bytes:
    if os.name != 'nt':
        return data
    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise RuntimeError('CryptUnprotectData failed')
    res = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return res

MIGRATION_MESSAGE = 'La autenticación antigua está desactivada. Usa ChatGPT mediante Codex App Server en Conexiones.'


class ChatGPTAuthManager:
    """Preserve legacy imports without loading, refreshing or transmitting old tokens."""
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir or Path(os.environ.get('LOCALAPPDATA', '')) / 'Axx').resolve()

    def is_authenticated(self) -> bool:
        return False

    def get_status(self) -> dict:
        return {'authenticated': False, 'models': [], 'email': None, 'name': None,
                'client_id': None, 'last_error_code': 'AUTH_MIGRATED', 'last_error': MIGRATION_MESSAGE}

    def start_oauth(self, port: int, open_browser: bool = True) -> dict:
        raise ValueError(MIGRATION_MESSAGE)

    def set_client_id(self, client_id: str):
        raise ValueError(MIGRATION_MESSAGE)

    def get_client_id(self):
        return None

    def handle_callback(self, code: str, state: str):
        return False, MIGRATION_MESSAGE

    def get_access_token(self):
        return None

    def refresh_access_token(self) -> bool:
        return False

    def clear_auth(self):
        # Legacy disconnect must not delete credentials owned by the user or Codex.
        return None
