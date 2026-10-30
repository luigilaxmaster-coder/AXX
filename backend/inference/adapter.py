"""Private inference boundary: bounded workers, wall deadline and cancellation."""
from __future__ import annotations
import json
import copy
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


def _attempt_details(source):
    read = source.get if isinstance(source, dict) else lambda key, default=None: getattr(source, key, default)
    details = {key: read(key) for key in ('upstream_attempts', 'attempt_budget_used')
               if type(read(key)) is int and read(key) >= 0}
    attempted = read('upstream_attempted')
    if any(value > 0 for value in details.values()):
        details['upstream_attempted'] = True
    elif type(attempted) is bool:
        details['upstream_attempted'] = attempted
        if attempted is False:
            details.update(upstream_attempts=0, attempt_budget_used=0)
        else:
            # Inconsistent zero counts cannot release a mission reservation.
            details = {'upstream_attempted': True}
    return details


class ActiveRequest:
    def __init__(self, request_id, deadline_mono, cancel_event=None):
        self.request_id, self.deadline_mono = request_id, deadline_mono
        self.cancelled, self.completed = False, False
        self.terminal_state = self.process = self.job = None
        self.lock = threading.Lock()
        self.cancel_event = cancel_event

    def is_cancelled(self):
        return self.cancelled or (self.cancel_event is not None and self.cancel_event.is_set())

def worker_main(state_path: str) -> int:
    """Same executable entry point; exactly one bounded stdin/stdout JSON object."""
    router, dispatched = None, False
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
        dispatched = True
        result = router.chat(data['request'], deadline_time=time.monotonic() + seconds)
        response, code = {'ok': True, 'result': result}, 0
    except Exception as exc:
        error_code = getattr(exc, 'code', 'PROCESS_FAILURE')
        if isinstance(exc, UpstreamError) and exc.status == 504:
            error_code = 'DEADLINE_EXCEEDED'
        response = {'ok': False, 'error': {'code': error_code, 'message': str(exc),
                    'retryable': error_code in ('UPSTREAM_TEMPORARY', 'NO_PROVIDER_AVAILABLE', 'STATE_UNAVAILABLE')}}
        response['error'].update(_attempt_details(exc) if dispatched else _attempt_details({'upstream_attempted': False}))
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
    supports_cancel_event = True

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

    def record_outcome(self, route: dict, task: str, outcome: str) -> dict:
        with self.lock:
            if self.router is None:
                raise ValueError('Adapter closed')
            return self.router.record_outcome(route, task, outcome)

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
    def _error(request_id, code, message, retryable=False, upstream_attempted=None,
               upstream_attempts=None, attempt_budget_used=None):
        result = {'request_id': request_id, 'ok': False,
                'error': {'code': code, 'retryable': retryable, 'message': message}}
        result['error'].update(_attempt_details({'upstream_attempted': upstream_attempted,
            'upstream_attempts': upstream_attempts, 'attempt_budget_used': attempt_budget_used}))
        return result

    def _worker_result(self, active, request, config_override=None):
        if active.is_cancelled():
            return {'ok': False, 'error': {'code': 'CANCELLED', 'message': 'Request cancelled before dispatch',
                                          'retryable': False, 'upstream_attempted': False}}
        command = ([sys.executable, '--router-worker'] if getattr(sys, 'frozen', False)
                   else [sys.executable, '-m', 'backend.server', '--router-worker'])
        command += ['--state', str(self.state_path)]
        data = json.dumps({'config': self.config if config_override is None else config_override, 'request': request,
                          'remaining_seconds': max(.001, active.deadline_mono - time.monotonic())},
                         allow_nan=False).encode('utf-8')
        if len(data) > MAX_WORKER_INPUT:
            raise RequestError('Worker input exceeds size limit')
        child_env = os.environ.copy()
        child_env.pop('AXX_HOST_TOKEN', None)
        if active.is_cancelled():
            return {'ok': False, 'error': {'code': 'CANCELLED', 'message': 'Request cancelled before dispatch',
                                          'retryable': False, 'upstream_attempted': False}}
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
                # A cancellation during process creation must not deliver a request
                # to the child. Before stdin is written, it cannot contact upstream.
                if active.is_cancelled():
                    proc.stdin.close()
                    return
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
                if active.is_cancelled():
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

    def route_candidate(self, envelope: dict, provider_name: str, *, provider_override=None) -> dict:
        """Internal evaluation boundary: exact configured route, unchanged free policy and capacity."""
        return self.route(dict(envelope, selection_mode='automatic_free'), _candidate_provider=provider_name,
                          _candidate_override=provider_override)

    def route(self, envelope: dict, *, _candidate_provider=None, _candidate_override=None, cancel_event=None) -> dict:
        request_id = str(uuid.uuid4())
        if not isinstance(envelope, dict):
            return self._error(request_id, 'INVALID_REQUEST', 'Envelope must be an object', upstream_attempted=False)
        request_id = envelope.get('request_id') or request_id
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            return self._error(str(request_id)[:128], 'INVALID_REQUEST', 'Invalid internal cancellation event', upstream_attempted=False)
        conversation_id, deadline_ms = envelope.get('conversation_id', 'default'), envelope.get('deadline_ms', 70000)
        if (not isinstance(request_id, str) or not 1 <= len(request_id) <= 128
                or not isinstance(conversation_id, str) or not 1 <= len(conversation_id) <= 128
                or type(deadline_ms) is not int or not 1 <= deadline_ms <= 70000):
            return self._error(str(request_id)[:128], 'INVALID_REQUEST', 'Invalid request identity or deadline', upstream_attempted=False)
        if 'upstream_attempt_budget' in envelope and (type(envelope['upstream_attempt_budget']) is not int
                or not 1 <= envelope['upstream_attempt_budget'] <= 10):
            return self._error(request_id, 'INVALID_REQUEST', 'upstream_attempt_budget must be an integer between 1 and 10', upstream_attempted=False)
        if envelope.get('sensitivity', 'public') not in ('public', 'approved_sensitive'):
            return self._error(request_id, 'INVALID_REQUEST', 'Local-only content cannot use remote inference', upstream_attempted=False)
        active = ActiveRequest(request_id, time.monotonic() + deadline_ms / 1000, cancel_event)
        with self.lock:
            if active.is_cancelled():
                return self._error(request_id, 'CANCELLED', 'Request cancelled before registration', upstream_attempted=False)
            if self.router is None:
                return self._error(request_id, 'PROCESS_FAILURE', 'Adapter closed', upstream_attempted=False)
            candidate_config = None
            if _candidate_provider is not None:
                providers = [p for p in self.config.get('providers', []) if p['name'] == _candidate_provider]
                if len(providers) != 1 or envelope.get('selection_mode') != 'automatic_free':
                    return self._error(request_id, 'INVALID_REQUEST', 'Invalid candidate route', upstream_attempted=False)
                candidate_config = copy.deepcopy(self.config)
                candidate_config['providers'] = copy.deepcopy(providers)
                if _candidate_override is not None:
                    if not isinstance(_candidate_override, dict) or any(_candidate_override.get(key) != providers[0].get(key)
                            for key in ('name', 'base_url', 'api_key_env', 'gateway_dashboard_env', 'kind')):
                        return self._error(request_id, 'INVALID_REQUEST', 'Candidate route identity changed', upstream_attempted=False)
                    candidate_config['providers'] = [copy.deepcopy(_candidate_override)]
                candidate_config['providers'][0]['candidate_only'] = False
                # Isolation must retain the account limit imposed by every configured sibling route.
                candidate_config['providers'][0]['scope_limit'] = min(
                    self.router._scope_limit(providers[0]),
                    candidate_config['providers'][0].get('scope_limit', providers[0]['daily_attempt_limit']))
            if request_id in self.active_requests or conversation_id in self.conversation_locks or len(self.active_requests) >= 2:
                return self._error(request_id, 'BUSY', 'Inference capacity is busy', True, upstream_attempted=False)
            self.active_requests[request_id], self.conversation_locks[conversation_id] = active, request_id
        dispatched = False
        try:
            request = {'messages': envelope.get('messages', []), 'axx_task': envelope.get('task', 'chat'),
                       'selection_mode': envelope.get('selection_mode', 'manual'),
                       'axx_sensitive': envelope.get('sensitivity') == 'approved_sensitive'}
            if 'upstream_attempt_budget' in envelope:
                request['axx_attempt_budget'] = envelope['upstream_attempt_budget']
            if envelope.get('model') and request['selection_mode'] != 'automatic_free':
                request['model'] = envelope['model']
            if envelope.get('provider_name') and request['selection_mode'] != 'automatic_free':
                request['provider_name'] = envelope['provider_name']
            generation = envelope.get('generation', {})
            if not isinstance(generation, dict):
                raise RequestError('generation must be an object')
            if set(generation) - {'temperature', 'max_tokens', 'tools'}:
                raise RequestError('Unsupported generation fields')
            for key in ('temperature', 'max_tokens', 'tools'):
                if key in generation:
                    request[key] = generation[key]
            self.router.validate_request(request)
            if active.is_cancelled():
                return self._error(request_id, 'CANCELLED', 'Request cancelled before dispatch', upstream_attempted=False)
            # Injection is reserved for deterministic offline tests.
            dispatched = True
            if self.router.transport is not http_transport:
                if candidate_config is None:
                    raw_result = self.router.chat(request, deadline_time=active.deadline_mono)
                else:
                    candidate_router = Router(candidate_config, state=self.state_path, transport=self.router.transport)
                    try:
                        raw_result = candidate_router.chat(request, deadline_time=active.deadline_mono)
                    finally:
                        candidate_router.close()
            else:
                worker = self._worker_result(active, request) if candidate_config is None else self._worker_result(active, request, candidate_config)
                if not worker['ok']:
                    error = worker.get('error', {})
                    with active.lock:
                        if active.is_cancelled():
                            return self._error(request_id, 'CANCELLED', 'Request cancelled; late response discarded',
                                               **_attempt_details(error))
                        return self._error(request_id, error.get('code', 'PROCESS_FAILURE'),
                                           error.get('message', 'Inference failed'), bool(error.get('retryable')), **_attempt_details(error))
                raw_result = worker['result']
            with active.lock:
                if active.is_cancelled():
                    return self._error(request_id, 'CANCELLED', 'Request cancelled; late response discarded',
                                       **_attempt_details(raw_result.get('axx_router', {})))
                if time.monotonic() >= active.deadline_mono:
                    return self._error(request_id, 'DEADLINE_EXCEEDED', 'Inference wall deadline exceeded',
                                       **_attempt_details(raw_result.get('axx_router', {})))
                self.router._validate_response_message(raw_result)
                active.completed, active.terminal_state = True, 'COMPLETED'
            return {'request_id': request_id, 'ok': True, 'message': raw_result['choices'][0]['message'],
                    'route': raw_result.get('axx_router', {}), **_attempt_details(raw_result.get('axx_router', {}))}
        except Exception as exc:
            code = getattr(exc, 'code', 'PROCESS_FAILURE')
            if isinstance(exc, UpstreamError) and exc.status == 504:
                code = 'DEADLINE_EXCEEDED'
            if active.is_cancelled():
                code = 'CANCELLED'
            return self._error(request_id, code, 'Request cancelled' if active.is_cancelled() else str(exc),
                               code in ('NO_PROVIDER_AVAILABLE', 'STATE_UNAVAILABLE', 'UPSTREAM_TEMPORARY'),
                               **(_attempt_details(exc) if dispatched else _attempt_details({'upstream_attempted': False})))
        finally:
            with self.lock:
                self.active_requests.pop(request_id, None)
                if self.conversation_locks.get(conversation_id) == request_id:
                    self.conversation_locks.pop(conversation_id, None)
