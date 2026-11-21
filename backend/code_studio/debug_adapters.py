"""Supervised Debug Adapter Protocol (DAP) Manager with Loopback Confinement & Evaluate Guard (PR-18 / CODE-04).

Enforces Invariants:
- CODE-04 / SEC-01: Debug adapters bind exclusively to 127.0.0.1 (loopback); external bindings
  (0.0.0.0 or non-loopback IPs) are rejected.
- Autonomous agents cannot run arbitrary mutating or side-effecting 'evaluate' expressions inside
  a paused debug frame unless explicitly approved by the user.
"""
from __future__ import annotations

import re
from typing import Any

from backend.code_studio.projects import CodeProjectService

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
            'state': 'paused',
            'breakpoints': [],
            'locals': {'counter': 3, 'status': 'ok'},
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

        value = session['locals'].get(expr, f'<evaluated:{expr}>')
        return {
            'session_id': session_id,
            'expression': expr,
            'result': value,
            'actor': actor,
        }
