"""Version-pinned Codex app-server client. This is not an MCP transport.

Credentials remain owned by Codex. Only concrete tools supplied by Axx's registry
are dispatched here; generated text is never executed. Pollable events are stored
in the existing SQLite database without storing OAuth material or input prompts.
"""
from __future__ import annotations

import hashlib
import base64
import io
from contextlib import contextmanager
import inspect
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from urllib.parse import urlsplit
from backend.prompts import compose
from backend.memory import task_memory


CODEX_VERSION = '0.160.0'
TERMINAL = {'completed', 'failed', 'cancelled', 'unknown', 'limit_reached'}
MAX_EVENTS = 4096
MAX_RESPONSE = 512 * 1024
MAX_CAPABILITY_MESSAGE = 128000
TURN_TIMEOUT = 70
# Requested process/thread overrides, not an inventory of effective built-ins.
# Codex 0.160.0 ignores unified_exec=false; never treat it as a security boundary.
REQUESTED_DISABLED_FEATURES = (
    'shell_tool', 'unified_exec', 'apps', 'multi_agent', 'remote_plugin', 'hooks',
    'view_image', 'browser_use', 'computer_use', 'plugins', 'code_mode_host',
    'in_app_browser', 'sleep_tool', 'tool_suggest',
    'image_generation', 'goals', 'skill_search', 'skill_mcp_dependency_install',
    'realtime_conversation',
)


class _WriteTask:
    def __init__(self, payload, deadline, admission=None, admitted=None):
        self.payload, self.admission, self.admitted = payload, admission, admitted
        self.deadline = deadline
        self.done, self.lock = threading.Event(), threading.Lock()
        self.state, self.error = 'queued', None


class _PipeWriter:
    """One owner for stdin. A caller never writes/closes a potentially blocked pipe."""
    def __init__(self, process, failed):
        self.process, self.failed = process, failed
        self.jobs = queue.Queue(maxsize=64)
        self.thread = threading.Thread(target=self._loop, daemon=True, name='axx-codex-writer')
        self.thread.start()

    def submit(self, payload, timeout, admission=None, admitted=None):
        deadline = time.monotonic() + timeout
        task = _WriteTask(payload, deadline, admission, admitted)
        try:
            self.jobs.put(task, timeout=max(0, deadline-time.monotonic()))
        except queue.Full as exc:
            self.failed(self.process, 'WRITE_QUEUE_TIMEOUT', deadline)
            raise ProviderError('WRITE_TIMEOUT', 'La cola del runtime no pudo aceptar el mensaje.') from exc
        if not task.done.wait(max(0, deadline-time.monotonic())):
            with task.lock:
                if task.done.is_set():
                    error = task.error
                else:
                    uncertain = task.state in {'writing', 'sent'}
                    task.state = 'cancelled'
                    error = ProviderError('WRITE_OUTCOME_UNKNOWN' if uncertain else 'WRITE_TIMEOUT',
                        'La escritura al runtime agotó el plazo. No se repetirá el mensaje.')
                    task.error = error
            if not task.done.is_set():
                self.failed(self.process, error.code, deadline)
            if error:
                raise error
        if task.error:
            raise task.error

    def _claim(self, task):
        # Admission commits ownership of this message, not completion or rollback
        # of its bytes. Account notifications after commit cannot unsend a message.
        if task.admission:
            with task.admission() as recheck:
                if callable(recheck):
                    recheck()
                with task.lock:
                    if task.state != 'queued':
                        return False
                    if time.monotonic() >= task.deadline:
                        raise ProviderError('WRITE_TIMEOUT', 'El mensaje expiró en la cola; no fue enviado.')
                    task.state = 'writing'
                    if task.admitted:
                        task.admitted()
        else:
            with task.lock:
                if task.state != 'queued':
                    return False
                if time.monotonic() >= task.deadline:
                    raise ProviderError('WRITE_TIMEOUT', 'El mensaje expiró en la cola; no fue enviado.')
                task.state = 'writing'
        return True

    def _loop(self):
        while True:
            try:
                task = self.jobs.get(timeout=.2)
            except queue.Empty:
                if self.process.poll() is not None:
                    return
                continue
            close_stdin = task.payload is None
            try:
                if not self._claim(task):
                    pass
                elif task.payload is None:
                    self.process.stdin.close()
                else:
                    count = self.process.stdin.write(task.payload)
                    if count != len(task.payload):
                        raise OSError('Partial protocol write')
                    self.process.stdin.flush()
                with task.lock:
                    if task.state != 'cancelled':
                        task.state = 'sent'
            except ProviderError as exc:
                task.error = exc  # Rejected admission does not corrupt transport.
            except Exception:
                task.error = ProviderError('WRITE_OUTCOME_UNKNOWN',
                    'El transporte terminó durante la escritura. Reconcilia las operaciones antes de repetir.')
                self.failed(self.process, 'WRITE_OUTCOME_UNKNOWN', task.deadline)
            finally:
                task.payload = None
                task.done.set()
            if close_stdin or self.process.poll() is not None:
                return


class ProviderError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _safe_error(value):
    text = str(value)[:2000]
    text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]+|eyJ[A-Za-z0-9_.-]{20,})', '[redacted]', text)
    text = re.sub(r'(?i)(bearer\s+)[^\s"\']+', r'\1[redacted]', text)
    return text


def _error_code(value):
    value = str(value).lower()
    if any(term in value for term in ('rate limit', 'rate_limit', 'usage limit', 'quota', 'limit reached', 'usage_limit')):
        return 'LIMIT_REACHED'
    if any(term in value for term in ('unauthorized', 'authentication', '401', 'revoked', 'token expired', 'sign in')):
        return 'AUTH_REQUIRED'
    return 'RUNTIME_ERROR'


def discover_codex():
    """Resolve a real executable; never invoke a shell shim or install implicitly."""
    explicit = os.environ.get('AXX_CODEX_PATH')
    if explicit:
        candidates = [Path(explicit)]
    else:
        base = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@openai/codex/node_modules'
        candidates = sorted(base.glob('@openai/codex-win32-*/vendor/*/bin/codex.exe'))
    for path in candidates:
        if path.is_file() and path.suffix.lower() == '.exe':
            return path.resolve()
    raise ProviderError('RUNTIME_MISSING', 'Instala @openai/codex@0.160.0 o configura AXX_CODEX_PATH con su ejecutable.')


def _runtime_environment():
    # The runtime owns its own credential lifecycle. Axx transport credentials
    # and unrelated API secrets have no reason to enter the model process.
    blocked = {'OPENAI_BASE_URL', 'OPENAI_API_BASE', 'AXX_HOST_INSTANCE'}
    return {key: value for key, value in os.environ.items()
            if key.upper() not in blocked and not re.search(r'TOKEN|API_KEY|SECRET|PASSWORD', key.upper())}


class CodexProvider:
    """Two global turns, one turn per conversation; all effectful work stays in Axx.

    Public methods return JSON-safe dictionaries. ``start`` is asynchronous;
    ``get(request_id, after)`` returns ordered events after a sequence cursor.
    The dispatcher signature is (name, arguments, request_id, call_id, *, admission).
    """
    supports_cancel_event = True
    supports_task_memory = True
    def __init__(self, commands, db_path, cwd, dispatcher=None):
        self.commands = commands
        self.dispatcher = dispatcher
        self.cwd = str(Path(cwd).resolve())
        self.lock = threading.RLock()
        self.start_lock = threading.RLock()
        self.rpc_context = threading.local()
        self.db = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.process = None
        self.writer = None
        self.closed = False
        self.pending = {}
        self.live = {}
        self.thread_runs = {}
        self.approvals = {}
        self.next_id = 0
        self.account = None
        self.runtime_error = None
        self.verified_model = None
        self.verified_at = None
        self.account_fingerprint = None
        self.account_epoch = 0
        self.selected_model = 'gpt-6.1-sol'
        self.login_id = None
        self.disabled_mcp = {}
        self.disabled_plugins = {}
        self.model_catalog = []
        self.auth_failed = False
        self.engine_state = None
        self.local_enabled = True
        with self.db:
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS connect_conversations (
                    conversation_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL,
                    model TEXT NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS connect_runs (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, body_json TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS connect_events (
                    request_id TEXT NOT NULL, seq INTEGER NOT NULL, event_json TEXT NOT NULL,
                    PRIMARY KEY(request_id,seq));
                CREATE TABLE IF NOT EXISTS connect_settings (
                    key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
            ''')
            setting = self.db.execute("SELECT value_json FROM connect_settings WHERE key='provider_enabled'").fetchone()
            if setting:
                try:
                    self.local_enabled = json.loads(setting[0]) is True
                except ValueError:
                    self.local_enabled = False
            for row in self.db.execute('SELECT request_id,body_json FROM connect_runs').fetchall():
                body = json.loads(row['body_json'])
                if body['state'] not in TERMINAL:
                    body.update(state='unknown', error={'code': 'PROCESS_RESTARTED',
                        'message': 'La ejecución anterior fue interrumpida; consulta sus acciones antes de repetir.'})
                    self.db.execute('UPDATE connect_runs SET body_json=?,updated_at=? WHERE request_id=?',
                                    (json.dumps(body), time.time(), row['request_id']))

    def _store(self, run):
        run['updated_at'] = time.time()
        persisted = {key: value for key, value in run.items() if not key.startswith('_')}
        if run.get('_source_tainted'):
            persisted.update(response='', response_retained=False)
            if persisted.get('error'):
                persisted['error']={'code':'SOURCE_INFERENCE_FAILED','message':'No terminó la consulta de contexto temporal.'}
                run['error']=dict(persisted['error'])
        with self.db:
            self.db.execute('UPDATE connect_runs SET body_json=?,updated_at=? WHERE request_id=?',
                            (json.dumps(persisted, ensure_ascii=False), run['updated_at'], run['request_id']))

    def _event(self, run, kind, data=None):
        with self.lock:
            if self.closed:
                return
            if self._stop_forgotten(run):
                return
            seq = run.get('last_event', 0) + 1
            run['last_event'] = seq
            event = {'seq': seq, 'type': kind, 'data': data or {}, 'at': time.time()}
            if run.get('_source_tainted'):
                event['data']={'characters':len(str((data or {}).get('delta','')))} if kind=='item/agentMessage/delta' else {}
            with self.db:
                self.db.execute('INSERT INTO connect_events VALUES (?,?,?)',
                                (run['request_id'], seq, json.dumps(event, ensure_ascii=False)))
                if seq > MAX_EVENTS:
                    self.db.execute('DELETE FROM connect_events WHERE request_id=? AND seq<=?',
                                    (run['request_id'], seq-MAX_EVENTS))
            self._store(run)

    def _load(self, request_id):
        row = self.db.execute('SELECT * FROM connect_runs WHERE request_id=?', (request_id,)).fetchone()
        if not row:
            raise ProviderError('NOT_FOUND', 'No existe esa ejecución de Axx Connect.')
        return json.loads(row['body_json'])

    def _assert_memory(self, run):
        if self.closed:
            raise ProviderError('CLOSED', 'El proveedor está detenido.')
        reference = run.get('memory_scope')
        task_id = reference.get('task_id') if isinstance(reference, dict) else run.get('memory_task_id', run.get('conversation_id'))
        try:
            if reference is None and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_forget_results'").fetchone():
                retired = self.db.execute("SELECT 1 FROM chat_forget_results, json_each(chat_forget_results.payload,'$.old_connect_ids') WHERE value=? LIMIT 1", (run.get('memory_context_id') or run.get('conversation_id'),)).fetchone()
                if retired:
                    raise ValueError('El contexto anterior de esta conversación fue olvidado')
            current = task_memory.assert_context(self.db, reference, run.get('memory_context_id'), task_id=task_id)
            task_memory.assert_dependencies(self.db,run.get('memory_dependencies',[]))
            return current
        except ValueError as exc:
            raise ProviderError('MEMORY_SCOPE_CHANGED', str(exc)) from exc

    def _memory_binding(self, body, conversation_id, previous=None):
        reference = body.get('memory_scope')
        context_id = body.get('memory_context_id')
        dependencies = body.get('memory_dependencies',previous.get('memory_dependencies',[]) if previous else [])
        if previous:
            if 'memory_scope' not in body:
                reference = previous.get('memory_scope')
            if 'memory_context_id' not in body:
                context_id = previous.get('memory_context_id')
        owner = reference.get('task_id') if isinstance(reference,dict) else conversation_id
        if not previous and reference is not None and 'memory_context_id' not in body:
            context_id = body.get('conversation_id')
        if not previous and reference is None and self.db.execute("SELECT 1 FROM sqlite_master WHERE name='chat_conversations'").fetchone():
            rows = self.db.execute('SELECT id,connect_id FROM chat_conversations WHERE id=? OR connect_id=?', (conversation_id,conversation_id)).fetchall()
            if len(rows) > 1:
                raise ProviderError('INVALID_INPUT', 'La conversación no tiene un ámbito de memoria único.')
            if rows:
                owner = rows[0]['id']
                if conversation_id == rows[0]['connect_id']:
                    context_id = context_id or conversation_id
        binding = {'memory_scope':reference, 'memory_context_id':context_id, 'memory_task_id':owner,
                   'memory_dependencies':dependencies}
        if not previous:
            try:
                binding['memory_scope'],binding['memory_context_id'] = task_memory.capture_context(self.db,reference,context_id,task_id=owner)
            except ValueError as exc:
                raise ProviderError('MEMORY_SCOPE_CHANGED',str(exc)) from exc
        binding['memory_scope'] = self._assert_memory(binding)
        binding['memory_dependencies'] = [dict(reference) for reference in dependencies]
        return {key:binding[key] for key in ('memory_scope','memory_context_id','memory_dependencies')}

    def _memory_projection(self, run):
        try:
            self._assert_memory(run)
        except ProviderError as exc:
            return dict(run, state='cancelled', response='', response_retained=False, inference_verified=False,
                        memory_forgotten=True, tool_results=[], events=[], pending_approvals=[],
                        error={'code':exc.code, 'message':str(exc)})
        return run

    def _stop_forgotten(self, run):
        if self.closed:
            return True
        try:
            self._assert_memory(run)
            return False
        except ProviderError as exc:
            run.update(state='cancelled', cancel_requested=True, inference_verified=False, memory_forgotten=True,
                       error={'code':exc.code, 'message':str(exc)})
            run['_cancel'].set()
            run['_done'].set()
            self._store(run)
            threading.Thread(target=self._interrupt_bounded, args=(run,), daemon=True).start()
            return True

    def _spawn(self):
        with self._budget_lock(self.start_lock):
            if self.closed:
                raise ProviderError('CLOSED', 'El proveedor está detenido.')
            if not self.local_enabled:
                raise ProviderError('DISCONNECTED', 'Axx Connect está desconectado localmente. Usa Reconectar para activarlo.')
            if self.process is not None and self.process.poll() is None:
                return
            executable = discover_codex()
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            version = subprocess.run([str(executable), '--version'], capture_output=True, text=True,
                                     timeout=self._remaining(10), creationflags=creationflags)
            if version.returncode or version.stdout.strip() != 'codex-cli ' + CODEX_VERSION:
                raise ProviderError('VERSION_MISMATCH', 'Axx Connect requiere codex-cli ' + CODEX_VERSION)
            # Overrides are process-local. No user config or authentication files are edited.
            args = [str(executable), 'app-server', '--listen', 'stdio://',
                    '-c', 'model_provider="openai"', '-c', 'forced_login_method="chatgpt"',
                    '-c', 'web_search="disabled"', '-c', 'mcp_servers={}', '-c', 'plugins={}']
            for feature in REQUESTED_DISABLED_FEATURES:
                args.extend(['-c', 'features.' + feature + '=false'])
            env = _runtime_environment()
            process = subprocess.Popen(args, cwd=self.cwd, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
                errors='replace', bufsize=1, creationflags=creationflags)
            self.process = process
            self.writer = _PipeWriter(process, self._transport_failed)
            self.verified_model = self.verified_at = None
            threading.Thread(target=self._read, args=(process,), daemon=True,
                             name='axx-codex-reader').start()
            # Drain stderr continuously without persisting runtime text/credentials.
            threading.Thread(target=lambda: self._drain_stderr(process), daemon=True,
                             name='axx-codex-stderr').start()
            try:
                self._rpc('initialize', {'clientInfo': {'name': 'axx_connect',
                    'title': 'Axx Connect', 'version': '0.1.0'},
                    'capabilities': {'experimentalApi': True}}, timeout=20)
                self._write({'method': 'initialized'})
                # Empty table overrides may merge with inherited configuration.
                # Disable each effective server/plugin explicitly for Axx threads.
                # Retain names only; never persist or log the configuration body.
                effective = self._rpc('config/read', {'includeLayers': False}).get('config', {})
                provider = (effective.get('model_providers') or {}).get('openai') or {}
                urls = [effective.get('openai_base_url'), effective.get('chatgpt_base_url'), provider.get('base_url')]
                official = True
                for url in filter(None, urls):
                    parsed = urlsplit(url)
                    official = official and parsed.scheme == 'https' and parsed.hostname in {'api.openai.com', 'chatgpt.com'} and not parsed.username and not parsed.password and parsed.port in (None, 443)
                if not official or provider.get('env_key'):
                    raise ProviderError('UNSUPPORTED_PROVIDER_CONFIG',
                        'Axx Connect requiere el proveedor oficial sin URL ni credencial API personalizada.')
                self.disabled_mcp = {name: {'enabled': False} for name in effective.get('mcp_servers', {})}
                self.disabled_plugins = {name: {'enabled': False} for name in effective.get('plugins', {})}
                try:
                    catalog = self._rpc('model/list', {'limit': 100, 'includeHidden': False})
                    self.model_catalog = [{'id': row.get('id'), 'model': row.get('model'),
                        'display_name': row.get('displayName'), 'description': row.get('description'),
                        'input_modalities': row.get('inputModalities'),
                        'reasoning_efforts': row.get('supportedReasoningEfforts')} for row in catalog.get('data', [])]
                except ProviderError:
                    self.model_catalog = []
                self.runtime_error = None
            except Exception:
                self._stop_process(process)
                raise

    @staticmethod
    def _drain_stderr(process):
        try:
            for _line in process.stderr:
                pass
        except (OSError, ValueError):
            pass

    def _write(self, message, *, timeout=20, admission=None, admitted=None):
        deadline = time.monotonic() + self._remaining(timeout)
        payload = json.dumps(message, ensure_ascii=False) + '\n'
        if not self.lock.acquire(timeout=max(0, deadline-time.monotonic())):
            raise ProviderError('WRITE_TIMEOUT', 'El plazo expiró esperando el transporte local.')
        try:
            process, writer = self.process, self.writer
        finally:
            self.lock.release()
        if process is None or process.poll() is not None or writer is None or writer.process is not process:
            raise ProviderError('DISCONNECTED', 'El proceso de Codex se desconectó.')
        remaining = min(deadline-time.monotonic(), self._remaining(timeout))
        if remaining <= 0:
            raise ProviderError('DEADLINE_EXCEEDED', 'El plazo expiró antes de escribir al runtime.')
        writer.submit(payload, remaining, admission=admission, admitted=admitted)

    def _transport_failed(self, process, code, deadline=None):
        # Never close stdin from this thread: a blocked TextIO write owns its
        # internal lock. Kill only this captured child BEFORE any global lock or
        # SQLite access. Diagnostics cannot extend an exhausted I/O deadline.
        if self.process is not process:
            return
        self._terminate_owned(process, min(1, max(0, deadline-time.monotonic())) if deadline is not None else 1)
        threading.Thread(target=self._mark_transport_failure, args=(process, code),
                         daemon=True, name='axx-codex-transport-failure').start()

    def _mark_transport_failure(self, process, code):
        with self.lock:
            # The old writer may finish after reconnect; never mark its successor.
            if self.process is not process:
                return
            error = {'code': code, 'message': 'El transporte local falló; los mensajes inciertos no se repiten.'}
            self.runtime_error = error
            self.verified_model = self.verified_at = None
            for result_queue in self.pending.values():
                try:
                    result_queue.put_nowait({'error': error})
                except queue.Full:
                    pass
            if not self.closed:
                affected = []
                for run in list(self.live.values()):
                    if run['state'] not in TERMINAL:
                        run.update(state='unknown', inference_verified=False, error=error)
                        run['_done'].set()
                        run['_turn_ready'].set()
                        affected.append(run)
                # Signal all affected workers before optional durable diagnostics.
                for run in affected:
                    try:
                        self._event(run, 'runtime/write_failed', error)
                    except sqlite3.Error:
                        pass  # Never let a locked/closed DB prevent process exit.

    @staticmethod
    def _terminate_owned(process, budget=1):
        deadline = time.monotonic() + max(0, budget)
        try:
            process.terminate()
            process.wait(timeout=min(.5, max(0, deadline-time.monotonic())))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=max(0, deadline-time.monotonic()))
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass

    def _request(self, method, params=None, timeout=20):
        deadline = time.monotonic() + self._remaining(timeout)
        if not self.lock.acquire(timeout=max(0, deadline-time.monotonic())):
            raise ProviderError('RPC_TIMEOUT', 'El plazo expiró esperando correlacionar ' + method)
        try:
            self.next_id += 1
            rid = self.next_id
            result_queue = queue.Queue(maxsize=1)
            self.pending[rid] = result_queue
            process = self.process
        finally:
            self.lock.release()
        try:
            run = getattr(self.rpc_context, 'run', None)
            admission = self.admission_guard(run) if run and method == 'turn/start' else None
            admitted = (lambda: run.update(_turn_request_sent=True)) if admission else None
            self._write({'id': rid, 'method': method, 'params': params or {}},
                        timeout=max(0, deadline-time.monotonic()), admission=admission, admitted=admitted)
            remaining = min(deadline-time.monotonic(), self._remaining(timeout))
            if remaining <= 0:
                if process is not None: self._transport_failed(process, 'RPC_TIMEOUT', time.monotonic())
                raise ProviderError('RPC_TIMEOUT', 'El plazo expiró después de escribir ' + method)
            try:
                response = result_queue.get(timeout=remaining)
            except queue.Empty as exc:
                deadline = getattr(self.rpc_context, 'deadline', None)
                code = 'DEADLINE_EXCEEDED' if deadline is not None and time.monotonic() >= deadline else 'RPC_TIMEOUT'
                if process is not None: self._transport_failed(process, code, time.monotonic())
                raise ProviderError(code, 'Codex no respondió a ' + method) from exc
            if 'error' in response:
                error = response['error']
                code = error.get('code')
                code = code if isinstance(code, str) and re.fullmatch(r'[A-Z_]{1,80}', code) else _error_code(error)
                raise ProviderError(code, _safe_error(error.get('message', error)))
            return response.get('result', {})
        finally:
            if self.lock.acquire(blocking=False):
                try:
                    if self.pending.get(rid) is result_queue:
                        self.pending.pop(rid, None)
                finally:
                    self.lock.release()
            else:
                # Correlation cleanup has no right to extend an expired request.
                threading.Thread(target=self._drop_pending, args=(rid, result_queue),
                                 daemon=True, name='axx-codex-rpc-cleanup').start()

    def _drop_pending(self, rid, result_queue):
        with self.lock:
            if self.pending.get(rid) is result_queue:
                self.pending.pop(rid, None)

    def _remaining(self, timeout=20):
        deadline = getattr(self.rpc_context, 'deadline', None)
        if deadline is None:
            return timeout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError('DEADLINE_EXCEEDED', 'Axx Connect alcanzó el límite total de 70 segundos.')
        return min(timeout, remaining)

    @contextmanager
    def _budget_lock(self, lock):
        timeout = self._remaining(20)
        if not lock.acquire(timeout=timeout):
            if getattr(self.rpc_context, 'deadline', None) is not None and timeout < 20:
                raise ProviderError('DEADLINE_EXCEEDED', 'Se agotó el plazo total esperando el inicio del runtime.')
            self._remaining()
            raise ProviderError('BUSY', 'El runtime está iniciando otra operación.')
        try:
            self._remaining()
            yield
        finally:
            lock.release()

    def _rpc(self, method, params=None, timeout=20):
        """Budget wrapper also exercised by injected protocol doubles in tests."""
        run = getattr(self.rpc_context, 'run', None)
        if run and method in {'thread/start','thread/resume','turn/start'}:
            with self.lock:
                self._assert_memory(run)
        result = self._request(method, params, timeout=self._remaining(timeout))
        if run and method in {'thread/start','thread/resume','turn/start'}:
            with self.lock:
                self._assert_memory(run)
        return result

    def _read(self, process):
        try:
            for line in process.stdout:
                if len(line) > 4 * 1024 * 1024:
                    raise ProviderError('PROTOCOL_ERROR', 'Evento de Codex demasiado grande.')
                try:
                    message = json.loads(line)
                except ValueError:
                    raise ProviderError('PROTOCOL_ERROR', 'Codex produjo una respuesta no válida.')
                if 'method' not in message and 'id' in message:
                    with self.lock:
                        pending = self.pending.get(message['id'])
                    if pending:
                        pending.put_nowait(message)
                elif 'method' in message and 'id' in message:
                    threading.Thread(target=self._server_request, args=(message,), daemon=True).start()
                else:
                    self._notification(message)
        except (OSError, ValueError, ProviderError) as exc:
            self.runtime_error = {'code': 'PROCESS_FAILED', 'message': _safe_error(exc)}
        finally:
            with self.lock:
                if self.process is process:
                    self.runtime_error = self.runtime_error or {'code': 'DISCONNECTED',
                        'message': 'El runtime de Codex terminó. Las acciones ejecutadas conservan sus efectos.'}
                    for result_queue in self.pending.values():
                        try:
                            result_queue.put_nowait({'error': {'message': 'Codex runtime disconnected'}})
                        except queue.Full:
                            pass
                    for run in list(self.live.values()):
                        if run['state'] not in TERMINAL:
                            run.update(state='unknown', error=self.runtime_error)
                            self._event(run, 'runtime/disconnected', self.runtime_error)
                            run['_done'].set()

    def _notification(self, message):
        method = message.get('method', '')
        params = message.get('params') or {}
        if method == 'account/updated':
            with self.lock:
                self.account = self.account_fingerprint = None
                self.account_epoch += 1
                self.verified_model = self.verified_at = None
                self.auth_failed = False
                self.engine_state = None
            return
        if method == 'account/login/completed':
            self.account = None
            return
        with self.lock:
            request_id = self.thread_runs.get(params.get('threadId'))
            run = self.live.get(request_id)
            if not run or run['state'] in TERMINAL:
                return
            if self._stop_forgotten(run):
                return
            if time.monotonic() >= run['_deadline']:
                self._deadline_failed(run)
                threading.Thread(target=self._interrupt_bounded, args=(run,), daemon=True).start()
                return
            event_turn = params.get('turnId') or (params.get('turn') or {}).get('id')
            if method in {'turn/started', 'turn/completed', 'item/agentMessage/delta'} and not event_turn:
                return  # Required by the pinned schema; never trust ambiguous completion.
            if event_turn:
                if run.get('turn_id') is None:
                    buffered = run.setdefault('_notifications', [])
                    if len(buffered) < MAX_EVENTS:
                        buffered.append(message)
                    return
                if event_turn != run['turn_id']:
                    return
            if method == 'turn/started':
                run['turn_id'] = params.get('turn', {}).get('id')
                run['state'] = 'processing'
                self._event(run, method, {'turn_id': run['turn_id']})
            elif method == 'item/agentMessage/delta':
                delta = str(params.get('delta', ''))
                if len(run['response']) + len(delta) > MAX_RESPONSE:
                    run.update(state='failed', error={'code': 'RESPONSE_LIMIT', 'message': 'Respuesta demasiado grande.'})
                    run['_done'].set()
                    return
                run['response'] += delta
                self._event(run, method, {'delta': delta})
            elif method == 'thread/tokenUsage/updated':
                run['usage'] = params.get('tokenUsage')
                self._event(run, method, {'usage': run['usage']})
            elif method == 'turn/completed':
                turn = params.get('turn') or {}
                state = turn.get('status')
                if state == 'completed':
                    if run.get('account_fingerprint') == self.account_fingerprint and run.get('account_epoch') == self.account_epoch and not self.auth_failed:
                        run.update(state='completed', inference_verified=True)
                        self.verified_model = run['model']
                        self.verified_at = time.time()
                        self.engine_state = None
                    else:
                        run.update(state='failed', inference_verified=False, error={'code': 'ACCOUNT_CHANGED',
                            'message': 'La cuenta cambió durante el turno. Se conserva la respuesta y la evidencia; esta ejecución no verifica la cuenta actual.'})
                elif state == 'interrupted':
                    run['state'] = 'cancelled'
                else:
                    error = turn.get('error') or {'message': 'El turno no terminó correctamente.'}
                    code = _error_code(error)
                    self._record_error(code)
                    run.update(state='limit_reached' if code == 'LIMIT_REACHED' else 'failed',
                               error={'code': code, 'message': _safe_error(error)})
                run['turn_status'] = state
                self._event(run, method, {'status': state, 'error': run.get('error')})
                run['_done'].set()
            elif method == 'error':
                error = params.get('error') or params
                self._event(run, method, {'message': _safe_error(error)})

    def _server_request(self, message):
        method, params = message['method'], message.get('params') or {}
        with self.lock:
            run = self.live.get(self.thread_runs.get(params.get('threadId')))
            if run and self._stop_forgotten(run):
                run = None
        if run and run.get('turn_id') is None:
            run['_turn_ready'].wait(timeout=max(0, min(20, run['_deadline'] - time.monotonic())))
        if not run or run.get('turn_id') is None or run['state'] in TERMINAL or run['_cancel'].is_set() or (
                params.get('turnId') and run.get('turn_id') and params['turnId'] != run['turn_id']):
            self._write({'id': message['id'], 'error': {'code': -32000, 'message': 'No active Axx execution'}})
            return
        if run.get('purpose') in {'capability','planning'}:
            # This generation thread has no authority to request any tool,
            # permission, file, shell or external interaction, even if the
            # runtime unexpectedly exposes a built-in outside dynamicTools.
            with self.lock:
                run.update(state='failed', inference_verified=False,
                    error={'code': 'CAPABILITY_TOOLS_FORBIDDEN',
                           'message': 'La generación de capacidades solo produce JSON; no puede solicitar herramientas ni permisos.'})
                self._event(run, 'capability/request_denied', {'method': method})
                run['_done'].set()
            self._write({'id': message['id'], 'error': {'code': -32000,
                         'message': 'Capability generation cannot request tools or permissions'}}, timeout=3)
            threading.Thread(target=self._interrupt_bounded, args=(run,), daemon=True).start()
            return
        if method == 'item/tool/call':
            tool = params.get('tool')
            from backend.connect.registry import tool_descriptors
            allowed = {entry['name'] for entry in tool_descriptors(self.commands, computer=True)}
            if run.get('purpose') == 'translation' or tool not in allowed or params.get('namespace') not in (None, 'axx'):
                self._write({'id': message['id'], 'result': {'contentItems': [
                    {'type': 'inputText', 'text': 'Tool outside the Axx registry is forbidden.'}], 'success': False}})
                return
            args = params.get('arguments')
            if not isinstance(args, dict):
                args = {}
            args = dict(args)
            if tool == 'axx_execute_action':
                args.update(origin='axx-provider', parent_execution_id=run['request_id'], delegation_depth=1)
            rejection = None
            with self.lock:
                if run['_cancel'].is_set():
                    return
                try:
                    self._assert_binding(run)
                    if time.monotonic() >= run['_deadline']:
                        raise ProviderError('DEADLINE_EXCEEDED', 'El límite total de ejecución expiró.')
                except ProviderError as exc:
                    if exc.code == 'DEADLINE_EXCEEDED':
                        self._deadline_failed(run)
                    else:
                        run.update(state='failed', inference_verified=False,
                            error={'code': exc.code, 'message': str(exc)})
                        self._event(run, 'run/error', run['error'])
                        run['_done'].set()
                    rejection = str(exc)
                if rejection is None:
                    run['state'] = 'executing_tool'
                    self._event(run, 'tool/started', {'tool': tool, 'call_id': params.get('callId')})
            if rejection is not None:
                threading.Thread(target=self._interrupt_bounded, args=(run,), daemon=True).start()
                self._write({'id': message['id'], 'result': {'contentItems': [
                    {'type': 'inputText', 'text': rejection}], 'success': False}}, timeout=3)
                return
            try:
                if self.dispatcher is None:
                    raise ProviderError('EXECUTOR_UNAVAILABLE', 'El despachador de Axx no está conectado.')
                result = self._dispatch(tool, args, run, params.get('callId'))
                success = not (isinstance(result, dict) and (result.get('error') or result.get('state') in {'failed', 'blocked'}))
            except Exception as exc:
                result = {'state': 'failed', 'error': {'code': getattr(exc, 'code', 'TOOL_ERROR'),
                                                     'message': _safe_error(exc)}}
                success = False
                if isinstance(exc, ProviderError) and exc.code in {'ACCOUNT_CHANGED', 'DISCONNECTED', 'DEADLINE_EXCEEDED'}:
                    with self.lock:
                        if exc.code == 'DEADLINE_EXCEEDED':
                            self._deadline_failed(run)
                        elif run['state'] not in TERMINAL:
                            run.update(state='failed', inference_verified=False, error=result['error'])
                            self._event(run, 'run/error', run['error'])
                            run['_done'].set()
                    threading.Thread(target=self._interrupt_bounded, args=(run,), daemon=True).start()
            with self.lock:
                if self.closed:
                    return
                admitted_operation = None
                if isinstance(result, dict) and result.get('origin') == 'axx-provider' and result.get('parent_execution_id') == run['request_id']:
                    admitted_operation = result.get('operation_id')
                    if isinstance(admitted_operation, str) and admitted_operation not in run['managed_operations']:
                        run['managed_operations'].append(admitted_operation)
                run['tool_results'].append({'tool': tool, 'call_id': params.get('callId'), 'result': result})
                self._stop_forgotten(run)
                if run['state'] not in TERMINAL and time.monotonic() >= run['_deadline']:
                    self._deadline_failed(run)
                terminal = run['state'] in TERMINAL
                if not terminal:
                    run['state'] = 'processing'
                self._event(run, 'tool/completed', run['tool_results'][-1])
            # If cancellation arrived while the dispatcher was running, only its admitted
            # operation can now be cancelled. Model-supplied IDs grant no ownership.
            if admitted_operation and run['_cancel'].is_set():
                try:
                    cancellation = self._dispatch('axx_cancel_task', {'operation_id': admitted_operation},
                        run, 'cancel-' + admitted_operation, cleanup=True)
                    self._event(run, 'tool/cancellation', {'operation_id': admitted_operation, 'result': cancellation})
                except Exception as exc:
                    self._event(run, 'tool/cancellation_error', {'operation_id': admitted_operation,
                        'message': _safe_error(exc)})
            if terminal:
                return  # Keep late executor evidence; never revive an ended turn.
            model_result = {key:value for key,value in result.items() if key not in {'memory_scope','memory_context_id','memory_dependencies'}} if isinstance(result,dict) else result
            content=[{'type': 'inputText', 'text': json.dumps(model_result, ensure_ascii=False)}]
            computer=getattr(getattr(self.commands,'executor',None),'computer_use',None)
            if computer is not None:
                try:content.extend(computer.image_content(result,run))
                except ValueError:pass
            try:
                self._write({'id': message['id'], 'result': {'contentItems': content, 'success': success}},
                    timeout=max(0, min(20, run['_deadline']-time.monotonic())), admission=self.admission_guard(run))
            except ProviderError:
                with self.lock:
                    self._stop_forgotten(run)
                return
            if len(content)>1:
                self._event(run,'computer/image_attached',{'observation_id':result['output']['observation_id'],
                    'image_sha256':result['output'].get('image_sha256')})
        else:
            # Approval payloads are surfaced for an explicit user decision; never auto-approved.
            approval_id = str(message['id'])
            with self.lock:
                self.approvals[approval_id] = (run['request_id'], message)
                run['state'] = 'waiting_intervention'
                self._event(run, 'approval/required', {'approval_id': approval_id, 'method': method,
                    'reason': _safe_error(params.get('reason', params.get('message', 'Intervención solicitada por Codex'))),
                    'command': _safe_error(params.get('command', '')), 'available_decisions': ['decline', 'cancel']})

    def status(self):
        with self.lock:
            if not self.local_enabled:
                return self._locally_disconnected()
        try:
            self._spawn()
            snapshot = self._account_snapshot()
            with self.lock:
                if not self.local_enabled:
                    return self._locally_disconnected()
            return snapshot | {'runtime': {'available': True, 'version': CODEX_VERSION,
                    'experimental': True, 'transport': 'stdio'},
                    'selected_model': self.selected_model, 'default_model': 'gpt-6.1-sol',
                    'models': [row['model'] for row in self.model_catalog if row.get('model')],
                    'model_catalog': self.model_catalog, 'catalog_is_entitlement_check': False,
                    'allow_paid': False, 'executor_connected': self.dispatcher is not None,
                    'local_connection_enabled': True, 'managed_credentials_revoked_by_axx': False,
                    'extra_credit_fallback': False,
                    'diagnostic': None if snapshot['authenticated'] else 'Inicia sesión en Codex con ChatGPT; no se permite API de pago.'}
        except Exception as exc:
            with self.lock:
                if not self.local_enabled:
                    return self._locally_disconnected()
            return {'state': 'disconnected', 'authenticated': False, 'inference_verified': False,
                    'allow_paid': False, 'runtime': {'available': False, 'version': CODEX_VERSION,
                    'experimental': True}, 'executor_connected': self.dispatcher is not None,
                    'selected_model': self.selected_model, 'default_model': 'gpt-6.1-sol',
                    'models': [], 'model_catalog': [], 'catalog_is_entitlement_check': False,
                    'error': {'code': getattr(exc, 'code', 'RUNTIME_ERROR'), 'message': _safe_error(exc)}}

    def _locally_disconnected(self):
        return {'state': 'disconnected', 'authenticated': False, 'inference_verified': False,
                'local_connection_enabled': False, 'managed_credentials_revoked_by_axx': False,
                'managed_account_status': 'not_checked', 'account': None,
                'allow_paid': False, 'extra_credit_fallback': False,
                'runtime': {'available': False, 'running': False, 'version': CODEX_VERSION,
                            'experimental': True, 'transport': 'stdio'},
                'executor_connected': self.dispatcher is not None,
                'selected_model': self.selected_model, 'default_model': 'gpt-6.1-sol',
                'models': [], 'model_catalog': [], 'catalog_is_entitlement_check': False,
                'diagnostic': 'Axx desconectado localmente. Las credenciales compartidas de Codex no se han revocado. Usa Reconectar para volver a comprobarlas.'}

    def _account_snapshot(self):
        # A slow account/read must not roll back an account change observed by
        # another status call or an account/updated notification in the meantime.
        for _attempt in range(2):
            with self.lock:
                epoch, refresh = self.account_epoch, self.auth_failed
            result = self._rpc('account/read', {'refreshToken': refresh})
            account = result.get('account')
            context = {key: (account or {}).get(key) for key in ('type', 'email', 'planType')}
            fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
            with self.lock:
                if epoch != self.account_epoch:
                    continue
                if self.account_fingerprint and self.account_fingerprint != fingerprint:
                    self.verified_model = self.verified_at = None
                    self.account_epoch += 1
                self.account_fingerprint = fingerprint
                self.account = context if account else None
                authenticated = bool(account and account.get('type') == 'chatgpt')
                self.auth_failed = False
                state = 'connected' if authenticated and self.verified_model else ('authenticated' if authenticated else 'disconnected')
                if authenticated and self.engine_state:
                    state = self.engine_state
                return {'state': state, 'account': self.account,
                    'account_fingerprint': self.account_fingerprint, 'account_epoch': self.account_epoch,
                    'authenticated': authenticated, 'inference_verified': bool(self.verified_model),
                    'model': self.verified_model, 'verified_at': self.verified_at}
        raise ProviderError('AUTH_STATE_CHANGED', 'La cuenta cambió durante la comprobación. Repite el diagnóstico.')

    def _record_error(self, code):
        if code == 'AUTH_REQUIRED':
            self.auth_failed = True
            self.verified_model = self.verified_at = None
            self.engine_state = None
        elif code == 'LIMIT_REACHED':
            self.engine_state = 'limit_reached'
        elif code == 'COST_UNKNOWN':
            self.engine_state = 'waiting_intervention'

    def _assert_binding(self, run):
        with self.lock:
            self._assert_memory(run)
            if not self.local_enabled:
                raise ProviderError('DISCONNECTED', 'Axx está desconectado localmente.')
            if run.get('account_fingerprint') != self.account_fingerprint or run.get('account_epoch') != self.account_epoch or self.auth_failed:
                raise ProviderError('ACCOUNT_CHANGED', 'La cuenta cambió antes de actuar. No se iniciará otra operación.')

    def admission_guard(self, run, *, cleanup=False):
        """Factory passed to the real admission point, never held over tool/RPC waits.

        Service lock precedes this provider lock. Cleanup remains scoped to an
        already-admitted operation by the service's request ownership checks.
        """
        @contextmanager
        def guard():
            timeout = 3 if cleanup else max(0, min(20, run['_deadline']-time.monotonic()))
            if not self.lock.acquire(timeout=timeout):
                code = 'DEADLINE_EXCEEDED' if not cleanup and timeout < 20 else 'BUSY'
                raise ProviderError(code, 'No se pudo admitir la operación dentro del plazo.')
            try:
                def recheck():
                    if self.closed:
                        raise ProviderError('CLOSED', 'El proveedor está detenido.')
                    if not cleanup:
                        self._assert_binding(run)
                        if (run['_cancel'].is_set() or run['state'] in TERMINAL
                                or run.get('_source_cancel') is not None and run['_source_cancel'].is_set()):
                            raise ProviderError('CANCELLED', 'La ejecución ya no admite trabajo nuevo.')
                        if time.monotonic() >= run['_deadline']:
                            raise ProviderError('DEADLINE_EXCEEDED', 'El plazo total expiró antes de la admisión.')
                recheck()
                yield recheck
                recheck()
            finally:
                self.lock.release()
        return guard

    def _dispatch(self, name, arguments, run, call_id, *, cleanup=False):
        if name.startswith('axx_computer_'):
            computer=getattr(getattr(self.commands,'executor',None),'computer_use',None)
            if computer is None:raise ProviderError('COMPUTER_UNAVAILABLE','Computer use no está conectado.')
            from .registry import tool_descriptors,validate
            descriptor=next(row for row in tool_descriptors(self.commands,computer=True) if row['name']==name)
            validate(descriptor['inputSchema'],arguments)
            with self.admission_guard(run,cleanup=cleanup)():
                prepared=computer.admit(name,arguments,run)
            if name in ('axx_computer_status','axx_computer_stop'):return prepared
            name,arguments='axx_execute_action',prepared
        dispatcher = self.dispatcher
        try:
            supported = dispatcher is not None and 'admission' in inspect.signature(dispatcher).parameters
        except (TypeError, ValueError):
            supported = False
        if not supported:
            raise ProviderError('DISPATCHER_ADMISSION_UNSUPPORTED',
                'El despachador no admite autorización atómica; no se ha ejecutado la herramienta.')
        # Never acquire a service lock while holding the provider lock here.
        return dispatcher(name, arguments, run['request_id'], call_id,
            admission=self.admission_guard(run, cleanup=cleanup))

    def _deadline_failed(self, run):
        with self.lock:
            if run['state'] in TERMINAL:
                return
            uncertain = bool(run.get('_turn_request_sent') or run.get('turn_id') or run.get('managed_operations'))
            run.update(state='unknown' if uncertain else 'failed', inference_verified=False,
                error={'code': 'DEADLINE_EXCEEDED', 'message': 'Se alcanzó el límite total de 70 segundos. Conserva la evidencia y consulta las acciones antes de repetir.'})
            self._event(run, 'run/timeout', {'effects_reverted': False})
            run['_done'].set()

    def _interrupt_bounded(self, run):
        with self.lock:
            if not run.get('turn_id') or run.get('_timeout_cleanup_started'):
                return
            run['_timeout_cleanup_started'] = True
        previous = getattr(self.rpc_context, 'deadline', None)
        self.rpc_context.deadline = None
        try:
            self._request('turn/interrupt', {'threadId': run['thread_id'], 'turnId': run['turn_id']}, timeout=3)
        except Exception:
            pass  # A missing acknowledgement cannot turn unknown into success.
        finally:
            self.rpc_context.deadline = previous

    def _tool_specs(self):
        from backend.connect.registry import dynamic_tools
        return dynamic_tools(self.commands,computer=getattr(getattr(self.commands,'executor',None),'computer_use',None) is not None)

    def _included_usage(self, model):
        """Read only; never consume reset credits or trigger a purchase RPC."""
        result = self._rpc('account/rateLimits/read')
        snapshots = result.get('rateLimitsByLimitId') or {}
        relevant = [value for key, value in snapshots.items()
                    if key == 'codex' or value.get('normalModelSlug') == model]
        if not relevant:
            relevant = [result.get('rateLimits') or {}]
        if result.get('ordinaryUsageAllowed') is False or any(
                value.get('rateLimitReachedType') or value.get('spendControlReached') is True
                for value in relevant):
            raise ProviderError('LIMIT_REACHED', 'El runtime no autoriza uso ordinario del plan; no se usarán créditos alternativos.')
        if result.get('ordinaryUsageAllowed') is not True:
            raise ProviderError('COST_UNKNOWN', 'El runtime no confirmó permiso para uso incluido del plan. No se iniciará inferencia ni facturación alternativa.')
        if result.get('ordinaryUsageAllowed') is True:
            self.engine_state = None
        return {'ordinary_usage_allowed': result.get('ordinaryUsageAllowed'),
                'usage_status_available': result.get('ordinaryUsageAllowed') is not None}

    def start(self, body, *, cancel_event=None, images=None):
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise ProviderError('INVALID_INPUT', 'Evento interno de cancelación inválido.')
        if cancel_event is not None and cancel_event.is_set():
            raise ProviderError('CANCELLED', 'El contexto autorizado ya no está vigente.')
        if not isinstance(body, dict):
            raise ProviderError('INVALID_INPUT', 'La solicitud debe ser un objeto.')
        purpose = body.get('purpose', 'chat')
        if not isinstance(purpose, str) or purpose not in {'chat', 'voice', 'translation', 'capability', 'planning'}:
            raise ProviderError('INVALID_INPUT', 'Propósito de inferencia no permitido.')
        images = self._planning_images(images, purpose)
        message = body.get('message', body.get('text'))
        message_limit = MAX_CAPABILITY_MESSAGE if purpose in {'capability','planning'} else 32000
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= message_limit:
            raise ProviderError('INVALID_INPUT', 'La instrucción excede el límite de ' + str(message_limit) + ' caracteres.')
        request_id = body.get('request_id', str(uuid.uuid4()))
        conversation_id = body.get('conversation_id', 'axx-main')
        model = body.get('model', 'gpt-6.1-sol')
        source_language, target_language = body.get('source_language'), body.get('target_language')
        if purpose == 'translation':
            for value, name in ((source_language, 'source_language'), (target_language, 'target_language')):
                if name == 'source_language' and value == 'auto':
                    continue
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value) or len(value) > 35:
                    raise ProviderError('INVALID_INPUT', name + ' debe ser un código de idioma válido.')
            if not isinstance(request_id, str):
                raise ProviderError('INVALID_INPUT', 'request_id inválido.')
            # No translation can reuse the action-bearing main chat thread.
            conversation_id = 'axx-translation-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
        elif source_language is not None or target_language is not None:
            raise ProviderError('INVALID_INPUT', 'Los idiomas sólo se admiten para traducción.')
        mode = {'chat': 'conversation', 'voice': 'voice', 'translation': 'translation',
                'capability': 'capability', 'planning': 'planning'}[purpose]
        try:
            prompt = compose(mode, connect=True, preferences=body.get('preferences'),
                             source_language=source_language, target_language=target_language)
        except ValueError as exc:
            raise ProviderError('INVALID_INPUT', str(exc)) from exc
        if purpose in {'capability','planning'}:
            if not isinstance(request_id, str): raise ProviderError('INVALID_INPUT', 'request_id inválido.')
            conversation_id = 'axx-'+purpose+'-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
        for value, name in ((request_id, 'request_id'), (conversation_id, 'conversation_id'), (model, 'model')):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
                raise ProviderError('INVALID_INPUT', name + ' inválido.')
        depth = body.get('delegation_depth', 0)
        if body.get('origin', 'axx') not in {'axx', 'axx-ui', 'test'} or body.get('parent_execution_id') or type(depth) is not int or depth != 0:
            raise ProviderError('RECURSION_BLOCKED', 'Una herramienta no puede iniciar otro planificador de Axx.')
        original_conversation_id = body.get('conversation_id', 'axx-main')
        fingerprint_data = [message, conversation_id, model, purpose, source_language, target_language, prompt['sha256']]
        if images:fingerprint_data.append(images)
        with self.lock:
            if self.closed:
                raise ProviderError('CLOSED', 'El proveedor está detenido.')
            if not self.local_enabled:
                raise ProviderError('DISCONNECTED', 'Axx está desconectado localmente. Usa Reconectar para habilitar inferencia.')
            existing = self.db.execute('SELECT fingerprint,body_json FROM connect_runs WHERE request_id=?', (request_id,)).fetchone()
            memory = self._memory_binding(body, original_conversation_id, json.loads(existing['body_json']) if existing else None)
            if purpose in {'chat','voice'} and memory['memory_context_id'] is not None and memory['memory_context_id'] != original_conversation_id:
                if body.get('memory_scope') is not None or body.get('memory_context_id') is not None:
                    raise ProviderError('INVALID_INPUT', 'La solicitud debe conservar el contexto opaco original del chat.')
                conversation_id = memory['memory_context_id']
            fingerprint_data.append(memory)
            fingerprint = hashlib.sha256(json.dumps(fingerprint_data, ensure_ascii=False).encode()).hexdigest()
            if existing:
                if existing['fingerprint'] != fingerprint:
                    raise ProviderError('DUPLICATE_MISMATCH', 'El identificador ya pertenece a otra solicitud.')
                return self.get(request_id)
            active = [run for run in self.live.values() if run['state'] not in TERMINAL]
            if len(active) >= 2 or any(run['conversation_id'] == conversation_id for run in active):
                raise ProviderError('BUSY', 'Ya hay una solicitud activa en esta conversación o dos globales.')
            now, admission_deadline = time.time(), time.monotonic() + TURN_TIMEOUT
            run = {'request_id': request_id, 'conversation_id': conversation_id, 'model': model,
                   'origin': 'axx', 'parent_execution_id': None, 'delegation_depth': 0,
                   'purpose': purpose, 'source_language': source_language, 'target_language': target_language,
                   'state': 'accepted', 'response': '', 'thread_id': None, 'turn_id': None,
                   'inference_verified': False,
                   'tool_results': [], 'usage': None, 'error': None, 'last_event': 0,
                   'managed_operations': [],
                   'created_at': now, 'updated_at': now, 'cancel_requested': False, **memory}
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                self._assert_memory(run)
                self.db.execute('INSERT INTO connect_runs VALUES (?,?,?,?,?,?)',
                    (request_id, fingerprint, conversation_id, json.dumps(run), now, now))
            run['_done'], run['_cancel'], run['_turn_ready'] = threading.Event(), threading.Event(), threading.Event()
            run['_deadline'] = admission_deadline
            run['_prompt'] = prompt
            run['_source_cancel'] = cancel_event
            run['_source_images'] = images
            run['_source_tainted'] = cancel_event is not None or bool(images)
            self.live[request_id] = run
            self.selected_model = model
            self._event(run, 'run/accepted')
            threading.Thread(target=self._run, args=(run, message), daemon=True,
                             name='axx-codex-turn').start()
            return self.get(request_id)

    def _run(self, run, message):
        self.rpc_context.deadline = run['_deadline']
        self.rpc_context.run = run
        try:
            with self.lock:
                self._assert_memory(run)
            self._remaining()
            health = self.status()
            if not health.get('authenticated'):
                error = health.get('error') or {}
                raise ProviderError(error.get('code', 'AUTH_REQUIRED'), error.get('message', 'Codex requiere una sesión ChatGPT autorizada. No se usará una API de pago.'))
            with self.lock:
                run['account_fingerprint'] = health.get('account_fingerprint')
                run['account_epoch'] = health.get('account_epoch')
            usage_permission = self._included_usage(run['model'])
            self._remaining()
            self._assert_binding(run)
            with self.lock:
                run['usage_permission'] = usage_permission
            with self.lock:
                # Legacy threads retain their old tool schema; preserve them under their original key.
                saved = None if run['purpose'] in {'capability','planning'} else self.db.execute(
                    'SELECT * FROM connect_conversations WHERE conversation_id=?',
                    (run['conversation_id'] + ':axx-direct-v2',)).fetchone()
            common = {'model': run['model'], 'modelProvider': 'openai', 'cwd': self.cwd,
                      'approvalPolicy': 'on-request', 'sandbox': 'read-only',
                      'approvalsReviewer': 'user',
                      'serviceTier': 'default',
                      'developerInstructions': '',
                      'config': {'features': dict(dict.fromkeys(REQUESTED_DISABLED_FEATURES, False),
                                 code_mode={'enabled': False, 'direct_only_tool_namespaces': ['axx']}),
                                 'web_search': 'disabled', 'mcp_servers': self.disabled_mcp,
                                 'plugins': self.disabled_plugins}}
            prompt = run['_prompt']
            ephemeral = run['purpose'] in {'capability', 'planning'}
            if ephemeral: common['ephemeral'] = True
            common['developerInstructions'] = prompt['text']
            with self.lock:
                self._event(run, 'prompt/compiled', {key: prompt[key] for key in ('version', 'mode', 'characters', 'sha256')})
            if saved:
                result = self._rpc('thread/resume', dict(common, threadId=saved['thread_id']))
            else:
                result = self._rpc('thread/start', dict(common, dynamicTools=[] if run['purpose'] in {'translation', 'capability','planning'} else self._tool_specs(),
                                       environments=[], allowProviderModelFallback=False))
            thread_id = result['thread']['id']
            if ephemeral and result['thread'].get('ephemeral') is not True:
                raise ProviderError('EPHEMERAL_UNVERIFIED', 'El runtime no confirmó una sesión temporal; no se envió el contexto.')
            with self.lock:
                run['thread_id'] = thread_id
                run['runtime_model'] = result.get('model')
                run['runtime_provider'] = result.get('modelProvider')
                if not result.get('model') or not result.get('modelProvider'):
                    raise ProviderError('MODEL_UNVERIFIED', 'El runtime no confirmó modelo y proveedor; el turno no se ha iniciado.')
                if result.get('model') is not None and result['model'] != run['model']:
                    raise ProviderError('MODEL_MISMATCH', 'El runtime devolvió un modelo diferente del solicitado; el turno no se ha iniciado.')
                if result.get('modelProvider') is not None and result['modelProvider'] != 'openai':
                    raise ProviderError('PROVIDER_MISMATCH', 'El runtime devolvió otro proveedor; el turno no se ha iniciado.')
                self.thread_runs[thread_id] = run['request_id']
                if not ephemeral:
                    with self.db:
                        self.db.execute('INSERT OR REPLACE INTO connect_conversations VALUES (?,?,?,?)',
                                        (run['conversation_id'] + ':axx-direct-v2', thread_id, run['model'], time.time()))
                self._event(run, 'thread/ready', {'thread_id': thread_id, 'resumed': bool(saved)})
            if run['_cancel'].is_set():
                run['state'] = 'cancelled'
                self._event(run, 'run/cancelled', {'effects_reverted': False})
                return
            self._assert_binding(run)
            self._remaining()
            result = self._rpc('turn/start', {'threadId': thread_id, 'input': [
                {'type': 'text', 'text': message}, *run.pop('_source_images', [])], 'environments': []})
            with self.lock:
                run['turn_id'] = result.get('turn', {}).get('id', run['turn_id'])
                run['_turn_ready'].set()
                for notification in run.pop('_notifications', []):
                    self._notification(notification)
                if run['state'] == 'accepted':
                    run['state'] = 'processing'
                    self._event(run, 'turn/dispatched', {'turn_id': run['turn_id']})
            while not run['_done'].wait(0.1):
                with self.lock:
                    if self._stop_forgotten(run):
                        break
                self._remaining()
                if run['_cancel'].is_set() and run.get('turn_id') and not run.get('_interrupt_sent'):
                    run['_interrupt_sent'] = True
                    self._rpc('turn/interrupt', {'threadId': thread_id, 'turnId': run['turn_id']})
        except Exception as exc:
            code = getattr(exc, 'code', _error_code(exc))
            if code == 'DEADLINE_EXCEEDED':
                self._deadline_failed(run)
                self._interrupt_bounded(run)
            with self.lock:
                if run['state'] not in TERMINAL:
                    self._record_error(code)
                    state = 'limit_reached' if code == 'LIMIT_REACHED' else ('unknown' if code == 'RPC_TIMEOUT' else 'failed')
                    run.update(state=state,
                               error={'code': code, 'message': _safe_error(exc)})
                    self._event(run, 'run/error', run['error'])
        finally:
            self.rpc_context.deadline = None
            self.rpc_context.run = None
            with self.lock:
                run.pop('_source_images', None)
                run.pop('_source_cancel', None)
                run.pop('_notifications', None)
                if run.get('_source_tainted') and run['state']!='completed':run['response']=''
                run['_turn_ready'].set()
                if not self.closed:
                    run['duration_ms'] = round((time.time()-run['created_at'])*1000)
                    self._store(run)
                if self.thread_runs.get(run.get('thread_id')) == run['request_id']:
                    self.thread_runs.pop(run.get('thread_id'), None)
                for key in [key for key, (rid, _) in self.approvals.items() if rid == run['request_id']]:
                    self.approvals.pop(key, None)

    @staticmethod
    def _planning_images(images, purpose):
        if images is None:return []
        if purpose != 'planning' or not isinstance(images, list) or len(images) > 2:
            raise ProviderError('INVALID_INPUT', 'La planificación admite hasta dos imágenes temporales autorizadas.')
        result = []
        from PIL import Image
        for url in images:
            if (not isinstance(url, str) or not url.startswith('data:image/jpeg;base64,')
                    or len(url) > 23 + ((350000+2)//3)*4):
                raise ProviderError('INVALID_INPUT', 'Imagen temporal inválida o demasiado grande.')
            try:
                raw = base64.b64decode(url.split(',',1)[1],validate=True)
                if not 0 < len(raw) <= 350000:raise ValueError()
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'JPEG' or not 0 < min(image.size) <= max(image.size) <= 1280:raise ValueError()
                    image.verify()
            except (ValueError, OSError, Image.DecompressionBombError):
                raise ProviderError('INVALID_INPUT', 'Imagen temporal JPEG inválida o fuera de límites.') from None
            result.append({'type':'image','url':url})
        return result

    def generate_plan(self, request, *, cancel_event=None):
        return self.generate_capability(request, purpose='planning', cancel_event=cancel_event)

    def generate_capability(self, request, *, purpose='capability', cancel_event=None):
        """Bounded adapter-shaped generation using the selected Codex account only."""
        if (purpose not in ('capability','planning') or not isinstance(request, dict) or request.get('provider_name') != '@codex'
                or request.get('allow_paid') is not False or not request.get('model')
                or request.get('task') not in {'code', 'plan'}):
            raise ProviderError('INVALID_INPUT', 'Selecciona @codex y un modelo explícito, con allow_paid=false.')
        messages = request.get('messages')
        if (not isinstance(messages, list) or not 2 <= len(messages) <= 4
                or any(not isinstance(row, dict) or set(row) != {'role', 'content'}
                       or not isinstance(row['content'], str) or not row['content'].strip() for row in messages)
                or messages[0]['role'] != 'system' or any(row['role'] != 'user' for row in messages[1:])):
            raise ProviderError('INVALID_INPUT', 'La generación requiere contrato y objetivo como datos separados.')
        timeout = request.get('deadline_ms', 70000)
        if type(timeout) is not int or not 1 <= timeout <= TURN_TIMEOUT * 1000:
            raise ProviderError('INVALID_INPUT', 'El plazo de generación debe estar entre 1 y 70000 ms.')
        deadline = time.monotonic() + timeout / 1000
        reference = {'system_reference': messages[0]['content'], 'goal': messages[1]['content']}
        if len(messages)>2:reference['preparation_feedback']=[row['content'] for row in messages[2:]]
        message = json.dumps(reference, ensure_ascii=False)
        images = request.get('images')
        if images and request.get('sensitivity') != 'approved_sensitive':
            raise ProviderError('INVALID_INPUT', 'Las imágenes de contexto requieren autorización de contenido sensible.')
        run = self.start({'request_id': request.get('request_id'), 'model': request['model'],
                          'message': message, 'purpose': purpose, 'origin': 'axx',
                          **{key:request[key] for key in ('memory_scope','memory_context_id','memory_dependencies','conversation_id') if key in request}}, cancel_event=cancel_event, images=images)
        request_id = run['request_id']
        while run['state'] not in TERMINAL:
            if cancel_event is not None and cancel_event.is_set():
                self.cancel(request_id)
                raise ProviderError('CANCELLED', 'El contexto autorizado cambió; se solicitó la cancelación.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.cancel(request_id)
                raise ProviderError('DEADLINE_EXCEEDED', 'La propuesta excedió su plazo; se solicitó la cancelación sin cambiar de proveedor.')
            with self.lock:
                event = (self.live.get(request_id) or {}).get('_done')
            if event is not None: event.wait(min(0.1, remaining))
            else: threading.Event().wait(min(0.1, remaining))
            run = self.get(request_id)
        with self.lock:
            live=self.live.get(request_id) or {}
            self._assert_memory(run)
            text=live.get('response') if run.get('response_retained') is False else run.get('response')
            if live.get('_source_tainted'):live['response']=''
        if cancel_event is not None and cancel_event.is_set():
            raise ProviderError('CANCELLED', 'El contexto autorizado cambió; se descartó la respuesta.')
        if run['state'] != 'completed' or run.get('inference_verified') is not True:
            error = run.get('error') or {}
            raise ProviderError(error.get('code', 'CAPABILITY_GENERATION_FAILED'),
                                error.get('message', 'La generación no terminó con identidad verificada.'))
        if (run.get('purpose') != purpose or run.get('runtime_model') != request['model']
                or run.get('runtime_provider') != 'openai' or run.get('tool_results') or run.get('pending_approvals')):
            raise ProviderError('CAPABILITY_UNVERIFIED', 'La propuesta no conserva aislamiento, modelo y proveedor exactos.')
        if not isinstance(text, str) or not text.strip() or len(text) > 64000:
            raise ProviderError('RESPONSE_LIMIT', 'La propuesta está vacía o supera 64000 caracteres.')
        return {'ok': True, 'message': {'content': text},
                'route': {'model': run['runtime_model'], 'provider_name': '@codex'}}

    def get(self, request_id, after=0):
        if type(after) is not int or after < 0:
            raise ProviderError('INVALID_INPUT', 'Cursor de eventos inválido.')
        with self.lock:
            run = self._load(request_id)
            rows = self.db.execute('SELECT event_json FROM connect_events WHERE request_id=? AND seq>? ORDER BY seq LIMIT 500',
                                   (request_id, after)).fetchall()
            run['events'] = [json.loads(row[0]) for row in rows]
            run['pending_approvals'] = [key for key, (rid, _) in self.approvals.items() if rid == request_id]
            run['effects_reverted'] = False
            return self._memory_projection(run)

    def history(self, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ProviderError('INVALID_INPUT', 'Límite de historial inválido.')
        with self.lock:
            return [self._memory_projection(json.loads(row[0])) for row in self.db.execute(
                'SELECT body_json FROM connect_runs ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()]

    def cancel(self, request_id):
        effects = []
        with self.lock:
            run = self.live.get(request_id)
            if run:
                self._stop_forgotten(run)
            if run and (run['state'] not in TERMINAL or run.get('memory_forgotten')):
                run['_cancel'].set()
                run['cancel_requested'] = True
                self._event(run, 'run/cancel_requested', {'effects_reverted': False})
                effects.extend(run.get('managed_operations', []))
        for operation_id in set(effects):
            if self.dispatcher:
                try:
                    self._dispatch('axx_cancel_task', {'operation_id': operation_id}, run,
                                   'cancel-' + operation_id, cleanup=True)
                except Exception:
                    # Cancellation cannot imply rollback, nor erase the operation record.
                    pass
        return self.get(request_id)

    def approve(self, request_id, approval_id, decision):
        if decision not in {'accept', 'decline', 'cancel'}:
            raise ProviderError('INVALID_INPUT', 'Decisión inválida.')
        with self.lock:
            entry = self.approvals.get(str(approval_id))
            if not entry or entry[0] != request_id:
                raise ProviderError('NOT_FOUND', 'La aprobación ya no está pendiente.')
            message = entry[1]
            method = message['method']
            # Native shell/file/permission tools are outside this provider's authority.
            # Axx effectful capabilities use the existing Axx approval path instead.
            if decision == 'accept':
                raise ProviderError('OUTSIDE_AXX_REGISTRY', 'Esta solicitud del runtime está fuera de las herramientas Axx. Cancélala y usa una capacidad registrada.')
            if method in {'item/commandExecution/requestApproval', 'item/fileChange/requestApproval'}:
                result = {'decision': decision}
            elif method == 'item/permissions/requestApproval':
                result = {'permissions': {}, 'scope': 'turn'}
            elif method == 'mcpServer/elicitation/request':
                result = {'action': decision, 'content': None}
            else:
                result = None
            # Claim the user decision once, then release the reader's lock before
            # any pipe wait. A write with uncertain outcome is never replayed.
            self.approvals.pop(str(approval_id), None)
            run = self.live[request_id]
            if run['state'] not in TERMINAL:
                run['state'] = 'processing'
            self._event(run, 'approval/resolved', {'approval_id': str(approval_id), 'decision': decision})
            if decision == 'cancel':
                run['_cancel'].set()
        if result is None:
            self._write({'id': message['id'], 'error': {'code': -32000, 'message': 'User declined unsupported request'}}, timeout=3)
        else:
            self._write({'id': message['id'], 'result': result}, timeout=3)
        return self.get(request_id)

    def login(self):
        self._set_local_enabled(True)
        self._spawn()
        # Browser URL goes only to the explicit login response, never an event/log.
        result = self._rpc('account/login/start', {'type': 'chatgpt'})
        self.login_id = result.get('loginId')
        return dict(result, state='authenticating')

    def login_cancel(self):
        if not self.local_enabled:
            return self._locally_disconnected() | {'cancelled': False}
        self._spawn()
        if not self.login_id:
            return {'state': 'disconnected', 'cancelled': False}
        result = self._rpc('account/login/cancel', {'loginId': self.login_id})
        self.login_id = None
        return dict(result, state='disconnected', cancelled=True)

    def reconnect(self):
        with self.lock:
            if any(run['state'] not in TERMINAL for run in self.live.values()):
                raise ProviderError('BUSY', 'Detén los turnos antes de reconectar.')
        with self.start_lock:
            with self.lock:
                if any(run['state'] not in TERMINAL for run in self.live.values()):
                    raise ProviderError('BUSY', 'Detén los turnos antes de reconectar.')
                process = self.process
            self._stop_process(process)
            self.process = None
            self._set_local_enabled(True)
            self.verified_model = self.verified_at = None
            self.engine_state = None
            return self.status()

    def logout(self):
        """Compatibility alias: disconnect only Axx, never the shared account."""
        return self.disconnect()

    def _set_local_enabled(self, enabled):
        with self.lock:
            if self.closed:
                raise ProviderError('CLOSED', 'El proveedor está detenido.')
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO connect_settings VALUES ('provider_enabled',?)", (json.dumps(enabled),))
            self.local_enabled = enabled

    def disconnect(self):
        """Persist Axx's opt-out and close only this provider's owned runtime."""
        with self.lock:
            if any(run['state'] not in TERMINAL for run in self.live.values()):
                raise ProviderError('BUSY', 'Detén los turnos activos antes de desconectar Axx.')
        with self.start_lock:
            with self.lock:
                if any(run['state'] not in TERMINAL for run in self.live.values()):
                    raise ProviderError('BUSY', 'Detén los turnos activos antes de desconectar Axx.')
                self._set_local_enabled(False)
                self.account = self.account_fingerprint = None
                self.account_epoch += 1
                self.verified_model = self.verified_at = None
                self.auth_failed = False
                self.engine_state = None
                self.login_id = None
                process = self.process
            self._stop_process(process)
            with self.lock:
                self.process = None
                self.runtime_error = None
                return self._locally_disconnected()

    def _stop_process(self, process):
        if process is None:
            return
        deadline = time.monotonic() + 3
        try:
            writer = self.writer
            if writer is not None and writer.process is process:
                writer.submit(None, timeout=1)
            else:
                # Only initialization failure or a controlled test double can
                # lack an owner. Even its close runs off the calling thread.
                closed = threading.Event()
                def close_pipe():
                    try:
                        process.stdin.close()
                    finally:
                        closed.set()
                threading.Thread(target=close_pipe, daemon=True).start()
                if not closed.wait(1):
                    raise subprocess.TimeoutExpired('stdin close', 1)
            # Reserve one second for terminate/kill within the same total budget.
            process.wait(timeout=max(0, deadline-time.monotonic()-1))
        except (OSError, ValueError, ProviderError, subprocess.TimeoutExpired):
            self._terminate_owned(process, max(0, deadline-time.monotonic()))

    def close(self):
        with self.start_lock:
            with self.lock:
                if self.closed:
                    return
                for run in self.live.values():
                    if run['state'] not in TERMINAL:
                        run['_cancel'].set()
                        run.update(state='unknown', error={'code': 'PROVIDER_CLOSED',
                            'message': 'Proveedor detenido; los efectos ya realizados permanecen.'})
                        self._event(run, 'runtime/closed', {'effects_reverted': False})
                        run['_done'].set()
                process = self.process
            self._stop_process(process)
            with self.lock:
                self.closed = True
                self.db.close()


# Stable name for callers while the runtime remains explicitly experimental.
ChatGPTCodexProvider = CodexProvider
