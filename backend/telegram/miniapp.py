"""Local-only Telegram Mini App facade, behind an explicitly configured HTTPS tunnel."""
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import re
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.parse import parse_qsl, urlsplit
import uuid

from backend.telegram.config import load_account
from backend.telegram.pairing import PairingStore

MAX_BODY = 16384


class MiniAppError(Exception):
    def __init__(self, code, status):
        self.code, self.status = code, status
        super().__init__(code)


def validate_init_data(raw, token, owner_id, now=None):
    if not isinstance(raw, str) or len(raw) > MAX_BODY or not raw or not isinstance(token, str):
        raise ValueError('Invalid initialization data')
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=64)
        data = dict(pairs)
        if len(data) != len(pairs) or 'hash' not in data or len(data['hash']) != 64:
            raise ValueError()
        received = data.pop('hash')
        if any(ch not in '0123456789abcdef' for ch in received):
            raise ValueError()
        check = '\n'.join(key + '=' + data[key] for key in sorted(data)).encode()
        secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received, expected):
            raise ValueError()
        stamp = int(data['auth_date'])
        now = time.time() if now is None else now
        if stamp > now + 30 or now - stamp > 300:
            raise ValueError()
        user = json.loads(data['user'])
        if not isinstance(user, dict) or type(user.get('id')) is not int or user['id'] != owner_id:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        raise ValueError('Invalid initialization data') from None
    return received


def _origin(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Invalid public URL')
    port = parsed.port
    return 'https://' + parsed.hostname.lower() + (':' + str(port) if port and port != 443 else '')


class _BoundedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        request.settimeout(5)
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class MiniAppFacade:
    def __init__(self, data_dir, service, asset_path=None):
        self.data_dir = data_dir
        self.service = service
        self.pairing = PairingStore(data_dir)
        self.asset_path = Path(asset_path) if asset_path else Path(__file__).with_name('webapp.html')
        self.server = None
        self.thread = None
        self.lock = threading.Lock()
        self.sessions = {}
        self.used = {}

    def _config(self):
        from backend.telegram.bot_config import load_bot
        bot = load_bot(self.data_dir)
        account = load_account(self.data_dir)
        if not bot['enabled'] or not account['enabled']:
            raise MiniAppError('PERMISSION_DENIED', 403)
        origin = _origin(bot['public_url'])
        return bot, account, origin

    def start(self, port=0):
        if self.server:
            return self.server.server_address[1]
        self._config()
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError('Invalid loopback port')
        facade = self
        asset_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, value, *, cookie=None, bond_cookie=None):
                raw = json.dumps(value, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                if cookie:
                    self.send_header('Set-Cookie', '__Host-axx_telegram=' + cookie + '; Path=/; Max-Age=600; HttpOnly; Secure; SameSite=Strict')
                if bond_cookie:
                    self.send_header('Set-Cookie', '__Host-axx_telegram_bond=' + bond_cookie + '; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Strict')
                self.end_headers()
                self.wfile.write(raw)

            def _discard_rejected_body(self):
                length = self.headers.get('Content-Length', '')
                if not length.isdecimal() or self.headers.get('Transfer-Encoding'):
                    return
                previous = self.connection.gettimeout()
                try:
                    self.connection.settimeout(0.5)
                    self.rfile.read(min(int(length), MAX_BODY))
                except (OSError, ValueError):
                    pass
                finally:
                    self.connection.settimeout(previous)

            def _body(self):
                if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                    raise ValueError()
                size = self.headers.get('Content-Length', '')
                if not size.isdecimal() or not 0 < int(size) <= MAX_BODY:
                    raise ValueError()
                raw = self.rfile.read(int(size))
                if len(raw) != int(size):
                    raise ValueError()
                def unique(pairs):
                    result = dict(pairs)
                    if len(result) != len(pairs):
                        raise ValueError()
                    return result
                value = json.loads(raw, object_pairs_hook=unique)
                if not isinstance(value, dict):
                    raise ValueError()
                return value

            def _session(self, bot, account):
                jar = cookies.SimpleCookie()
                jar.load(self.headers.get('Cookie', ''))
                cookie = jar.get('__Host-axx_telegram')
                key = cookie.value if cookie else ''
                with facade.lock:
                    item = facade.sessions.get(key)
                    if not item:
                        raise MiniAppError('AUTH_REQUIRED', 401)
                    if item['until'] <= time.time():
                        facade.sessions.pop(key, None)
                        raise MiniAppError('SESSION_EXPIRED', 401)
                    if item['account'] != account['account_id'] or item['owner'] != account['owner_id'] or not hmac.compare_digest(item['bot'], hashlib.sha256(bot['token'].encode()).digest()):
                        facade.sessions.pop(key, None)
                        raise MiniAppError('PERMISSION_DENIED', 403)
                    bound = jar.get('__Host-axx_telegram_bond')
                    if not bound or not facade.pairing.check(account, bound.value, item['binding']):
                        facade.sessions.pop(key, None)
                        raise MiniAppError('PAIRING_REQUIRED', 403)
                    return item.copy()

            def do_GET(self):
                if self.path == '/health':
                    self._send(200, {'ready': False})
                    return
                try:
                    bot, account, _ = facade._config()
                    if self.path == '/api/state':
                        session = self._session(bot, account)
                        status = facade.service.status()
                        fields = ('state', 'worker_running', 'messages', 'voice_notes', 'files', 'pc_commands', 'private_calls')
                        public = {key: status[key] for key in fields if key in status}
                        public.update(facade.service.diagnostics(account['owner_id']))
                        public['session_expires_at'] = session['until']
                        appearance = getattr(facade.service, 'appearance', None)
                        if callable(appearance):
                            snapshot = appearance()
                            if snapshot is not None:
                                from backend.mobile.http_api import checked_appearance
                                snapshot = checked_appearance(snapshot)
                            public['appearance'] = snapshot
                        self._send(200, public)
                    elif self.path in ('/api/activity', '/api/history', '/api/commands'):
                        self._session(bot, account)
                        action = {'/api/activity': facade.service.activity, '/api/history': facade.service.history,
                                  '/api/commands': facade.service.command_catalog}[self.path]
                        self._send(200, action(account['owner_id']))
                    elif self.path in ('/', '/app.js', '/app.css', '/desktop-avatar.js', '/avatar-renderer.js'):
                        assets = {'/': (facade.asset_path, 'text/html; charset=utf-8'),
                                  '/app.js': (facade.asset_path.with_name('webapp.js'), 'application/javascript; charset=utf-8'),
                                  '/app.css': (facade.asset_path.with_name('webapp.css'), 'text/css; charset=utf-8'),
                                  '/desktop-avatar.js': (asset_root / 'mobile/www/js/desktop-avatar.js', 'application/javascript; charset=utf-8'),
                                  '/avatar-renderer.js': (asset_root / 'mobile/js/avatar-renderer.js', 'application/javascript; charset=utf-8')}
                        target, mime = assets[self.path]
                        html = target.read_bytes()
                        self.send_response(200)
                        self.send_header('Content-Type', mime)
                        self.send_header('Content-Length', str(len(html)))
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors https://web.telegram.org https://*.web.telegram.org")
                        self.end_headers()
                        self.wfile.write(html)
                    else:
                        self._send(404, {'error': 'not_found'})
                except MiniAppError as error:
                    self._send(error.status, {'error': error.code})
                except ValueError:
                    self._send(403, {'error': 'PERMISSION_DENIED'})
                except Exception:
                    self._send(503, {'error': 'CORE_UNAVAILABLE'})

            def do_POST(self):
                try:
                    bot, account, origin = facade._config()
                    if self.headers.get('Origin') != origin:
                        self._discard_rejected_body()
                        raise MiniAppError('PERMISSION_DENIED', 403)
                    body = self._body()
                    if self.path == '/api/session':
                        if set(body) not in ({'init_data'}, {'init_data', 'pairing_token'}):
                            raise ValueError()
                        try:
                            digest = validate_init_data(body['init_data'], bot['token'], account['owner_id'])
                        except ValueError:
                            raise MiniAppError('AUTH_REQUIRED', 401) from None
                        now = time.time()
                        jar = cookies.SimpleCookie()
                        jar.load(self.headers.get('Cookie', ''))
                        bond = jar.get('__Host-axx_telegram_bond')
                        try:
                            current = self._session(bot, account)
                        except Exception:
                            current = None
                        if current and current['init'] == digest:
                            self._send(200, {'csrf': current['csrf']})
                            return
                        with facade.lock:
                            facade.used = {k: v for k, v in facade.used.items() if v > now}
                            facade.sessions = {k: v for k, v in facade.sessions.items() if v['until'] > now}
                            if digest in facade.used or len(facade.used) >= 1024 or len(facade.sessions) >= 1024:
                                raise MiniAppError('AUTH_REQUIRED', 401)
                            binding = facade.pairing.check(account, bond.value) if bond else None
                            new_bond = None
                            if not binding:
                                try:
                                    binding, new_bond = facade.pairing.consume(account, body.get('pairing_token', ''))
                                except ValueError:
                                    raise MiniAppError('PAIRING_REQUIRED', 403) from None
                            facade.used[digest] = now + 331
                            session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                            facade.sessions[session] = {'until': now + 600, 'csrf': csrf, 'account': account['account_id'], 'owner': account['owner_id'], 'bot': hashlib.sha256(bot['token'].encode()).digest(), 'init': digest, 'binding': binding}
                        self._send(200, {'csrf': csrf}, cookie=session, bond_cookie=new_bond)
                    elif self.path in ('/api/review', '/api/decision'):
                        expected = {'operation_id', 'csrf'} if self.path == '/api/review' else {'token', 'decision', 'csrf'}
                        if set(body) != expected:
                            raise ValueError()
                        session = self._session(bot, account)
                        if not isinstance(body['csrf'], str) or not hmac.compare_digest(body['csrf'], session['csrf']):
                            raise MiniAppError('PERMISSION_DENIED', 403)
                        try:
                            if self.path == '/api/review':
                                operation_id = body['operation_id']
                                if not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id:
                                    raise ValueError()
                                result = facade.service.review_operation(account['owner_id'], operation_id)
                                fields = ('state', 'operation_id', 'title', 'description', 'risk', 'inputs', 'plan_hash', 'expires_at', 'token', 'can_confirm', 'reason')
                                if result.get('can_confirm') is not True:
                                    fields = tuple(key for key in fields if key != 'token')
                            else:
                                if not isinstance(body['token'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,61}', body['token']) or body['decision'] not in ('confirm', 'cancel'):
                                    raise ValueError()
                                result = facade.service.decide_operation(account['owner_id'], body['token'], body['decision'])
                                fields = ('state', 'text', 'operation_id', 'postconditions_passed', 'next_operation_id')
                        except ValueError:
                            raise MiniAppError('PERMISSION_DENIED', 403) from None
                        self._send(200, {key: result[key] for key in fields if key in result})
                    elif self.path == '/api/cancel':
                        if set(body) != {'operation_id', 'csrf'}:
                            raise ValueError()
                        session = self._session(bot, account)
                        if not isinstance(body['csrf'], str) or not hmac.compare_digest(body['csrf'], session['csrf']):
                            raise MiniAppError('PERMISSION_DENIED', 403)
                        try:
                            result = facade.service.cancel_operation(account['owner_id'], body['operation_id'])
                        except ValueError:
                            raise MiniAppError('PERMISSION_DENIED', 403) from None
                        self._send(200, {'state': result['state']})
                    elif self.path == '/api/chat':
                        if set(body) != {'text', 'request_id', 'csrf'}:
                            raise ValueError()
                        session = self._session(bot, account)
                        if not isinstance(body['csrf'], str) or not hmac.compare_digest(body['csrf'], session['csrf']):
                            raise MiniAppError('PERMISSION_DENIED', 403)
                        text, request_id = body['text'], body['request_id']
                        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 12000 or not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
                            raise ValueError()
                        result = facade.service.admit_miniapp(account['owner_id'], text, request_id)
                        self._send(200, {key: result[key] for key in ('state', 'text', 'operation_id') if key in result})
                    else:
                        self._send(404, {'error': 'not_found'})
                except MiniAppError as error:
                    self._send(error.status, {'error': error.code})
                except (ValueError, TypeError, KeyError, UnicodeError):
                    self._send(400, {'error': 'INVALID_REQUEST'})
                except Exception:
                    self._send(503, {'error': 'CORE_UNAVAILABLE'})

        self.server = _BoundedServer(('127.0.0.1', port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='telegram-miniapp')
        self.thread.start()
        return self.server.server_address[1]

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.server = None
        with self.lock:
            self.sessions.clear()
            self.used.clear()
