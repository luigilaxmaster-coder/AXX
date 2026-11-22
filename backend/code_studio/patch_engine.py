"""Transactional CodeChangeSet Engine, Unified Diff Generator, and Atomic Rollback (PR-13 / CODE-03).

Enforces Invariants:
- CODE-03: Every agent edit is represented as a validated CodeChangeSet v1 with base_sha256,
  proposed_sha256, and diff_digest. Application uses durable recovery intents, verified replacements and conflict-safe compensation. Rollback restores exact base_sha256 bytes across all touched files.
- I-02 / I-08: Agents cannot write arbitrarily without a tracked CodeChangeSet and workspace lease/scope.
"""
from __future__ import annotations

import copy
import difflib
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from backend.code_studio.projects import (
    CodeConflictError,
    CodeProjectService,
    detect_encoding_and_eol,
    encode_with_preserved_format,
    resolve_scoped_project_path,
)

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
SHA256_RE = re.compile(r'^[a-f0-9]{64}$')
VALID_STATUSES = frozenset({'proposed', 'validated', 'applied', 'conflict', 'failed', 'integrated'})
VALID_ENCODINGS = frozenset({'utf-8', 'utf-8-sig', 'utf-16-le', 'utf-16-be'})
VALID_LINE_ENDINGS = frozenset({'LF', 'CRLF', 'MIXED'})


class CodeChangeSetValidationError(ValueError):
    """Raised when a CodeChangeSet payload violates code-changeset.schema.json."""


def validate_code_changeset(payload: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate a CodeChangeSet v1 against schemas/code-changeset.schema.json."""
    if not isinstance(payload, dict):
        raise CodeChangeSetValidationError('CodeChangeSet must be a JSON object')

    required = {
        'schema_version',
        'changeset_id',
        'project_id',
        'workspace_id',
        'agent_id',
        'base_commit',
        'branch',
        'status',
        'files',
        'test_report_refs',
        'created_at',
    }
    allowed = required | {'approval_operation_id'}
    missing = required - set(payload.keys())
    if missing:
        raise CodeChangeSetValidationError(f'Missing required CodeChangeSet fields: {sorted(missing)}')
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise CodeChangeSetValidationError(f'Unknown CodeChangeSet fields: {sorted(unknown)}')

    if payload.get('schema_version') != '1.0':
        raise CodeChangeSetValidationError("schema_version must be '1.0'")

    for id_field in ('changeset_id', 'project_id', 'workspace_id', 'agent_id'):
        val = payload.get(id_field)
        if not isinstance(val, str) or not ID_RE.fullmatch(val):
            raise CodeChangeSetValidationError(f'Invalid {id_field}: {val!r}')

    base_commit = payload.get('base_commit')
    if not isinstance(base_commit, str) or not (7 <= len(base_commit) <= 64):
        raise CodeChangeSetValidationError('base_commit must be 7..64 chars')

    branch = payload.get('branch')
    if not isinstance(branch, str) or not (1 <= len(branch) <= 240):
        raise CodeChangeSetValidationError('branch must be 1..240 chars')

    if payload.get('status') not in VALID_STATUSES:
        raise CodeChangeSetValidationError(f"Invalid status: {payload.get('status')!r}")

    files = payload.get('files')
    if not isinstance(files, list) or not (1 <= len(files) <= 500):
        raise CodeChangeSetValidationError('files must be a non-empty list (1..500 items)')

    file_req = {'path', 'base_sha256', 'proposed_sha256', 'diff_digest', 'encoding'}
    file_allowed = file_req | {'line_ending', 'is_binary'}
    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            raise CodeChangeSetValidationError(f'files[{idx}] must be an object')
        f_missing = file_req - set(item.keys())
        if f_missing:
            raise CodeChangeSetValidationError(f'files[{idx}] missing fields: {sorted(f_missing)}')
        f_unknown = set(item.keys()) - file_allowed
        if f_unknown:
            raise CodeChangeSetValidationError(f'files[{idx}] unknown fields: {sorted(f_unknown)}')
        path = item.get('path')
        if not isinstance(path, str) or not (1 <= len(path) <= 1024):
            raise CodeChangeSetValidationError(f'files[{idx}].path invalid')
        for sha_field in ('base_sha256', 'proposed_sha256', 'diff_digest'):
            sha_val = item.get(sha_field)
            if not isinstance(sha_val, str) or not SHA256_RE.fullmatch(sha_val):
                raise CodeChangeSetValidationError(f'files[{idx}].{sha_field} must be 64-char hex sha256')
        if item.get('encoding') not in VALID_ENCODINGS:
            raise CodeChangeSetValidationError(f"files[{idx}].encoding invalid: {item.get('encoding')!r}")
        if 'line_ending' in item and item['line_ending'] not in VALID_LINE_ENDINGS:
            raise CodeChangeSetValidationError(f"files[{idx}].line_ending invalid: {item.get('line_ending')!r}")
        if 'is_binary' in item and not isinstance(item['is_binary'], bool):
            raise CodeChangeSetValidationError(f'files[{idx}].is_binary must be boolean')

    if 'approval_operation_id' in payload:
        op_id = payload['approval_operation_id']
        if not isinstance(op_id, str) or not ID_RE.fullmatch(op_id):
            raise CodeChangeSetValidationError('Invalid approval_operation_id')

    refs = payload.get('test_report_refs')
    if not isinstance(refs, list) or len(refs) > 128 or not all(isinstance(r, str) and ID_RE.fullmatch(r) for r in refs):
        raise CodeChangeSetValidationError('Invalid test_report_refs')

    created_at = payload.get('created_at')
    if not isinstance(created_at, str) or not created_at.strip():
        raise CodeChangeSetValidationError('created_at must be an ISO-8601 string')

    return copy.deepcopy(payload)


def compute_unified_diff(path: str, old_text_lf: str, new_text_lf: str) -> tuple[str, str]:
    """Compute unified diff text and its SHA-256 diff_digest."""
    diff_lines = list(
        difflib.unified_diff(
            old_text_lf.splitlines(keepends=True),
            new_text_lf.splitlines(keepends=True),
            fromfile=f'a/{path}',
            tofile=f'b/{path}',
        )
    )
    diff_text = ''.join(diff_lines)
    diff_digest = hashlib.sha256(diff_text.encode('utf-8')).hexdigest()
    return diff_text, diff_digest


class CodePatchEngine:
    """Proposes, persists, applies with recovery, and rolls back CodeChangeSets (CODE-03)."""

    def __init__(self, project_service: CodeProjectService):
        self.projects = project_service
        self._init_schema()

    def _init_schema(self) -> None:
        with self.projects.lock, self.projects._connect() as db:
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS code_changesets (
                        changeset_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES code_projects(project_id) ON DELETE CASCADE,
                        workspace_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        base_commit TEXT NOT NULL,
                        branch TEXT NOT NULL,
                        status TEXT NOT NULL,
                        changeset_json TEXT NOT NULL,
                        proposed_blobs_json TEXT NOT NULL,
                        approval_operation_id TEXT,
                        created_at_ms INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS code_changeset_reviews (
                        review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        changeset_id TEXT NOT NULL REFERENCES code_changesets(changeset_id) ON DELETE CASCADE,
                        reviewer_id TEXT NOT NULL,
                        verdict TEXT NOT NULL CHECK(verdict IN ('approved', 'changes', 'unclear')),
                        model TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    );
                    '''
                )

    def record_review(self, changeset_id: str, reviewer_id: str, verdict: str, model: str, summary: str) -> dict[str, Any]:
        self.get_changeset(changeset_id)
        now = self.projects.clock()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                review_id = db.execute(
                    'INSERT INTO code_changeset_reviews (changeset_id, reviewer_id, verdict, model, summary, created_at_ms) '
                    'VALUES (?, ?, ?, ?, ?, ?)', (changeset_id, reviewer_id, verdict, model, summary[:4000], now)).lastrowid
        return {'review_id': review_id, 'changeset_id': changeset_id, 'reviewer_id': reviewer_id, 'verdict': verdict,
                'model': model, 'summary': summary[:4000], 'created_at_ms': now}

    def list_reviews(self, changeset_id: str) -> list[dict[str, Any]]:
        with self.projects.lock, self.projects._connect() as db:
            return [dict(r) for r in db.execute(
                'SELECT * FROM code_changeset_reviews WHERE changeset_id=? ORDER BY review_id', (changeset_id,))]

    def propose_changeset(
        self,
        *,
        changeset_id: str,
        project_id: str,
        workspace_id: str,
        agent_id: str,
        base_commit: str,
        branch: str,
        file_edits: list[dict[str, Any]],
        created_at: str | None = None,
        test_report_refs: list[str] | None = None,
        approval_operation_id: str | None = None,
        target_root: Path | None = None,
    ) -> dict[str, Any]:
        """Build and persist a validated CodeChangeSet proposal from a list of {'path': ..., 'new_content': ...}."""
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        root = Path(target_root).resolve() if target_root else self.projects.get_project_root(project_id)
        files_manifest: list[dict[str, Any]] = []
        proposed_blobs: dict[str, dict[str, str]] = {}

        for edit in file_edits:
            rel_path = str(edit['path'])
            new_content = str(edit['new_content'])
            full_path = resolve_scoped_project_path(root, rel_path)
            if not full_path.is_file():
                raise FileNotFoundError(f'Cannot propose edit for missing file: {rel_path}')

            current_raw = full_path.read_bytes()
            current_info = detect_encoding_and_eol(current_raw)
            base_sha = edit.get('expected_base_sha256') or current_info['sha256']
            if base_sha != current_info['sha256']:
                raise CodeConflictError(
                    f'Base SHA-256 mismatch while building proposal for {rel_path}: '
                    f"expected={base_sha}, on_disk={current_info['sha256']}"
                )

            target_eol = 'CRLF' if current_info['line_ending'] == 'CRLF' else 'LF'
            new_raw = encode_with_preserved_format(
                new_content,
                encoding=current_info['encoding'],
                line_ending=target_eol,
            )
            proposed_sha = hashlib.sha256(new_raw).hexdigest()
            diff_text, diff_digest = compute_unified_diff(rel_path, current_info['text'], new_content.replace('\r\n', '\n'))

            files_manifest.append(
                {
                    'path': rel_path,
                    'base_sha256': base_sha,
                    'proposed_sha256': proposed_sha,
                    'diff_digest': diff_digest,
                    'encoding': current_info['encoding'],
                    'line_ending': current_info['line_ending'],
                    'is_binary': False,
                }
            )
            proposed_blobs[rel_path] = {
                'new_content': new_content,
                'diff_text': diff_text,
            }

        payload: dict[str, Any] = {
            'schema_version': '1.0',
            'changeset_id': changeset_id,
            'project_id': project_id,
            'workspace_id': workspace_id,
            'agent_id': agent_id,
            'base_commit': base_commit,
            'branch': branch,
            'status': 'proposed',
            'files': files_manifest,
            'test_report_refs': list(test_report_refs or []),
            'created_at': created_at,
        }
        if approval_operation_id:
            payload['approval_operation_id'] = approval_operation_id

        validated = validate_code_changeset(payload)
        now = self.projects.clock()
        with self.projects.lock, self.projects._connect() as db:
            with db:
                inserted = db.execute(
                    '''
                    INSERT INTO code_changesets
                        (changeset_id, project_id, workspace_id, agent_id, base_commit, branch, status,
                         changeset_json, proposed_blobs_json, approval_operation_id, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(changeset_id) DO NOTHING
                    ''',
                    (
                        changeset_id,
                        project_id,
                        workspace_id,
                        agent_id,
                        base_commit,
                        branch,
                        validated['status'],
                        json.dumps(validated, ensure_ascii=False),
                        json.dumps(proposed_blobs, ensure_ascii=False),
                        approval_operation_id,
                        now,
                    ),
                )
                if inserted.rowcount != 1:
                    raise CodeConflictError('ChangeSet ID already exists; use a new ID for a revised proposal')
        return validated

    def get_changeset(self, changeset_id: str) -> dict[str, Any]:
        with self.projects.lock, self.projects._connect() as db:
            row = db.execute(
                'SELECT changeset_json FROM code_changesets WHERE changeset_id=?',
                (changeset_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'CodeChangeSet not found: {changeset_id}')
            return json.loads(row['changeset_json'])

    def get_diffs(self, changeset_id: str) -> dict[str, Any]:
        with self.projects.lock, self.projects._connect() as db:
            row = db.execute('SELECT proposed_blobs_json, created_at_ms FROM code_changesets WHERE changeset_id=?',
                             (changeset_id,)).fetchone()
            if not row:
                raise LookupError(f'CodeChangeSet not found: {changeset_id}')
        blobs = json.loads(row['proposed_blobs_json'])
        return {'created_at_ms': int(row['created_at_ms']),
                'files': [{'path': path, 'diff_text': blob['diff_text']} for path, blob in blobs.items()]}

    def apply_changeset(
        self,
        changeset_id: str,
        *,
        target_root: Path | None = None,
    ) -> dict[str, Any]:
        """Apply after all-file CAS preflight, serializing writes with project saves (CODE-03)."""
        with self.projects.lock:
            with self.projects.lock, self.projects._connect() as db:
                row = db.execute(
                    'SELECT changeset_json, proposed_blobs_json FROM code_changesets WHERE changeset_id=?',
                    (changeset_id,),
                ).fetchone()
                if not row:
                    raise LookupError(f'CodeChangeSet not found: {changeset_id}')
                changeset = json.loads(row['changeset_json'])
                proposed_blobs = json.loads(row['proposed_blobs_json'])

            project_id = changeset['project_id']
            root = Path(target_root).resolve() if target_root else self.projects.get_project_root(project_id)

            # Phase 1: Preflight check ALL files before writing any bytes
            staged_writes: list[dict[str, Any]] = []
            for f_entry in changeset['files']:
                rel_path = f_entry['path']
                full_path = resolve_scoped_project_path(root, rel_path)
                if not full_path.is_file():
                    self._update_status(changeset_id, 'conflict')
                    raise CodeConflictError(f'File missing on disk during apply: {rel_path}')

                current_raw = full_path.read_bytes()
                current_sha = hashlib.sha256(current_raw).hexdigest()
                if current_sha != f_entry['base_sha256']:
                    self._update_status(changeset_id, 'conflict')
                    raise CodeConflictError(
                        f"CAS conflict applying {changeset_id} on {rel_path}: "
                        f"expected base_sha256={f_entry['base_sha256']}, on_disk={current_sha}"
                    )

                current_info = detect_encoding_and_eol(current_raw)
                blob_info = proposed_blobs.get(rel_path)
                if not blob_info:
                    raise CodeChangeSetValidationError(f'Missing proposed content blob for {rel_path}')

                target_eol = 'CRLF' if f_entry.get('line_ending') == 'CRLF' else 'LF'
                new_raw = encode_with_preserved_format(
                    blob_info['new_content'],
                    encoding=f_entry['encoding'],
                    line_ending=target_eol,
                )
                new_sha = hashlib.sha256(new_raw).hexdigest()
                if new_sha != f_entry['proposed_sha256']:
                    self._update_status(changeset_id, 'failed')
                    raise CodeChangeSetValidationError(
                        f"Proposed SHA-256 mismatch for {rel_path}: expected={f_entry['proposed_sha256']}, actual={new_sha}"
                    )

                staged_writes.append(
                    {
                        'rel_path': rel_path,
                        'full_path': full_path,
                        'current_raw': current_raw,
                        'current_info': current_info,
                        'new_raw': new_raw,
                        'new_sha': new_sha,
                        'encoding': f_entry['encoding'],
                        'line_ending': target_eol,
                    }
                )

            for item in staged_writes:
                self.projects._record_snapshot(project_id=project_id, relative_path=item['rel_path'],
                    sha256=item['current_info']['sha256'], encoding=item['current_info']['encoding'],
                    line_ending=item['current_info']['line_ending'], raw_blob=item['current_raw'],
                    actor=changeset['agent_id'], operation_id=f'changeset:{changeset_id}:before')
            self.projects.recovery.replace(project_id, root,
                [{'path':i['rel_path'],'before':i['current_raw'],'after':i['new_raw'],
                  'encoding':i['encoding'],'line_ending':i['line_ending']} for i in staged_writes],
                actor=changeset['agent_id'], changeset_id=changeset_id, final_status='applied')
            return self.get_changeset(changeset_id)

    def rollback_changeset(
        self,
        changeset_id: str,
        *,
        target_root: Path | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Validate every file/snapshot before restoring, excluding project saves (CODE-03)."""
        with self.projects.lock:
            if type(force) is not bool:
                raise ValueError('force must be a boolean')
            changeset = self.get_changeset(changeset_id)
            project_id = changeset['project_id']
            root = Path(target_root).resolve() if target_root else self.projects.get_project_root(project_id)
            staged = []
            for entry in changeset['files']:
                relative = entry['path']; base_sha = entry['base_sha256']
                path = resolve_scoped_project_path(root, relative)
                if not force and path.is_file():
                    current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                    if current_sha != entry['proposed_sha256']:
                        raise CodeConflictError(
                            f"Cannot rollback {changeset_id}: {relative} was modified after apply "
                            f"(expected={entry['proposed_sha256']}, on_disk={current_sha})")
                with self.projects._connect() as db:
                    row = db.execute(
                        'SELECT raw_blob FROM code_time_machine_snapshots '
                        'WHERE project_id=? AND relative_path=? AND sha256=? ORDER BY snapshot_id DESC LIMIT 1',
                        (project_id, relative, base_sha)).fetchone()
                if not row:
                    raise LookupError(f'Time Machine snapshot {base_sha} not found for {relative}')
                raw = bytes(row['raw_blob'])
                if hashlib.sha256(raw).hexdigest() != base_sha:
                    raise RuntimeError(f'Snapshot hash mismatch for {relative}; files were not modified')
                staged.append((path, relative, raw, base_sha))
            self.projects.recovery.replace(project_id, root,
                [{'path':relative,'before':path.read_bytes() if path.is_file() else None,'after':raw,
                  'encoding':detect_encoding_and_eol(raw)['encoding'],
                  'line_ending':detect_encoding_and_eol(raw)['line_ending']} for path,relative,raw,sha in staged],
                actor='rollback',changeset_id=changeset_id,final_status='proposed')
            return {'status':'rolled_back','changeset_id':changeset_id,'project_id':project_id,
                    'files':[{'path':relative,'restored_sha256':sha} for path,relative,raw,sha in staged]}

    def _update_status(self, changeset_id: str, new_status: str) -> dict[str, Any]:
        with self.projects.lock, self.projects._connect() as db:
            row = db.execute(
                'SELECT changeset_json FROM code_changesets WHERE changeset_id=?',
                (changeset_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'CodeChangeSet not found: {changeset_id}')
            changeset = json.loads(row['changeset_json'])
            changeset['status'] = new_status
            with db:
                db.execute(
                    'UPDATE code_changesets SET status=?, changeset_json=? WHERE changeset_id=?',
                    (new_status, json.dumps(changeset, ensure_ascii=False), changeset_id),
                )
            return changeset
