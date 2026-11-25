"""Isolated Git Worktree Manager and Dirty-File Protection for Concurrent Coding Agents (PR-14 / CODE-02).

Enforces Invariants:
- CODE-02: Multiple coding agents operate in isolated git worktrees on dedicated branches
  ('axx/agent/<agent_id>/<task_id>'); they never modify the user's primary working copy directly.
- Never runs 'git reset --hard', 'git clean -fd', or 'git checkout --' on user workspaces.
- Integration into the primary workspace verifies that target files have no uncommitted user edits
  (dirty working tree protection) and matches the expected base_sha256.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess
from typing import Any

from backend.code_studio.patch_engine import CodePatchEngine
from backend.code_studio.projects import CodeConflictError, CodeProjectService, resolve_scoped_project_path

SAFE_SLUG_RE = re.compile(r'^[A-Za-z0-9_.-]{1,80}$')
PROHIBITED_GIT_ARGS = frozenset({'--hard', '-fd', '-fx', '-fxd'})


class DirtyWorktreeError(CodeConflictError):
    """Raised when attempting to integrate changes into a user file with uncommitted local modifications (CODE-02)."""


class GitWorkspaceService:
    """Manages isolated Git worktrees per agent and enforces non-destructive integration into the main tree."""

    def __init__(
        self,
        project_service: CodeProjectService,
        patch_engine: CodePatchEngine,
        *,
        worktrees_base_dir: str | Path | None = None,
    ):
        self.projects = project_service
        self.patch_engine = patch_engine
        self.worktrees_base_dir = Path(worktrees_base_dir).resolve() if worktrees_base_dir else None
        self._init_schema()

    def _init_schema(self) -> None:
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS code_worktrees (
                        workspace_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES code_projects(project_id) ON DELETE CASCADE,
                        agent_id TEXT NOT NULL,
                        branch_name TEXT NOT NULL,
                        worktree_path TEXT NOT NULL,
                        base_commit TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active', 'integrated', 'conflict', 'removed')),
                        created_at_ms INTEGER NOT NULL
                    );
                    '''
                )

    def _run_git(self, cwd: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        for arg in args:
            if arg in PROHIBITED_GIT_ARGS:
                raise PermissionError(f'Prohibited destructive git argument blocked: {arg}')
        proc = subprocess.run(
            ['git', *args],
            cwd=str(cwd),
            # Preserve explicit empty Git config values on Windows, including
            # hosts whose CRT environment has lost them after an environment edit.
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
            check=False,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed (code {proc.returncode}): {proc.stderr.strip()}")
        return proc

    def get_head_commit(self, repo_root: Path) -> str:
        proc = self._run_git(repo_root, ['rev-parse', 'HEAD'])
        return proc.stdout.strip()

    def detect_dirty_files(self, repo_root: Path) -> list[str]:
        """Return relative paths of all modified, staged, or untracked files in repo_root."""
        proc = self._run_git(repo_root, ['status', '--porcelain', '-uall'])
        dirty: list[str] = []
        for raw_line in proc.stdout.splitlines():
            if len(raw_line) >= 4:
                path_part = raw_line[3:].strip()
                if ' -> ' in path_part:
                    path_part = path_part.split(' -> ', 1)[1].strip()
                dirty.append(path_part.strip('"').replace('\\', '/'))
        return dirty

    def create_agent_worktree(
        self,
        *,
        workspace_id: str,
        project_id: str,
        agent_id: str,
        task_slug: str,
    ) -> dict[str, Any]:
        """Create an isolated git worktree on branch 'axx/agent/<agent_id>/<task_slug>' (CODE-02)."""
        for label, val in (('workspace_id', workspace_id), ('agent_id', agent_id), ('task_slug', task_slug)):
            if not isinstance(val, str) or not SAFE_SLUG_RE.fullmatch(val):
                raise ValueError(f'Invalid {label}: {val!r}')

        repo_root = self.projects.get_project_root(project_id)
        base_commit = self.get_head_commit(repo_root)
        branch_name = f'axx/agent/{agent_id}/{task_slug}'

        base_dir = self.worktrees_base_dir or (repo_root.parent / f'.{repo_root.name}_axx_worktrees')
        base_dir.mkdir(parents=True, exist_ok=True)
        wt_path = (base_dir / workspace_id).resolve()
        if wt_path.parent != base_dir.resolve():
            raise ValueError('Worktree path must be a direct child of its managed root')
        if wt_path.exists():
            raise FileExistsError('Worktree destination already exists; preserving its files')

        self._run_git(repo_root, ['worktree', 'add', '-b', branch_name, str(wt_path), base_commit])

        now = self.projects.clock()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO code_worktrees
                        (workspace_id, project_id, agent_id, branch_name, worktree_path, base_commit, status, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
                    ''',
                    (workspace_id, project_id, agent_id, branch_name, str(wt_path), base_commit, now),
                )
        return {
            'workspace_id': workspace_id,
            'project_id': project_id,
            'agent_id': agent_id,
            'branch_name': branch_name,
            'worktree_path': str(wt_path),
            'base_commit': base_commit,
            'status': 'active',
        }

    def get_worktree(self, workspace_id: str) -> dict[str, Any]:
        with self.projects.lock, self.projects._connect() as db:
            row = db.execute(
                'SELECT * FROM code_worktrees WHERE workspace_id=?',
                (workspace_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'Worktree not found: {workspace_id}')
            return dict(row)

    def propose_and_apply_in_worktree(
        self,
        *,
        changeset_id: str,
        workspace_id: str,
        file_edits: list[dict[str, Any]],
        test_report_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Propose and apply an agent CodeChangeSet strictly inside the agent's isolated git worktree (CODE-02)."""
        wt = self.get_worktree(workspace_id)
        wt_root = Path(wt['worktree_path']).resolve()

        self.patch_engine.propose_changeset(
            changeset_id=changeset_id,
            project_id=wt['project_id'],
            workspace_id=workspace_id,
            agent_id=wt['agent_id'],
            base_commit=wt['base_commit'],
            branch=wt['branch_name'],
            file_edits=file_edits,
            test_report_refs=test_report_refs,
            target_root=wt_root,
        )
        return self.patch_engine.apply_changeset(changeset_id, target_root=wt_root)

    def integrate_into_primary_workspace(self, changeset_id: str) -> dict[str, Any]:
        """Integrate an agent's validated CodeChangeSet into the primary project workspace without overwriting dirty user files (CODE-02)."""
        changeset = self.patch_engine.get_changeset(changeset_id)
        project_id = changeset['project_id']
        primary_root = self.projects.get_project_root(project_id)

        dirty_set = set(self.detect_dirty_files(primary_root))
        touched_paths = [f['path'].replace('\\', '/') for f in changeset['files']]
        dirty_overlap = [p for p in touched_paths if p in dirty_set]
        if dirty_overlap:
            self.patch_engine._update_status(changeset_id, 'conflict')
            raise DirtyWorktreeError(
                f'Integration blocked: primary workspace has uncommitted user changes in {dirty_overlap}'
            )

        # Apply atomically to primary_root (which also verifies base_sha256 against primary_root)
        self.patch_engine.apply_changeset(changeset_id, target_root=primary_root)
        updated = self.patch_engine._update_status(changeset_id, 'integrated')
        return updated

    def remove_agent_worktree(self, workspace_id: str) -> dict[str, Any]:
        wt = self.get_worktree(workspace_id)
        repo_root = self.projects.get_project_root(wt['project_id'])
        wt_path = Path(wt['worktree_path'])
        if wt_path.exists():
            if self.detect_dirty_files(wt_path):
                raise DirtyWorktreeError('Worktree has uncommitted files; preserve or commit them before removal')
            self._run_git(repo_root, ['worktree', 'remove', str(wt_path)])
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.execute(
                    "UPDATE code_worktrees SET status='removed' WHERE workspace_id=?",
                    (workspace_id,),
                )
        return {'workspace_id': workspace_id, 'status': 'removed'}
