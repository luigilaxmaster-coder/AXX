"""Bounded Windows window observation and UI Automation helpers.

UIA runs in a short-lived, dedicated MTA PowerShell process. The script is a
packaged constant; requests are JSON on stdin and never become PowerShell code.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import threading
import uuid
from urllib.parse import urlsplit, parse_qs

MAX_WINDOWS = 512
MAX_CONTROLS = 250
MAX_UITEXT = 8192
UIA_TIMEOUT_SECONDS = 8
OBSERVATION_SESSION_ID = str(uuid.uuid4())
OBSERVATION_MAX_AGE = 15.0
_observations = {}
_observation_lock = threading.Lock()


def _remember_observation(result):
    with _observation_lock:
        now = time.monotonic()
        for key in list(_observations):
            if now - _observations[key]['observation']['completed_monotonic'] > OBSERVATION_MAX_AGE:
                del _observations[key]
        while len(_observations) >= 64:
            del _observations[next(iter(_observations))]
        _observations[result['observation']['observation_id']] = copy.deepcopy(result)


def observe_geometry(window_id):
    from backend.magic_pen import monitors, physical_dpi_context
    class GuiThreadInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                    *[(name, wintypes.HWND) for name in ('active', 'focus', 'capture', 'menu', 'move', 'caret')],
                    ('caret_rect', wintypes.RECT)]
    with physical_dpi_context() as user:
        user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetWindowThreadProcessId.restype = wintypes.DWORD
        user.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GuiThreadInfo)]
        user.GetForegroundWindow.restype = wintypes.HWND
        user.IsIconic.argtypes = [wintypes.HWND]
        rect = wintypes.RECT()
        if not user.GetWindowRect(wintypes.HWND(window_id), ctypes.byref(rect)):
            raise ValueError('La geometría de ventana no está disponible.')
        pid = wintypes.DWORD()
        thread = user.GetWindowThreadProcessId(wintypes.HWND(window_id), ctypes.byref(pid))
        info = GuiThreadInfo(); info.cbSize = ctypes.sizeof(info)
        focused = int(info.focus or 0) if user.GetGUIThreadInfo(thread, ctypes.byref(info)) else None
        return {'window_bounds': {'x': rect.left, 'y': rect.top, 'width': rect.right-rect.left, 'height': rect.bottom-rect.top},
                'monitors': monitors(), 'focus_hwnd': focused, 'foreground_window_id': int(user.GetForegroundWindow() or 0),
                'minimized': bool(user.IsIconic(wintypes.HWND(window_id)))}


def process_started(pid):
    _, kernel = _windows_api()
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)]*4]
    handle = kernel.OpenProcess(0x1000, False, _positive_int(pid, 'pid'))
    if not handle:
        raise ValueError('No se pudo verificar la instancia del proceso.')
    try:
        created, ended, cpu_kernel, cpu_user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(ended), ctypes.byref(cpu_kernel), ctypes.byref(cpu_user)):
            raise ValueError('No se pudo verificar el inicio del proceso.')
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


def get_observation(observation_id, window_id, expected_pid, *, max_age=OBSERVATION_MAX_AGE):
    """Resolve a backend-issued reference, never a client-asserted timestamp."""
    if not isinstance(observation_id, str) or not 0 < max_age <= OBSERVATION_MAX_AGE:
        raise ValueError('Referencia de observación inválida.')
    with _observation_lock:
        result = copy.deepcopy(_observations.get(observation_id))
    if not result:
        raise ValueError('STALE_OBSERVATION: vuelve a observar la ventana.')
    observed = result['observation']
    age = time.monotonic() - observed['completed_monotonic']
    if (observed['session_id'] != OBSERVATION_SESSION_ID or not 0 <= age <= max_age
            or observed['window_id'] != window_id or observed['pid'] != expected_pid):
        raise ValueError('STALE_OBSERVATION: cambió la sesión, el objetivo o la observación venció.')
    return result


def validate_control_state(window_id, expected_pid, control_id, observation_id, pattern, value):
    """Validate before taking focus, then revalidate again immediately before dispatch."""
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    if pattern == 'Value':
        valid = isinstance(value, str) and len(value) <= MAX_UITEXT and '\x00' not in value
        if valid:
            value.encode('utf-16-le')
    elif pattern in ('Toggle', 'SelectionItem'):
        valid = type(value) is bool
    elif pattern == 'ExpandCollapse':
        valid = value in ('expanded', 'collapsed')
    elif pattern == 'RangeValue':
        valid = type(value) in (int, float) and math.isfinite(value)
    elif pattern == 'Scroll':
        valid = (isinstance(value, dict) and set(value) == {'horizontal', 'vertical'}
                 and all(type(v) in (int, float) and math.isfinite(v) and (v == -1 or 0 <= v <= 100) for v in value.values()))
    else:
        valid = False
    if not valid:
        raise ValueError('Patrón o estado UIA no compatible.')
    observed = get_observation(observation_id, window_id, expected_pid)
    matches = [c for c in observed.get('controls', []) if c.get('control_id') == control_id]
    if observed.get('truncated') or len(matches) != 1:
        raise ValueError('La observación está incompleta o el control no es único.')
    control = matches[0]
    if pattern not in control.get('patterns', []) or not control.get('enabled') or control.get('offscreen'):
        raise ValueError('El control observado no admite esta acción.')
    observation = observed['observation']
    if observation.get('minimized') or not observation.get('process_started') or not observation.get('window_bounds'):
        raise ValueError('La observación no acredita identidad y geometría del proceso.')
    return {'operation': 'set_state', 'window_id': window_id, 'pid': expected_pid,
                 'control_id': control_id, 'pattern': pattern, 'state': value,
                 'expected_title': observed['window_title'], 'expected_name': control.get('name', ''),
                 'expected_process_started': observation['process_started'],
                 '_observation_deadline': observation['completed_monotonic'] + OBSERVATION_MAX_AGE,
            'expected_bounds': observation['window_bounds']}


def set_control_state(window_id, expected_pid, control_id, observation_id, pattern, value, cancelled=None):
    """Set an observed UIA state and require native readback of that state."""
    return _uia(validate_control_state(window_id, expected_pid, control_id, observation_id, pattern, value), cancelled=cancelled)


def read_control_grid(window_id, expected_pid, control_id, observation_id, row=0, column=0, rows=10, columns=10, cancelled=None):
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    if (any(type(v) is not int or v < 0 for v in (row, column))
            or any(type(v) is not int or not 1 <= v <= 20 for v in (rows, columns)) or rows*columns > 200):
        raise ValueError('Lectura de tabla fuera de límites: máximo 20 por eje y 200 celdas.')
    observed = get_observation(observation_id, window_id, expected_pid)
    matches = [c for c in observed.get('controls', []) if c.get('control_id') == control_id]
    if observed.get('truncated') or len(matches) != 1 or 'Grid' not in matches[0].get('patterns', []):
        raise ValueError('No se observó una tabla única con GridPattern.')
    identity = observed['observation']
    if not identity.get('process_started') or not identity.get('window_bounds'):
        raise ValueError('La observación no acredita identidad y geometría del proceso.')
    return _uia({'operation': 'read_grid', 'window_id': window_id, 'pid': expected_pid, 'control_id': control_id,
                 'row': row, 'column': column, 'rows': rows, 'columns': columns,
                 'expected_title': observed['window_title'], 'expected_name': matches[0].get('name', ''),
                 '_observation_deadline': identity['completed_monotonic'] + OBSERVATION_MAX_AGE,
                 'expected_process_started': identity['process_started'], 'expected_bounds': identity['window_bounds']}, cancelled=cancelled)


class UncertainEffect(ValueError):
    """A dispatched write has no confirmed postcondition; never retry automatically."""


def process_name(pid):
    _, kernel = _windows_api()
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle: return ''
    try:
        name = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(name))
        return Path(name.value).name.lower() if kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)) else ''
    finally:
        kernel.CloseHandle(handle)


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


def close_window(window_id, expected_pid, cancelled=None):
    """Ask one observed window to close; never terminate its process."""
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    user, _ = _windows_api()
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.PostMessageW.restype = wintypes.BOOL
    current = next((row for row in list_windows() if row['window_id'] == window_id and row['pid'] == expected_pid), None)
    if not current:
        raise ValueError('La ventana observada ya no existe o cambió de proceso.')
    if expected_pid == os.getpid() or process_name(expected_pid) in {'explorer.exe', 'axx.exe', 'axx-backend.exe'}:
        raise ValueError('Esta ventana no se cierra mediante el comando general.')
    if cancelled is not None and cancelled.is_set():
        raise ValueError('Cierre cancelado antes de solicitarlo.')
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(wintypes.HWND(window_id), ctypes.byref(pid))
    if not user.IsWindow(wintypes.HWND(window_id)) or pid.value != expected_pid:
        raise ValueError('La ventana cambió antes de solicitar el cierre.')
    if not user.PostMessageW(wintypes.HWND(window_id), 0x0010, 0, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not any(row['window_id'] == window_id and row['pid'] == expected_pid for row in list_windows()):
            return {'closed': True, 'window_id': window_id, 'pid': expected_pid}
        time.sleep(0.1)
    return {'closed': False, 'window_id': window_id, 'pid': expected_pid}


def observe_foreground(expected_title=None, timeout=5.0, before=None, aliases=(), cancelled=None, control=None, expected_process=None):
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
        if expected_process:
            candidates = [row for row in windows if process_name(row['pid']) == expected_process]
            fresh = [row for row in candidates if row['window_id'] not in before_ids]
            selected = fresh if fresh else candidates
            active = [row for row in selected if row['foreground']]
            target = active[0] if len(active) == 1 else selected[0] if len(selected) == 1 else None
            if target:
                if not target['foreground'] and control is not None:
                    focus_window(target['window_id'], target['pid'], control)
                current = next((row for row in list_windows() if row['window_id'] == target['window_id'] and row['pid'] == target['pid']), None)
                ready = bool(current and current['foreground'])
                return {'launch_requested': True, 'window_observed': True, 'foreground_verified': ready,
                        'ready_for_action': ready, 'window': current, 'verification': 'process_window_readback' if ready else 'launch_handoff_only'}
        matching = [] if expected_process else [row for row in windows if any(expected in _normalize(row['title']) for expected in expected_values)]
        fresh = [row for row in matching if row['window_id'] not in before_ids]
        selected = fresh if fresh else matching
        active = [row for row in selected if row['foreground']]
        latest = active[0] if len(active) == 1 else selected[0] if len(selected) == 1 else None
        if latest:
            if not latest['foreground'] and control is not None:
                try:
                    focus_window(latest['window_id'], latest['pid'], control)
                except ValueError:
                    if cancelled is not None and cancelled.is_set():
                        raise
                latest = next((row for row in list_windows() if row['window_id'] == latest['window_id'] and row['pid'] == latest['pid']), None)
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
    window_observed = bool(latest and title_matches)
    foreground_verified = bool(latest and latest.get('foreground') and title_matches)
    ready = foreground_verified
    return {'launch_requested': True, 'window_observed': window_observed,
            'foreground_verified': foreground_verified, 'ready_for_action': ready,
            'window': latest, 'verification': 'foreground_window_observation' if ready else 'visible_window_observation' if window_observed else 'launch_handoff_only'}


def focus_window(window_id, expected_pid, control=None):
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    user, kernel = _windows_api()
    hwnd = wintypes.HWND(window_id)
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not user.IsWindow(hwnd) or pid.value != expected_pid:
        raise ValueError('La ventana observada ya no existe o cambió de proceso.')
    if control is None:
        if not user.SetForegroundWindow(hwnd):
            raise ValueError('Windows no concedió el foco; se requiere el dueño de entrada de Axx.')
    else:
        control.focus(window_id, expected_pid)
    deadline = time.monotonic() + 1.0
    while int(user.GetForegroundWindow() or 0) != window_id:
        if control is not None and control.is_set(): raise ValueError('Foco cancelado por entrada local.')
        if time.monotonic() >= deadline: raise ValueError('No se confirmó el foco de la ventana solicitada.')
        time.sleep(.02)
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value != expected_pid or (control is not None and control.is_set()):
        raise ValueError('La identidad o el control cambió durante el enfoque.')
    return {'window_id': window_id, 'pid': expected_pid, 'foreground_verified': True,
            'verification': 'foreground_window_readback'}


def inspect_controls(window_id, expected_pid, cancelled=None):
    return _uia({'operation': 'inspect', 'window_id': _positive_int(window_id, 'window_id'),
                 'pid': _positive_int(expected_pid, 'pid')}, cancelled=cancelled)


def inspect_browser_controls(window_id, expected_pid, cancelled=None):
    return _uia({'operation': 'inspect_browser', 'window_id': _positive_int(window_id, 'window_id'),
                 'pid': _positive_int(expected_pid, 'pid')}, cancelled=cancelled)


def find_control(window_id, expected_pid, name, cancelled=None):
    """Resolve an exact semantic button label; abstain on incomplete/ambiguous trees."""
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('Indica el nombre exacto del botón (máximo 200 caracteres).')
    observed = inspect_controls(window_id, expected_pid, cancelled)
    candidates = [row for row in observed.get('controls', [])
                  if row.get('control_type') == 'ControlType.Button'
                  and row.get('enabled') and not row.get('offscreen')
                  and row.get('supports_invoke_pattern') is True
                  and _normalize(row.get('name', '')).strip() == _normalize(name).strip()]
    status = ('ambiguous' if observed.get('truncated') or len(candidates) > 1
              else 'selected' if len(candidates) == 1 else 'not_found')
    return {'selection_status': status, 'candidate': candidates[0] if status == 'selected' else None,
            'candidate_count': len(candidates), 'observation': observed.get('observation'),
            'window_title': observed.get('window_title'), 'truncated': bool(observed.get('truncated')),
            'reason': 'incomplete_observation' if observed.get('truncated') else status,
            'verification': 'semantic_control_selection', 'effect_executed': False}


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


def scrape_window_tree(window_id, expected_pid, cancelled=None):
    return _uia({'operation': 'scrape_app', 'window_id': _positive_int(window_id, 'window_id'),
                 'pid': _positive_int(expected_pid, 'pid')}, cancelled=cancelled)


def locate_edit_controls(window_id, expected_pid, cancelled=None):
    return _uia({'operation': 'locate_edit', 'window_id': _positive_int(window_id, 'window_id'),
                 'pid': _positive_int(expected_pid, 'pid')}, cancelled=cancelled)


def set_control_value(window_id, expected_pid, control_id, value, cancelled=None, expected_title=None):
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    if not isinstance(control_id, str) or len(control_id) != 64 or any(c not in '0123456789abcdef' for c in control_id):
        raise ValueError('control_id observado inválido')
    if not isinstance(value, str) or len(value) > MAX_UITEXT or '\x00' in value:
        raise ValueError('El texto debe ser válido y no exceder 8.192 caracteres.')
    value.encode('utf-16-le')
    return _uia({'operation': 'set_value', 'window_id': window_id, 'pid': expected_pid,
                 'control_id': control_id, 'value': value, 'expected_title': expected_title}, cancelled=cancelled)


def read_control_value(window_id, expected_pid, control_id, observation_id, cancelled=None):
    """Read one visible ValuePattern control bound to a fresh backend observation."""
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    if not isinstance(control_id, str) or not re.fullmatch(r'[a-f0-9]{64}', control_id):
        raise ValueError('control_id observado inválido')
    observed = get_observation(observation_id, window_id, expected_pid)
    controls = [row for row in observed.get('controls', []) if row.get('control_id') == control_id]
    if (observed.get('truncated') or len(controls) != 1 or not controls[0].get('supports_value_pattern')
            or not controls[0].get('enabled') or controls[0].get('offscreen')):
        raise ValueError('El control de valor no es único, visible o compatible en la observación.')
    identity, control = observed['observation'], controls[0]
    result = _uia({'operation': 'read_value', 'window_id': _positive_int(window_id, 'window_id'),
        'pid': _positive_int(expected_pid, 'pid'), 'control_id': control_id,
        'expected_title': observed['window_title'], 'expected_name': control['name'],
        'expected_process_started': identity['process_started'], 'expected_bounds': identity['window_bounds'],
        '_observation_deadline': identity['completed_monotonic'] + OBSERVATION_MAX_AGE}, cancelled=cancelled)
    if (result.get('verification') != 'uia_control_value_observed' or result.get('control_id') != control_id
            or result.get('window_id') != window_id or result.get('pid') != expected_pid
            or result.get('process_started') != identity['process_started']
            or not isinstance(result.get('value'), str) or len(result['value'].encode('utf-16-le')) > 4096):
        raise ValueError('La lectura del control no coincide con su identidad o excede el límite.')
    return result


def invoke_control(window_id, expected_pid, control_id, expected_title, expected_name, cancelled=None):
    window_id = _positive_int(window_id, 'window_id')
    expected_pid = _positive_int(expected_pid, 'pid')
    if not isinstance(control_id, str) or len(control_id) != 64 or any(c not in '0123456789abcdef' for c in control_id):
        raise ValueError('control_id observado inválido')
    if not all(isinstance(value, str) and 1 <= len(value) <= 2048 for value in (expected_title, expected_name)):
        raise ValueError('La ventana y el botón observados son obligatorios')
    return _uia({'operation': 'invoke', 'window_id': window_id, 'pid': expected_pid,
                 'control_id': control_id, 'expected_title': expected_title, 'expected_name': expected_name}, cancelled=cancelled)


def _uia(payload, cancelled=None, timeout=None):
    if os.name != 'nt':
        raise ValueError('UI Automation requiere Windows.')
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = Path(__file__).with_name('uia_worker.ps1')
    if not executable.is_file() or not script.is_file():
        raise ValueError('El worker UI Automation no está disponible en este runtime.')
    payload = dict(payload)
    if payload['operation'] in ('set_state', 'read_grid', 'read_value'):
        remaining_ms = int((payload.pop('_observation_deadline', 0) - time.monotonic()) * 1000)
        if not 0 < remaining_ms <= OBSERVATION_MAX_AGE * 1000:
            raise ValueError('STALE_OBSERVATION: la observación caducó antes del worker.')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetTickCount64.restype = ctypes.c_ulonglong
        payload['expected_tick_deadline'] = kernel.GetTickCount64() + remaining_ms
    request = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    if cancelled is not None and cancelled.is_set(): raise ValueError('UI Automation cancelada antes del despacho.')
    def write_error(message):
        error = UncertainEffect(message)
        error.target = {key: payload[key] for key in ('window_id', 'pid', 'control_id', 'expected_title') if key in payload}
        return error
    error_type = write_error if payload['operation'] in ('set_value', 'invoke', 'set_state') else ValueError
    # Windows PowerShell execution policy applies to script files. Pass the
    # fixed, packaged worker as a command payload instead of changing policy.
    # Keep the Windows command line below 32K regardless of worker size/CRLF.
    # This loader is constant; the bundled path is an environment value, and
    # application arguments remain JSON on stdin, never script source.
    loader = "& ([scriptblock]::Create([IO.File]::ReadAllText($env:AXX_UIA_WORKER, [Text.Encoding]::UTF8)))"
    encoded_worker = base64.b64encode(loader.encode('utf-16-le')).decode('ascii')
    runtime_names = {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA', 'PSMODULEPATH'}
    env = {key: value for key, value in os.environ.items() if key.upper() in runtime_names}
    env['AXX_UIA_WORKER'] = str(script.resolve())
    started_at = time.time()
    started_monotonic = time.monotonic()
    observing = payload['operation'] in ('inspect', 'inspect_browser', 'read_content', 'scrape_app', 'locate_edit')
    geometry = observe_geometry(payload['window_id']) if observing else None
    try:
        process = subprocess.Popen([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-MTA',
                                    '-EncodedCommand', encoded_worker],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=env)
        timeout_sec = timeout or (15.0 if payload.get('operation') in ('inspect', 'scrape_app', 'read_content') else UIA_TIMEOUT_SECONDS)
        deadline = time.monotonic() + timeout_sec
        input_bytes = request.encode('utf-8')
        first_communicate = True
        while True:
            if cancelled is not None and cancelled.is_set():
                process.kill()
                process.communicate()
                raise error_type('UI Automation cancelada; comprueba el estado del control antes de reintentar.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.communicate()
                raise error_type('UI Automation excedió el límite; verifica la ventana antes de reintentar.')
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
        if 'process' in locals():
            process.kill()
            process.communicate()
            raise error_type('Se perdió el canal del worker; comprueba el efecto antes de reintentar.') from exc
        raise ValueError('No se pudo iniciar el worker de UI Automation.') from exc
    if len(result.stdout.encode('utf-8', errors='replace')) > 512 * 1024:
        raise error_type('La respuesta de UI Automation excede el límite.')
    if result.returncode:
        message = result.stderr.strip()[:1000] or 'UI Automation rechazó la operación.'
        try:
            rejected = json.loads(result.stdout)
        except (ValueError, TypeError):
            rejected = None
        if isinstance(rejected, dict) and rejected.get('success') is False and rejected.get('effect_started') is False:
            raise ValueError(str(rejected.get('error', message))[:1000])
        raise error_type(message)
    try:
        response = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise error_type('UI Automation devolvió una respuesta inválida.') from exc
    if not isinstance(response, dict) or response.get('success') is not True:
        raise error_type(str(response.get('error', 'UI Automation no confirmó el resultado.'))[:1000])
    if observing:
        after = observe_geometry(payload['window_id'])
        if any(after[k] != geometry[k] for k in ('window_bounds', 'monitors', 'minimized')):
            raise ValueError('STALE_OBSERVATION: la ventana o los monitores cambiaron durante la observación.')
        response['observation'] = {'schema_version': 1, 'observation_id': str(uuid.uuid4()),
                                   'context_id': 'host', 'session_id': OBSERVATION_SESSION_ID,
                                   'window_id': payload['window_id'], 'pid': payload['pid'],
                                   'process_started': response.get('process_started'),
                                   'process_time_format': 'windows_filetime_100ns',
                                   'started_at': started_at, 'completed_at': time.time(),
                                   'completed_monotonic': time.monotonic(),
                                   **after,
                                   'coordinate_epoch': hashlib.sha256(json.dumps([after['window_bounds'], after['monitors']], sort_keys=True).encode()).hexdigest(),
                                   'duration_ms': round((time.monotonic() - started_monotonic) * 1000, 2),
                                   'coordinate_system': 'physical_virtual_desktop_pixels',
                                   'source': 'windows_uia', 'screenshot': None,
                                   'screenshot_unavailable_reason': 'Esta ruta observa accesibilidad, no captura imagen.'}
        _remember_observation(response)
    return response


def _normalize(value):
    import unicodedata
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(value).casefold())
                   if not unicodedata.combining(ch))
