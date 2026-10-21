"""Private inference boundary: bounded workers, wall deadline and cancellation."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from .router import Router, RouterError, RequestError, UpstreamError, parse_strict_json, http_transport
from .process_manager import spawn_managed_process, terminate_process_tree

MAX_WORKER_INPUT = 3 * 1024 * 1024
MAX_WORKER_OUTPUT = 8 * 1024 * 1024
MAX_WORKER_ERROR = 64 * 1024

class ActiveRequest:
    def __init__(self, request_id, deadline_mono):
        self.request_id, self.deadline_mono = request_id, deadline_mono
        self.cancelled, self.completed = False, False
        self.terminal_state = self.process = self.job = None
        self.lock = threading.Lock()

def worker_main(state_path: str) -> int:
    """Same executable entry point; exactly one bounded stdin/stdout JSON object."""
    router = None
    try:
        raw = sys.stdin.buffer.read(MAX_WORKER_INPUT + 1)
        if len(raw) > MAX_WORKER_INPUT:
            raise RequestError('Worker input exceeds size limit')
        data = parse_strict_json(raw)
        if not isinstance(data, dict):
            raise RequestError('Worker input must be an object')
        config = data['config']
        if config.get('allow_paid', False) is not False:
            raise RequestError('Paid inference is disabled')
        seconds = data.get('remaining_seconds', 70)
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 70:
            raise RequestError('Invalid worker deadline')
        router = Router(config, state=state_path)
        result = router.chat(data['request'], deadline_time=time.monotonic() + seconds)
        response, code = {'ok': True, 'result': result}, 0
    except Exception as exc:
        error_code = getattr(exc, 'code', 'PROCESS_FAILURE')
        if isinstance(exc, UpstreamError) and exc.status == 504:
            error_code = 'DEADLINE_EXCEEDED'
        response = {'ok': False, 'error': {'code': error_code, 'message': str(exc),
                    'retryable': error_code in ('UPSTREAM_TEMPORARY', 'NO_PROVIDER_AVAILABLE', 'STATE_UNAVAILABLE')}}
        code = 1
    finally:
        if router:
            router.close()
    encoded = json.dumps(response, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_WORKER_OUTPUT:
        encoded = b'{"ok":false,"error":{"code":"INVALID_RESPONSE","message":"Response exceeds worker limit","retryable":false}}'
        code = 1
    sys.stdout.buffer.write(encoded + b'\n')
    sys.stdout.buffer.flush()
    return code

class InferenceAdapter:
    def __init__(self, config: dict, state_path: str | Path = 'state.db', *, router_instance: Router | None = None):
        if config.get('allow_paid', False) is not False:
            raise ValueError('Paid inference is disabled')
        self.config, self.state_path = config, Path(state_path).resolve()
        self.router = router_instance or Router(config, state=self.state_path)
        self.active_requests, self.conversation_locks = {}, {}
        self.lock = threading.RLock()

    def close(self):
        with self.lock:
            ids = list(self.active_requests)
        for request_id in ids:
            self.cancel(request_id)
        with self.lock:
            if self.router:
                self.router.close()
                self.router = None

    def update_config(self, new_config: dict):
        with self.lock:
            self.config = new_config
            if self.router:
                try:
                    self.router.close()
                except Exception:
                    pass
            self.router = Router(new_config, state=self.state_path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_status(self) -> dict:
        with self.lock:
            return self.router.status() if self.router else {'error': 'Adapter closed', 'providers': []}

    def cancel(self, request_id: str) -> bool:
        with self.lock:
            req = self.active_requests.get(request_id)
            if not req:
                return False
            with req.lock:
                if req.completed or req.terminal_state:
                    return False
                req.cancelled, req.terminal_state = True, 'CANCELLED'
                proc, job = req.process, req.job
        if proc:
            terminate_process_tree(proc, job)
        return True

    @staticmethod
    def _error(request_id, code, message, retryable=False):
        return {'request_id': request_id, 'ok': False,
                'error': {'code': code, 'retryable': retryable, 'message': message}}

    def _worker_result(self, active, request):
        command = ([sys.executable, '--router-worker'] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-m', 'backend.server', '--router-worker'])
        command += ['--state', str(self.state_path)]
        data = json.dumps({'config': self.config, 'request': request,
                          'remaining_seconds': max(.001, active.deadline_mono - time.monotonic())},
                         allow_nan=False).encode('utf-8')
        if len(data) > MAX_WORKER_INPUT:
            raise RequestError('Worker input exceeds size limit')
        child_env = os.environ.copy()
        child_env.pop('AXX_HOST_TOKEN', None)
        proc, job = spawn_managed_process(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=child_env,
                                         cwd=str(Path(__file__).resolve().parents[2]))
        with active.lock:
            active.process, active.job = proc, job
        output, errors, overflow = bytearray(), bytearray(), threading.Event()
        def collect(pipe, target, limit):
            try:
                while True:
                    chunk = pipe.read(8192)
                    if not chunk:
                        break
                    if len(target) + len(chunk) > limit:
                        overflow.set()
                        break
                    target.extend(chunk)
            finally:
                pipe.close()
        readers = [threading.Thread(target=collect, args=(proc.stdout, output, MAX_WORKER_OUTPUT), daemon=True),
                   threading.Thread(target=collect, args=(proc.stderr, errors, MAX_WORKER_ERROR), daemon=True)]
        write_errors = []
        def write_input():
            try:
                proc.stdin.write(data)
                proc.stdin.close()
            except (OSError, ValueError) as exc:
                write_errors.append(exc)
                try:
                    proc.stdin.close()
                except (OSError, ValueError):
                    pass
        writer = threading.Thread(target=write_input, daemon=True)
        for reader in readers:
            reader.start()
        writer.start()
        try:
            while proc.poll() is None:
                if active.cancelled:
                    return {'ok': False, 'error': {'code': 'CANCELLED', 'message': 'Request cancelled', 'retryable': False}}
                if overflow.is_set():
                    raise RouterError('Worker output exceeds size limit', code='INVALID_RESPONSE')
                if time.monotonic() >= active.deadline_mono:
                    raise RouterError('Inference wall deadline exceeded', code='DEADLINE_EXCEEDED')
                if write_errors:
                    raise RouterError('Inference worker input channel failed')
                time.sleep(.02)
            read_deadline = time.monotonic() + 1
            for reader in readers:
                reader.join(timeout=max(0, read_deadline - time.monotonic()))
            if overflow.is_set():
                raise RouterError('Worker output exceeds size limit', code='INVALID_RESPONSE')
            if not output:
                raise RouterError('Inference worker exited without a result')
            result = parse_strict_json(bytes(output))
            if not isinstance(result, dict) or type(result.get('ok')) is not bool:
                raise RouterError('Invalid inference worker envelope', code='INVALID_RESPONSE')
            if result['ok'] and proc.returncode != 0:
                raise RouterError('Inference worker failed after producing output')
            return result
        finally:
            if proc.poll() is None:
                terminate_process_tree(proc, job)
            if job:
                job.close()
            # Killing the worker closes its stdin read end, releasing a blocked writer.
            # All pipe cleanup shares a one-second budget beyond the inference deadline.
            cleanup_deadline = time.monotonic() + 1
            for pipe_thread in [writer, *readers]:
                pipe_thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))

    def route(self, envelope: dict) -> dict:
        request_id = str(uuid.uuid4())
        if not isinstance(envelope, dict):
            return self._error(request_id, 'INVALID_REQUEST', 'Envelope must be an object')
        request_id = envelope.get('request_id') or request_id
        conversation_id, deadline_ms = envelope.get('conversation_id', 'default'), envelope.get('deadline_ms', 70000)
        if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 128
                or not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 128
                or type(deadline_ms) is not int or not 1 <= deadline_ms <= 70000):
            return self._error(str(request_id)[:128], 'INVALID_REQUEST', 'Invalid request identity or deadline')
        if envelope.get('sensitivity', 'public') not in ('public', 'approved_sensitive'):
            return self._error(request_id, 'INVALID_REQUEST', 'Local-only content cannot use remote inference')
        active = ActiveRequest(request_id, time.monotonic() + deadline_ms / 1000)
        with self.lock:
            if self.router is None:
                return self._error(request_id, 'PROCESS_FAILURE', 'Adapter closed')
            if request_id in self.active_requests or conversation_id in self.conversation_locks or len(self.active_requests) >= 2:
                return self._error(request_id, 'BUSY', 'Inference capacity is busy', True)
            self.active_requests[request_id], self.conversation_locks[conversation_id] = active, request_id
        try:
            request = {'messages': envelope.get('messages', []), 'axx_task': envelope.get('task', 'chat'),
                       'axx_sensitive': envelope.get('sensitivity') == 'approved_sensitive'}
            generation = envelope.get('generation', {})
            if not isinstance(generation, dict):
                raise RequestError('generation must be an object')
            if set(generation) - {'temperature', 'max_tokens', 'tools'}:
                raise RequestError('Unsupported generation fields')
            for key in ('temperature', 'max_tokens', 'tools'):
                if key in generation:
                    request[key] = generation[key]
            self.router.validate_request(request)
            # Injection is reserved for deterministic offline tests.
            if self.router.transport is not http_transport:
                raw_result = self.router.chat(request, deadline_time=active.deadline_mono)
            else:
                worker = self._worker_result(active, request)
                if not worker['ok']:
                    error = worker.get('error', {})
                    return self._error(request_id, error.get('code', 'PROCESS_FAILURE'),
                                       error.get('message', 'Inference failed'), bool(error.get('retryable')))
                raw_result = worker['result']
            with active.lock:
                if active.cancelled:
                    return self._error(request_id, 'CANCELLED', 'Request cancelled; late response discarded')
                if time.monotonic() >= active.deadline_mono:
                    return self._error(request_id, 'DEADLINE_EXCEEDED', 'Inference wall deadline exceeded')
                self.router._validate_response_message(raw_result)
                active.completed, active.terminal_state = True, 'COMPLETED'
            return {'request_id': request_id, 'ok': True, 'message': raw_result['choices'][0]['message'],
                    'route': raw_result.get('axx_router', {})}
        except Exception as exc:
            code = getattr(exc, 'code', 'PROCESS_FAILURE')
            if isinstance(exc, UpstreamError) and exc.status == 504:
                code = 'DEADLINE_EXCEEDED'
            if active.cancelled:
                code = 'CANCELLED'
            return self._error(request_id, code, 'Request cancelled' if active.cancelled else str(exc),
                               code in ('NO_PROVIDER_AVAILABLE', 'STATE_UNAVAILABLE', 'UPSTREAM_TEMPORARY'))
        finally:
            with self.lock:
                self.active_requests.pop(request_id, None)
                if self.conversation_locks.get(conversation_id) == request_id:
                    self.conversation_locks.pop(conversation_id, None)
