"""Supervised Toolchain and Test Runner producing Verifiable TestReceipts (PR-14 / CODE-03 / ORCH-04).

Enforces Invariants:
- I-02 / I-08: Only allowlisted test/lint executables can run without shell=True.
- ORCH-04: Generates cryptographic TestReceipt (stdout_hash, stderr_hash, exit_code) consumed by
  IndependentVerifierService and SuperpowersWorkflowService.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from backend.code_studio.projects import CodeProjectService

ALLOWED_EXECUTABLES = frozenset({
    'python',
    'python.exe',
    sys.executable.lower(),
    Path(sys.executable).name.lower(),
    'pytest',
    'pytest.exe',
    'node',
    'node.exe',
    'npm',
    'npm.cmd',
    'cargo',
    'cargo.exe',
    'git',
    'git.exe',
})


class UnauthorizedToolchainError(PermissionError):
    """Raised when a test command attempts to invoke a non-allowlisted executable or shell syntax."""


class SupervisedTestRunner:
    """Runs allowlisted test suites inside a project or worktree and persists verifiable TestReceipts."""

    def __init__(self, project_service: CodeProjectService):
        self.projects = project_service
        self._init_schema()

    def _init_schema(self) -> None:
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS code_test_receipts (
                        report_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES code_projects(project_id) ON DELETE CASCADE,
                        workspace_id TEXT NOT NULL,
                        command_json TEXT NOT NULL,
                        exit_code INTEGER NOT NULL,
                        stdout_hash TEXT NOT NULL,
                        stderr_hash TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        stdout_preview TEXT NOT NULL,
                        stderr_preview TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    );
                    '''
                )

    def run_test_command(
        self,
        *,
        report_id: str,
        project_id: str,
        workspace_id: str,
        command: list[str],
        cwd: Path | None = None,
        timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise UnauthorizedToolchainError('command must be a non-empty list of strings')

        exe = command[0]
        exe_base = Path(exe).name.lower()
        if exe.lower() not in ALLOWED_EXECUTABLES and exe_base not in ALLOWED_EXECUTABLES:
            raise UnauthorizedToolchainError(f'Executable not in supervised toolchain allowlist: {exe!r}')

        # Block inline code execution flags like python -c or node -e in test runner
        if exe_base in ('python', 'python.exe') and '-c' in command[1:]:
            raise UnauthorizedToolchainError("Inline 'python -c' execution is prohibited in SupervisedTestRunner")
        if exe_base in ('node', 'node.exe') and ('-e' in command[1:] or '--eval' in command[1:]):
            raise UnauthorizedToolchainError("Inline 'node -e' execution is prohibited in SupervisedTestRunner")

        target_cwd = Path(cwd).resolve() if cwd else self.projects.get_project_root(project_id)
        project_root = self.projects.get_project_root(project_id)
        allowed_worktree = False
        with self.projects.lock, self.projects._connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='code_worktrees'").fetchone():
                allowed_worktree = any(Path(row[0]).resolve() == target_cwd for row in db.execute(
                    "SELECT worktree_path FROM code_worktrees WHERE project_id=? AND status='active'", (project_id,)))
        if not (target_cwd == project_root or target_cwd.is_relative_to(project_root) or allowed_worktree):
            raise UnauthorizedToolchainError(f'Test working directory {target_cwd} is outside authorized boundaries')

        # Sanitize environment variables so secrets are not leaked to test subprocesses
        safe_env = {
            k: v
            for k, v in os.environ.items()
            if not any(secret_tok in k.upper() for secret_tok in ('API_KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'DPAPI'))
        }

        t0 = time.perf_counter()
        proc = subprocess.run(
            command,
            cwd=str(target_cwd),
            env=safe_env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_sec,
            shell=False,
            check=False,
        )
        duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
        stdout_hash = hashlib.sha256(proc.stdout.encode('utf-8')).hexdigest()
        stderr_hash = hashlib.sha256(proc.stderr.encode('utf-8')).hexdigest()

        receipt = {
            'report_id': report_id,
            'project_id': project_id,
            'workspace_id': workspace_id,
            'command': list(command),
            'exit_code': int(proc.returncode),
            'stdout_hash': stdout_hash,
            'stderr_hash': stderr_hash,
            'duration_ms': duration_ms,
            'stdout_preview': proc.stdout[:4000],
            'stderr_preview': proc.stderr[:4000],
            'passed': proc.returncode == 0,
        }

        now = self.projects.clock()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO code_test_receipts
                        (report_id, project_id, workspace_id, command_json, exit_code, stdout_hash, stderr_hash,
                         duration_ms, stdout_preview, stderr_preview, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        report_id,
                        project_id,
                        workspace_id,
                        json.dumps(command),
                        receipt['exit_code'],
                        stdout_hash,
                        stderr_hash,
                        duration_ms,
                        receipt['stdout_preview'],
                        receipt['stderr_preview'],
                        now,
                    ),
                )
        return receipt

    def get_receipt(self, report_id: str) -> dict[str, Any]:
        with self.projects.lock, self.projects._connect() as db:
            row = db.execute(
                'SELECT * FROM code_test_receipts WHERE report_id=?',
                (report_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'TestReceipt not found: {report_id}')
            return {
                'report_id': row['report_id'],
                'project_id': row['project_id'],
                'workspace_id': row['workspace_id'],
                'command': json.loads(row['command_json']),
                'exit_code': int(row['exit_code']),
                'stdout_hash': row['stdout_hash'],
                'stderr_hash': row['stderr_hash'],
                'duration_ms': int(row['duration_ms']),
                'stdout_preview': row['stdout_preview'],
                'stderr_preview': row['stderr_preview'],
                'passed': int(row['exit_code']) == 0,
                'created_at_ms': int(row['created_at_ms']),
            }
