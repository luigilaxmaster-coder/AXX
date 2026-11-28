"""Read-only discovery and transports for sessions owned by the official clients.

No credentials, conversation database or action executor lives here. Codex keeps
its existing Connect lifecycle; Claude Code owns its own resumed conversation.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time


SESSION_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$')


def quota_window(value, *, minutes=None):
    if not isinstance(value, dict):
        return None
    used = value.get('usedPercent', value.get('used_percentage'))
    if type(used) not in (int, float) or not math.isfinite(used) or not 0 <= used <= 100:
        return None
    duration = value.get('windowDurationMins', minutes)
    reset = value.get('resetsAt', value.get('resets_at'))
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        duration = None
    if type(reset) not in (int, float) or not math.isfinite(reset) or reset <= 0:
        reset = None
    return {'used_percent': round(used, 2), 'remaining_percent': round(100-used, 2),
            'window_minutes': duration, 'resets_at': reset}


def codex_usage(result):
    buckets = result.get('rateLimitsByLimitId') or {}
    bucket = buckets.get('codex') or result.get('rateLimits') or {}
    windows = [w for w in (quota_window(bucket.get('primary')), quota_window(bucket.get('secondary'))) if w]
    return {'provider': 'codex', 'source': 'account/rateLimits/read', 'checked_at': time.time(),
            'available': bool(windows), 'windows': windows,
            'ordinary_usage_allowed': result.get('ordinaryUsageAllowed')}


def claude_usage(payload):
    rates = payload.get('rate_limits') or {}
    windows = [w for w in (quota_window(rates.get('five_hour'), minutes=300),
                           quota_window(rates.get('seven_day'), minutes=10080)) if w]
    info = payload.get('rate_limit_info') or {}
    # Some CLI versions emit only a warning and reset time, without utilization.
    # Those events never become a fabricated allowance percentage.
    return {'provider': 'claude', 'source': 'Claude Code rate_limit_event', 'checked_at': time.time(),
            'available': bool(windows), 'windows': windows,
            'status': info.get('status'), 'using_overage': info.get('isUsingOverage')}


def claude_executable():
    candidate = shutil.which('claude')
    if not candidate or Path(candidate).suffix.lower() != '.exe':
        return None
    return str(Path(candidate).resolve())


def claude_environment():
    # The official CLI reads its own subscription login. Never copy OAuth files
    # or silently route a resumed session to an inherited API key/cloud account.
    return {k: v for k, v in os.environ.items() if not re.search(r'TOKEN|API_KEY|SECRET|PASSWORD', k, re.I)
            and not k.upper().startswith(('ANTHROPIC_', 'CLAUDE_CODE_USE_', 'AWS_', 'GOOGLE_', 'AZURE_'))}


def claude_sessions(base=None, cursor=None, session_id=None):
    if cursor is not None and (not isinstance(cursor, str) or not cursor.isdecimal() or len(cursor) > 6):
        raise ValueError('Cursor de conversaciones inválido.')
    offset = int(cursor or 0)
    executable = claude_executable()
    if not executable:
        return {'provider': 'claude', 'available': False, 'sessions': [], 'reason': 'Claude Code CLI no está instalado.'}
    root = Path(base) if base else Path.home()/'.claude'/'projects'
    if not root.is_dir():
        return {'provider': 'claude', 'available': True, 'sessions': [], 'reason': 'No hay conversaciones locales de Claude Code.'}
    candidates = []
    for directory in list(root.iterdir())[:200]:
        if not directory.is_dir() or directory.is_symlink():
            continue
        for file in directory.glob('*.jsonl'):
            if session_id is not None and file.stem != session_id:
                continue
            if file.is_symlink() or not SESSION_ID.fullmatch(file.stem):
                continue
            try:
                candidates.append((file.stat().st_mtime, file))
            except OSError:
                pass
    sessions = []
    for modified, file in sorted(candidates, key=lambda pair: pair[0], reverse=True)[offset:offset+60]:
        cwd, title, session_id = None, None, file.stem
        try:
            with file.open('rb') as stream:
                sample = stream.read(128*1024)
                if stream.seek(0, 2) > 128*1024:
                    stream.seek(max(0, stream.tell()-32*1024))
                    sample += b'\n'+stream.read(32*1024)
            for line in sample.splitlines():
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(record, dict):
                    continue
                cwd = record.get('cwd') or cwd
                if record.get('type') in ('summary', 'custom-title'):
                    title = record.get('customTitle') or record.get('summary') or title
            if not isinstance(cwd, str) or not Path(cwd).is_dir():
                continue
            sessions.append({'id': session_id, 'provider': 'claude', 'project': str(Path(cwd).resolve()),
                             'title': str(title or 'Conversación de Claude Code')[:120],
                             'updated_at': modified, 'model': None, 'active': False})
        except OSError:
            continue
    return {'provider': 'claude', 'available': True, 'sessions': sessions,
            'has_more': len(candidates) > offset+60, 'next_cursor': str(offset+60) if len(candidates) > offset+60 else None,
            'scope': 'Claude Code local; los chats de Claude Desktop y la web tienen listas independientes.'}


def run_claude_session(target, message, cancel, deadline, emit, usage_update):
    """One CLI transport, bounded output, prompt on stdin, no shell or tool execution."""
    executable = claude_executable()
    if not executable:
        raise RuntimeError('Claude Code CLI no está disponible.')
    args = [executable, '--print', '--resume', target['session_id'], '--output-format', 'stream-json',
            '--verbose', '--include-partial-messages', '--tools', '', '--permission-mode', 'dontAsk',
            '--disable-slash-commands', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--setting-sources', '', '--settings', '{"disableAllHooks":true}']
    process = subprocess.Popen(args, cwd=target['cwd'], env=claude_environment(), shell=False,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines, errors = queue.Queue(maxsize=256), bytearray()
    def read_stdout():
        try:
            while True:
                line = process.stdout.readline(512*1024+1)
                if not line:
                    break
                if len(line) > 512*1024:
                    process.terminate(); break
                while not cancel.is_set():
                    try:
                        lines.put(line, timeout=.1); break
                    except queue.Full:
                        if process.poll() is not None:
                            return
        finally:
            try: lines.put(None, timeout=.5)
            except queue.Full: pass
    def read_stderr():
        while True:
            chunk = process.stderr.read(1024)
            if not chunk: return
            if len(errors) < 8192: errors.extend(chunk[:8192-len(errors)])
    threading.Thread(target=read_stdout, daemon=True, name='axx-claude-output').start()
    threading.Thread(target=read_stderr, daemon=True, name='axx-claude-errors').start()
    def write_prompt():
        try:
            process.stdin.write(message.encode('utf-8')); process.stdin.close()
        except OSError: pass
    threading.Thread(target=write_prompt, daemon=True, name='axx-claude-input').start()
    response, result = '', None
    try:
        while time.monotonic() < deadline and not cancel.is_set():
            try: line = lines.get(timeout=.1)
            except queue.Empty:
                if process.poll() is not None: break
                continue
            if line is None: break
            try: record = json.loads(line)
            except (ValueError, UnicodeError): continue
            if not isinstance(record, dict): continue
            if record.get('type') == 'rate_limit_event': usage_update(claude_usage(record))
            elif record.get('type') == 'stream_event':
                delta = record.get('event', {}).get('delta', {})
                if delta.get('type') == 'text_delta':
                    text = str(delta.get('text', ''))
                    if len(response)+len(text) > 512*1024: raise RuntimeError('Respuesta demasiado grande.')
                    response += text; emit(text)
            elif record.get('type') == 'result':
                if record.get('session_id') != target['session_id']:
                    raise RuntimeError('Claude devolvió otra sesión. No se repetirá el mensaje.')
                if record.get('is_error'):
                    raise RuntimeError('Claude no completó el mensaje. Revisa la sesión y sus límites antes de reenviar.')
                result = str(record.get('result', response))
                if len(result) > 512*1024: raise RuntimeError('Respuesta demasiado grande.')
        if cancel.is_set(): raise RuntimeError('Solicitud cancelada; no se repetirá automáticamente.')
        if time.monotonic() >= deadline: raise TimeoutError('Se agotó el plazo; comprueba la sesión antes de reenviar.')
        if result is None: raise RuntimeError('Claude no confirmó el resultado. Revisa autenticación y permisos de la CLI.')
        return result
    finally:
        if process.poll() is None:
            process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            try: stream.close()
            except OSError: pass
