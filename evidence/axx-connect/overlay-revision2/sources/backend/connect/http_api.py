"""Authenticated Axx transports; credentials stay in the native backend."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
import urllib.parse

from backend.auth.chatgpt_auth import _dpapi_encrypt, _dpapi_decrypt


def publish_endpoint(state_dir, server):
    if os.name != 'nt':
        return  # This installation's local discovery requires Windows DPAPI.
    directory = Path(state_dir) / 'connect'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'endpoint.dpapi'
    payload = {'port': server.server_port, 'token': server.host_token,
               'instance_id': server.instance_id, 'pid': os.getpid()}
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(_dpapi_encrypt(json.dumps(payload).encode('utf-8')))
    os.replace(temporary, path)


def remove_endpoint(state_dir, instance_id):
    path = Path(state_dir) / 'connect' / 'endpoint.dpapi'
    try:
        value = json.loads(_dpapi_decrypt(path.read_bytes()))
        if value.get('instance_id') == instance_id:
            path.unlink(missing_ok=True)
    except (OSError, ValueError, RuntimeError):
        pass


class ConnectHTTP:
    """No public routes; caller has already checked host, origin and bearer."""
    def __init__(self, handler):
        self.h = handler
        self.service = handler.connect
        self.provider = handler.provider

    def _engine(self, synchronous=False):
        server = self.h.server
        if not self.provider:
            return {'state': 'unavailable', 'inference_verified': False}
        if getattr(self.provider, 'local_enabled', True) is False:
            return self.provider.status()
        def update():
            try:
                result = self.provider.status()
                result['checked_at'] = time.time()
                with server.connect_engine_lock:
                    server.connect_engine_status = result
                return result
            finally:
                with server.connect_engine_lock:
                    server.connect_engine_checking = False
        if synchronous:
            return update()
        with server.connect_engine_lock:
            cached = server.connect_engine_status
            stale = not cached or time.time() - cached.get('checked_at', 0) > 30
            if stale and not server.connect_engine_checking:
                server.connect_engine_checking = True
                threading.Thread(target=update, name='axx-connect-health', daemon=True).start()
        return dict(cached or {'state': 'checking', 'authenticated': False, 'inference_verified': False},
                    status_source='last_runtime_check', refresh_pending=server.connect_engine_checking)

    def get(self, path):
        if not path.startswith('/axx-api/connect/'):
            return False
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.h.path).query)
        def one(key, default=None):
            values = query.get(key, [default])
            if len(values) != 1:
                raise ValueError('Duplicate query field')
            return values[0]
        if not self.service:
            raise ValueError('Axx Connect is unavailable')
        if path == '/axx-api/connect/status':
            result = self.service.status()
            result['instance_id'] = self.h.server.instance_id
            result['engine'] = self._engine(synchronous=one('engine', '0') == '1')
        elif path == '/axx-api/connect/capabilities':
            result = self.service.capabilities(one('q', ''), int(one('limit', 100)), int(one('offset', 0)))
        elif path == '/axx-api/connect/task':
            result = self.service.get_task(one('operation_id'))
        elif path == '/axx-api/connect/run':
            result = self.provider.get(one('request_id'), after=int(one('after', 0)))
        elif path == '/axx-api/connect/ui/claim':
            result = self.service.ui_claim()
        elif path == '/axx-api/connect/history':
            with self.service.lock:
                tasks = [json.loads(row[0]) for row in self.service.db.execute('SELECT result_json FROM connect_tasks ORDER BY created_at DESC LIMIT 50')]
            result = {'operations': self.h.commands.operations(), 'tasks': tasks, 'runs': self.provider.history()}
        else:
            self.h._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': 'Unknown Axx Connect route'}})
            return True
        self.h._send_json(200, result)
        return True

    def post(self, path, body):
        if not path.startswith('/axx-api/connect/'):
            return False
        if not self.service or not self.provider:
            raise ValueError('Axx Connect is unavailable')
        if path == '/axx-api/connect/start':
            result = self.provider.start(body)
        elif path == '/axx-api/connect/cancel':
            if set(body) - {'operation_id', 'request_id'}:
                raise ValueError('Unsupported cancellation fields')
            result = self.provider.cancel(body['request_id']) if 'request_id' in body else self.service.cancel_task(body.get('operation_id'))
        elif path == '/axx-api/connect/execute':
            result = self.service.execute(body)
        elif path == '/axx-api/connect/ui/complete':
            result = self.service.ui_complete(body)
        elif path == '/axx-api/connect/ui/claim':
            if set(body) != {'handlers'}:
                raise ValueError('A UI handler announcement is required')
            result = self.service.ui_claim(body['handlers'])
        elif path == '/axx-api/connect/approval':
            if set(body) != {'request_id', 'approval_id', 'decision'}:
                raise ValueError('Invalid approval fields')
            result = self.provider.approve(body['request_id'], body['approval_id'], body['decision'])
        elif path == '/axx-api/connect/login':
            if body:
                raise ValueError('Login accepts no credentials')
            result = self.provider.login()
            url = result.get('authUrl') or result.get('auth_url')
            if url:
                import webbrowser
                parsed = urllib.parse.urlsplit(url)
                if parsed.scheme != 'https' or parsed.hostname not in {'auth.openai.com', 'chatgpt.com'} or parsed.username or parsed.password or parsed.port not in {None, 443}:
                    raise ValueError('Runtime returned an unexpected authentication host')
                webbrowser.open(url)
        elif path in ('/axx-api/connect/disconnect', '/axx-api/connect/logout'):
            if body:
                raise ValueError('Local disconnect accepts no parameters')
            result = self.provider.disconnect()
            with self.h.server.connect_engine_lock:
                self.h.server.connect_engine_status = None
        elif path == '/axx-api/connect/login-cancel':
            if body:
                raise ValueError('Login cancellation accepts no parameters')
            result = self.provider.login_cancel()
        elif path == '/axx-api/connect/reconnect':
            if body:
                raise ValueError('Reconnect accepts no parameters')
            result = self.provider.reconnect()
        else:
            self.h._send_json(404, {'error': {'code': 'NOT_FOUND', 'message': 'Unknown Axx Connect route'}})
            return True
        self.h._send_json(200, result)
        return True
