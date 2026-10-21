"""ChatGPT Subscription OAuth 2.0 PKCE authentication manager for Axx.
Complies with official OpenAI documentation for open-source / local agents:
- dynamic_agent_client with PKCE S256
- scope: openid profile email offline_access resource.invoke chatgpt.tokens.use.direct
- Loopback redirect: http://127.0.0.1:<port>/auth/callback
- Token protection via Windows DPAPI per-user encryption.
"""
from __future__ import annotations
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

LOG = logging.getLogger('axx.auth')

AUTH_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
CLIENT_ID = "dynamic_agent_client"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
RESOURCE = "https://api.openai.com/v1"

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

def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

class ChatGPTAuthManager:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = Path(data_dir or (os.environ.get('LOCALAPPDATA', '') + r'\Axx')).resolve()
        self.auth_file = self.data_dir / 'auth' / 'chatgpt.json'
        self.pending_states: dict[str, dict] = {}
        self.lock = threading.RLock()
        self._cached_auth: dict | None = None
        self.last_error: str | None = None
        self.last_error_code: str | None = None
        self._load_cached_auth()

    def _load_cached_auth(self):
        try:
            if not self.auth_file.exists():
                self._cached_auth = None
                return
            raw = self.auth_file.read_bytes()
            dec = _dpapi_decrypt(raw)
            self._cached_auth = json.loads(dec.decode('utf-8'))
        except Exception as e:
            LOG.warning('Failed to load cached ChatGPT auth: %s', e)
            self._cached_auth = None

    def _save_auth(self, data: dict):
        self.auth_file.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data).encode('utf-8')
        enc = _dpapi_encrypt(raw)
        self.auth_file.write_bytes(enc)
        self._cached_auth = data

    def clear_auth(self):
        with self.lock:
            self._cached_auth = None
            self.last_error = None
            self.last_error_code = None
            if self.auth_file.exists():
                try:
                    self.auth_file.unlink()
                except Exception as e:
                    LOG.warning('Failed to delete auth file: %s', e)

    def is_authenticated(self) -> bool:
        with self.lock:
            if not self._cached_auth:
                return False
            access_token = self._cached_auth.get('access_token')
            refresh_token = self._cached_auth.get('refresh_token')
            expires_at = self._cached_auth.get('expires_at', 0)
            if not access_token:
                return False
            if time.time() < (expires_at - 60):
                return True
            if refresh_token:
                return self.refresh_access_token()
            return False

    def get_client_id(self) -> str:
        with self.lock:
            client_file = self.data_dir / 'auth' / 'client_id.txt'
            if client_file.exists():
                try:
                    val = client_file.read_text(encoding='utf-8').strip()
                    if val:
                        return val
                except Exception:
                    pass
            return os.environ.get('OPENAI_OAUTH_CLIENT_ID', CLIENT_ID)

    def set_client_id(self, client_id: str):
        with self.lock:
            client_id = (client_id or '').strip()
            client_file = self.data_dir / 'auth' / 'client_id.txt'
            client_file.parent.mkdir(parents=True, exist_ok=True)
            if client_id:
                client_file.write_text(client_id, encoding='utf-8')
            elif client_file.exists():
                try:
                    client_file.unlink()
                except Exception:
                    pass

    def get_status(self) -> dict:
        with self.lock:
            authed = self.is_authenticated()
            user_info = self._cached_auth.get('user', {}) if self._cached_auth else {}
            models = ["gpt-4o", "gpt-4o-mini", "o1-mini", "chatgpt-auto"] if authed else []
            return {
                "authenticated": authed,
                "email": user_info.get("email"),
                "name": user_info.get("name") or "Usuario de ChatGPT",
                "expires_at": self._cached_auth.get("expires_at") if self._cached_auth else None,
                "subscription_tier": "ChatGPT Plus / Pro",
                "models": models,
                "default_model": "gpt-4o" if authed else None,
                "client_id": self.get_client_id(),
                "last_error": self.last_error,
                "last_error_code": self.last_error_code
            }

    def start_oauth(self, port: int, open_browser: bool = True) -> dict:
        verifier_bytes = secrets.token_bytes(32)
        code_verifier = _base64url(verifier_bytes)
        challenge_bytes = hashlib.sha256(code_verifier.encode('ascii')).digest()
        code_challenge = _base64url(challenge_bytes)
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        redirect_uri = f"http://127.0.0.1:{port}/auth/callback"

        client_id = self.get_client_id()
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "agent_name_hint": "Axx",
            "ext_agent_host_id": "axx-desktop-local",
        }

        auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

        with self.lock:
            # Clean expired pending states (>15 mins)
            now = time.time()
            self.pending_states = {k: v for k, v in self.pending_states.items() if now - v.get('created', 0) < 900}
            self.pending_states[state] = {
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "created": now,
                "state": state
            }

        if open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception as e:
                LOG.warning('webbrowser.open failed: %s', e)

        return {
            "auth_url": auth_url,
            "state": state,
            "redirect_uri": redirect_uri
        }

    def handle_callback(self, code: str, state: str) -> tuple[bool, str]:
        with self.lock:
            pending = self.pending_states.pop(state, None)
            if not pending:
                return False, "Estado de autorización inválido o expirado. Por favor, inicia sesión de nuevo desde Axx."

        code_verifier = pending["code_verifier"]
        redirect_uri = pending["redirect_uri"]

        body_params = {
            "grant_type": "authorization_code",
            "client_id": self.get_client_id(),
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE
        }

        data_bytes = urllib.parse.urlencode(body_params).encode('utf-8')
        req = urllib.request.Request(
            TOKEN_URL,
            data=data_bytes,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_resp = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8', errors='replace')
            LOG.error('Token exchange HTTPError %d: %s', e.code, err_msg)
            is_invalid_client = 'invalid_client' in err_msg.lower()
            with self.lock:
                self.last_error = err_msg
                self.last_error_code = 'invalid_client' if is_invalid_client else 'http_error'
            if is_invalid_client:
                return False, "OAuth 'invalid_client': OpenAI restringe el flujo OAuth directo para aplicaciones de escritorio sin registro previo. Usa tu clave de API en la pestaña '🔑 Por API' o 'Conectar por API'."
            return False, f"Error al intercambiar credenciales con OpenAI: {err_msg[:200]}"
        except Exception as e:
            LOG.error('Token exchange failed: %s', e)
            with self.lock:
                self.last_error = str(e)
                self.last_error_code = 'network_error'
            return False, f"Fallo de conexión con OpenAI: {e}"

        with self.lock:
            self.last_error = None
            self.last_error_code = None

        access_token = token_resp.get("access_token")
        refresh_token = token_resp.get("refresh_token")
        expires_in = token_resp.get("expires_in", 3600)
        id_token = token_resp.get("id_token")

        user_info = {}
        if id_token:
            try:
                # Decodificar payload sin firma para obtener email/perfil básico
                parts = id_token.split('.')
                if len(parts) >= 2:
                    padded = parts[1] + '=' * ((4 - len(parts[1]) % 4) % 4)
                    payload_bytes = base64.urlsafe_b64decode(padded.encode('ascii'))
                    user_info = json.loads(payload_bytes.decode('utf-8'))
            except Exception:
                pass

        auth_record = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + float(expires_in),
            "user": {
                "email": user_info.get("email"),
                "name": user_info.get("name") or user_info.get("email", "Usuario"),
                "sub": user_info.get("sub")
            },
            "saved_at": time.time()
        }

        with self.lock:
            self._save_auth(auth_record)

        return True, "Autorización completada exitosamente."

    def refresh_access_token(self) -> bool:
        with self.lock:
            if not self._cached_auth or not self._cached_auth.get("refresh_token"):
                return False
            refresh_token = self._cached_auth["refresh_token"]

        body_params = {
            "grant_type": "refresh_token",
            "client_id": self.get_client_id(),
            "refresh_token": refresh_token,
            "resource": RESOURCE
        }
        data_bytes = urllib.parse.urlencode(body_params).encode('utf-8')
        req = urllib.request.Request(
            TOKEN_URL,
            data=data_bytes,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                token_resp = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            LOG.warning('Token refresh failed: %s', e)
            return False

        with self.lock:
            if not self._cached_auth:
                return False
            self._cached_auth["access_token"] = token_resp.get("access_token", self._cached_auth.get("access_token"))
            if "refresh_token" in token_resp:
                self._cached_auth["refresh_token"] = token_resp["refresh_token"]
            expires_in = token_resp.get("expires_in", 3600)
            self._cached_auth["expires_at"] = time.time() + float(expires_in)
            self._save_auth(self._cached_auth)

        return True

    def get_access_token(self) -> str | None:
        with self.lock:
            if self.is_authenticated():
                return self._cached_auth.get("access_token")
            return None
