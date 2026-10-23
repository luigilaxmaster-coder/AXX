"""Bounded Windows window observation and UI Automation helpers.

UIA runs in a short-lived, dedicated MTA PowerShell process. The script is a
packaged constant; requests are JSON on stdin and never become PowerShell code.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import base64
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit, parse_qs

MAX_WINDOWS = 512
MAX_CONTROLS = 250
MAX_UITEXT = 8192
UIA_TIMEOUT_SECONDS = 8


def _positive_int(value, label):
    if type(value) is not int or value <= 0 or value > 0xFFFFFFFFFFFFFFFF:
        raise ValueError(f"{label} inválido")
    return value


def _windows_api():
    if os.name != 'nt':
        raise ValueError('El control de ventanas requiere Windows.')
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.restype = ctypes.c_int
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetForegroundWindow.argtypes = []
    user.GetForegroundWindow.restype = wintypes.HWND
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsWindow.restype = wintypes.BOOL
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.SetForegroundWindow.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user.AttachThreadInput.restype = wintypes.BOOL
    kernel.GetCurrentProcessId.argtypes = []
    kernel.GetCurrentProcessId.restype = wintypes.DWORD
    kernel.GetCurrentThreadId.argtypes = []
    kernel.GetCurrentThreadId.restype = wintypes.DWORD
    return user, kernel


def list_windows():
    """Return visible top-level windows with ephemeral HWND/PID identity."""
    user, kernel = _windows_api()
    foreground = int(user.GetForegroundWindow() or 0)
    rows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        title_len = min(max(user.GetWindowTextLengthW(hwnd), 0), 2048)
        if title_len == 0:
            return True
        title = ctypes.create_unicode_buffer(title_len + 1)
        user.GetWindowTextW(hwnd, title, len(title))
        class_name = ctypes.create_unicode_buffer(256)
        user.GetClassNameW(hwnd, class_name, len(class_name))
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            rows.append({'window_id': int(hwnd), 'pid': int(pid.value), 'title': title.value,
                         'class_name': class_name.value, 'foreground': int(hwnd) == foreground})
        return len(rows) < MAX_WINDOWS

    callback = callback_type(visit)
    if not user.EnumWindows(callback, 0):
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
    return rows[:MAX_WINDOWS]


def observe_foreground(expected_title=None, timeout=5.0, before=None, aliases=(), cancelled=None):
    """Observe launch/focus state without inferring app readiness from dispatch."""
    if type(timeout) not in (int, float) or not 0.0 <= timeout <= 10.0:
        raise ValueError('Timeout de observación inválido')
    before_ids = {int(row['window_id']) for row in (before or []) if isinstance(row, dict) and type(row.get('window_id')) is int}
    expected_values = [_normalize(value) for value in (expected_title, *aliases) if isinstance(value, str) and value.strip()]
    deadline = time.monotonic() + timeout
    latest = None
    while True:
        if cancelled is not None and cancelled.is_set():
            raise ValueError('Observación cancelada antes de confirmar el foco.')
        windows = list_windows()
        foreground = next((row for row in windows if row['foreground']), None)
        title = _normalize(foreground['title']) if foreground else ''
        matches_name = any(expected in title for expected in expected_values)
        observed_new = bool(foreground and foreground['window_id'] not in before_ids)
        latest = foreground
        if foreground and (matches_name or observed_new):
            break
        if time.monotonic() >= deadline:
            break
        if cancelled is None:
            time.sleep(0.15)
        elif cancelled.wait(0.15):
            raise ValueError('Observación cancelada antes de confirmar el foco.')
    window_observed = latest is not None
    title = _normalize(latest.get('title', '')) if latest else ''
    title_matches = any(expected in title for expected in expected_values)
    window_observed = bool(latest and (title_matches or latest['window_id'] not in before_ids))
    foreground_verified = bool(latest and latest.get('foreground') and title_matches)
    ready = foreground_verified
    return {'launch_requested': True, 'window_observed': window_observed,
            'foreground_verified': foreground_verified, 'ready_for_action': ready,
            'window': latest, 'verification': 'foreground_window_observation' if ready else 'launch_handoff_only'}


def focus_window(window_id, expected_pid):
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    user, kernel = _windows_api()
    hwnd = wintypes.HWND(window_id)
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not user.IsWindow(hwnd) or pid.value != expected_pid:
        raise ValueError('La ventana observada ya no existe o cambió de proceso.')
    foreground_hwnd = user.GetForegroundWindow()
    foreground_thread = user.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
    current_thread = kernel.GetCurrentThreadId()
    attached = bool(foreground_thread and foreground_thread != current_thread and
                    user.AttachThreadInput(current_thread, foreground_thread, True))
    try:
        if not user.SetForegroundWindow(hwnd):
            raise ValueError('Windows no concedió el foco a la ventana solicitada.')
    finally:
        if attached:
            user.AttachThreadInput(current_thread, foreground_thread, False)
    time.sleep(0.08)
    foreground = int(user.GetForegroundWindow() or 0)
    if foreground != window_id:
        raise ValueError('No se confirmó el foco de la ventana solicitada.')
    return {'window_id': window_id, 'pid': expected_pid, 'foreground_verified': True,
            'verification': 'foreground_window_readback'}


def inspect_controls(window_id, expected_pid, cancelled=None):
    return _uia({'operation': 'inspect', 'window_id': _positive_int(window_id, 'window_id'),
                 'pid': _positive_int(expected_pid, 'pid')}, cancelled=cancelled)


def read_window_content(window_id, expected_pid, expected_title, cancelled=None):
    if not isinstance(expected_title, str) or not 1 <= len(expected_title) <= 2048:
        raise ValueError('Indica el título observado de la ventana.')
    result = _uia({'operation': 'read_content', 'window_id': _positive_int(window_id, 'window_id'),
                 'pid': _positive_int(expected_pid, 'pid'), 'expected_title': expected_title}, cancelled=cancelled)
    return summarize_window_content(result)


def summarize_window_content(result):
    """Keep observed text and links; never infer destinations from labels."""
    lines, links, seen = [], [], set()
    visible = sorted((row for row in result.get('controls', []) if not row.get('offscreen')),
                     key=lambda row: (row.get('bounds', {}).get('y', 0), row.get('bounds', {}).get('x', 0)))
    for row in visible:
        text = row.get('text') or row.get('value') or row.get('name') or ''
        if text and text not in seen:
            lines.append(text); seen.add(text)
        if row.get('control_type') != 'ControlType.Hyperlink': continue
        url = row.get('value', '')
        try: parsed = urlsplit(url)
        except ValueError: continue
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password: continue
        if any(link['url'] == url for link in links): continue
        link = {'title': row.get('text') or row.get('name') or url, 'url': url, 'control_id': row['control_id']}
        video_id = parse_qs(parsed.query).get('v', [''])[0]
        if (parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com') and parsed.path == '/watch'
                and row.get('automation_id') == 'video-title' and len(video_id) == 11
                and all(c.isascii() and (c.isalnum() or c in '-_') for c in video_id)):
            link['video_id'] = video_id
        links.append(link)
    text = '\n'.join(lines)
    result.update(text=text[:24000], links=links, observed_at=time.time(),
                  truncated=result.get('truncated', False) or len(text) > 24000,
                  content_status='observed' if lines else 'unavailable')
    return result


def set_control_value(window_id, expected_pid, control_id, value, cancelled=None):
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    if not isinstance(control_id, str) or len(control_id) != 64 or any(c not in '0123456789abcdef' for c in control_id):
        raise ValueError('control_id observado inválido')
    if not isinstance(value, str) or len(value) > MAX_UITEXT or '\x00' in value:
        raise ValueError('El texto debe ser válido y no exceder 8.192 caracteres.')
    value.encode('utf-16-le')
    return _uia({'operation': 'set_value', 'window_id': window_id, 'pid': expected_pid,
                 'control_id': control_id, 'value': value}, cancelled=cancelled)


def _uia(payload, cancelled=None):
    if os.name != 'nt':
        raise ValueError('UI Automation requiere Windows.')
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = Path(__file__).with_name('uia_worker.ps1')
    if not executable.is_file() or not script.is_file():
        raise ValueError('El worker UI Automation no está disponible en este runtime.')
    request = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    # Windows PowerShell execution policy applies to script files. Pass the
    # fixed, packaged worker as a command payload instead of changing policy.
    encoded_worker = base64.b64encode(script.read_text(encoding='utf-8-sig').encode('utf-16-le')).decode('ascii')
    try:
        process = subprocess.Popen([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-MTA',
                                    '-EncodedCommand', encoded_worker],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + UIA_TIMEOUT_SECONDS
        input_bytes = request.encode('utf-8')
        first_communicate = True
        while True:
            if cancelled is not None and cancelled.is_set():
                process.kill()
                process.communicate()
                raise ValueError('UI Automation cancelada; comprueba el estado del control antes de reintentar.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.communicate()
                raise ValueError('UI Automation excedió el límite; verifica la ventana antes de reintentar.')
            try:
                stdout, stderr = process.communicate(input_bytes if first_communicate else None,
                                                     timeout=min(0.1, remaining))
                break
            except subprocess.TimeoutExpired:
                # communicate() must not be called with stdin again after the first timeout.
                first_communicate = False
                continue
        class Completed:
            pass
        result = Completed()
        result.stdout = stdout.decode('utf-8', errors='replace')
        result.stderr = stderr.decode('utf-8', errors='replace')
        result.returncode = process.returncode
    except OSError as exc:
        raise ValueError('No se pudo iniciar el worker de UI Automation.') from exc
    if len(result.stdout.encode('utf-8', errors='replace')) > 512 * 1024:
        raise ValueError('La respuesta de UI Automation excede el límite.')
    if result.returncode:
        message = result.stderr.strip()[:1000] or 'UI Automation rechazó la operación.'
        raise ValueError(message)
    try:
        response = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError('UI Automation devolvió una respuesta inválida.') from exc
    if not isinstance(response, dict) or response.get('success') is not True:
        raise ValueError(str(response.get('error', 'UI Automation no confirmó el resultado.'))[:1000])
    return response


def _normalize(value):
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(value).casefold())
                   if not unicodedata.combining(ch))
