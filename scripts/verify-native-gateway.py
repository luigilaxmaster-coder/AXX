"""Validate the installed Axx -> AnythingMCP -> Windows route, with bounded input.

Moves the physical cursor twelve pixels without clicking, then restores it through
the same installed command endpoint. Temporarily pauses only the identified local
AnythingMCP app container to test cancellation; its database is never paused.
The output contains identities, timings and receipt hashes, never private payloads.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAX_REPLY = 4 * 1024 * 1024
TOOL_NAME = 'axx_windows_native_execute'
CONTAINER_NAME = 'axx-anythingmcp-app-1'


class VerificationError(RuntimeError):
    """Only stable codes are exposed; transport bodies may contain private data."""


def require(condition, code):
    if not condition:
        raise VerificationError(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class LoopbackApi:
    def __init__(self, port, token, prefix):
        require(type(port) is int and 1 <= port <= 65535, 'invalid_loopback_port')
        require(isinstance(token, str) and '\r' not in token and '\n' not in token, 'invalid_local_token')
        self.port, self.token, self.prefix = port, token, prefix
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def __call__(self, route, body=None, *, timeout=15):
        require(route.startswith(self.prefix) and not route.startswith('//') and '#' not in route, 'invalid_loopback_route')
        request = urllib.request.Request('http://127.0.0.1:' + str(self.port) + route,
            data=None if body is None else json.dumps(body, allow_nan=False).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_REPLY + 1)
            require(len(raw) <= MAX_REPLY, 'local_response_too_large')
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise VerificationError('local_http_' + str(exc.code)) from None
        except (OSError, ValueError, TimeoutError):
            raise VerificationError('local_transport_or_json_error') from None


def choose_pointer_target(point, bounds):
    """A twelve-pixel segment stays within the cursor's current physical monitor."""
    x, y = point
    left, top, right, bottom = bounds
    require(left <= x < right and top <= y < bottom, 'cursor_outside_monitor')
    for dx, dy in ((12, 0), (-12, 0), (0, 12), (0, -12)):
        target = x + dx, y + dy
        if (left <= target[0] < right and top <= target[1] < bottom
                and all(-32768 <= value <= 32767 for value in target)):
            return target
    raise VerificationError('no_safe_pointer_segment')


class PhysicalCursor:
    def __init__(self):
        require(os.name == 'nt', 'windows_required')
        self.user = C.WinDLL('user32', use_last_error=True)
        self.user.GetPhysicalCursorPos.argtypes = [C.POINTER(W.POINT)]
        self.user.GetPhysicalCursorPos.restype = W.BOOL
        self.user.MonitorFromPoint.argtypes = [W.POINT, W.DWORD]
        self.user.MonitorFromPoint.restype = W.HMONITOR
        self.user.GetMonitorInfoW.argtypes = [W.HMONITOR, C.c_void_p]
        self.user.GetMonitorInfoW.restype = W.BOOL

    def position(self):
        from backend.magic_pen import physical_dpi_context
        point = W.POINT()
        # Even GetPhysicalCursorPos was observed virtualized on an unaware
        # Python thread at 125% scaling. Match the owner's per-monitor context.
        with physical_dpi_context():
            require(self.user.GetPhysicalCursorPos(C.byref(point)), 'physical_cursor_unavailable')
        return point.x, point.y

    def bounds(self, point):
        from backend.magic_pen import physical_dpi_context
        class MonitorInfo(C.Structure):
            _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('flags', W.DWORD)]
        info = MonitorInfo()
        info.cbSize = C.sizeof(info)
        with physical_dpi_context():
            monitor = self.user.MonitorFromPoint(W.POINT(*point), 0)
            require(monitor and self.user.GetMonitorInfoW(monitor, C.byref(info)), 'physical_monitor_unavailable')
        rect = info.rcMonitor
        return rect.left, rect.top, rect.right, rect.bottom


def audit_rows(payload):
    if isinstance(payload, dict) and set(payload) >= {'items'}:
        payload = payload['items']
    require(isinstance(payload, list) and len(payload) < 10000 and all(isinstance(row, dict) for row in payload), 'invalid_or_truncated_audit')
    return payload


def native_audit_rows(payload, server_id):
    """The upstream toolName query filter is ignored, so filter both fields here."""
    return [row for row in audit_rows(payload) if row.get('mcpServerId') == server_id
            and isinstance(row.get('tool'), dict) and row['tool'].get('name') == TOOL_NAME]


def receipt_hash(row):
    output = row.get('output')
    if not isinstance(output, dict) or output.get('isError'):
        return None
    blocks = output.get('content')
    if not isinstance(blocks, list):
        return None
    texts = [block.get('text') for block in blocks if isinstance(block, dict) and block.get('type') == 'text']
    if len(texts) != 1 or not isinstance(texts[0], str) or len(texts[0]) > 4096:
        return None
    try:
        value = json.loads(texts[0])
    except ValueError:
        return None
    receipt = value.get('receipt') if isinstance(value, dict) else None
    if not isinstance(receipt, str) or not 20 <= len(receipt) <= 100:
        return None
    return hashlib.sha256(receipt.encode()).hexdigest()


def audit_signature(rows):
    """Detect extra invocations as well as upstream aggregation of a repeated call."""
    return sorted((row.get('id'), row.get('repeatCount')) for row in rows)


def checked_container(lines):
    try:
        identity, name, labels, state = [json.loads(line) for line in lines.splitlines()]
    except (ValueError, TypeError):
        raise VerificationError('invalid_container_inspection') from None
    require(isinstance(identity, str) and re.fullmatch(r'[a-f0-9]{64}', identity), 'invalid_container_identity')
    require(name == '/' + CONTAINER_NAME and isinstance(labels, dict)
            and labels.get('com.docker.compose.project') == 'axx-anythingmcp'
            and labels.get('com.docker.compose.service') == 'app', 'container_ownership_mismatch')
    require(isinstance(state, dict) and state.get('Running') is True, 'gateway_container_not_running')
    return identity, state.get('Paused') is True


class OwnedGatewayContainer:
    def __init__(self):
        wsl = shutil.which('wsl')
        require(wsl, 'wsl_unavailable_use_explicit_skip_cancel')
        self.command = [wsl, '-d', 'Ubuntu-24.04', '-u', 'root', '--exec', 'docker']
        self.identity, paused = self.inspect(CONTAINER_NAME)
        require(not paused, 'gateway_container_already_paused')
        self.pause_attempted = False

    def call(self, *args):
        try:
            result = subprocess.run(self.command + list(args), capture_output=True, text=True,
                                    timeout=8, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.SubprocessError):
            raise VerificationError('owned_docker_command_failed') from None
        require(result.returncode == 0, 'owned_docker_command_rejected')
        return result.stdout.strip()

    def inspect(self, identity):
        # Read only these four fields; never fetch the container environment.
        template = '{{json .Id}}\n{{json .Name}}\n{{json .Config.Labels}}\n{{json .State}}'
        return checked_container(self.call('container', 'inspect', '--format', template, identity))

    def pause(self):
        identity, paused = self.inspect(self.identity)
        require(identity == self.identity and not paused, 'gateway_container_changed_before_pause')
        self.pause_attempted = True
        self.call('container', 'pause', self.identity)
        require(self.inspect(self.identity) == (self.identity, True), 'gateway_pause_unconfirmed')

    def restore(self):
        if self.pause_attempted:
            identity, paused = self.inspect(self.identity)
            require(identity == self.identity, 'gateway_container_changed_before_unpause')
            if paused:
                self.call('container', 'unpause', self.identity)
            require(self.inspect(self.identity) == (self.identity, False), 'gateway_unpause_unconfirmed')
            self.pause_attempted = False


class InstalledVerifier:
    def __init__(self, data_dir, expected_version, skip_cancel=False):
        self.data_dir, self.expected_version, self.skip_cancel = Path(data_dir), expected_version, skip_cancel
        self.report = {'schema_version': 1, 'installed_host': True, 'passed': False, 'fully_validated': False,
                       'checks': [], 'operations': [], 'limitations': [
                           'Window enumeration does not certify every application or the 3D interface.',
                           'Pointer verification sends no clicks, text, messages or remote connections.',
                           'URL/content loading and application profile actions require separate runtime acceptance.']}
        self.successes = []
        self.api = self.audit = self.cursor = None
        self.server_id = None

    def check(self, name, condition, **safe_values):
        self.report['checks'].append({'name': name, 'passed': bool(condition), **safe_values})
        require(condition, name)

    def identify(self):
        import psutil
        from backend.connect.mcp_server import LocalAxxClient
        from backend.auth.chatgpt_auth import _dpapi_decrypt
        descriptor = LocalAxxClient(self.data_dir)._descriptor()
        self.api = LoopbackApi(descriptor['port'], descriptor['token'], '/axx-api/')
        live = self.api('/axx-api/status')
        snapshot = json.loads((self.data_dir / 'logs/native-runtime.json').read_text(encoding='utf-8'))
        self.check('installed_identity', live.get('ready') is True and live.get('native') is True
                   and snapshot.get('backendReady') is True and snapshot.get('version') == self.expected_version
                   and snapshot.get('backendInstance') == descriptor['instance_id'] == live.get('instance_id')
                   and snapshot.get('backendPort') == descriptor['port'] and descriptor.get('pid') == live.get('pid'))
        host, backend = psutil.Process(snapshot['pid']), psutil.Process(live['pid'])
        host_exe, backend_exe = Path(host.exe()).resolve(), Path(backend.exe()).resolve()
        actual_host = Path(snapshot['executable']).resolve()
        self.check('installed_processes', host_exe == actual_host and host_exe.name.casefold() == 'axx.exe'
                   and backend_exe.name.casefold() == 'axx-backend.exe'
                   and host_exe.parent in backend_exe.parents and host.pid in [parent.pid for parent in backend.parents()]
                   and ROOT not in host_exe.parents)
        self.report['identity'] = {'version': snapshot['version'], 'backend_instance': live['instance_id'],
            'desktop_pid': host.pid, 'backend_pid': backend.pid,
            'desktop_executable_sha256': hashlib.sha256(host_exe.read_bytes()).hexdigest(),
            'backend_executable_sha256': hashlib.sha256(backend_exe.read_bytes()).hexdigest()}
        native = self.api('/axx-api/mcp/connections').get('native_windows', {})
        endpoint = urllib.parse.urlsplit(native.get('endpoint') or '')
        self.check('gateway_configured', native.get('mode') == 'gateway' and native.get('state') in ('configured', 'verified')
                   and endpoint.scheme == 'http' and endpoint.hostname == '127.0.0.1' and endpoint.port == 4000
                   and re.fullmatch(r'/mcp/[A-Za-z0-9_-]{1,100}', endpoint.path)
                   and not endpoint.query and not endpoint.fragment and endpoint.username is None)
        self.server_id = endpoint.path.rsplit('/', 1)[1]
        session = self.data_dir / 'anythingmcp/administrator-session.dpapi'
        require(session.stat().st_size <= 16384 and not session.is_symlink(), 'invalid_administrator_session')
        token = _dpapi_decrypt(session.read_bytes()).decode('ascii')
        require(re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token), 'invalid_administrator_jwt')
        self.audit = LoopbackApi(4000, token, '/api/audit/')
        self.cursor = PhysicalCursor()

    def audit_snapshot(self):
        return native_audit_rows(self.audit('/api/audit/invocations?limit=1000'), self.server_id)

    def prepare(self, command, inputs):
        identity = 'native-gateway-' + uuid.uuid4().hex
        prepared = self.api('/axx-api/commands/prepare', {'operation_id': identity, 'command_id': command,
                                                        'inputs': inputs, 'source': 'text'})
        require(prepared.get('operation_id') == identity and prepared.get('state') in ('prepared', 'awaiting_approval'), 'command_prepare_rejected')
        return identity

    def execute(self, command, inputs):
        identity = self.prepare(command, inputs)
        started = time.monotonic()
        result = self.api('/axx-api/commands/execute', {'operation_id': identity, 'approved': True}, timeout=40)
        evidence = result.get('evidence', {})
        self.check('verified_' + command, result.get('state') == 'succeeded' and result.get('postconditions_passed') is True
                   and evidence.get('transport') == 'anythingmcp_streamable_http'
                   and re.fullmatch(r'[a-f0-9]{64}', evidence.get('gateway_receipt_sha256', ''))
                   and evidence.get('native_operation_id') == 'cmd-' + hashlib.sha256(identity.encode()).hexdigest())
        record = {'operation_id': identity, 'command': command, 'state': result['state'],
                  'postconditions_passed': True, 'receipt_sha256': evidence['gateway_receipt_sha256'],
                  'duration_ms': round((time.monotonic() - started) * 1000, 2)}
        self.report['operations'].append(record)
        self.successes.append(record)
        return identity, result

    def correlate(self):
        deadline = time.monotonic() + 5
        while True:
            rows = self.audit_snapshot()
            hashes = [receipt_hash(row) for row in rows]
            counts = [hashes.count(record['receipt_sha256']) for record in self.successes]
            if all(count == 1 for count in counts) or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        for record, count in zip(self.successes, counts):
            self.check('audit_one_invocation_' + record['operation_id'], count == 1)
            row = rows[hashes.index(record['receipt_sha256'])]
            self.check('audit_success_and_single_call_' + record['operation_id'], row.get('status') == 'SUCCESS'
                       and row.get('repeatCount') == 1 and isinstance(row.get('id'), str)
                       and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', row['id']))
            record['audit_id'] = row['id']
            record['audit_duration_ms'] = row.get('durationMs')
            record['audit_repeat_count'] = row.get('repeatCount')
        return rows

    def replay(self, identity, first):
        before = audit_signature(self.correlate())
        result = self.api('/axx-api/commands/execute', {'operation_id': identity, 'approved': True})
        self.check('replay_same_receipt', result.get('replayed') is True and result.get('state') == first['state']
                   and result.get('evidence', {}).get('gateway_receipt_sha256') == first['evidence']['gateway_receipt_sha256'])
        self.check('replay_no_gateway_call', audit_signature(self.audit_snapshot()) == before)

    def cancel_with_gateway_paused(self):
        container, identity, worker = OwnedGatewayContainer(), None, None
        replies = queue.Queue()
        original = self.cursor.position()
        target = choose_pointer_target(original, self.cursor.bounds(original))
        def execute():
            try:
                replies.put(self.api('/axx-api/commands/execute', {'operation_id': identity, 'approved': True}, timeout=40))
            except Exception as exc:
                replies.put(exc)
        try:
            container.pause()
            identity = self.prepare('axx.desktop.pointer.move', {'x': target[0], 'y': target[1]})
            worker = threading.Thread(target=execute, daemon=True, name='verify-owned-gateway-cancel')
            worker.start()
            expected = 'cmd-' + hashlib.sha256(identity.encode()).hexdigest()
            deadline = time.monotonic() + 3
            while True:
                native = self.api('/axx-api/mcp/connections', timeout=1).get('native_windows', {})
                if native.get('last_operation_id') == expected and native.get('state') == 'running':
                    break
                require(time.monotonic() < deadline and replies.empty(), 'cancel_probe_not_waiting_on_gateway')
                time.sleep(.03)
            started = time.monotonic()
            cancelled = self.api('/axx-api/commands/cancel', {'operation_id': identity}, timeout=2)
            require(cancelled.get('cancel_requested') is True, 'cancel_request_not_recorded')
            try:
                result = replies.get(timeout=max(.01, 3 - (time.monotonic() - started)))
            except queue.Empty:
                raise VerificationError('cancel_did_not_finish_within_three_seconds') from None
            elapsed = time.monotonic() - started
            require(isinstance(result, dict), 'cancel_execution_transport_failed')
            evidence = result.get('evidence', {})
            observed = self.cursor.position()
            self.report['cancellation'] = {'operation_id': identity, 'before': list(original), 'target': list(target),
                'observed': list(observed), 'dx': observed[0] - original[0], 'dy': observed[1] - original[1],
                'duration_ms': round(elapsed * 1000, 2), 'native_started': evidence.get('native_started'),
                'effect_uncertain': evidence.get('effect_uncertain')}
            self.check('cancel_before_native_effect', elapsed < 3 and result.get('state') == 'cancelled'
                       and evidence.get('native_started') is False and evidence.get('effect_uncertain') is False
                       and observed == original, duration_ms=round(elapsed * 1000, 2),
                       dx=observed[0] - original[0], dy=observed[1] - original[1])
            self.report['operations'].append({'operation_id': identity, 'command': 'axx.desktop.pointer.move',
                'state': result['state'], 'native_started': False, 'effect_uncertain': False,
                'duration_ms': round(elapsed * 1000, 2)})
        finally:
            try:
                if identity and worker and worker.is_alive():
                    self.api('/axx-api/commands/cancel', {'operation_id': identity}, timeout=2)
            finally:
                container.restore()
                if worker:
                    worker.join(timeout=5)
                if self.cursor.position() != original:
                    self.execute('axx.desktop.pointer.move', {'x': original[0], 'y': original[1]})
                    self.check('cancel_probe_pointer_restored', self.cursor.position() == original)
        self.check('gateway_recovered', self.api('/axx-api/mcp/connections')['native_windows']['mode'] == 'gateway')
        self.execute('axx.desktop.list_windows', {})

    def run(self):
        self.identify()
        identity, result = self.execute('axx.desktop.list_windows', {})
        self.replay(identity, result)
        self.execute('axx.app.windows', {'application': 'chrome'})
        original = self.cursor.position()
        target = choose_pointer_target(original, self.cursor.bounds(original))
        pointer = self.report['pointer'] = {'coordinate_system': 'physical_virtual_desktop_pixels',
            'dpi_context': 'per_monitor_v2', 'tolerance_px': 0, 'before': list(original), 'target': list(target),
            'requested_displacement_px': {'dx': target[0] - original[0], 'dy': target[1] - original[1]}}
        attempted = False
        try:
            attempted = True
            identity, result = self.execute('axx.desktop.pointer.move', {'x': target[0], 'y': target[1]})
            observed = self.cursor.position()
            pointer.update(observed=list(observed),
                actual_displacement_px={'dx': observed[0] - original[0], 'dy': observed[1] - original[1]},
                readback_delta_px={'dx': observed[0] - target[0], 'dy': observed[1] - target[1]})
            self.check('physical_pointer_readback', observed == target,
                       dx=observed[0] - target[0], dy=observed[1] - target[1])
            self.replay(identity, result)
        finally:
            if attempted:
                self.execute('axx.desktop.pointer.move', {'x': original[0], 'y': original[1]})
                restored = self.cursor.position()
                pointer.update(restored=list(restored),
                    restoration_delta_px={'dx': restored[0] - original[0], 'dy': restored[1] - original[1]})
                self.check('physical_pointer_restored', restored == original,
                           dx=restored[0] - original[0], dy=restored[1] - original[1])
        if self.skip_cancel:
            self.report['limitations'].append('Cancellation with a paused gateway was explicitly skipped and remains unverified.')
        else:
            self.cancel_with_gateway_paused()
        self.correlate()
        self.check('gateway_final_verified', self.api('/axx-api/mcp/connections')['native_windows']['state'] == 'verified')
        self.report.update(passed=True, fully_validated=not self.skip_cancel)
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Axx')
    parser.add_argument('--expected-version', default=json.loads((ROOT / 'src-tauri/tauri.conf.json').read_text(encoding='utf-8'))['version'])
    parser.add_argument('--skip-cancel', action='store_true', help='Explicitly leave paused-gateway cancellation unverified')
    args = parser.parse_args()
    verifier = InstalledVerifier(args.data_dir, args.expected_version, args.skip_cancel)
    try:
        verifier.run()
    except Exception as exc:
        # No exception strings from native/UIA/HTTP/DPAPI are written to the receipt.
        verifier.report['error'] = str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verifier.report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': verifier.report['passed'], 'fully_validated': verifier.report['fully_validated'],
                      'checks': len(verifier.report['checks']), 'receipt': str(args.output)}))
    return 0 if verifier.report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
