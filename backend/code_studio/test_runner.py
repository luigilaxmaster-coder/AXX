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
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any

from backend.code_studio.projects import CodeProjectService, CodeConflictError, resolve_scoped_project_path

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
                columns = {r[1] for r in db.execute('PRAGMA table_info(code_test_receipts)')}
                for name, definition in [('changeset_id', 'TEXT'), ('file_hashes_json', "TEXT NOT NULL DEFAULT '{}'"),
                                         ('workspace_unchanged', 'INTEGER NOT NULL DEFAULT 0'),
                                         ('execution_status', "TEXT NOT NULL DEFAULT 'legacy'"),
                                         ('cleanup_verified', 'INTEGER NOT NULL DEFAULT 0')]:
                    if name not in columns:
                        db.execute(f'ALTER TABLE code_test_receipts ADD COLUMN {name} {definition}')
                db.execute('CREATE TABLE IF NOT EXISTS code_test_dispatches '
                           '(report_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, status TEXT NOT NULL)')

    def run_test_command(
        self,
        *,
        report_id: str,
        project_id: str,
        workspace_id: str,
        command: list[str],
        cwd: Path | None = None,
        timeout_sec: float = 30.0,
        changeset_id: str | None = None,
        cancel_event=None,
    ) -> dict[str, Any]:
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise UnauthorizedToolchainError('command must be a non-empty list of strings')
        if not isinstance(report_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',report_id):
            raise ValueError('Invalid test report_id')
        if type(timeout_sec) not in (int,float) or not math.isfinite(timeout_sec) or not 1 <= timeout_sec <= 120:
            raise ValueError('Test deadline must be between 1 and 120 seconds')

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

        # Bind the receipt to the immutable change bytes, including legacy callers
        # which identify only their workspace. An edited worktree must be reviewed again.
        file_hashes = {}
        with self.projects.lock, self.projects._connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='code_changesets'").fetchone():
                row = (db.execute('SELECT changeset_id, changeset_json FROM code_changesets WHERE changeset_id=?',
                                  (changeset_id,)).fetchone() if changeset_id else
                       db.execute("SELECT changeset_id, changeset_json FROM code_changesets WHERE workspace_id=? "
                                  "AND status='applied' ORDER BY created_at_ms DESC LIMIT 1", (workspace_id,)).fetchone())
                if changeset_id and row is None:
                    raise CodeConflictError('Unknown changeset for test execution')
                if row is not None:
                    change = json.loads(row['changeset_json'])
                    if change['workspace_id'] != workspace_id or change['project_id'] != project_id:
                        raise CodeConflictError('Test changeset belongs to another workspace')
                    changeset_id = row['changeset_id']
                    file_hashes = {f['path']: f['proposed_sha256'] for f in change['files']}
        def unchanged():
            return all(hashlib.sha256(resolve_scoped_project_path(target_cwd, p).read_bytes()).hexdigest() == sha
                       for p, sha in file_hashes.items())
        if not unchanged():
            raise CodeConflictError('Worktree bytes differ from the proposed changeset before testing')

        fingerprint=hashlib.sha256(json.dumps([project_id,workspace_id,str(target_cwd),command,changeset_id,file_hashes,
                                               timeout_sec],sort_keys=True).encode()).hexdigest()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT * FROM code_test_dispatches WHERE report_id=?',(report_id,)).fetchone()
                if old:
                    if old['request_sha256']!=fingerprint or old['status']!='completed':
                        raise CodeConflictError('Test report already claimed; inspect its receipt before creating another run')
                    return self.get_receipt(report_id)
                if db.execute('SELECT 1 FROM code_test_receipts WHERE report_id=?',(report_id,)).fetchone():
                    raise CodeConflictError('A historical test receipt cannot be overwritten')
                db.execute('INSERT INTO code_test_dispatches VALUES (?, ?, ?)',(report_id,fingerprint,'running'))

        # Sanitize environment variables so secrets are not leaked to test subprocesses
        safe_env = {
            k: v
            for k, v in os.environ.items()
            if not any(secret_tok in k.upper() for secret_tok in ('API_KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'DPAPI'))
        }

        t0 = time.perf_counter()
        execution_status, cleanup_verified = 'exited', True
        if os.name == 'nt':
            from types import SimpleNamespace
            from backend.actions.process_runner import run_process
            executable = shutil.which(exe_base)
            if exe_base in ('python','python.exe',Path(sys.executable).name.lower()):
                from backend.code_studio.toolchain import installed_python
                executable=installed_python()
            if not executable or (Path(exe).is_absolute() and Path(exe).resolve()!=Path(executable).resolve()):
                raise UnauthorizedToolchainError('Select the installed supervised executable, not a project-supplied lookalike')
            args=command[1:]
            if exe_base in ('npm','npm.cmd'):
                npm_cli=Path(executable).parent/'node_modules/npm/bin/npm-cli.js'
                executable=shutil.which('node')
                if not executable or not npm_cli.is_file():
                    raise UnauthorizedToolchainError('Installed npm CLI could not be resolved without a batch shell')
                args=[str(npm_cli),*args]
            result=run_process({'executable':str(Path(executable).resolve()),'args':args,'cwd':str(target_cwd),
                                'timeout_s':math.ceil(timeout_sec)},target_cwd,cancelled=cancel_event)
            out=result.get('output') or {}
            execution_status=out.get('status','cancelled' if cancel_event is not None and cancel_event.is_set() else 'unknown')
            cleanup_verified=bool((result.get('evidence') or {}).get('cleanup_verified'))
            proc=SimpleNamespace(stdout=out.get('stdout',''),stderr=out.get('stderr',''),returncode=out.get('exit_code') if out.get('exit_code') is not None else -1)
        else:
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
        try:
            workspace_unchanged = unchanged()
        except (OSError, PermissionError):
            workspace_unchanged = False
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
            'passed': proc.returncode == 0 and workspace_unchanged and execution_status=='exited' and cleanup_verified,
            'execution_status':execution_status, 'cleanup_verified':cleanup_verified,
            'changeset_id': changeset_id, 'file_hashes': file_hashes, 'workspace_unchanged': workspace_unchanged,
        }

        now = self.projects.clock()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.execute(
                    '''
                    INSERT INTO code_test_receipts
                        (report_id, project_id, workspace_id, command_json, exit_code, stdout_hash, stderr_hash,
                         duration_ms, stdout_preview, stderr_preview, created_at_ms, changeset_id, file_hashes_json, workspace_unchanged,
                         execution_status, cleanup_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        changeset_id, json.dumps(file_hashes), int(workspace_unchanged),
                        execution_status,int(cleanup_verified),
                    ),
                )
                db.execute("UPDATE code_test_dispatches SET status='completed' WHERE report_id=?",(report_id,))
        return receipt

    def list_receipts(self, workspace_id: str, *, since_ms: int = 0) -> list[dict[str, Any]]:
        with self.projects.lock, self.projects._connect() as db:
            ids = [r[0] for r in db.execute('SELECT report_id FROM code_test_receipts WHERE workspace_id=? AND created_at_ms>=? '
                                            'ORDER BY created_at_ms', (workspace_id, since_ms))]
        return [self.get_receipt(report_id) for report_id in ids]

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
                'passed': int(row['exit_code']) == 0 and bool(row['workspace_unchanged']) and row['execution_status']=='exited' and bool(row['cleanup_verified']),
                'execution_status':row['execution_status'],'cleanup_verified':bool(row['cleanup_verified']),
                'changeset_id': row['changeset_id'], 'file_hashes': json.loads(row['file_hashes_json']),
                'workspace_unchanged': bool(row['workspace_unchanged']),
                'created_at_ms': int(row['created_at_ms']),
            }
