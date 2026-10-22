from __future__ import annotations

import ipaddress
import http.client
import json
import logging
import os
import socket
import ssl
import threading
import time
import uuid
import tempfile
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from backend.mobile.trust_store import MobileTrustStore, PairingError, CommandConflict
from backend.mobile.shared_state import SharedState

LOG = logging.getLogger("axx.mobile")
MAX_BODY = 2 * 1024 * 1024


def lan_address():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError as exc:
        raise RuntimeError("No local IPv4 address is available for the phone") from exc
    finally:
        probe.close()
    parsed = ipaddress.ip_address(address)
    if not parsed.is_private:
        raise RuntimeError("Axx Mobile requires a private IPv4 network")
    return address


def _identity_files(data_dir: Path, host: str):
    data_dir.mkdir(parents=True, exist_ok=True)
    cert_path = data_dir / "mobile-host-cert.pem"
    key_path = data_dir / ("mobile-host-key.dpapi" if os.name == 'nt' else "mobile-host-key.pem")
    if cert_path.exists() != key_path.exists():
        raise RuntimeError("Mobile identity is incomplete; restore its certificate and key before enabling access")
    if not cert_path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Axx Desktop Mobile Gateway")])
        address = ipaddress.ip_address(host)
        cert = (x509.CertificateBuilder()
                .subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
                .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(address)]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(key, hashes.SHA256()))
        key_bytes = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption())
        if os.name == 'nt':
            from backend.auth.chatgpt_auth import _dpapi_encrypt
            key_bytes = _dpapi_encrypt(key_bytes)
        cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
        key_tmp, cert_tmp = key_path.with_suffix(".tmp"), cert_path.with_suffix(".tmp")
        key_tmp.write_bytes(key_bytes)
        if os.name != 'nt': os.chmod(key_tmp, 0o600)
        cert_tmp.write_bytes(cert_bytes)
        key_tmp.replace(key_path)
        cert_tmp.replace(cert_path)
    certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
    return cert_path, key_path, fingerprint


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class MobileGateway:
    """Opt-in TLS gateway over Axx's existing private backend services."""

    def __init__(self, state_path, data_dir, backend_call, pc_name=None, host_resolver=lan_address):
        self.store = MobileTrustStore(state_path)
        self.store.recover_commands()
        self.shared = SharedState(state_path)
        from .voice import RemoteVoice
        self.voice = RemoteVoice(self.store, self.shared, backend_call)
        from .control import RemoteControl
        self.control = RemoteControl(self.store)
        self.data_dir = Path(data_dir) / "mobile"
        self.backend_call = backend_call
        self.pc_name = pc_name or socket.gethostname()
        self.host_resolver = host_resolver
        self.httpd = None
        self.thread = None
        self._lock = threading.RLock()
        self._last_pairing = None
        self._identity = None
        self._chat_slots = threading.BoundedSemaphore(2)
        self._last_contact = 0
        self._claimed = False
        self._pairing_deadline = 0
        self.preferences = None
        self.appearance = None

    def admit_chat(self, device_id, body):
        if set(body) - {'command_id', 'operation', 'text', 'conversation_id'} or body.get('operation') != 'chat':
            raise ValueError('Unsupported operation')
        if not isinstance(body.get('text'), str) or not 1 <= len(body['text'].strip()) <= 12000:
            raise ValueError('Enter between 1 and 12000 characters')
        conversation_id = body.get('conversation_id')
        if not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 160:
            raise ValueError('Select a PC conversation')
        command_id = body.get('command_id')
        payload = {k:v for k,v in body.items() if k != 'command_id'}
        admission = self.store.admit_command(device_id, command_id, payload)
        if admission['duplicate']:
            return self.store.command(device_id, command_id)
        task_id = admission['task_id']
        preferences = dict(self.preferences or {})
        if preferences.get('provider') != 'bridge' or not preferences.get('model') or not preferences.get('provider_name'):
            self.store.finish_command(task_id, 'failed', {'error':{'code':'ENGINE_NOT_AVAILABLE',
                'message':'Select a configured API connection in Axx. Mobile Axx Connect queries still require tool isolation verification.'}})
            return self.store.command(device_id, command_id)
        if not self._chat_slots.acquire(blocking=False):
            self.store.finish_command(task_id, 'failed', {'error':{'code':'BUSY','message':'Axx is busy. Your text is still saved on the phone.'}})
            return self.store.command(device_id, command_id)

        def run():
            try:
                self.store.finish_command(task_id, 'running')
                snapshot = self.shared.merge_messages([{'id':task_id+':user', 'role':'user', 'text':body['text'], 'at':time.time()*1000}], 'mobile', conversation_id)
                request = {'request_id':task_id, 'conversation_id':conversation_id, 'messages':[
                    {'role':m['role'],'content':m['text']} for m in snapshot['messages'][-100:]
                ]}
                for key in ('model', 'provider_name'):
                    request[key] = preferences[key]
                result = self.backend_call('POST', '/axx-api/chat', request)
                if result.get('ok', True) is False:
                    self.store.finish_command(task_id, 'failed', result)
                    return
                answer = result.get('choices', [{}])[0].get('message', {}).get('content')
                if not isinstance(answer, str):
                    raise ValueError('The engine did not return a conversation response')
                self.shared.merge_messages([{'id':task_id+':assistant', 'role':'assistant', 'text':answer, 'at':time.time()*1000}], 'mobile', conversation_id)
                self.store.finish_command(task_id, 'completed', result)
            except Exception:
                LOG.exception('Mobile conversation outcome unavailable')
                self.store.finish_command(task_id, 'outcome_unknown', {'error':{'code':'OUTCOME_UNKNOWN','message':'Check status before sending again.'}})
            finally:
                self._chat_slots.release()
        threading.Thread(target=run, name='axx-mobile-chat', daemon=True).start()
        return self.store.command(device_id, command_id)

    @classmethod
    def for_backend(cls, server, state_path, data_dir):
        def call(method, path, body):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=75)
            try:
                connection.request(method, path, body=json.dumps(body) if body is not None else None,
                                   headers={'Authorization':'Bearer '+server.host_token, 'Content-Type':'application/json'})
                response = connection.getresponse()
                raw = response.read(8*1024*1024+1)
                if len(raw) > 8*1024*1024:
                    raise ValueError('Respuesta demasiado grande')
                result = json.loads(raw)
                if response.status >= 400:
                    result['ok'] = False
                return result
            finally:
                connection.close()
        return cls(state_path, data_dir, call)

    def status(self):
        with self._lock:
            if not self.httpd:
                return {"enabled": False, "devices": self.store.devices()}
            return {"enabled": True, "endpoint": f"https://{self.httpd.server_address[0]}:{self.httpd.server_port}",
                    "fingerprint": self._identity[2], "devices": self.store.devices()}

    def start(self):
        with self._lock:
            if self.httpd:
                return self.pairing()
            host = self.host_resolver()
            cert, key, fingerprint = _identity_files(self.data_dir, host)
            gateway = self

            class Handler(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def setup(self):
                    self.request.settimeout(10)
                    self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.request = context.wrap_socket(self.request, server_side=True)
                    super().setup()

                def finish(self):
                    try:
                        super().finish()
                    finally:
                        self.request.close()

                def log_message(self, format, *args):
                    LOG.info("%s %s", self.command, self.path.split("?", 1)[0])

                def _send(self, status, data):
                    body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    keepalive = status == 200 and self.path in ('/v1/control/events','/v1/control/status')
                    self.send_header("Connection", "keep-alive" if keepalive else "close")
                    self.end_headers()
                    self.wfile.write(body)
                    self.close_connection = not keepalive

                def _body(self):
                    if self.headers.get('Origin') or self.headers.get('Transfer-Encoding'):
                        raise ValueError('This transport requires the native Axx client')
                    if self.headers.get_content_type() != 'application/json':
                        raise ValueError('application/json is required')
                    length = self.headers.get("Content-Length", "")
                    if not length.isdecimal() or not 0 < int(length) <= MAX_BODY:
                        raise ValueError("Request body is missing or too large")
                    value = json.loads(self.rfile.read(int(length)))
                    if not isinstance(value, dict):
                        raise ValueError("Request must be a JSON object")
                    return value

                def _authorize(self, scope):
                    if gateway.httpd is not self.server:
                        self._send(403, {'ok':False,'error':{'code':'GATEWAY_DISABLED','message':'Mobile access is off on the PC. Generate a new QR in Axx settings.'}})
                        return False
                    if self.headers.get('Origin'):
                        self._send(403, {'ok':False, 'error':{'code':'NATIVE_CLIENT_REQUIRED'}})
                        return False
                    value = self.headers.get("Authorization", "")
                    credential = value[7:] if value.startswith("Bearer ") else ""
                    self.device_id = gateway.store.device_for(credential, scope)
                    if not self.device_id:
                        self._send(403, {"ok": False, "error": {"code": "SCOPE_DENIED",
                                  "message": "This device is not authorized for this operation."}})
                        return False
                    gateway._last_contact = time.monotonic()
                    return True

                def do_GET(self):
                    try:
                        routes = {
                            "/v1/status": ("/axx-api/status", "query"),
                            "/v1/catalog": ("/axx-api/actions", "query"),
                            "/v1/providers": ("/axx-api/providers", "query"),
                            "/v1/tasks": ("/axx-api/commands/operations", "query"),
                        }
                        path = urllib.parse.urlsplit(self.path).path
                        if path == '/v1/control/status':
                            if self._authorize('query'):
                                self._send(200, {'ok':True,'data':gateway.control.status(self.device_id)})
                            return
                        if path == '/v1/command':
                            if not self._authorize('query'): return
                            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                            if set(query) != {'command_id'} or len(query['command_id']) != 1:
                                raise ValueError('command_id required')
                            command = gateway.store.command(self.device_id, query['command_id'][0])
                            self._send(200 if command else 404, {'ok':bool(command), 'data':command})
                            return
                        if path == '/v1/appearance':
                            if self._authorize('query'):
                                self._send(200, {'ok':True,'data':{'appearance':gateway.appearance}})
                            return
                        if path == '/v1/snapshot':
                            if self._authorize('query'):
                                self._send(200, {'ok':True, 'data':{**gateway.shared.snapshot(), 'appearance':gateway.appearance}})
                            return
                        if path not in routes:
                            self._send(404, {"ok": False, "error": {"code": "NOT_FOUND", "message": "Unknown route"}})
                            return
                        backend_path, scope = routes[path]
                        if not self._authorize(scope):
                            return
                        data = gateway.backend_call("GET", backend_path, None)
                        if path == "/v1/catalog":
                            data = {"tools": data.get("tools", [])} if isinstance(data, dict) else {"tools": []}
                        self._send(200, {"ok": True, "data": data})
                    except Exception:
                        LOG.exception("Mobile GET failed")
                        self._send(502, {"ok": False, "error": {"code": "BACKEND_UNAVAILABLE",
                                  "message": "Axx could not complete the query."}})

                def do_POST(self):
                    try:
                        path = urllib.parse.urlsplit(self.path).path
                        body = self._body()
                        if path in ('/v1/control/acquire','/v1/control/renew','/v1/control/events','/v1/control/release'):
                            operation=path.rsplit('/',1)[1]
                            if not self._authorize('query' if operation=='release' else 'input.control'):return
                            result=getattr(gateway.control,operation)(self.device_id,body)
                            self._send(200, {'ok':True,'data':result});return
                        if path == "/v1/pair/claim":
                            result = gateway.store.consume_pairing(body.get("code"), body.get("device_name", ""))
                            gateway._last_contact = time.monotonic()
                            gateway._claimed = True
                            gateway._pairing_deadline = 0
                            self._send(200, {"ok": True, "device_id": result["device_id"],
                                             "credential": result["credential"], "scopes": result["scopes"]})
                            return
                        if path == "/v1/commands":
                            if not self._authorize("query"):
                                return
                            result = gateway.admit_chat(self.device_id, body)
                            self._send(202, {'ok':True, 'data':result})
                            return
                        if path in ('/v1/voice/poll','/v1/voice/audio','/v1/voice/cancel'):
                            if not self._authorize('voice'):return
                            if path.endswith('/poll'):result=gateway.voice.poll(self.device_id,body)
                            elif path.endswith('/audio'):result=gateway.voice.audio(self.device_id,body)
                            else:
                                if set(body)!={'session_id'}:raise ValueError('session_id required')
                                result=gateway.voice.cancel(body['session_id'],self.device_id)
                            self._send(200, {'ok':True,'data':result});return
                        self._send(404, {"ok": False, "error": {"code": "NOT_FOUND", "message": "Unknown route"}})
                    except CommandConflict:
                        self._send(409, {'ok':False, 'error':{'code':'COMMAND_CONFLICT','message':'This ID already belongs to another request.'}})
                    except PairingError:
                        self._send(403, {"ok": False, "error": {"code": "PAIRING_REJECTED",
                                  "message": "This QR expired, was already used or is invalid. Select Show new QR on your PC and scan again."}})
                    except (ValueError, TypeError, json.JSONDecodeError) as exc:
                        self._send(400, {"ok": False, "error": {"code": "INVALID_REQUEST", "message": str(exc)}})
                    except Exception:
                        LOG.exception("Mobile POST failed")
                        self._send(502, {"ok": False, "error": {"code": "BACKEND_UNAVAILABLE",
                                  "message": "Axx could not complete the operation."}})

            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if os.name == 'nt':
                from backend.auth.chatgpt_auth import _dpapi_decrypt
                descriptor, temporary = tempfile.mkstemp(dir=self.data_dir, suffix='.pem')
                try:
                    with os.fdopen(descriptor, 'wb') as output: output.write(_dpapi_decrypt(key.read_bytes()))
                    context.load_cert_chain(str(cert), temporary)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            else:
                context.load_cert_chain(str(cert), str(key))
            httpd = BoundedHTTPServer((host, 0), Handler)
            self.httpd = httpd
            self.thread = threading.Thread(target=httpd.serve_forever, name="axx-mobile-gateway", daemon=True)
            self.thread.start()
            self._identity = (cert, key, fingerprint)
            self._last_contact = time.monotonic()
            self._claimed = False
            def watchdog():
                while self.httpd is httpd:
                    time.sleep(1)
                    self.expire_idle(httpd)
            threading.Thread(target=watchdog, name='axx-mobile-idle', daemon=True).start()
            return self.pairing()

    def pairing(self):
        with self._lock:
            self.store.invalidate_pairings()
            code = self.store.create_pairing()
            # A fresh QR needs its full scan window, including while Android opens its camera.
            self._pairing_deadline = time.monotonic() + 120
            endpoint = self.status()['endpoint']
            fingerprint = self._identity[2]
            pairing_uri = "axx://pair?" + urllib.parse.urlencode({"endpoint": endpoint, "fingerprint": fingerprint, "code": code})
            return {"enabled": True, "endpoint": endpoint, "fingerprint": fingerprint,
                    "pairing_code": code, "pairing_uri": pairing_uri, "expires_in": 120,
                    "scopes": ["query", "voice"]}

    def expire_idle(self, server):
        with self._lock:
            now = time.monotonic()
            if (self.httpd is server and now >= self._pairing_deadline
                    and now - self._last_contact > (30 if self._claimed else 120)):
                self.stop()

    def close(self):
        self.stop()
        self.control.close()

    def revoke(self, device_id):
        self.control.disconnect(device_id)
        self.voice.disconnect(device_id)
        return self.store.revoke(device_id)

    def stop(self):
        self.control.disconnect()
        self.voice.disconnect()
        with self._lock:
            self.store.invalidate_pairings()
            httpd, thread = self.httpd, self.thread
            self.httpd = self.thread = None
            if not httpd:
                return False
        httpd.shutdown()
        httpd.server_close()
        if thread:
            thread.join(timeout=2)
        return True
