"""Durable file-group intents; interruption is recovered without overwriting outsiders."""
from __future__ import annotations

import hashlib
import json
import uuid
import os
import threading
import psutil
from pathlib import Path

from .projects import CodeConflictError, atomic_write_bytes, resolve_scoped_project_path


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


_ACTIVE = set()
_ACTIVE_LOCK = threading.Lock()


class FileRecovery:
    def __init__(self, projects):
        self.projects = projects
        with projects.lock, projects._connect() as db, db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS code_file_transactions (
                    transaction_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    root_ref TEXT NOT NULL, state TEXT NOT NULL, changeset_id TEXT,
                    initial_status TEXT, final_status TEXT, actor TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL, error TEXT);
                CREATE TABLE IF NOT EXISTS code_file_transaction_items (
                    transaction_id TEXT NOT NULL REFERENCES code_file_transactions(transaction_id),
                    ordinal INTEGER NOT NULL, path TEXT NOT NULL,
                    before_blob BLOB, after_blob BLOB NOT NULL,
                    before_sha TEXT, after_sha TEXT NOT NULL,
                    encoding TEXT NOT NULL, line_ending TEXT NOT NULL,
                    PRIMARY KEY(transaction_id, ordinal));
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(code_file_transactions)')}
            for name, kind in (('owner_pid','INTEGER'),('owner_started','REAL'),('operation_id','TEXT')):
                if name not in columns:
                    db.execute(f'ALTER TABLE code_file_transactions ADD COLUMN {name} {kind}')
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS code_one_pending_project ON code_file_transactions(project_id) WHERE state IN ('prepared','recovery_conflict')")
        self.recover()

    def list(self, project_id=None):
        with self.projects.lock, self.projects._connect() as db:
            sql = 'SELECT transaction_id,project_id,state,changeset_id,created_at_ms,error FROM code_file_transactions'
            args = ()
            if project_id is not None:
                sql += ' WHERE project_id=?'; args = (project_id,)
            rows = [dict(row) for row in db.execute(sql + ' ORDER BY created_at_ms DESC LIMIT 200', args)]
            for row in rows:
                root = db.execute('SELECT root_ref FROM code_file_transactions WHERE transaction_id=?',(row['transaction_id'],)).fetchone()[0]
                row['files'] = []
                for item in db.execute('SELECT path,before_sha,after_sha FROM code_file_transaction_items WHERE transaction_id=? ORDER BY ordinal',(row['transaction_id'],)):
                    value=dict(item)
                    if row['state'] not in ('prepared','recovery_conflict'):
                        row['files'].append(value);continue
                    try:
                        path=resolve_scoped_project_path(root,item['path'])
                        value['current_sha']=self.projects._file_sha256(path) if path.is_file() else None
                    except OSError:value['current_sha']=None
                    row['files'].append(value)
            return rows

    def assert_writable(self, project_id):
        with self.projects._connect() as db:
            pending = db.execute("SELECT transaction_id FROM code_file_transactions WHERE project_id=? AND state IN ('prepared','recovery_conflict') LIMIT 1", (project_id,)).fetchone()
        if pending:
            raise CodeConflictError('An interrupted file transaction needs recovery: ' + pending[0])

    def _state(self, transaction_id, state, error=None):
        with self.projects._connect() as db, db:
            db.execute('UPDATE code_file_transactions SET state=?,error=? WHERE transaction_id=?', (state, error, transaction_id))

    def _recover_one(self, row):
        transaction_id = row['transaction_id']
        try:
            root = Path(row['root_ref'])
            with self.projects._connect() as db:
                items = db.execute('SELECT * FROM code_file_transaction_items WHERE transaction_id=? ORDER BY ordinal', (transaction_id,)).fetchall()
            staged = []
            for item in items:
                before = bytes(item['before_blob']) if item['before_blob'] is not None else None
                after = bytes(item['after_blob'])
                if digest(before) != item['before_sha'] or digest(after) != item['after_sha']:
                    raise CodeConflictError('Recovery journal checksum mismatch: ' + item['path'])
                path = resolve_scoped_project_path(root, item['path'])
                current = self.projects._file_sha256(path) if path.is_file() else None
                if current not in (item['before_sha'], item['after_sha']):
                    raise CodeConflictError('External edit preserved during recovery: ' + item['path'])
                staged.append((path, before, after, current))
            # All participants are checked before compensating any file.
            for path, before, after, current in staged:
                if current == digest(before):
                    continue
                if before is None:
                    if self.projects._file_sha256(path) != digest(after):
                        raise CodeConflictError('File changed during recovery')
                    path.unlink()
                else:
                    if self.projects._file_sha256(path) != digest(after):
                        raise CodeConflictError('File changed during recovery')
                    atomic_write_bytes(path, before)
            for path, before, _, _ in staged:
                current = self.projects._file_sha256(path) if path.is_file() else None
                if current != digest(before):
                    raise CodeConflictError('File changed before recovery verification')
            self._state(transaction_id, 'rolled_back')
            return True
        except Exception as exc:
            self._state(transaction_id, 'recovery_conflict', str(exc))
            return False

    def recover(self, project_id=None):
        if project_id is not None:
            self.projects.get_project_root(project_id)
        with self.projects.lock, self.projects._connect() as db:
            sql = "SELECT * FROM code_file_transactions WHERE state IN ('prepared','recovery_conflict')"
            rows = db.execute(sql + (' AND project_id=?' if project_id is not None else ''), (project_id,) if project_id is not None else ()).fetchall()
            for row in rows:
                with _ACTIVE_LOCK:
                    active = row['transaction_id'] in _ACTIVE
                if active:
                    continue
                if row['owner_pid'] and row['owner_pid'] != os.getpid():
                    try:
                        if abs(psutil.Process(row['owner_pid']).create_time() - row['owner_started']) < .01:
                            continue
                    except psutil.NoSuchProcess:
                        pass
                    except (psutil.AccessDenied, TypeError):
                        continue
                self._recover_one(row)
            return self.list(project_id)

    def replace(self, project_id, root, items, *, actor, changeset_id=None, final_status=None, operation_id=None):
        """Prepare durably, replace/verify, then commit bookkeeping in one SQLite transaction."""
        with self.projects.lock:
            self.assert_writable(project_id)
            if not items or len(items) > 500 or sum(len(i['after']) + len(i['before'] or b'') for i in items) > 64 * 1024 * 1024:
                raise ValueError('File transaction exceeds its bounded group size')
            seen = set()
            for item in items:
                path = resolve_scoped_project_path(root, item['path'])
                key = str(path).casefold()
                if key in seen:
                    raise ValueError('Duplicate path in file transaction')
                seen.add(key)
                current = path.read_bytes() if path.is_file() else None
                if current != item['before']:
                    raise CodeConflictError('File changed before journal preparation: ' + item['path'])
            transaction_id = uuid.uuid4().hex
            with _ACTIVE_LOCK:
                _ACTIVE.add(transaction_id)
            try:
                with self.projects._connect() as db, db:
                    db.execute('BEGIN IMMEDIATE')
                    if db.execute("SELECT 1 FROM code_file_transactions WHERE project_id=? AND state IN ('prepared','recovery_conflict')",(project_id,)).fetchone():
                        raise CodeConflictError('Another file transaction needs completion or recovery')
                    for item in items:
                        path=resolve_scoped_project_path(root,item['path'])
                        if (path.read_bytes() if path.is_file() else None)!=item['before']:
                            raise CodeConflictError('File changed before transaction admission')
                    row = db.execute('SELECT status FROM code_changesets WHERE changeset_id=?', (changeset_id,)).fetchone() if changeset_id else None
                    db.execute('INSERT INTO code_file_transactions '
                               '(transaction_id,project_id,root_ref,state,changeset_id,initial_status,final_status,actor,created_at_ms,owner_pid,owner_started,operation_id) '
                               'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                               (transaction_id,project_id,str(Path(root).resolve()),'prepared',changeset_id,row[0] if row else None,final_status,actor,self.projects.clock(),os.getpid(),psutil.Process().create_time(),operation_id))
                    for index, item in enumerate(items):
                        db.execute('INSERT INTO code_file_transaction_items VALUES (?,?,?,?,?,?,?,?,?)',
                                   (transaction_id,index,item['path'],item['before'],item['after'],digest(item['before']),digest(item['after']),item['encoding'],item['line_ending']))
                for item in items:
                    path = resolve_scoped_project_path(root, item['path'])
                    if (path.read_bytes() if path.is_file() else None) != item['before']:
                        raise CodeConflictError('File changed during group apply: ' + item['path'])
                    atomic_write_bytes(path, item['after'])
                for item in items:
                    path = resolve_scoped_project_path(root, item['path'])
                    if self.projects._file_sha256(path) != digest(item['after']):
                        raise CodeConflictError('File group changed before commit: ' + item['path'])
                with self.projects._connect() as db, db:
                    for item in items:
                        self.projects._insert_snapshot(db, project_id=project_id, relative_path=item['path'],
                            sha256=digest(item['after']), encoding=item['encoding'], line_ending=item['line_ending'],
                            raw_blob=item['after'], actor=actor, operation_id=operation_id or 'transaction:' + transaction_id)
                    if changeset_id:
                        value = db.execute('SELECT changeset_json FROM code_changesets WHERE changeset_id=?', (changeset_id,)).fetchone()
                        changeset = json.loads(value[0]); changeset['status'] = final_status
                        db.execute('UPDATE code_changesets SET status=?,changeset_json=? WHERE changeset_id=?', (final_status,json.dumps(changeset,ensure_ascii=False),changeset_id))
                    db.execute("UPDATE code_file_transactions SET state='committed' WHERE transaction_id=?", (transaction_id,))
            except Exception:
                with self.projects._connect() as db:
                    row = db.execute('SELECT * FROM code_file_transactions WHERE transaction_id=?', (transaction_id,)).fetchone()
                if row is not None:
                    self._recover_one(row)
                raise
            finally:
                with _ACTIVE_LOCK:
                    _ACTIVE.discard(transaction_id)
            return transaction_id

    def acknowledge(self, transaction_id, expected_hashes, preserve_external):
        if preserve_external is not True or not isinstance(expected_hashes,dict):
            raise ValueError('Explicit preserve_external and current file hashes are required')
        with self.projects.lock, self.projects._connect() as db:
            row=db.execute('SELECT * FROM code_file_transactions WHERE transaction_id=?',(transaction_id,)).fetchone()
            if not row or row['state']!='recovery_conflict':
                raise CodeConflictError('Transaction is not awaiting conflict review')
            actual={}
            for item in db.execute('SELECT path FROM code_file_transaction_items WHERE transaction_id=?',(transaction_id,)):
                path=resolve_scoped_project_path(row['root_ref'],item['path'])
                actual[item['path']]=self.projects._file_sha256(path) if path.is_file() else None
            if actual!=expected_hashes:
                raise CodeConflictError('Files changed since recovery review')
            self._state(transaction_id,'reconciled','Current files preserved by explicit review: '+json.dumps(actual,sort_keys=True))
            return {'transaction_id':transaction_id,'state':'reconciled','preserved_hashes':actual}
