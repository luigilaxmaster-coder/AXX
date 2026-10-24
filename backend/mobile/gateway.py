from __future__ import annotations

import ipaddress
import http.client
import json
import logging
import math
import os
import socket
import ssl
import threading
import time
import uuid
import tempfile
import urllib.parse
from collections import deque
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
        self._avatar_lock = threading.Lock()
        self._avatar_sequence = 0
        self._avatar_events = deque(maxlen=128)

    def avatar_gesture(self, device_id, body):
        if not isinstance(body, dict) or set(body) != {'kind', 'dx', 'dy'} or body['kind'] not in ('rotate', 'move', 'end'):
            raise ValueError('Invalid avatar gesture')
        dx, dy = body['dx'], body['dy']
        if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 200 for value in (dx, dy)):
            raise ValueError('Avatar gesture is out of range')
        if body['kind'] == 'end' and (dx != 0 or dy != 0):
            raise ValueError('Avatar end gesture must have zero movement')
        with self._avatar_lock:
            self._avatar_sequence += 1
            event = {'sequence': self._avatar_sequence, 'device_id': device_id,
                     'kind': body['kind'], 'dx': dx, 'dy': dy, 'at': time.monotonic()}
            self._avatar_events.append(event)
            return {'sequence': self._avatar_sequence}

    def avatar_events(self, since):
        if type(since) is not int or since < 0:
            raise ValueError('Invalid avatar sequence')
        with self._avatar_lock:
            now = time.monotonic()
            events = [{key: value for key, value in event.items() if key != 'at'}
                      for event in self._avatar_events if event['sequence'] > since and now - event['at'] <= 2]
            return {'sequence': self._avatar_sequence, 'events': events}

    def clear_avatar_device(self, device_id):
        with self._avatar_lock:
            self._avatar_events = deque((event for event in self._avatar_events if event['device_id'] != device_id), maxlen=128)

    def work_execute(self, device_id, body):
        from backend.commands import ADAPTERS, TERMINAL
        allowed = set(ADAPTERS)
        if (not isinstance(body, dict) or set(body) != {'command_id', 'inputs', 'operation_id', 'approved'}
                or body['command_id'] not in allowed or not isinstance(body['inputs'], dict)
                or type(body['approved']) is not bool):
            raise ValueError('Invalid Work command')
        try:
            operation_id = str(uuid.UUID(body['operation_id']))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError('Invalid Work operation ID') from exc
        if operation_id != body['operation_id']:
            raise ValueError('Invalid Work operation ID')
        prepared = self.backend_call('POST', '/axx-api/commands/prepare',
                                     {'command_id': body['command_id'], 'inputs': body['inputs'],
                                      'source': 'text', 'operation_id': operation_id})
        if prepared.get('ok') is False:
            raise ValueError(prepared.get('error', {}).get('message', 'Work preparation failed'))
        if prepared.get('state') in TERMINAL:
            return prepared
        self.store.record_work(operation_id, device_id, body['command_id'], prepared['inputs'])
        risk = ADAPTERS[body['command_id']]['risk']
        if risk not in ('read', 'desktop_open'):
            return {**prepared, 'state': 'awaiting_pc_approval', 'pc_approval_required': True}
        result = self.backend_call('POST', '/axx-api/commands/execute',
                                   {'operation_id': operation_id, 'approved': True})
        if result.get('ok') is False:
            raise ValueError(result.get('error', {}).get('message', 'Work execution failed'))
        return result

    def work_operation(self, operation_id, device_id=None):
        try:
            canonical = str(uuid.UUID(operation_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError('Invalid Work operation ID') from exc
        if canonical != operation_id:
            raise ValueError('Invalid Work operation ID')
        if device_id is not None:
            record = self.store.work_request(operation_id)
            if not record or record['device_id'] != device_id:
                raise ValueError('Work operation does not belong to this phone')
        result = self.backend_call('GET', '/axx-api/commands/operations?operation_id='+urllib.parse.quote(operation_id), None)
        if result.get('ok') is False:
            raise ValueError(result.get('error', {}).get('message', 'Work operation unavailable'))
        return result.get('operation')

    def work_catalog(self):
        from backend.commands import ADAPTERS
        return {'commands': [{'id': key, 'title': value['title'], 'description': value['description'],
                              'risk': value['risk'], 'parameters': value['parameters'],
                              'pc_approval_required': value['risk'] not in ('read', 'desktop_open')}
                             for key, value in ADAPTERS.items()]}

    def work_resolve(self, body):
        if not isinstance(body, dict) or set(body) != {'text'} or not isinstance(body['text'], str) or not 1 <= len(body['text'].strip()) <= 8000:
            raise ValueError('Escribe una orden de hasta 8.000 caracteres')
        result = self.backend_call('POST', '/axx-api/commands/resolve', {'text': body['text'], 'source': 'text'})
        if result.get('ok') is False:
            raise ValueError(result.get('error', {}).get('message', 'No se pudo interpretar la orden'))
        return result

    def pending_work(self):
        rows = self.store.pending_work_requests()
        pending = []
        approved_devices = {row['device_id'] for row in self.store.devices()
                            if not row['revoked'] and 'tools.control' in row['scopes']}
        for record in rows:
            operation_id = record['operation_id']
            if record['device_id'] not in approved_devices:
                continue
            from backend.commands import ADAPTERS
            operation = self.work_operation(operation_id)
            if operation and operation['state'] == 'awaiting_approval':
                pending.append(record)
        return {'operations': pending}

    def approve_work(self, body):
        if not isinstance(body, dict) or set(body) != {'operation_id', 'approved'} or type(body['approved']) is not bool:
            raise ValueError('Invalid Work approval')
        operation_id = body['operation_id']
        record = self.store.work_request(operation_id)
        if not record:
            raise ValueError('Unknown phone Work request')
        if not any(row['device_id'] == record['device_id'] and not row['revoked'] and 'tools.control' in row['scopes']
                   for row in self.store.devices()):
            raise ValueError('This phone no longer has Work permission')
        operation = self.work_operation(operation_id)
        if not operation or operation['command_id'] != record['command_id'] or operation['inputs'] != record['inputs']:
            raise ValueError('Work request changed before approval')
        if not body['approved']:
            return self.backend_call('POST', '/axx-api/commands/cancel', {'operation_id': operation_id})
        return self.backend_call('POST', '/axx-api/commands/execute', {'operation_id': operation_id, 'approved': True})

    def _execute_pc_command(self, device_id, user_text, conversation_id, task_id):
        """Only exact registered commands; the persisted chat mode stays authoritative."""
        if user_text.split(maxsplit=1)[0] == '/cli':
            return 'Selecciona una ventana observada en Comandos de Axx. /cli no ejecuta controles por nombre desde el teléfono.'
        resolved = self.backend_call('POST', '/axx-api/commands/resolve', {'text': user_text, 'source': 'text'})
        if resolved.get('match') != 'exact' or not resolved.get('command_id'):
            # A conversational imperative ("escribe un poema") is not authority
            # to run a PC action. Explicit slash commands remain fail-closed.
            if user_text.startswith('/'):
                return 'No hay un comando exacto registrado para esa orden. Revisa el catálogo de Comandos en la PC.'
            return None
        if not any(d['device_id'] == device_id and not d['revoked'] and 'tools.control' in d['scopes']
                   for d in self.store.devices()):
            return 'Activa el permiso Work de este teléfono en Axx para preparar comandos de la PC.'
        thread = self.backend_call('GET', '/axx-api/chat/conversations?shared_id='+urllib.parse.quote(conversation_id), None)
        if not thread.get('id'): raise ValueError('No se pudo resolver el chat de origen en la PC')
        operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'axx-mobile:'+task_id))
        prepared = self.backend_call('POST', '/axx-api/commands/prepare', {
            'command_id': resolved['command_id'], 'inputs': resolved.get('inputs', {}),
            'source': 'text', 'conversation_id': thread['id'], 'operation_id': operation_id})
        if prepared.get('operation_id') != operation_id:
            raise ValueError('La preparación no corresponde a la solicitud móvil')
        self.store.record_work(operation_id, device_id, prepared['command_id'], prepared['inputs'])
        if prepared.get('state') == 'awaiting_approval':
            return f'Orden preparada en la PC: {prepared["command_id"]}. Revisa y aprueba la tarjeta de este chat. Operación: {operation_id}.'
        if prepared.get('state') != 'prepared':
            return f'La orden no se ejecutó. Estado: {prepared.get("state", "desconocido")}. Operación: {operation_id}.'
        # Never manufacture approval. Auto-safe authorization is evaluated by the backend.
        if not any(d['device_id'] == device_id and not d['revoked'] and 'tools.control' in d['scopes']
                   for d in self.store.devices()):
            self.backend_call('POST', '/axx-api/commands/cancel', {'operation_id': operation_id})
            return 'El permiso Work fue revocado antes de ejecutar.'
        result = self.backend_call('POST', '/axx-api/commands/execute', {'operation_id': operation_id, 'approved': False})
        if result.get('state') == 'succeeded' and result.get('postconditions_passed') is True:
            output = json.dumps(result.get('output'), ensure_ascii=False)[:12000]
            return f'Ejecutado y verificado en la PC: {prepared["command_id"]}.\n{output}'
        return f'No se confirmó el efecto en la PC. Estado: {result.get("state", "desconocido")}. Consulta la operación {operation_id} antes de repetir.'

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

        user_text = body['text'].strip()
        is_potential_cmd = user_text.startswith('/') or any(user_text.lower().startswith(p) for p in (
            'abre ', 'abrir ', 'estado ', 'iniciar ', 'ejecutar ', 'haz ', 'crea ', 'crear ', 'cerrar ', 'leer ', 'escribe ', 'escribir '
        ))

        preferences = dict(self.preferences or {})
        engine_available = preferences.get('provider') == 'bridge' and (
            preferences.get('selection_mode') == 'automatic_free' or
            bool(preferences.get('model') and preferences.get('provider_name')))
        def engine_unavailable():
            self.store.finish_command(task_id, 'failed', {'error':{'code':'ENGINE_NOT_AVAILABLE',
                'message':'Select a configured API connection in Axx. Mobile Axx Connect queries still require tool isolation verification.'}})
        if not is_potential_cmd and not engine_available:
            engine_unavailable()
            return self.store.command(device_id, command_id)

        if not self._chat_slots.acquire(blocking=False):
            self.store.finish_command(task_id, 'failed', {'error':{'code':'BUSY','message':'Axx is busy. Your text is still saved on the phone.'}})
            return self.store.command(device_id, command_id)

        def run():
            try:
                self.store.finish_command(task_id, 'running')
                snapshot = self.shared.merge_messages([{'id':task_id+':user', 'role':'user', 'text':body['text'], 'at':time.time()*1000}], 'mobile', conversation_id)

                # 1. If this is an explicit or recognizable command for the PC, execute/prepare it directly on the PC
                if is_potential_cmd:
                    pc_ans = self._execute_pc_command(device_id, user_text, conversation_id, task_id)
                    if pc_ans is not None:
                        self.shared.merge_messages([{'id':task_id+':assistant', 'role':'assistant', 'text':pc_ans, 'at':time.time()*1000}], 'pc', conversation_id)
                        self.store.finish_command(task_id, 'completed', {'choices': [{'message': {'role': 'assistant', 'content': pc_ans}}]})
                        return

                if not engine_available:
                    engine_unavailable()
                    return

                # 2. General conversational query: inject PC host primary device instruction so the LLM knows it controls the PC
                pc_sys_prompt = (
                    "Eres Axx, el asistente autónomo ejecutándose en la computadora principal del usuario (Windows PC). "
                    "El usuario se comunica desde su teléfono mediante Axx Mobile. "
                    "Cualquier orden o consulta sobre el sistema, programas, ventanas, procesos o archivos se refiere "
                    "a la PC anfitriona. No afirmes haber ejecutado ninguna acción sin un recibo del ejecutor. "
                )
                messages = [{'role': 'system', 'content': pc_sys_prompt}]
                for m in snapshot['messages'][-100:]:
                    messages.append({'role': m['role'], 'content': m['text']})

                request = {'request_id':task_id, 'conversation_id':conversation_id, 'messages': messages}
                for key in ('model', 'provider_name'):
                    request[key] = preferences.get(key, '')
                request['selection_mode'] = preferences.get('selection_mode', 'manual')
                result = self.backend_call('POST', '/axx-api/chat', request)
                if result.get('ok', True) is False:
                    self.store.finish_command(task_id, 'failed', result)
                    return
                answer = result.get('choices', [{}])[0].get('message', {}).get('content')
                if not isinstance(answer, str):
                    raise ValueError('The engine did not return a conversation response')
                self.shared.merge_messages([{'id':task_id+':assistant', 'role':'assistant', 'text':answer, 'at':time.time()*1000}], 'pc', conversation_id)
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
            always_on = self.store.access_settings()['always_on']
            if not self.httpd:
                return {"enabled": False, "always_on": always_on, "devices": self.store.devices()}
            return {"enabled": True, "endpoint": f"https://{self.httpd.server_address[0]}:{self.httpd.server_port}",
                    "fingerprint": self._identity[2], "always_on": always_on, "devices": self.store.devices()}

    def start(self, create_pairing=True):
        with self._lock:
            if self.httpd:
                return self.pairing() if create_pairing else self.status()
            host = self.host_resolver()
            cert, key, fingerprint = _identity_files(self.data_dir, host)
            settings = self.store.access_settings()
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
                        if path == '/v1/work/operation':
                            if not self._authorize('tools.control'): return
                            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                            if set(query) != {'operation_id'} or len(query['operation_id']) != 1:
                                raise ValueError('operation_id required')
                            operation = gateway.work_operation(query['operation_id'][0], self.device_id)
                            self._send(200 if operation else 404, {'ok': bool(operation), 'data': operation});return
                        if path == '/v1/work/catalog':
                            if self._authorize('tools.control'):
                                self._send(200, {'ok': True, 'data': gateway.work_catalog()})
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
                        if path == '/v1/avatar/gesture':
                            if not self._authorize('input.control'):return
                            self._send(200, {'ok':True,'data':gateway.avatar_gesture(self.device_id,body)});return
                        if path == '/v1/work/execute':
                            if not self._authorize('tools.control'):return
                            self._send(200, {'ok':True,'data':gateway.work_execute(self.device_id,body)});return
                        if path == '/v1/work/resolve':
                            if not self._authorize('tools.control'):return
                            self._send(200, {'ok':True,'data':gateway.work_resolve(body)});return
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
            httpd = BoundedHTTPServer((host, settings['port']), Handler)
            self.httpd = httpd
            self.thread = threading.Thread(target=httpd.serve_forever, name="axx-mobile-gateway", daemon=True)
            self.thread.start()
            self._identity = (cert, key, fingerprint)
            self._last_contact = time.monotonic()
            self._claimed = False
            self.store.set_access_settings(always_on=settings['always_on'], port=httpd.server_port)
            def watchdog():
                while self.httpd is httpd:
                    time.sleep(1)
                    self.expire_idle(httpd)
            threading.Thread(target=watchdog, name='axx-mobile-idle', daemon=True).start()
            return self.pairing() if create_pairing else self.status()

    def set_always_access(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        if enabled:
            self.start(create_pairing=False)
            self.store.set_access_settings(always_on=True, port=self.httpd.server_port)
            return self.status()
        self.store.set_access_settings(always_on=False)
        self.stop()
        return self.status()

    def resume(self):
        if self.store.access_settings()['always_on']:
            try:
                self.start(create_pairing=False)
            except (OSError, RuntimeError):
                LOG.exception('Persistent mobile access could not start')

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
            if (self.httpd is server and not self.store.access_settings()['always_on'] and now >= self._pairing_deadline
                    and now - self._last_contact > (30 if self._claimed else 120)):
                self.stop()

    def close(self):
        self.stop()
        self.control.close()

    def revoke(self, device_id):
        self.control.disconnect(device_id)
        self.voice.disconnect(device_id)
        self.clear_avatar_device(device_id)
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
