"""Development-only Telegram bridge to the installed Axx backend."""
import argparse
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode
import urllib.request

from backend.auth.chatgpt_auth import _dpapi_decrypt, _dpapi_encrypt
from backend.telegram.config import _file_lease
from backend.telegram.worker import NoRedirect

MAX_RESPONSE = 1024 * 1024


class CoreClient:
    def __init__(self, descriptor_path):
        self.descriptor_path = Path(descriptor_path)
        self.instance_id = None

    def _descriptor(self):
        raw = self.descriptor_path.read_bytes()
        if len(raw) > 16384:
            raise ValueError('Invalid installed backend endpoint')
        desc = json.loads(_dpapi_decrypt(raw))
        if (not isinstance(desc, dict) or type(desc.get('port')) is not int or not 1 <= desc['port'] <= 65535
                or not isinstance(desc.get('token'), str) or len(desc['token']) < 32
                or not isinstance(desc.get('instance_id'), str) or not desc['instance_id']):
            raise ValueError('Invalid installed backend endpoint')
        if self.instance_id is not None and desc['instance_id'] != self.instance_id:
            raise RuntimeError('Installed backend changed')
        return desc

    def request(self, method, route, body=None):
        desc = self._descriptor()
        headers = {'Authorization': 'Bearer ' + desc['token']}
        raw = None
        if body is not None:
            raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request('http://127.0.0.1:' + str(desc['port']) + route,
                                         data=raw, headers=headers, method=method)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=75) as response:
            data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError('Installed backend response too large')
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError('Invalid installed backend response')
        if route == '/axx-api/status':
            if result.get('instance_id') != desc['instance_id'] or result.get('ready') is not True:
                raise ValueError('Installed backend identity mismatch')
            self.instance_id = desc['instance_id']
        return result

    def verify(self):
        return self.request('GET', '/axx-api/status')


class ChatProxy:
    def __init__(self, core):
        self.core = core

    def get(self, conversation_id):
        return self.core.request('GET', '/axx-api/chat/conversations?' + urlencode({'id': conversation_id}))

    def mutate(self, action, body):
        if action not in ('create', 'save'):
            raise ValueError('Unsupported chat action')
        return self.core.request('POST', '/axx-api/chat/' + action, body)


class CommandProxy:
    def __init__(self, core):
        self.core = core

    def resolve(self, text, source='text'):
        return self.core.request('POST', '/axx-api/commands/resolve', {'text': text, 'source': source})

    def executable_catalog(self):
        return self.core.request('GET', '/axx-api/commands/executable')

    def prepare(self, command_id, inputs, *, source, operation_id, conversation_id, command_mode):
        return self.core.request('POST', '/axx-api/commands/prepare', {'command_id': command_id, 'inputs': inputs,
            'source': source, 'operation_id': operation_id, 'conversation_id': conversation_id, 'command_mode': command_mode})

    def get(self, operation_id):
        try:
            return self.core.request('GET', '/axx-api/commands/operations?' + urlencode({'operation_id': operation_id})).get('operation')
        except Exception:
            return None

    def execute(self, operation_id, approved=False):
        if approved is not False:
            raise ValueError('Remote approval is not supported')
        return self.core.request('POST', '/axx-api/commands/execute', {'operation_id': operation_id, 'approved': False})

    def cancel(self, operation_id):
        return self.core.request('POST', '/axx-api/commands/cancel', {'operation_id': operation_id})


class DisabledInference:
    def route(self, request):
        return {'ok': False, 'error': {'code': 'SELECTED_PROVIDER_UNAVAILABLE'}}

    def cancel(self, request_id):
        return False


class CallbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, service):
        self.token = secrets.token_urlsafe(32)
        self.instance_id = secrets.token_hex(16)
        self.service = service
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1', 0), CallbackHandler)

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


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def authorized(self):
        return (not self.headers.get('Origin')
                and self.headers.get('Host') == '127.0.0.1:' + str(self.server.server_port)
                and secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.token))

    def send_json(self, status, value):
        encoded = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if not self.authorized():
            self.send_json(403, {'error': 'forbidden'})
        elif self.path == '/axx-api/telegram/status':
            self.send_json(200, self.server.service.status())
        elif self.path == '/axx-api/telegram/commands':
            self.send_json(200, self.server.service.command_catalog())
        else:
            self.send_json(404, {'error': 'not_found'})

    def do_POST(self):
        if not self.authorized():
            self.send_json(403, {'error': 'forbidden'})
            return
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                raise ValueError()
            length = self.headers.get('Content-Length', '')
            if not length.isdecimal() or not 0 < int(length) <= 16384:
                raise ValueError()
            raw = self.rfile.read(int(length))
            if len(raw) != int(length):
                raise ValueError()
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError()
            if self.path == '/axx-api/telegram/input':
                result = self.server.service.admit(body)
            elif self.path == '/axx-api/telegram/bot-input':
                result = self.server.service.admit_bot(body)
            else:
                self.send_json(404, {'error': 'not_found'})
                return
            self.send_json(200, result)
        except Exception:
            self.send_json(400, {'error': 'invalid_request'})


def write_endpoint(path, server):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({'port': server.server_port, 'token': server.token,
                      'instance_id': server.instance_id, 'pid': os.getpid()}).encode()
    encrypted = _dpapi_encrypt(raw)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.endpoint-', delete=False) as f:
            name = f.name
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def remove_endpoint(path, server):
    try:
        value = json.loads(_dpapi_decrypt(path.read_bytes()))
        if value.get('instance_id') == server.instance_id:
            path.unlink(missing_ok=True)
    except (OSError, ValueError, RuntimeError):
        pass


def write_health(path, core_bound, service, facade):
    process = service.bot_process
    value = {'core_bound': bool(core_bound),
             'bot_running': bool(process is not None and process.poll() is None),
             'miniapp_port': facade.server.server_port if facade.server else None,
             'checked_at': time.time()}
    name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.health-', delete=False) as f:
            name = f.name
            json.dump(value, f)
        os.replace(name, path)
    except OSError:
        pass
    finally:
        if name and os.path.exists(name):
            try:
                os.unlink(name)
            except OSError:
                pass


def maintain(service, facade, endpoint, port, now, retry_at):
    if now < retry_at:
        return retry_at
    try:
        service.start_bot(endpoint_file=endpoint)
    except (OSError, ValueError, RuntimeError, ImportError):
        pass
    if facade.server is None:
        try:
            facade.start(port=port)
        except (OSError, ValueError, KeyError, RuntimeError, ImportError):
            pass
    return now + 10


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Axx')
    parser.add_argument('--miniapp-port', type=int, default=6451)
    parser.add_argument('--account-channel', action='store_true')
    args = parser.parse_args(argv)
    data_dir = args.data_dir
    local_dir = data_dir / 'telegram' / 'local-channel'
    with _file_lease(local_dir / 'daemon.lock', 'TELEGRAM_DAEMON_IN_USE'):
        core = CoreClient(data_dir / 'connect' / 'endpoint.dpapi')
        core.verify()
        from backend.telegram.service import TelegramService
        from backend.telegram.miniapp import MiniAppFacade
        service = TelegramService(data_dir, ChatProxy(core), CommandProxy(core), DisabledInference(), lambda: None)
        service.connection = lambda: True
        server = CallbackServer(service)
        thread = threading.Thread(target=server.serve_forever, daemon=True, name='telegram-local-callback')
        endpoint = local_dir / 'connect' / 'endpoint.dpapi'
        facade = MiniAppFacade(data_dir, service)
        try:
            thread.start()
            write_endpoint(endpoint, server)
            if args.account_channel:
                service.start(endpoint_file=endpoint)
            retry_at = 0
            while True:
                try:
                    core.verify()
                except Exception:
                    write_health(local_dir / 'health.json', False, service, facade)
                    raise
                retry_at = maintain(service, facade, endpoint, args.miniapp_port, time.monotonic(), retry_at)
                write_health(local_dir / 'health.json', True, service, facade)
                time.sleep(2)
        finally:
            service.close()
            facade.close()
            write_health(local_dir / 'health.json', False, service, facade)
            remove_endpoint(endpoint, server)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
