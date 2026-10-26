"""User-configured MCP connections with private persistence and bounded transport jobs."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

from .catalog import digest, tool_record, validate_arguments


def checked_config(body):
    if not isinstance(body, dict) or set(body) - {'name', 'context', 'transport', 'url', 'token', 'command', 'args', 'env', 'cwd'}:
        raise ValueError('Configuración MCP desconocida')
    config = copy.deepcopy(body)
    for key in ('name', 'context'):
        if not isinstance(config.get(key), str) or not 1 <= len(config[key]) <= 120:
            raise ValueError('Indica nombre y contexto/cuenta de la conexión')
    if config.get('transport') == 'streamable_http':
        if set(config) - {'name', 'context', 'transport', 'url', 'token'}: raise ValueError('Campos incompatibles con transporte HTTP')
        url = urlsplit(config.get('url', ''))
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.fragment or url.query
                or (url.scheme == 'http' and url.hostname not in ('127.0.0.1', '::1'))):
            raise ValueError('MCP remoto requiere HTTPS; HTTP sólo admite loopback literal. Sin credenciales en URL')
        _ = url.port
        token = config.get('token', '')
        if not isinstance(token, str) or len(token) > 8192 or any(ord(char) < 32 for char in token):
            raise ValueError('Credencial inválida')
    elif config.get('transport') == 'stdio':
        if set(config) - {'name', 'context', 'transport', 'command', 'args', 'env', 'cwd'}: raise ValueError('Campos incompatibles con stdio')
        from backend.actions.tools import artifact_path_error
        raw = config.get('command')
        if artifact_path_error(raw) or not Path(raw).is_absolute() or not Path(raw).is_file() or Path(raw).suffix.lower() != '.exe':
            raise ValueError('Selecciona un ejecutable .exe local absoluto para el servidor MCP')
        if Path(raw).name.casefold() in ('cmd.exe', 'powershell.exe', 'pwsh.exe', 'wscript.exe', 'cscript.exe'):
            raise ValueError('Selecciona el runtime/servidor MCP directamente, sin shell')
        args = config.setdefault('args', [])
        if not isinstance(args, list) or len(args) > 32 or any(not isinstance(v, str) or len(v) > 4096 or '\0' in v for v in args):
            raise ValueError('Argumentos stdio inválidos')
        env = config.setdefault('env', {})
        if not isinstance(env, dict) or len(env) > 32 or any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,79}', k)
                or not isinstance(v, str) or len(v) > 8192 or '\0' in v for k, v in env.items()):
            raise ValueError('Entorno stdio inválido')
        if any(k.casefold() in ('path', 'pythonpath', 'pythonhome', 'node_options', 'comspec', 'systemroot') for k in env):
            raise ValueError('No se permite reemplazar el entorno del runtime')
        if config.get('cwd') and (artifact_path_error(config['cwd']) or not Path(config['cwd']).is_absolute() or not Path(config['cwd']).is_dir()):
            raise ValueError('Directorio stdio inválido')
    else: raise ValueError('Selecciona stdio o streamable_http')
    if len(json.dumps(config)) > 60000: raise ValueError('Configuración demasiado grande')
    return config


class Transport:
    def __init__(self, config, cancelled=None, call_timeout=25):
        from backend.inference.process_manager import spawn_managed_process
        if type(call_timeout) is not int or not 1 <= call_timeout <= 90:
            raise ValueError('Plazo MCP inválido')
        self.call_timeout = call_timeout
        self.lock, self.messages = threading.RLock(), queue.Queue(maxsize=8)
        self.closed = False
        command = ([sys.executable, '--mcp-client-worker'] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-m', 'backend.mcp_host.worker'])
        self.process, self.job = spawn_managed_process(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        def collect():
            try:
                while not self.closed:
                    line = self.process.stdout.readline(1024 * 1024 + 2)
                    if not line or len(line) > 1024 * 1024 or not line.endswith(b'\n'): break
                    self.messages.put_nowait(json.loads(line))
            except (ValueError, OSError, queue.Full): pass
            finally:
                try: self.messages.put_nowait({'error': 'transport_closed'})
                except queue.Full: pass
        self.reader = threading.Thread(target=collect, name='axx-mcp-transport', daemon=True)
        self.reader.start()
        try:
            self._write(dict(config, call_timeout=call_timeout))
            self.ready = self._receive(cancelled or threading.Event(), 20)
            if self.ready.get('ready') is not True: raise ValueError('No se inicializó MCP: ' + str(self.ready.get('error', 'unknown')))
        except Exception:
            self.close(); raise

    def _write(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=True, allow_nan=False)+'\n').encode())
        self.process.stdin.flush()

    def _receive(self, cancelled, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancelled.is_set(): raise ValueError('Llamada MCP cancelada; revisar posibles efectos antes de repetir')
            try: return self.messages.get(timeout=.1)
            except queue.Empty: pass
        raise TimeoutError('MCP no respondió dentro del plazo; revisar efectos antes de repetir')

    def request(self, method, cancelled=None, **data):
        cancelled = cancelled or threading.Event()
        with self.lock:
            if self.closed or cancelled.is_set(): raise ValueError('Conexión MCP cerrada o cancelada')
            key = uuid.uuid4().hex
            try:
                self._write({'id': key, 'method': method, **data})
                response = self._receive(cancelled, self.call_timeout + 5)
                if response.get('id') != key or response.get('error'):
                    raise ValueError('Fallo de transporte MCP: ' + str(response.get('error', 'response_mismatch')))
                return response['result']
            except Exception:
                self.close(); raise

    def close(self):
        from backend.inference.process_manager import terminate_process_tree
        if self.closed: return
        self.closed = True
        terminate_process_tree(self.process, self.job)
        for stream in (self.process.stdin, self.process.stdout):
            try: stream.close()
            except (OSError, ValueError): pass


class McpHost:
    def __init__(self, state_dir, commands):
        self.path = Path(state_dir) / 'mcp-connections.dpapi'
        self.commands, self.lock = commands, threading.RLock()
        self.publish_lock = threading.Lock()
        self.connections, self.transports, self.catalog = {}, {}, {}
        self.probes = {}
        self.storage_error = None
        if self.path.exists():
            from backend.auth.chatgpt_auth import _dpapi_decrypt
            try:
                if self.path.stat().st_size > 2 * 1024 * 1024: raise ValueError('Configuración MCP demasiado grande')
                stored = json.loads(_dpapi_decrypt(self.path.read_bytes()))
                if not isinstance(stored, dict) or len(stored) > 16: raise ValueError('Registro MCP inválido')
                for key, item in stored.items():
                    if not re.fullmatch('[a-f0-9]{16}', key): raise ValueError('Identidad MCP inválida')
                    config = checked_config(item['config'])
                    self.connections[key] = {**item, 'config': config, 'revision': digest(config), 'status': 'disconnected'}
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                self.connections = {}
                self.storage_error = 'No se pudo leer la configuración MCP privada. Se conserva intacta; no se guardarán cambios.'

    def _save(self):
        if self.storage_error: raise ValueError(self.storage_error)
        from backend.auth.chatgpt_auth import _dpapi_encrypt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_bytes(_dpapi_encrypt(json.dumps(self.connections, ensure_ascii=True, allow_nan=False).encode()))
        os.replace(temporary, self.path)

    def list(self):
        with self.lock:
            rows = []
            for key, item in self.connections.items():
                config = item['config']
                rows.append({'id': key, 'name': config['name'], 'context': config['context'], 'transport': config['transport'],
                    'endpoint': config.get('url', config.get('command')), 'status': item['status'],
                    'last_checked': item.get('last_checked'), 'diagnostic': item.get('diagnostic'),
                    'rejected_tools': copy.deepcopy(item.get('rejected_tools', [])),
                    'protocol': item.get('protocol'), 'tools': [copy.deepcopy(t) for t in self.catalog.values() if t['connection_id'] == key]})
            return {'connections': rows, 'storage_error': self.storage_error}

    def add(self, body):
        config = checked_config(body)
        with self.lock:
            if self.storage_error: raise ValueError(self.storage_error)
            if len(self.connections) >= 16: raise ValueError('Se admiten hasta 16 conexiones MCP')
            key = uuid.uuid4().hex[:16]
            self.connections[key] = {'config': config, 'revision': digest(config), 'status': 'disconnected', 'policies': {}}
            self._save()
        return {'id': key, 'status': 'disconnected'}

    def _discover(self, key, transport, cancelled=None):
        rows, cursors, cursor = [], set(), None
        for _ in range(20):
            page = transport.request('tools/list', cancelled, **({'cursor': cursor} if cursor else {}))
            if not isinstance(page.get('tools'), list): raise ValueError('Catálogo MCP inválido')
            rows.extend(page['tools'])
            if len(rows) > 500: raise ValueError('El servidor supera 500 herramientas; limita su catálogo')
            if len(json.dumps(rows, allow_nan=False)) > 4 * 1024 * 1024: raise ValueError('El catálogo supera 4 MiB')
            cursor = page.get('nextCursor')
            if not cursor: break
            if not isinstance(cursor, str) or len(cursor) > 4096 or cursor in cursors: raise ValueError('Paginación MCP repetida o inválida')
            cursors.add(cursor)
        else: raise ValueError('El catálogo excedió 20 páginas')
        names = [row.get('name') for row in rows if isinstance(row, dict)]
        if any(not isinstance(name, str) for name in names) or len(set(names)) != len(rows):
            raise ValueError('Nombres MCP duplicados o inválidos')
        from jsonschema.exceptions import SchemaError
        records, rejected = [], []
        for row in rows:
            try: records.append(tool_record(key, self.connections[key]['revision'], row))
            except (ValueError, TypeError, SchemaError):
                rejected.append({'name': str(row.get('name', ''))[:128], 'reason': 'Esquema no admitido por los límites de Axx'})
        transport.rejected_tools = rejected
        return records

    def probe(self, key):
        failure, transport, ticket = None, None, object()
        with self.lock:
            if key not in self.connections: raise ValueError('Conexión desconocida')
            item = self.connections[key]
            if key in self.probes: raise ValueError('Ya se está comprobando esta conexión')
            self.probes[key] = ticket
            item['status'] = 'connecting'
            config = copy.deepcopy(item['config'])
            previous = self.transports.pop(key, None)
            for row in self.catalog.values():
                if row['connection_id'] == key: row['enabled'] = False
        self._publish()
        try:
            if previous: previous.close()
            transport = Transport(config)
            with self.lock:
                if self.probes.get(key) is not ticket: raise ValueError('Comprobación cancelada')
                self.transports[key] = transport
            records = self._discover(key, transport)
            with self.lock:
                if self.probes.get(key) is not ticket: raise ValueError('Comprobación cancelada')
                for row in records:
                    policy = item['policies'].get(row['schema_digest'] + ':' + row['name'], {})
                    row.update(enabled=policy.get('enabled', False), read_only=policy.get('read_only', False))
                self.catalog = {k:v for k,v in self.catalog.items() if v['connection_id'] != key} | {row['id']:row for row in records}
                item.update(status='connected', protocol=transport.ready['protocol'], diagnostic=None,
                            rejected_tools=transport.rejected_tools, last_checked=time.time())
                self._save()
                result = {'id':key,'status':item['status'],'tools':len(records),'protocol':item.get('protocol')}
        except Exception as exc:
            if transport: transport.close()
            with self.lock:
                if self.probes.get(key) is ticket:
                    self.transports.pop(key, None)
                    item.update(status='disconnected', diagnostic=type(exc).__name__ + ': conexión o catálogo no comprobado', last_checked=time.time())
                    for row in self.catalog.values():
                        if row['connection_id'] == key: row['enabled'] = False
                    self._save()
            failure = ValueError('Conexión o catálogo no comprobado; actualiza antes de ejecutar')
        finally:
            with self.lock:
                if self.probes.get(key) is ticket: self.probes.pop(key)
            self._publish()
        if failure: raise failure
        return result

    def activate(self, tool_id, enabled, read_only=False):
        if type(enabled) is not bool or type(read_only) is not bool: raise ValueError('Activación inválida')
        with self.lock:
            row = self.catalog.get(tool_id)
            if not row: raise ValueError('Descubre primero la herramienta')
            if self.connections[row['connection_id']]['status'] != 'connected': raise ValueError('Conexión no comprobada')
            row.update(enabled=enabled, read_only=read_only)
            self.connections[row['connection_id']]['policies'][row['schema_digest'] + ':' + row['name']] = {'enabled':enabled, 'read_only':read_only}
            self._save()
            result = copy.deepcopy(row)
        self._publish()
        return result

    def disconnect(self, key):
        with self.lock:
            if key not in self.connections: raise ValueError('Conexión desconocida')
            self.probes.pop(key, None)
            transport = self.transports.pop(key, None)
            if transport: transport.close()
            self.connections[key]['status'] = 'disconnected'
            for row in self.catalog.values():
                if row['connection_id'] == key: row['enabled'] = False
            self._save()
        self._publish()
        return {'id':key, 'status':'disconnected'}

    def _publish(self):
        # Lock order: never hold the host lock while entering CommandService.
        with self.publish_lock:
            with self.lock: records = copy.deepcopy(list(self.catalog.values()))
            self.commands.refresh_mcp_catalog(self, records)

    def validate(self, key, arguments):
        with self.lock:
            row = self.catalog.get(key)
            if not row or not row['enabled'] or self.connections[row['connection_id']]['status'] != 'connected':
                raise ValueError('Herramienta MCP desactivada o desconectada')
            row = copy.deepcopy(row)
        validate_arguments(row['input_schema'], arguments)
        return copy.deepcopy(row)

    def call(self, key, arguments, cancelled, operation_id):
        # No manager lock across I/O: disconnect/cancel must remain available.
        with self.lock:
            row = self.validate(key, arguments)
            transport = self.transports[row['connection_id']]
        try:
            current = self._discover(row['connection_id'], transport, cancelled)
            if not any(value['id'] == key for value in current):
                raise ValueError('El esquema MCP cambió; actualiza el catálogo antes de ejecutar')
            with self.lock: self.validate(key, arguments)
            if cancelled.is_set(): raise ValueError('Cancelado antes del despacho MCP')
            result = transport.request('tools/call', cancelled, name=row['name'], arguments=arguments,
                                       meta={'axx/operation_id':operation_id, 'axx/schema_digest':row['schema_digest']})
        except Exception:
            transport.close()
            with self.lock:
                if self.transports.get(row['connection_id']) is transport:
                    self.transports.pop(row['connection_id'])
                    self.connections[row['connection_id']]['status'] = 'disconnected'
                    for value in self.catalog.values():
                        if value['connection_id'] == row['connection_id']: value['enabled'] = False
                    self._save()
            self._publish()
            raise
        return result, row

    def close(self):
        with self.lock:
            self.probes.clear()
            transports = list(self.transports.values())
            self.transports.clear()
        for transport in transports: transport.close()
