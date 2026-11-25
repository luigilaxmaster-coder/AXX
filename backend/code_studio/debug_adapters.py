"""Supervised Debug Adapter Protocol (DAP) Manager with Loopback Confinement & Evaluate Guard (PR-18 / CODE-04).

Enforces Invariants:
- CODE-04 / SEC-01: Debug adapters bind exclusively to 127.0.0.1 (loopback); external bindings
  (0.0.0.0 or non-loopback IPs) are rejected.
- Autonomous agents cannot run arbitrary mutating or side-effecting 'evaluate' expressions inside
  a paused debug frame unless explicitly approved by the user.
"""
from __future__ import annotations

import re
import hashlib
import shutil
import sys
from pathlib import Path
import threading
from typing import Any

from backend.code_studio.projects import CodeProjectService, resolve_scoped_project_path, ID_RE, CodeConflictError
from backend.code_studio.dap_process import DapProcess

ALLOWED_DAP_ADAPTERS = frozenset({'debugpy', 'node-inspect', 'codelldb'})
LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})
SAFE_IDENTIFIER_EXPR_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\[\]\'\" ]{0,120}$')
DANGEROUS_EVAL_PATTERNS = (
    re.compile(r'(__import__|eval\s*\(|exec\s*\(|compile\s*\(|open\s*\()', re.IGNORECASE),
    re.compile(r'(os\.system|subprocess|shutil\.rmtree|unlink|remove|popen|socket)', re.IGNORECASE),
    re.compile(r'(process\.exit|child_process|fs\.unlink|fs\.write)', re.IGNORECASE),
)


class DebugSecurityError(PermissionError):
    """Raised when a DAP session violates loopback binding or attempts an unauthorized evaluate expression (CODE-04)."""


class DebugAdapterManager:
    """Manages local loopback DAP sessions and guards frame expression evaluation (CODE-04)."""

    def __init__(self, project_service: CodeProjectService):
        self.projects = project_service
        self.sessions: dict[str, dict[str, Any]] = {}
        self.processes: dict[str, DapProcess] = {}
        self.lock = threading.RLock()

    def launch_python(self, *, session_id: str, project_id: str, path: str, line: int,
                      expected_sha256: str, user_approved: bool = False) -> dict[str, Any]:
        if user_approved is not True:
            raise DebugSecurityError('Launching a program in the debugger requires explicit owner approval')
        if not isinstance(session_id, str) or not ID_RE.fullmatch(session_id) or type(line) is not int or line < 1:
            raise ValueError('Invalid debug session ID or breakpoint line')
        root = self.projects.get_project_root(project_id)
        program = resolve_scoped_project_path(root, path)
        if program.suffix.lower() != '.py' or not program.is_file():
            raise ValueError('The Python debugger requires a scoped .py file')
        if hashlib.sha256(program.read_bytes()).hexdigest() != expected_sha256:
            raise CodeConflictError('The program changed since approval; reload it before debugging')
        from backend.code_studio.toolchain import installed_python
        python = installed_python('debugpy')
        if not python:
            raise RuntimeError('UNAVAILABLE: Python/debugpy is not installed on this machine')
        with self.lock:
            if session_id in self.sessions or len(self.processes) >= 2:
                raise DebugSecurityError('Debug session already exists or concurrency limit reached')
            proc = DapProcess(python, root)
            self.processes[session_id] = proc
            self.sessions[session_id] = {'session_id': session_id, 'project_id': project_id,
                'path': path, 'adapter': 'debugpy', 'state': 'starting', 'transport': 'stdio', 'port': None}
        try:
            proc.request('initialize', {'clientID': 'axx', 'adapterID': 'python', 'pathFormat': 'path',
                'linesStartAt1': True, 'columnsStartAt1': True, 'supportsRunInTerminalRequest': False})
            launching = proc.send('launch', {'name': 'AXX Code Studio', 'type': 'python', 'request': 'launch',
                'program': str(program), 'cwd': str(root), 'console': 'internalConsole',
                'justMyCode': True, 'stopOnEntry': False, 'subProcess': False, 'python': [python]})
            if proc.event(['initialized']) is None:
                raise TimeoutError('DAP initialize event was not received')
            points = proc.request('setBreakpoints', {'source': {'path': str(program)}, 'breakpoints': [{'line': line}]})
            proc.request('configurationDone', {})
            proc.response(launching)
            self.sessions[session_id]['breakpoints'] = points.get('breakpoints', [])
            return self.inspect(session_id, wait=True)
        except Exception:
            self.stop(session_id)
            raise

    def inspect(self, session_id: str, *, wait: bool = False) -> dict[str, Any]:
        with self.lock:
            session, proc = self.sessions[session_id], self.processes.get(session_id)
        if proc is None:
            return dict(session)
        event = proc.event(['stopped', 'terminated', 'exited'], timeout=15 if wait else .1)
        if event and event['event'] == 'stopped':
            session['state'], session['thread_id'] = 'stopped', event['body'].get('threadId')
        elif event:
            session['state'] = 'terminated'
        elif session['state'] == 'starting':
            session['state'] = 'running'
        if session['state'] == 'stopped':
            frames = proc.request('stackTrace', {'threadId': session['thread_id'], 'levels': 10}).get('stackFrames', [])
            # Only expose frames in the authorized project, with no adapter-internal file access.
            root = self.projects.get_project_root(session['project_id'])
            scoped = []
            for frame in frames:
                raw = (frame.get('source') or {}).get('path')
                if raw and Path(raw).is_relative_to(root):
                    frame = dict(frame, source={'path': Path(raw).relative_to(root).as_posix()})
                    scoped.append(frame)
            session['stack_frames'] = scoped
            session['locals'] = {}
            if scoped:
                scopes = proc.request('scopes', {'frameId': scoped[0]['id']}).get('scopes', [])
                for scope in scopes:
                    if scope.get('name', '').lower() in ('locals', 'local'):
                        variables = proc.request('variables', {'variablesReference': scope['variablesReference']}).get('variables', [])
                        session['locals'] = {v['name']: str(v.get('value', ''))[:500] for v in variables[:100]}
        return dict(session)

    def resume(self, session_id: str, *, step: bool = False) -> dict[str, Any]:
        session, proc = self.sessions[session_id], self.processes[session_id]
        if session['state'] != 'stopped':
            raise ValueError('The debuggee is not paused')
        proc.request('next' if step else 'continue', {'threadId': session['thread_id']})
        session['state'] = 'running'
        session['locals'], session['stack_frames'] = {}, []
        return self.inspect(session_id, wait=True)

    def stop(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            proc = self.processes.pop(session_id, None)
            session = self.sessions.get(session_id)
        if proc is not None:
            proc.close()
        if session is not None:
            session['state'] = 'terminated'
        return dict(session or {'session_id': session_id, 'state': 'terminated'})

    def close(self):
        for session_id in list(self.processes):
            self.stop(session_id)

    def probe_available_adapters(self) -> dict[str, Any]:
        """Discover allowlisted loopback DAP adapters installed on host; declares UNAVAILABLE when missing."""
        import shutil
        from backend.code_studio.toolchain import installed_python
        adapters: dict[str, Any] = {
            'debugpy': {
                'adapter': 'debugpy',
                'installed': installed_python('debugpy') is not None,
                'loopback_only': True,
            },
            'node-inspect': {
                'adapter': 'node-inspect',
                'installed': shutil.which('node') is not None,
                'loopback_only': True,
            },
            'codelldb': {
                'adapter': 'codelldb',
                'installed': shutil.which('codelldb') is not None,
                'loopback_only': True,
            },
        }
        for v in adapters.values():
            v['status'] = 'detected' if v['installed'] and v['adapter'] == 'debugpy' else 'UNAVAILABLE'
            v['connected'] = False
            v['reason'] = 'Launch and handshake required' if v['status'] == 'detected' else 'No supported DAP process connected'
        return {'adapters': adapters}

    def create_debug_session(
        self,
        *,
        session_id: str,
        project_id: str,
        adapter: str,
        host: str = '127.0.0.1',
        port: int = 5678,
    ) -> dict[str, Any]:
        if adapter not in ALLOWED_DAP_ADAPTERS:
            raise DebugSecurityError(f'Debug adapter {adapter!r} is not in allowlist: {sorted(ALLOWED_DAP_ADAPTERS)}')
        if host.strip().lower() not in LOOPBACK_HOSTS:
            raise DebugSecurityError(f'DAP session must bind to loopback (127.0.0.1), rejected host: {host!r}')
        if not (1024 <= int(port) <= 65535):
            raise ValueError('DAP port must be between 1024 and 65535')

        root = self.projects.get_project_root(project_id)
        session = {
            'session_id': session_id,
            'project_id': project_id,
            'project_root': str(root),
            'adapter': adapter,
            'host': '127.0.0.1',
            'port': int(port),
            'state': 'unavailable',
            'breakpoints': [],
            'locals': {},
        }
        self.sessions[session_id] = session
        return dict(session)

    def evaluate_expression(
        self,
        *,
        session_id: str,
        expression: str,
        actor: str = 'agent',
        user_approved: bool = False,
    ) -> dict[str, Any]:
        """Evaluate an expression in a paused frame, blocking dangerous or mutating agent expressions (CODE-04)."""
        if session_id not in self.sessions:
            raise LookupError(f'DAP session not found: {session_id}')
        session = self.sessions[session_id]
        expr = expression.strip()

        for pat in DANGEROUS_EVAL_PATTERNS:
            if pat.search(expr):
                if not user_approved:
                    raise DebugSecurityError(
                        f'Blocked dangerous DAP evaluate expression from {actor!r} without explicit user approval: {expr!r}'
                    )

        if actor != 'user' and not user_approved and not SAFE_IDENTIFIER_EXPR_RE.fullmatch(expr):
            raise DebugSecurityError(
                f'Autonomous agent DAP evaluate is restricted to read-only variable inspection; rejected: {expr!r}'
            )

        return {
            'session_id': session_id,
            'expression': expr,
            'result': None,
            'status': 'unsupported_mode',
            'reason': 'No debug adapter process is connected; no expression was evaluated',
            'actor': actor,
        }
