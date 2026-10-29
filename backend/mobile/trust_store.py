import hashlib
import json
import secrets
import sqlite3
import time
import uuid
import threading
from contextlib import contextmanager
from pathlib import Path


PAIRING_TTL_SECONDS = 120
ALLOWED_SCOPES = frozenset({
    "query", "voice", "tools.control", "files.read", "files.write", "admin"
})


class PairingError(ValueError):
    pass


class CommandConflict(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class MobileTrustStore:
    """Device grants and command admission journal in Axx's existing SQLite DB."""

    def __init__(self, db_path):
        self.db_path = str(Path(db_path))
        self._pairings = {}
        self._pairing_lock = threading.Lock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mobile_pairings (
                    pairing_hash TEXT PRIMARY KEY,
                    scopes_json TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    consumed_at REAL
                );
                CREATE TABLE IF NOT EXISTS mobile_devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    credential_hash TEXT NOT NULL UNIQUE,
                    scopes_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS mobile_access_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mobile_commands (
                    device_id TEXT NOT NULL REFERENCES mobile_devices(device_id),
                    command_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    accepted_at REAL NOT NULL,
                    PRIMARY KEY (device_id, command_id)
                );
                CREATE TABLE IF NOT EXISTS mobile_command_results (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    result TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mobile_work_requests (
                    operation_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL REFERENCES mobile_devices(device_id),
                    command_id TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)

    @staticmethod
    def _scopes(scopes):
        values = sorted(set(scopes))
        if not values or not set(values) <= ALLOWED_SCOPES:
            raise ValueError("Unsupported mobile permission scope")
        return values

    def create_pairing(self, scopes=("query", "voice"), now=None):
        scopes = self._scopes(scopes)
        code = secrets.token_urlsafe(24)
        created_at = time.time() if now is None else float(now)
        with self._connect() as db:
            db.execute(
                "INSERT INTO mobile_pairings(pairing_hash, scopes_json, expires_at) VALUES(?,?,?)",
                (_digest(code), json.dumps(scopes), created_at + PAIRING_TTL_SECONDS),
            )
        with self._pairing_lock:
            self._pairings[_digest(code)] = time.monotonic() + PAIRING_TTL_SECONDS
        return code

    def consume_pairing(self, code, name, now=None, *, credential=None):
        if not isinstance(code, str) or not code or not isinstance(name, str) or not name.strip():
            raise PairingError("Pairing code and device name are required")
        consumed_at = time.time() if now is None else float(now)
        with self._pairing_lock:
            deadline = self._pairings.pop(_digest(code), None)
        if deadline is None or time.monotonic() >= deadline:
            raise PairingError('Pairing code is not active in this desktop session')
        new_credential = secrets.token_urlsafe(32)
        device_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT scopes_json, expires_at, consumed_at FROM mobile_pairings WHERE pairing_hash=?",
                (_digest(code),),
            ).fetchone()
            if row is None or row["consumed_at"] is not None or consumed_at >= row["expires_at"]:
                db.rollback()
                raise PairingError("Pairing code is invalid, expired, or already used")
            if credential is not None:
                device = db.execute(
                    "SELECT device_id,scopes_json FROM mobile_devices WHERE credential_hash=? AND revoked_at IS NULL",
                    (_digest(credential),),
                ).fetchone()
                if device is None:
                    raise PairingError('This phone was revoked; forget the PC before pairing again')
                device_id, scopes = device['device_id'], device['scopes_json']
            else:
                credential, scopes = new_credential, row['scopes_json']
                db.execute(
                    "INSERT INTO mobile_devices(device_id,name,credential_hash,scopes_json,created_at) VALUES(?,?,?,?,?)",
                    (device_id, name.strip()[:80], _digest(credential), scopes, consumed_at),
                )
            db.execute("UPDATE mobile_pairings SET consumed_at=? WHERE pairing_hash=? AND consumed_at IS NULL",
                       (consumed_at, _digest(code)))
            db.commit()
        return {"device_id": device_id, "credential": credential,
                "scopes": json.loads(scopes)}

    def invalidate_pairings(self):
        with self._pairing_lock:
            self._pairings.clear()

    def access_settings(self):
        with self._connect() as db:
            rows = db.execute("SELECT key,value FROM mobile_access_settings WHERE key IN ('always_on','port','network_mode')").fetchall()
        values = {row['key']: row['value'] for row in rows}
        try:
            port = int(values.get('port', '0'))
        except ValueError:
            port = 0
        return {'always_on': values.get('always_on') == '1', 'port': port if 0 <= port <= 65535 else 0,
                'network_mode': values.get('network_mode') if values.get('network_mode') in ('lan', 'tailscale') else 'lan'}

    def set_network_mode(self, mode):
        from .network import MobileNetwork
        MobileNetwork.validate_mode(mode)
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO mobile_access_settings(key,value) VALUES('network_mode',?)", (mode,))

    def set_access_settings(self, *, always_on, port=None):
        if type(always_on) is not bool or (port is not None and (type(port) is not int or not 1 <= port <= 65535)):
            raise ValueError('Invalid mobile access settings')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("INSERT OR REPLACE INTO mobile_access_settings(key,value) VALUES('always_on',?)",
                       ('1' if always_on else '0',))
            if port is not None:
                db.execute("INSERT OR REPLACE INTO mobile_access_settings(key,value) VALUES('port',?)", (str(port),))
            db.commit()

    def authorize(self, credential, required_scope):
        return self.device_for(credential, required_scope) is not None

    def device_for(self, credential, required_scope):
        if not isinstance(credential, str) or not credential:
            return None
        with self._connect() as db:
            row = db.execute(
                "SELECT device_id,scopes_json FROM mobile_devices WHERE credential_hash=? AND revoked_at IS NULL",
                (_digest(credential),),
            ).fetchone()
        return row['device_id'] if row and required_scope in json.loads(row['scopes_json']) else None

    def revoke(self, device_id, now=None):
        revoked_at = time.time() if now is None else float(now)
        with self._connect() as db:
            cursor = db.execute("UPDATE mobile_devices SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",
                                (revoked_at, device_id))
        return cursor.rowcount == 1

    def set_tool_permission(self, device_id, enabled):
        return self._set_permission(device_id,enabled,'tools.control')

    def set_input_permission(self, device_id, enabled):
        return self._set_permission(device_id,enabled,'input.control')

    def set_file_permissions(self, device_id, read, write, config_payload=None):
        if not isinstance(device_id, str) or type(read) is not bool or type(write) is not bool:
            raise ValueError('Invalid file permissions')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT scopes_json FROM mobile_devices WHERE device_id=? AND revoked_at IS NULL', (device_id,)).fetchone()
            if not row:
                raise ValueError('Dispositivo no autorizado')
            scopes = set(json.loads(row['scopes_json'])) - {'files.read', 'files.write'}
            scopes.update(scope for scope, enabled in (('files.read', read), ('files.write', write)) if enabled)
            db.execute('UPDATE mobile_devices SET scopes_json=? WHERE device_id=?', (json.dumps(sorted(scopes)), device_id))
            if config_payload is not None:
                db.execute('INSERT OR REPLACE INTO mobile_file_config VALUES(?,?)', (device_id, config_payload))
                db.execute('DELETE FROM mobile_file_refs WHERE device_id=?', (device_id,))
            db.commit()
        return sorted(scopes)

    def _set_permission(self, device_id, enabled, scope):
        if not isinstance(device_id,str) or type(enabled) is not bool:raise ValueError('Invalid device permission')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT scopes_json FROM mobile_devices WHERE device_id=? AND revoked_at IS NULL',(device_id,)).fetchone()
            if not row:raise ValueError('Dispositivo no autorizado')
            scopes=set(json.loads(row['scopes_json']))
            if enabled:scopes.add(scope)
            else:scopes.discard(scope)
            db.execute('UPDATE mobile_devices SET scopes_json=? WHERE device_id=?',(json.dumps(sorted(scopes)),device_id))
            db.commit()
        return sorted(scopes)

    def devices(self):
        with self._connect() as db:
            rows = db.execute(
                "SELECT device_id,name,scopes_json,created_at,revoked_at FROM mobile_devices ORDER BY created_at"
            ).fetchall()
        return [{"device_id": row["device_id"], "name": row["name"],
                 "scopes": json.loads(row["scopes_json"]), "created_at": row["created_at"],
                 "revoked": row["revoked_at"] is not None} for row in rows]

    def record_work(self, operation_id, device_id, command_id, inputs):
        encoded = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT device_id,command_id,inputs_json FROM mobile_work_requests WHERE operation_id=?',
                             (operation_id,)).fetchone()
            if row:
                if row['device_id'] != device_id or row['command_id'] != command_id or row['inputs_json'] != encoded:
                    raise ValueError('Work operation belongs to another request')
            else:
                db.execute('INSERT INTO mobile_work_requests VALUES(?,?,?,?,?)',
                           (operation_id, device_id, command_id, encoded, time.time()))
            db.commit()

    def work_request(self, operation_id):
        with self._connect() as db:
            row = db.execute('SELECT * FROM mobile_work_requests WHERE operation_id=?', (operation_id,)).fetchone()
        return ({'operation_id': row['operation_id'], 'device_id': row['device_id'],
                 'command_id': row['command_id'], 'inputs': json.loads(row['inputs_json']),
                 'created_at': row['created_at']} if row else None)

    def pending_work_requests(self):
        with self._connect() as db:
            rows = db.execute('SELECT * FROM mobile_work_requests WHERE created_at>? ORDER BY created_at DESC LIMIT 30',
                              (time.time() - 600,)).fetchall()
        return [{'operation_id': row['operation_id'], 'device_id': row['device_id'],
                 'command_id': row['command_id'], 'inputs': json.loads(row['inputs_json']),
                 'created_at': row['created_at']} for row in rows]

    def admit_command(self, device_id, command_id, payload, task_id=None, now=None):
        if not isinstance(command_id, str) or not command_id.strip() or len(command_id) > 128:
            raise ValueError("command_id must be a non-empty string up to 128 characters")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        payload_hash = _digest(canonical)
        accepted_at = time.time() if now is None else float(now)
        new_task_id = task_id or str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            device = db.execute("SELECT revoked_at FROM mobile_devices WHERE device_id=?", (device_id,)).fetchone()
            if device is None or device["revoked_at"] is not None:
                db.rollback()
                raise PairingError("Device is not authorized")
            inserted = db.execute("INSERT OR IGNORE INTO mobile_commands(device_id,command_id,payload_hash,task_id,accepted_at) VALUES(?,?,?,?,?)",
                       (device_id, command_id, payload_hash, new_task_id, accepted_at))
            row = db.execute("SELECT payload_hash,task_id FROM mobile_commands WHERE device_id=? AND command_id=?",
                             (device_id, command_id)).fetchone()
            if inserted.rowcount:
                db.execute('INSERT INTO mobile_command_results VALUES(?,?,?,?)', (new_task_id, 'admitted', None, accepted_at))
            db.commit()
        if row["payload_hash"] != payload_hash:
            raise CommandConflict("command_id was already admitted with a different payload")
        return {"command_id": command_id, "task_id": row["task_id"],
                "payload_hash": payload_hash, "duplicate": inserted.rowcount == 0}

    def finish_command(self, task_id, state, result=None):
        if state not in ('running', 'completed', 'failed', 'outcome_unknown'):
            raise ValueError('Invalid task state')
        with self._connect() as db:
            db.execute('UPDATE mobile_command_results SET state=?,result=?,updated_at=? WHERE task_id=?',
                       (state, json.dumps(result, ensure_ascii=False) if result is not None else None, time.time(), task_id))

    def recover_commands(self):
        with self._connect() as db:
            db.execute("UPDATE mobile_command_results SET state='outcome_unknown' WHERE state IN ('admitted','running')")

    def command(self, device_id, command_id):
        with self._connect() as db:
            row = db.execute('''SELECT c.command_id,c.task_id,c.payload_hash,r.state,r.result,r.updated_at
                FROM mobile_commands c JOIN mobile_command_results r USING(task_id)
                WHERE c.device_id=? AND c.command_id=?''', (device_id, command_id)).fetchone()
        if not row:
            return None
        result = dict(row)
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result
