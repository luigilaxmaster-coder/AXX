"""Authorized Code Projects, Windows Path/Reparse Security, Encoding/EOL Preservation, and Code Time Machine (PR-13 / CODE-01 / SEC-03).

Enforces Invariants:
- SEC-03: Strict canonical path resolution within authorized project root; blocks '..' traversal,
  Windows symlinks/junctions/reparse points escaping root, Alternate Data Streams (ADS), and secret files.
- CODE-01: Binary file detection, large-file read-only degradation, exact encoding (utf-8, utf-8-sig,
  utf-16-le, utf-16-be) and line ending (CRLF, LF, MIXED) preservation, and CAS save conflict detection.
- Code Time Machine: stores content-addressed snapshots of every file revision for instant rollback.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import time
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
MAX_EDITABLE_BYTES = 2 * 1024 * 1024  # 2 MiB default before read-only degraded mode

BLOCKED_BASENAMES = frozenset({
    '.env',
    '.env.local',
    '.env.production',
    'id_rsa',
    'id_ed25519',
    'endpoint.dpapi',
})


class CodeSecurityError(PermissionError):
    """Raised when a file path violates project root boundary, symlink/reparse rules, or secret protection (SEC-03)."""


class CodeConflictError(ValueError):
    """Raised when saving or patching a file whose on-disk SHA-256 differs from base_sha256 (CODE-01 / CODE-03)."""


class BinaryFileError(ValueError):
    """Raised when attempting to open or edit a binary file as text (CODE-01)."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        st = os.lstat(path)
        attrs = getattr(st, 'st_file_attributes', 0)
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    except OSError:
        return False
    return False


def resolve_scoped_project_path(project_root: str | Path, relative_path: str) -> Path:
    """Resolve a path inside project_root, blocking traversal, Windows ADS, symlinks/junctions, and secret files (SEC-03)."""
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise CodeSecurityError('Empty file path')
    if '\x00' in relative_path:
        raise CodeSecurityError('Null byte in file path')
    # Block Windows Alternate Data Streams (colon anywhere in relative path) or UNC paths
    if ':' in relative_path or relative_path.startswith(('\\\\', '//', '/', '\\')):
        raise CodeSecurityError(f'Absolute, UNC, or Alternate Data Stream path rejected: {relative_path!r}')

    root = Path(project_root).resolve()
    norm_parts = Path(relative_path).parts
    if '..' in norm_parts:
        raise CodeSecurityError(f'Path traversal (..) rejected: {relative_path!r}')
    if any(part.rstrip(' .').casefold() == '.git' for part in (*root.parts, *norm_parts)):
        raise CodeSecurityError('Access to Git metadata through the file editor is prohibited')

    candidate = root / relative_path

    # Check every existing ancestor from root down to candidate for reparse points / symlinks
    curr = root
    for part in norm_parts:
        curr = curr / part
        if curr.exists() or curr.is_symlink():
            if _is_reparse_or_symlink(curr):
                raise CodeSecurityError(f'Symlink or Windows junction/reparse point rejected: {curr}')

    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise CodeSecurityError(f'Resolved path {resolved} escapes project root {root}')
    if resolved.name.lower() in BLOCKED_BASENAMES:
        raise CodeSecurityError(f'Access to protected secret file {resolved.name!r} is blocked')
    return resolved


def detect_encoding_and_eol(raw_bytes: bytes) -> dict[str, Any]:
    """Detect binary content, BOM/UTF-8/UTF-16 encoding, and CRLF/LF/MIXED line endings (CODE-01)."""
    if raw_bytes.startswith(b'\xef\xbb\xbf'):
        encoding = 'utf-8-sig'
        text = raw_bytes.decode('utf-8-sig')
    elif raw_bytes.startswith(b'\xff\xfe'):
        encoding = 'utf-16-le'
        text = raw_bytes[2:].decode('utf-16-le')
    elif raw_bytes.startswith(b'\xfe\xff'):
        encoding = 'utf-16-be'
        text = raw_bytes[2:].decode('utf-16-be')
    else:
        if b'\x00' in raw_bytes[:8192]:
            raise BinaryFileError('Binary file detected (null bytes present); cannot open as text')
        try:
            text = raw_bytes.decode('utf-8')
            encoding = 'utf-8'
        except UnicodeDecodeError as exc:
            raise BinaryFileError('File is not valid UTF-8 or UTF-16 text') from exc

    crlf_count = text.count('\r\n')
    lf_only_count = text.count('\n') - crlf_count
    if crlf_count > 0 and lf_only_count == 0:
        line_ending = 'CRLF'
    elif lf_only_count > 0 and crlf_count == 0:
        line_ending = 'LF'
    elif crlf_count > 0 and lf_only_count > 0:
        line_ending = 'MIXED'
    else:
        line_ending = 'LF'

    normalized_text = text.replace('\r\n', '\n')
    return {
        'encoding': encoding,
        'line_ending': line_ending,
        'text': normalized_text,
        'raw_text': text,
        'sha256': hashlib.sha256(raw_bytes).hexdigest(),
        'size_bytes': len(raw_bytes),
    }


def encode_with_preserved_format(text_lf: str, *, encoding: str, line_ending: str) -> bytes:
    """Encode normalized text back to exact target line endings and BOM/encoding (CODE-01)."""
    normalized = text_lf.replace('\r\n', '\n')
    if line_ending == 'CRLF':
        formatted = normalized.replace('\n', '\r\n')
    else:
        formatted = normalized

    if encoding == 'utf-8-sig':
        return b'\xef\xbb\xbf' + formatted.encode('utf-8')
    if encoding == 'utf-16-le':
        return b'\xff\xfe' + formatted.encode('utf-16-le')
    if encoding == 'utf-16-be':
        return b'\xfe\xff' + formatted.encode('utf-16-be')
    if encoding == 'utf-8':
        return formatted.encode('utf-8')
    raise ValueError(f'Unsupported encoding: {encoding!r}')


def atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    """Write bytes atomically via temp file + fsync + os.replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f'.{target_path.name}.{os.getpid()}.{int(time.time() * 1000000)}.tmp')
    try:
        with tmp_path.open('wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
        if target_path.read_bytes() != payload:
            raise CodeConflictError('Post-write verification mismatch; file changed during save')
    finally:
        tmp_path.unlink(missing_ok=True)


class CodeProjectService:
    """Manages authorized Code Studio projects, safe file reading/saving, and Code Time Machine snapshots."""

    def __init__(
        self,
        db_path: str | Path = ':memory:',
        *,
        max_editable_bytes: int = MAX_EDITABLE_BYTES,
        clock=None,
    ):
        self.db_path = str(db_path)
        self.max_editable_bytes = int(max_editable_bytes)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.lock = threading.RLock()
        self._persistent_conn: sqlite3.Connection | None = None
        if self.db_path == ':memory:':
            self._persistent_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()
        from .recovery import FileRecovery
        self.recovery = FileRecovery(self)

    def _connect(self):
        if self._persistent_conn is not None:
            return _NullClosing(self._persistent_conn)
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        return closing(conn)

    def _init_schema(self) -> None:
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS code_projects (
                        project_id TEXT PRIMARY KEY,
                        project_root_ref TEXT NOT NULL,
                        git_root_ref TEXT,
                        project_revision INTEGER NOT NULL DEFAULT 1 CHECK(project_revision > 0),
                        created_at_ms INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS code_time_machine_snapshots (
                        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id TEXT NOT NULL REFERENCES code_projects(project_id) ON DELETE CASCADE,
                        relative_path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        encoding TEXT NOT NULL,
                        line_ending TEXT NOT NULL,
                        raw_blob BLOB NOT NULL,
                        actor TEXT NOT NULL,
                        operation_id TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS code_drafts (
                        project_id TEXT NOT NULL REFERENCES code_projects(project_id),
                        relative_path TEXT NOT NULL, revision INTEGER NOT NULL,
                        content TEXT, base_content TEXT, base_sha256 TEXT,
                        encoding TEXT, line_ending TEXT, updated_at_ms INTEGER NOT NULL,
                        PRIMARY KEY(project_id,relative_path));
                    CREATE INDEX IF NOT EXISTS idx_time_machine_lookup
                        ON code_time_machine_snapshots(project_id, relative_path, created_at_ms);
                    '''
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def register_project(self, project_id: str, project_root: str | Path) -> dict[str, Any]:
        if not isinstance(project_id, str) or not ID_RE.fullmatch(project_id):
            raise ValueError(f'Invalid project_id: {project_id!r}')
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise ValueError(f'Project root directory does not exist: {root}')
        git_root = str(root) if (root / '.git').exists() else None
        now = self.clock()
        with self.lock, self._connect() as db:
            with db:
                existing = db.execute('SELECT project_root_ref FROM code_projects WHERE project_id=?', (project_id,)).fetchone()
                if existing and Path(existing['project_root_ref']).resolve() != root:
                    raise CodeSecurityError('A registered project ID cannot be moved to another root')
                db.execute(
                    '''
                    INSERT OR IGNORE INTO code_projects (project_id, project_root_ref, git_root_ref, project_revision, created_at_ms)
                    VALUES (?, ?, ?, 1, ?)
                    ''',
                    (project_id, str(root), git_root, now),
                )
        return {'project_id': project_id, 'project_root': str(root), 'git_root': git_root}

    def get_project_root(self, project_id: str) -> Path:
        with self.lock, self._connect() as db:
            row = db.execute(
                'SELECT project_root_ref FROM code_projects WHERE project_id=?',
                (project_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'Project not registered: {project_id}')
            return Path(row['project_root_ref']).resolve()

    @staticmethod
    def _file_sha256(path: Path) -> str:
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    def list_projects(self) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT project_id, project_root_ref, git_root_ref FROM code_projects ORDER BY project_id LIMIT 200')]

    def list_directory(self, project_id: str, relative_path: str = '') -> list[dict[str, Any]]:
        root = self.get_project_root(project_id)
        directory = resolve_scoped_project_path(root, relative_path) if relative_path else root
        if not directory.is_dir():
            raise NotADirectoryError(relative_path)
        entries = []
        with os.scandir(directory) as children:
            for child in children:
                if len(entries) >= 2000:
                    raise ValueError('Directory exceeds the 2000-entry limit; open a narrower folder')
                if child.name in {'.git', 'node_modules', '__pycache__', '.venv', 'target', 'build'}:
                    continue
                child_path = Path(child.path).relative_to(root).as_posix()
                try:
                    checked = resolve_scoped_project_path(root, child_path)
                except CodeSecurityError:
                    continue
                entries.append({'path': child_path, 'name': child.name, 'directory': checked.is_dir()})
        return sorted(entries, key=lambda entry: (not entry['directory'], entry['name'].casefold()))

    def read_document(self, project_id: str, relative_path: str) -> dict[str, Any]:
        """Read a file inside an authorized project with binary/BOM/EOL detection and large-file read-only degradation (CODE-01)."""
        root = self.get_project_root(project_id)
        full_path = resolve_scoped_project_path(root, relative_path)
        if not full_path.is_file():
            raise FileNotFoundError(f'File not found: {relative_path}')

        size = full_path.stat().st_size
        if size > self.max_editable_bytes:
            with full_path.open('rb') as fh:
                raw_head = fh.read(self.max_editable_bytes)
            info = detect_encoding_and_eol(raw_head)
            return {
                'project_id': project_id,
                'path': relative_path,
                'sha256': self._file_sha256(full_path),
                'encoding': info['encoding'],
                'line_ending': info['line_ending'],
                'size_bytes': size,
                'read_only_degraded': True,
                'truncated': True,
                'truncation_notice': f'Archivo grande ({size} bytes): abierto en modo solo lectura truncado a {self.max_editable_bytes} bytes.',
                'content': info['text'],
            }

        raw = full_path.read_bytes()
        info = detect_encoding_and_eol(raw)
        return {
            'project_id': project_id,
            'path': relative_path,
            'sha256': info['sha256'],
            'encoding': info['encoding'],
            'line_ending': info['line_ending'],
            'size_bytes': info['size_bytes'],
            'read_only_degraded': False,
            'truncated': False,
            'content': info['text'],
        }

    def save_document(
        self,
        project_id: str,
        relative_path: str,
        new_content: str,
        *,
        expected_sha256: str,
        encoding: str | None = None,
        line_ending: str | None = None,
        actor: str = 'user',
        operation_id: str = 'op-save',
    ) -> dict[str, Any]:
        """Atomically save a file with CAS expected_sha256 verification and Time Machine snapshot recording (CODE-01)."""
        with self.lock:
            self.recovery.assert_writable(project_id)
            root = self.get_project_root(project_id)
            full_path = resolve_scoped_project_path(root, relative_path)
            if not full_path.is_file():
                raise FileNotFoundError(f'File not found: {relative_path}')

            if not isinstance(new_content, str) or len(new_content.encode('utf-8')) > self.max_editable_bytes:
                raise ValueError('Edited document exceeds the editable text size limit')
            if full_path.stat().st_size > self.max_editable_bytes:
                raise ValueError('Large files are read-only')
            current_raw = full_path.read_bytes()
            current_info = detect_encoding_and_eol(current_raw)
            if current_info['sha256'] != expected_sha256:
                raise CodeConflictError(
                    f"Save conflict on {relative_path}: expected sha256={expected_sha256}, on_disk={current_info['sha256']}"
                )

            target_enc = encoding or current_info['encoding']
            target_eol = line_ending or (
                'CRLF' if current_info['line_ending'] == 'CRLF' else 'LF'
            )
            new_raw = encode_with_preserved_format(new_content, encoding=target_enc, line_ending=target_eol)
            new_sha = hashlib.sha256(new_raw).hexdigest()

            # Preserve the old bytes before preparing the durable write intent.
            self._record_snapshot(
                project_id=project_id,
                relative_path=relative_path,
                sha256=current_info['sha256'],
                encoding=current_info['encoding'],
                line_ending=current_info['line_ending'],
                raw_blob=current_raw,
                actor=actor,
                operation_id=f'{operation_id}:before',
            )
            self.recovery.replace(project_id, root,
                [{'path':relative_path,'before':current_raw,'after':new_raw,
                  'encoding':target_enc,'line_ending':target_eol}],
                actor=actor,operation_id=f'{operation_id}:after')

            return {
                'status': 'saved',
                'project_id': project_id,
                'path': relative_path,
                'previous_sha256': current_info['sha256'],
                'new_sha256': new_sha,
                'encoding': target_enc,
                'line_ending': target_eol,
                'size_bytes': len(new_raw),
            }

    def restore_snapshot(
        self,
        project_id: str,
        relative_path: str,
        target_sha256: str,
        *,
        actor: str = 'rollback',
        operation_id: str = 'op-restore',
    ) -> dict[str, Any]:
        """Restore a file from Code Time Machine by its historical SHA-256 (CODE-03)."""
        with self.lock:
            self.recovery.assert_writable(project_id)
            root = self.get_project_root(project_id)
            full_path = resolve_scoped_project_path(root, relative_path)
            with self.lock, self._connect() as db:
                row = db.execute(
                    '''
                    SELECT raw_blob, encoding, line_ending FROM code_time_machine_snapshots
                    WHERE project_id=? AND relative_path=? AND sha256=?
                    ORDER BY snapshot_id DESC LIMIT 1
                    ''',
                    (project_id, relative_path, target_sha256),
                ).fetchone()
                if not row:
                    raise LookupError(f'Snapshot {target_sha256} not found for {relative_path}')
                raw_blob = bytes(row['raw_blob'])
                encoding = row['encoding']
                line_ending = row['line_ending']

            if hashlib.sha256(raw_blob).hexdigest() != target_sha256:
                raise RuntimeError('Snapshot hash mismatch; file was not modified')
            current = full_path.read_bytes() if full_path.is_file() else None
            if current is not None:
                info = detect_encoding_and_eol(current)
                self._record_snapshot(project_id=project_id,relative_path=relative_path,
                    sha256=info['sha256'],encoding=info['encoding'],line_ending=info['line_ending'],
                    raw_blob=current,actor=actor,operation_id=f'{operation_id}:before')
            self.recovery.replace(project_id, root,
                [{'path':relative_path,'before':current,'after':raw_blob,
                  'encoding':encoding,'line_ending':line_ending}],
                actor=actor,operation_id=operation_id)
            return {
                'status': 'restored',
                'project_id': project_id,
                'path': relative_path,
                'restored_sha256': target_sha256,
                'encoding': encoding,
                'line_ending': line_ending,
            }

    def _record_snapshot(
        self,
        *,
        project_id: str,
        relative_path: str,
        sha256: str,
        encoding: str,
        line_ending: str,
        raw_blob: bytes,
        actor: str,
        operation_id: str,
    ) -> None:
        with self.lock, self._connect() as db, db:
            self._insert_snapshot(db, project_id=project_id, relative_path=relative_path,
                sha256=sha256, encoding=encoding, line_ending=line_ending,
                raw_blob=raw_blob, actor=actor, operation_id=operation_id)

    def _insert_snapshot(self, db, *, project_id, relative_path, sha256, encoding, line_ending, raw_blob, actor, operation_id):
        db.execute('INSERT INTO code_time_machine_snapshots '
                   '(project_id,relative_path,sha256,encoding,line_ending,raw_blob,actor,operation_id,created_at_ms) '
                   'VALUES (?,?,?,?,?,?,?,?,?)',
                   (project_id,relative_path,sha256,encoding,line_ending,raw_blob,actor,operation_id,self.clock()))

    def list_drafts(self, project_id):
        self.get_project_root(project_id)
        with self.lock,self._connect() as db:
            return [dict(row) for row in db.execute('SELECT relative_path,revision,updated_at_ms FROM code_drafts WHERE project_id=? AND content IS NOT NULL ORDER BY updated_at_ms DESC',(project_id,))]

    def get_draft(self, project_id, relative_path):
        resolve_scoped_project_path(self.get_project_root(project_id),relative_path)
        with self.lock,self._connect() as db:
            row=db.execute('SELECT * FROM code_drafts WHERE project_id=? AND relative_path=?',(project_id,relative_path)).fetchone()
            return dict(row) if row else {'project_id':project_id,'relative_path':relative_path,'revision':0,'content':None}

    def save_draft(self, project_id, relative_path, *, expected_revision, content, base_content=None, base_sha256=None, encoding=None, line_ending=None):
        resolve_scoped_project_path(self.get_project_root(project_id),relative_path)
        if type(expected_revision) is not int or expected_revision<0:
            raise ValueError('Draft expected_revision must be a nonnegative integer')
        if content is not None:
            if not all(isinstance(v,str) and len(v.encode('utf-8'))<=self.max_editable_bytes for v in (content,base_content)):
                raise ValueError('Draft content/base exceeds editable size or is not text')
            if not isinstance(base_sha256,str) or not re.fullmatch('[0-9a-f]{64}',base_sha256):
                raise ValueError('Draft base_sha256 must be a SHA-256 digest')
            encode_with_preserved_format('',encoding=encoding,line_ending=line_ending)
            if line_ending not in ('LF','CRLF','MIXED'):
                raise ValueError('Draft line ending is invalid')
        with self.lock,self._connect() as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM code_drafts WHERE project_id=? AND relative_path=?',(project_id,relative_path)).fetchone()
            revision=row[0] if row else 0
            if expected_revision!=revision:
                raise CodeConflictError('Draft revision conflict; another editor saved a different draft')
            db.execute('INSERT INTO code_drafts VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(project_id,relative_path) DO UPDATE SET revision=excluded.revision,content=excluded.content,base_content=excluded.base_content,base_sha256=excluded.base_sha256,encoding=excluded.encoding,line_ending=excluded.line_ending,updated_at_ms=excluded.updated_at_ms',
                       (project_id,relative_path,revision+1,content,base_content,base_sha256,encoding,line_ending,self.clock()))
            return {'revision':revision+1,'persisted':True,'cleared':content is None}
