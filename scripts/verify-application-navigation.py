"""Verify one installed-gateway Chrome navigation using an isolated local fixture.

Creates a new Chrome profile and two loopback pages. No user profile, cookies,
private pages or screenshots are accessed. A successful URL readback alone is
insufficient: the fixture HTTP server must independently observe the target GET.
Do not run until the expected desktop version has been installed.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MAX_REPLY = 4 * 1024 * 1024
PREFIX = 'axx-app-navigation-'


class VerificationError(RuntimeError):
    """Stable codes only; native and HTTP exception text is never published."""


def require(condition, code):
    if not condition:
        raise VerificationError(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class InstalledApi:
    def __init__(self, descriptor):
        require(type(descriptor.get('port')) is int and 1 <= descriptor['port'] <= 65535, 'invalid_backend_port')
        token = descriptor.get('token')
        require(isinstance(token, str) and len(token) >= 32 and '\r' not in token and '\n' not in token,
                'invalid_backend_token')
        self.descriptor = descriptor
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def __call__(self, route, body=None, timeout=15):
        require(route.startswith('/axx-api/') and '#' not in route and not route.startswith('//'), 'invalid_backend_route')
        request = urllib.request.Request('http://127.0.0.1:' + str(self.descriptor['port']) + route,
            data=None if body is None else json.dumps(body, allow_nan=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self.descriptor['token'], 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_REPLY + 1)
            require(len(raw) <= MAX_REPLY, 'backend_reply_too_large')
            result = json.loads(raw)
            require(isinstance(result, dict), 'backend_reply_not_object')
            return result
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise VerificationError('backend_http_' + str(code)) from None
        except (OSError, ValueError, TimeoutError):
            raise VerificationError('backend_transport_or_json_error') from None


def installed_identity(data_dir, version, *, observe_only=False):
    import psutil
    from backend.connect.mcp_server import LocalAxxClient
    client = LocalAxxClient(data_dir)
    descriptor = client._descriptor()
    require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', descriptor.get('instance_id', '')),
            'invalid_backend_instance')
    api = InstalledApi(descriptor)
    path = data_dir/'logs/native-runtime.json'
    require(not path.is_symlink() and path.stat().st_size <= 65536, 'invalid_runtime_snapshot')
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    status = api('/axx-api/status')
    require(snapshot.get('version') == version and snapshot.get('backendReady') is True
            and status.get('ready') is True and status.get('native') is True
            and snapshot.get('backendInstance') == descriptor['instance_id'] == status.get('instance_id')
            and snapshot.get('backendPort') == descriptor['port'] and descriptor.get('pid') == status.get('pid'),
            'installed_version_or_instance_mismatch')
    host, backend = psutil.Process(snapshot['pid']), psutil.Process(status['pid'])
    host_exe, backend_exe = Path(host.exe()).resolve(), Path(backend.exe()).resolve()
    require(host_exe == Path(snapshot['executable']).resolve() and host_exe.name.casefold() == 'axx.exe'
            and backend_exe.name.casefold() == 'axx-backend.exe' and host_exe.parent in backend_exe.parents
            and host.pid in [parent.pid for parent in backend.parents()] and ROOT not in host_exe.parents,
            'installed_process_identity_mismatch')
    gateway = api('/axx-api/mcp/connections').get('native_windows', {})
    endpoint = urllib.parse.urlsplit(gateway.get('endpoint') or '')
    allowed_states = ('configured', 'verified', 'error') if observe_only else ('configured', 'verified')
    require(gateway.get('mode') == 'gateway' and gateway.get('state') in allowed_states
            and endpoint.scheme == 'http' and endpoint.hostname == '127.0.0.1' and endpoint.port == 4000
            and re.fullmatch(r'/mcp/[A-Za-z0-9_-]{1,100}', endpoint.path)
            and endpoint.username is None and not endpoint.query and not endpoint.fragment, 'gateway_not_configured')
    identity = {'version': version, 'backend_instance': descriptor['instance_id'], 'desktop_pid': host.pid,
                'backend_pid': backend.pid, 'desktop_executable_sha256': hashlib.sha256(host_exe.read_bytes()).hexdigest(),
                'backend_executable_sha256': hashlib.sha256(backend_exe.read_bytes()).hexdigest()}
    return api, client, identity


def chrome_binary(requested=None):
    import winreg
    candidates = set()
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
                                    0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                if isinstance(value, str):
                    candidates.add(Path(value.strip('"')).resolve())
            except OSError:
                pass
    for name in ('PROGRAMFILES', 'PROGRAMFILES(X86)'):
        if os.environ.get(name):
            candidates.add((Path(os.environ[name])/'Google/Chrome/Application/chrome.exe').resolve())
    valid = {path for path in candidates if path.is_file() and path.name.casefold() == 'chrome.exe' and not path.is_symlink()}
    if requested:
        selected = requested.resolve(strict=True)
        require(selected in valid, 'chrome_not_observed_in_app_paths_or_program_files')
        return selected
    require(len(valid) == 1, 'chrome_installation_missing_or_ambiguous')
    return next(iter(valid))


def checked_fixture_url(url, port, nonce, page):
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port == port
            and parsed.username is None and parsed.password is None and not parsed.fragment
            and parsed.path == '/' + page and parsed.query == 'fixture=' + nonce, 'invalid_fixture_url')
    return url


def select_owned_window(rows, owners):
    matches = [row for row in rows if row.get('pid') in owners
               and row.get('process_started') == owners[row['pid']]]
    require(len(matches) == 1, 'owned_chrome_window_missing_or_ambiguous')
    row = matches[0]
    require(type(row.get('window_id')) is int and row['window_id'] > 0, 'invalid_owned_window')
    return row


class FixturePages:
    def __init__(self):
        self.nonce, self.events = uuid.uuid4().hex, {'start': threading.Event(), 'target': threading.Event()}
        self.target_count, self.target_after = 0, None
        self.lock = threading.Lock()
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def handle(self):
                try:
                    super().handle()
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    # Chrome may close preconnected sockets during owned cleanup.
                    pass
            def do_GET(self):
                page = next((name for name in fixture.events if self.path == '/' + name + '?fixture=' + fixture.nonce), None)
                if not page:
                    self.send_response(404)
                    self.end_headers()
                    return
                with fixture.lock:
                    if page == 'target' and fixture.target_after is not None and time.monotonic() >= fixture.target_after:
                        fixture.target_count += 1
                        fixture.events['target'].set()
                    elif page == 'start':
                        fixture.events['start'].set()
                body = ('<!doctype html><html><head><title>Axx navigation fixture ' + page +
                        '</title></head><body><h1>Local Axx fixture ' + page + '</h1></body></html>').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='axx-owned-navigation-http')

    def url(self, page):
        return checked_fixture_url('http://127.0.0.1:' + str(self.server.server_port) + '/' + page + '?fixture=' + self.nonce,
                                   self.server.server_port, self.nonce, page)

    def start(self):
        self.thread.start()

    def close(self):
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        if self.thread.ident is not None:
            self.thread.join(timeout=5)
        require(not self.thread.is_alive(), 'fixture_http_cleanup_failed')


class OwnedChrome:
    def __init__(self, executable):
        self.executable, self.owned, self.tree = executable, {}, {}
        self.root = self.process = None
        self.birth = None

    def start(self, directory, url):
        import psutil
        self.process = subprocess.Popen([str(self.executable), '--user-data-dir=' + str(directory/'profile'), '--no-first-run',
            '--no-default-browser-check', '--force-renderer-accessibility', '--disable-background-networking',
            '--disable-component-update', '--disable-sync', '--disable-extensions', '--new-window', url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
        self.root = psutil.Process(self.process.pid)
        self.birth = self.root.create_time()
        self.refresh()

    def refresh(self):
        import psutil
        require(self.root and self.root.is_running() and self.root.create_time() == self.birth, 'owned_chrome_root_changed')
        require(Path(self.root.exe()).resolve() == self.executable, 'owned_chrome_executable_changed')
        for process in [self.root, *self.root.children(recursive=True)]:
            try:
                executable, birth = Path(process.exe()).resolve(), process.create_time()
                self.tree[process.pid] = (birth, executable)
                if executable == self.executable:
                    self.owned[process.pid] = birth
            except (psutil.Error, OSError):
                continue
        return dict(self.owned)

    def windows(self):
        import psutil
        owners, rows = self.refresh(), []
        user = C.WinDLL('user32', use_last_error=True)
        callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, W.LPARAM], W.BOOL
        user.IsWindowVisible.argtypes, user.IsWindowVisible.restype = [W.HWND], W.BOOL
        user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        @callback_type
        def observe(hwnd, _):
            pid = W.DWORD()
            user.GetWindowThreadProcessId(hwnd, C.byref(pid))
            if pid.value not in owners or not user.IsWindowVisible(hwnd):
                return True
            try:
                process = psutil.Process(pid.value)
                if process.create_time() != owners[pid.value] or Path(process.exe()).resolve() != self.executable:
                    return True
                name = C.create_unicode_buffer(256)
                if user.GetClassNameW(hwnd, name, len(name)) and name.value == 'Chrome_WidgetWin_1':
                    rows.append({'window_id': int(hwnd), 'pid': pid.value, 'process_started': owners[pid.value]})
            except (psutil.Error, OSError):
                pass
            return True
        require(user.EnumWindows(observe, 0), 'windows_observation_failed')
        return rows, owners

    def close(self):
        import psutil
        try:
            self.refresh()
        except (VerificationError, psutil.Error, OSError):
            pass
        processes = []
        for pid, (birth, executable) in self.tree.items():
            try:
                process = psutil.Process(pid)
                if process.create_time() == birth and Path(process.exe()).resolve() == executable:
                    processes.append(process)
            except (psutil.Error, OSError):
                continue
        for process in reversed(processes):
            try:
                process.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(processes, timeout=4)
        for process in alive:
            try:
                if process.create_time() == self.tree[process.pid][0]:
                    process.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=4)
        # The original Popen handle remains safe even if psutil initialization failed.
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=4)
        remaining = []
        for process in alive:
            try:
                if process.is_running() and process.create_time() == self.tree[process.pid][0]:
                    remaining.append(process.pid)
            except psutil.NoSuchProcess:
                pass
        require(not remaining, 'owned_chrome_cleanup_failed')


def clean_temporary(directory, temporary_root):
    require(directory.parent == temporary_root and directory.name.startswith(PREFIX) and not directory.is_symlink()
            and directory.resolve(strict=True) == directory and ROOT not in directory.parents, 'temporary_cleanup_scope_invalid')
    shutil.rmtree(directory)
    require(not directory.exists(), 'temporary_cleanup_failed')


def sanitized_inspection(output):
    require(isinstance(output, dict) and isinstance(output.get('controls'), list), 'inspection_shape_invalid')
    focused = output.get('focused_control_id')
    controls, bars = output['controls'], []
    for row in controls:
        if not isinstance(row, dict):
            continue
        name = row.get('name') or ''
        address = isinstance(name, str) and any(term in name.casefold() for term in ('address', 'direcc', 'buscar o escribir'))
        if not address and (not focused or row.get('control_id') != focused):
            continue
        clean = {key: row.get(key) for key in ('control_id', 'control_type', 'enabled', 'offscreen',
            'supports_value_pattern', 'supports_invoke_pattern', 'read_only', 'patterns')}
        clean['is_focused'] = bool(focused and row.get('control_id') == focused)
        clean['read_only_present'] = 'read_only' in row
        clean['value_present'] = 'value' in row
        if address:
            clean['name'] = name[:200]
        bars.append(clean)
    return {'process_started': output.get('process_started'), 'control_count': len(controls),
            'truncated': output.get('truncated'), 'focused_id_present': bool(focused),
            'focused_id_enumerated': bool(focused) and any(row.get('control_id') == focused for row in controls if isinstance(row, dict)),
            'focused_control_id': focused, 'address_or_focused_controls': bars}


def verify_source_observation(args, report):
    """Read one own fixture with the source UIA cache; no executor or input broker."""
    require(os.name == 'nt', 'windows_required')
    from backend.actions import windows_automation as uia
    from backend.actions.application_tools import _address_bars
    from backend.application_catalog import profile_for
    command = next(row for row in profile_for('chrome')['commands'] if row['id'] == 'navigate')
    executable = chrome_binary(args.chrome_executable)
    report['chrome_executable_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
    report['source_sha256'] = {name: hashlib.sha256((ROOT/'backend/actions'/name).read_bytes()).hexdigest()
                             for name in ('windows_automation.py', 'application_tools.py', 'uia_worker.ps1')}
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix=PREFIX, dir=temporary_root)).resolve(strict=True)
    pages, chrome = None, None
    try:
        pages = FixturePages()
        pages.start()
        expected = pages.url('start')
        chrome = OwnedChrome(executable)
        chrome.start(directory, expected)
        require(pages.events['start'].wait(15), 'chrome_start_page_not_loaded')
        deadline = time.monotonic() + 10
        while True:
            rows, owners = chrome.windows()
            if rows:
                selected = select_owned_window(rows, owners)
                break
            require(time.monotonic() < deadline, 'owned_chrome_window_missing')
            time.sleep(.1)
        report['window'] = {key: selected[key] for key in ('window_id', 'pid')}
        report['owned_process_instances'] = [{'pid': pid, 'process_started': owners[pid]} for pid in sorted(owners)]
        observed = uia.inspect_controls(selected['window_id'], selected['pid'])
        report['inspection'] = sanitized_inspection(observed)
        require(observed.get('truncated') is False, 'source_inspection_truncated')
        candidates = _address_bars(observed, command)
        report['address_candidate_count'] = len(candidates)
        require(len(candidates) == 1, 'source_address_bar_missing_or_ambiguous')
        candidate = candidates[0]
        result = uia.read_control_value(selected['window_id'], selected['pid'], candidate['control_id'],
                                        observed['observation']['observation_id'])
        actual_hash = hashlib.sha256(result['value'].encode('utf-8')).hexdigest()
        expected_hash = hashlib.sha256(expected.encode('utf-8')).hexdigest()
        display_hash = hashlib.sha256(expected.removeprefix('http://').encode('utf-8')).hexdigest()
        report['value_readback'] = {'verification': result.get('verification'),
            'control_id': result.get('control_id'), 'actual_value_sha256': actual_hash,
            'expected_url_sha256': expected_hash, 'url_hash_matches': actual_hash == expected_hash,
            'expected_display_without_http_sha256': display_hash, 'display_without_http_hash_matches': actual_hash == display_hash,
            'actual_length': len(result['value']), 'expected_url_length': len(expected),
            'actual_starts_http': result['value'].startswith('http://'),
            'actual_empty': result['value'] == ''}
        require(result.get('verification') == 'uia_control_value_observed' and actual_hash == expected_hash,
                'source_value_readback_differed')
        require(not pages.events['target'].is_set() and pages.target_count == 0, 'unexpected_fixture_target_request')
        report['observation_verified'] = True
    except Exception as exc:
        report['verification_error'] = str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
        raise
    finally:
        cleanup_errors, cleanup_error_types = [], {}
        for code, cleanup in [('owned_chrome_cleanup_failed', lambda: chrome.close() if chrome else None),
                              ('fixture_http_cleanup_failed', lambda: pages.close() if pages else None),
                              ('temporary_cleanup_failed', lambda: clean_temporary(directory, temporary_root))]:
            try:
                cleanup()
            except Exception as exc:
                cleanup_errors.append(code)
                cleanup_error_types[code] = type(exc).__name__
        report.update(cleanup_complete=not cleanup_errors, cleanup_errors=cleanup_errors,
                      cleanup_error_types=cleanup_error_types)
        require(not cleanup_errors, 'fixture_cleanup_incomplete')
    report['passed'] = True


def verify(args, report):
    require(os.name == 'nt', 'windows_required')
    api, client, identity = installed_identity(args.data_dir, args.expected_version, observe_only=args.observe_only)
    report['identity'] = identity
    executable = chrome_binary(args.chrome_executable)
    report['chrome_executable_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
    temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    directory = Path(tempfile.mkdtemp(prefix=PREFIX, dir=temporary_root)).resolve(strict=True)
    pages, chrome, pending = None, None, None
    terminal = False
    try:
        pages = FixturePages()
        pages.start()
        chrome = OwnedChrome(executable)
        chrome.start(directory, pages.url('start'))
        require(pages.events['start'].wait(15), 'chrome_start_page_not_loaded')
        deadline = time.monotonic() + 10
        while True:
            rows, owners = chrome.windows()
            if rows:
                selected = select_owned_window(rows, owners)
                break
            require(time.monotonic() < deadline, 'owned_chrome_window_missing')
            time.sleep(.1)
        report['window'] = {key: selected[key] for key in ('window_id', 'pid')}
        report['owned_process_ids'] = sorted(owners)
        report['owned_process_instances'] = [{'pid': pid, 'process_started': owners[pid]} for pid in sorted(owners)]
        url = pages.url('target')
        inputs = {'application': 'chrome', 'window_id': selected['window_id'], 'pid': selected['pid']}
        command = 'axx.app.inspect' if args.observe_only else 'axx.app.navigate'
        if not args.observe_only:
            inputs.update(command_id='navigate', url=url)
        pending = PREFIX + uuid.uuid4().hex
        prepared = api('/axx-api/commands/prepare', {'operation_id': pending, 'command_id': command,
                                                   'inputs': inputs, 'source': 'text'})
        require(prepared.get('operation_id') == pending and prepared.get('inputs') == inputs
                and prepared.get('state') in ('prepared', 'awaiting_approval'), 'navigation_prepare_rejected')
        # Revalidate the exact process/window immediately before approving this fixture only.
        rows, owners = chrome.windows()
        require(select_owned_window(rows, owners) == selected, 'owned_chrome_window_changed')
        if not args.observe_only:
            pages.target_after = time.monotonic()
        result = api('/axx-api/commands/execute', {'operation_id': pending, 'approved': True}, timeout=45)
        terminal = result.get('state') in ('succeeded', 'failed', 'unknown', 'cancelled', 'expired', 'blocked')
        evidence = result.get('evidence') or {}
        receipt = evidence.get('gateway_receipt_sha256')
        receipt = receipt if isinstance(receipt, str) and re.fullmatch(r'[a-f0-9]{64}', receipt) else None
        state = result.get('state') if terminal else 'invalid_or_nonterminal'
        report['operation'] = {'operation_id': pending, 'command': command, 'state': state,
            'postconditions_passed': result.get('postconditions_passed') is True,
            'gateway_receipt_sha256': receipt}
        if args.observe_only and result.get('output'):
            report['inspection'] = sanitized_inspection(result['output'])
        if not args.observe_only:
            report['operation']['target_url_sha256'] = hashlib.sha256(url.encode()).hexdigest()
            report['independent_target_get'] = pages.events['target'].wait(5)
            report['target_get_count'] = pages.target_count
            output = result.get('output') if isinstance(result.get('output'), dict) else {}
            observed_url = output.get('observed_url')
            report['application_result'] = {
                'scheme_verified': output.get('scheme_verified') if type(output.get('scheme_verified')) is bool else None,
                'content_verified': output.get('content_verified') if type(output.get('content_verified')) is bool else None,
                'observed_url_sha256': hashlib.sha256(observed_url.encode('utf-8')).hexdigest() if isinstance(observed_url, str) else None}
        require(result.get('state') == 'succeeded' and result.get('postconditions_passed') is True
                and evidence.get('transport') == 'anythingmcp_streamable_http'
                and receipt is not None
                and evidence.get('native_operation_id') == 'cmd-' + hashlib.sha256(pending.encode()).hexdigest(),
                'inspection_gateway_unverified' if args.observe_only else 'navigation_gateway_effect_unverified')
        if not args.observe_only:
            require(evidence.get('verification') == 'application_url_readback', 'navigation_gateway_effect_unverified')
            require(report['independent_target_get'] and pages.target_count == 1, 'independent_target_get_not_exactly_one')
            require(output.get('window_id') == selected['window_id'] and output.get('pid') == selected['pid']
                    and output.get('url') == url and type(output.get('scheme_verified')) is bool
                    and output.get('content_verified') is False
                    and evidence.get('scheme_verified') is output['scheme_verified']
                    and evidence.get('content_verified') is False, 'application_verification_scope_invalid')
        after = client._descriptor()
        require(after['instance_id'] == identity['backend_instance'] == api('/axx-api/status').get('instance_id')
                and after['port'] == api.descriptor['port'], 'installed_instance_changed')
        report['observation_verified' if args.observe_only else 'navigation_verified'] = True
    except Exception as exc:
        report['verification_error'] = str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
        raise
    finally:
        cleanup_errors = []
        cleanup_error_types = {}
        if pending and not terminal:
            try:
                cancelled = api('/axx-api/commands/cancel', {'operation_id': pending}, timeout=5)
                require(cancelled.get('operation_id') == pending, 'fixture_cancel_identity_mismatch')
                deadline = time.monotonic() + 5
                while cancelled.get('state') not in ('succeeded', 'failed', 'unknown', 'cancelled', 'expired', 'blocked'):
                    require(cancelled.get('cancel_requested') is True and time.monotonic() < deadline,
                            'fixture_operation_cancel_unconfirmed')
                    time.sleep(.1)
                    cancelled = api('/axx-api/commands/operations?' + urllib.parse.urlencode({'operation_id': pending}),
                                    timeout=2).get('operation') or {}
                    require(cancelled.get('operation_id') == pending, 'fixture_cancel_identity_mismatch')
            except Exception as exc:
                cleanup_errors.append('fixture_operation_cancel_unconfirmed')
                cleanup_error_types['fixture_operation_cancel_unconfirmed'] = type(exc).__name__
        for code, cleanup in [('owned_chrome_cleanup_failed', lambda: chrome.close() if chrome else None),
                              ('fixture_http_cleanup_failed', lambda: pages.close() if pages else None),
                              ('temporary_cleanup_failed', lambda: clean_temporary(directory, temporary_root))]:
            try:
                cleanup()
            except Exception as exc:
                cleanup_errors.append(code)
                cleanup_error_types[code] = type(exc).__name__
        report['cleanup_complete'] = not cleanup_errors
        report['cleanup_errors'] = cleanup_errors
        report['cleanup_error_types'] = cleanup_error_types
        require(not cleanup_errors, 'fixture_cleanup_incomplete')
    report['passed'] = True


def self_check():
    nonce = 'test-only-fixture'
    good = 'http://127.0.0.1:12345/target?fixture=' + nonce
    require(checked_fixture_url(good, 12345, nonce, 'target') == good, 'self_check_url')
    for bad in ('https://example.test/target', good.replace('127.0.0.1', 'localhost'), good + '#fragment',
                good.replace('127.0.0.1', 'user@127.0.0.1')):
        try:
            checked_fixture_url(bad, 12345, nonce, 'target')
        except VerificationError:
            continue
        raise VerificationError('self_check_url_rejection')
    one = {'window_id': 3, 'pid': 7, 'process_started': 1.5}
    require(select_owned_window([one], {7: 1.5}) == one, 'self_check_window')
    for rows, owners in [([one, one], {7: 1.5}), ([one], {8: 1.5}), ([one], {7: 2.0})]:
        try:
            select_owned_window(rows, owners)
        except VerificationError:
            continue
        raise VerificationError('self_check_window_rejection')
    return {'passed': True, 'self_check': True, 'native_execution_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('LOCALAPPDATA', Path.home()))/'Axx')
    parser.add_argument('--expected-version')
    parser.add_argument('--chrome-executable', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--observe-only', action='store_true', help='Inspect a NEW isolated fixture; never send hotkeys or navigate commands')
    parser.add_argument('--source-observe-only', action='store_true', help='Read a NEW fixture through source UIA/cache only; no executor or input')
    args = parser.parse_args()
    if args.self_check:
        print(json.dumps(self_check()))
        return 0
    if not args.output or not args.expected_version or not re.fullmatch(r'\d+\.\d+\.\d+', args.expected_version):
        parser.error('--output and --expected-version X.Y.Z are required')
    if args.observe_only and args.source_observe_only:
        parser.error('choose one observation mode')
    scope = 'one_isolated_chrome_observation_via_installed_gateway' if args.observe_only else 'one_isolated_chrome_navigation_via_installed_gateway'
    if args.source_observe_only:
        scope = 'one_isolated_chrome_source_uia_value_readback_without_input'
    report = {'schema_version': 1, 'scope': scope,
              'passed': False, 'navigation_verified': False, 'cleanup_complete': False,
              'limitations': ['This fixture does not validate user profiles, downloads, other applications or all Chrome actions.']}
    try:
        if args.source_observe_only:
            verify_source_observation(args, report)
        else:
            verify(args, report)
    except Exception as exc:
        report['error'] = str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'navigation_verified': report['navigation_verified'],
                      'cleanup_complete': report['cleanup_complete'], 'receipt': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
