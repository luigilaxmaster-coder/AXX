"""Resource Leases with Monotonic Fencing Tokens and Window Identity Verification (PR-15 / PC-02 / PC-03).

Enforces Invariants:
- I-04 / PC-02: Every mutable resource ('host_input', 'window', 'browser_profile', 'workspace_write',
  'repo_branch', 'gpu_heavy', 'vm_instance', 'microphone', 'remote_worker') requires an active
  ResourceLease v1 with a strictly monotonic integer fencing_token.
- Stale fencing tokens from preempted or timed-out runs are rejected before any side effect occurs.
- PC-03: Window targets are bound by composite identity (hwnd + pid + process_start_ms + class_name);
  if a window closes or its handle is recycled by another process, execution aborts immediately.
"""
from __future__ import annotations

from contextlib import closing
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
VALID_RESOURCE_TYPES = frozenset({
    'host_input',
    'window',
    'browser_profile',
    'workspace_write',
    'repo_branch',
    'gpu_heavy',
    'vm_instance',
    'microphone',
    'remote_worker',
})
VALID_LEASE_STATUSES = frozenset({'active', 'revoking', 'released', 'expired', 'unknown'})


class LeaseValidationError(ValueError):
    """Raised when a ResourceLease payload violates schemas/workspace-lease.schema.json."""


class LeaseConflictError(RuntimeError):
    """Raised when a resource is already leased by another active run (PC-02)."""


class StaleFencingTokenError(PermissionError):
    """Raised when a worker presents an outdated, revoked, or non-matching fencing_token (PC-02)."""


class WindowIdentityMismatchError(RuntimeError):
    """Raised when a target window's hwnd/pid/process_start_ms/class_name no longer matches the leased target (PC-03)."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def validate_resource_lease(payload: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate a ResourceLease v1 against schemas/workspace-lease.schema.json."""
    if not isinstance(payload, dict):
        raise LeaseValidationError('ResourceLease must be a JSON object')

    required = {
        'schema_version',
        'lease_id',
        'owner_run_id',
        'resource_type',
        'resource_key',
        'fencing_token',
        'lease_start',
        'lease_end',
        'status',
    }
    missing = required - set(payload.keys())
    if missing:
        raise LeaseValidationError(f'Missing required ResourceLease fields: {sorted(missing)}')
    unknown = set(payload.keys()) - required
    if unknown:
        raise LeaseValidationError(f'Unknown ResourceLease fields: {sorted(unknown)}')

    if payload.get('schema_version') != '1.0':
        raise LeaseValidationError("schema_version must be '1.0'")

    for field in ('lease_id', 'owner_run_id'):
        val = payload.get(field)
        if not isinstance(val, str) or not ID_RE.fullmatch(val):
            raise LeaseValidationError(f'Invalid {field}: {val!r}')

    if payload.get('resource_type') not in VALID_RESOURCE_TYPES:
        raise LeaseValidationError(f"Invalid resource_type: {payload.get('resource_type')!r}")

    rk = payload.get('resource_key')
    if not isinstance(rk, str) or not (1 <= len(rk) <= 300):
        raise LeaseValidationError('resource_key must be 1..300 chars')

    ft = payload.get('fencing_token')
    if not isinstance(ft, int) or isinstance(ft, bool) or ft < 1:
        raise LeaseValidationError('fencing_token must be an integer >= 1')

    for dt_field in ('lease_start', 'lease_end'):
        dt_val = payload.get(dt_field)
        if not isinstance(dt_val, str) or not dt_val.strip():
            raise LeaseValidationError(f'{dt_field} must be an ISO-8601 string')

    if payload.get('status') not in VALID_LEASE_STATUSES:
        raise LeaseValidationError(f"Invalid status: {payload.get('status')!r}")

    return copy.deepcopy(payload)


def build_window_identity_key(
    *,
    hwnd: int,
    pid: int,
    process_start_ms: int,
    class_name: str,
    process_name: str = '',
) -> str:
    """Build a canonical composite identity key for a Win32 window (PC-03)."""
    if hwnd <= 0 or pid <= 0 or process_start_ms <= 0 or not class_name.strip():
        raise ValueError('hwnd, pid, process_start_ms (>0) and non-empty class_name are required')
    proc_clean = process_name.strip().lower() or 'unknown'
    cls_clean = class_name.strip()
    return f'hwnd:{int(hwnd)}:pid:{int(pid)}:start:{int(process_start_ms)}:class:{cls_clean}:proc:{proc_clean}'


def verify_window_identity(leased_resource_key: str, live_window_info: dict[str, Any]) -> bool:
    """Verify that a live Win32 window still matches the leased composite identity key (PC-03)."""
    if not live_window_info or not live_window_info.get('exists', True):
        raise WindowIdentityMismatchError(f'Target window no longer exists for lease key {leased_resource_key}')
    live_key = build_window_identity_key(
        hwnd=int(live_window_info.get('hwnd', 0)),
        pid=int(live_window_info.get('pid', 0)),
        process_start_ms=int(live_window_info.get('process_start_ms', 0)),
        class_name=str(live_window_info.get('class_name', '')),
        process_name=str(live_window_info.get('process_name', '')),
    )
    if live_key != leased_resource_key:
        raise WindowIdentityMismatchError(
            f'Window identity mismatch (handle recycled or process changed): expected={leased_resource_key}, live={live_key}'
        )
    return True


class ResourceLeaseManager:
    """SQLite-backed lease manager issuing monotonic fencing tokens per resource (PC-02)."""

    def __init__(self, db_path: str | Path = ':memory:', *, clock=None):
        self.db_path = str(db_path)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.lock = threading.RLock()
        self._persistent_conn: sqlite3.Connection | None = None
        if self.db_path == ':memory:':
            self._persistent_conn = sqlite3.connect(':memory:', check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()

    def _connect(self):
        if self._persistent_conn is not None:
            return _NullClosing(self._persistent_conn)
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return closing(conn)

    def _init_schema(self) -> None:
        with self.lock, self._connect() as db:
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS resource_leases (
                        lease_id TEXT PRIMARY KEY,
                        owner_run_id TEXT NOT NULL,
                        resource_type TEXT NOT NULL,
                        resource_key TEXT NOT NULL,
                        fencing_token INTEGER NOT NULL CHECK(fencing_token >= 1),
                        lease_start_ms INTEGER NOT NULL,
                        lease_end_ms INTEGER NOT NULL,
                        lease_json TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK(status IN ('active', 'revoking', 'released', 'expired', 'unknown'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_resource_leases_lookup
                        ON resource_leases(resource_type, resource_key, status);

                    CREATE TABLE IF NOT EXISTS resource_fencing_counters (
                        resource_type TEXT NOT NULL,
                        resource_key TEXT NOT NULL,
                        last_fencing_token INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (resource_type, resource_key)
                    );
                    '''
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def _expire_stale_leases(self, db: sqlite3.Connection, now_ms: int) -> None:
        rows = db.execute(
            "SELECT lease_id, lease_json FROM resource_leases WHERE status='active' AND lease_end_ms <= ?",
            (now_ms,),
        ).fetchall()
        for row in rows:
            data = json.loads(row['lease_json'])
            data['status'] = 'expired'
            db.execute(
                "UPDATE resource_leases SET status='expired', lease_json=? WHERE lease_id=?",
                (json.dumps(data, ensure_ascii=False), row['lease_id']),
            )

    def acquire_lease(
        self,
        *,
        lease_id: str,
        owner_run_id: str,
        resource_type: str,
        resource_key: str,
        ttl_ms: int = 60_000,
    ) -> dict[str, Any]:
        """Acquire an exclusive ResourceLease with a strictly increasing fencing_token (PC-02)."""
        if ttl_ms <= 0:
            raise ValueError('ttl_ms must be > 0')
        now_ms = self.clock()
        end_ms = now_ms + int(ttl_ms)
        start_iso = datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_iso = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        with self.lock, self._connect() as db:
            with db:
                self._expire_stale_leases(db, now_ms)
                active_row = db.execute(
                    '''
                    SELECT lease_id, owner_run_id, fencing_token FROM resource_leases
                    WHERE resource_type=? AND resource_key=? AND status IN ('active', 'revoking')
                    LIMIT 1
                    ''',
                    (resource_type, resource_key),
                ).fetchone()
                if active_row is not None:
                    raise LeaseConflictError(
                        f"Resource ({resource_type}, {resource_key}) is already leased by run "
                        f"{active_row['owner_run_id']!r} (lease_id={active_row['lease_id']})"
                    )

                counter_row = db.execute(
                    '''
                    SELECT last_fencing_token FROM resource_fencing_counters
                    WHERE resource_type=? AND resource_key=?
                    ''',
                    (resource_type, resource_key),
                ).fetchone()
                next_token = (int(counter_row['last_fencing_token']) + 1) if counter_row else 1

                db.execute(
                    '''
                    INSERT OR REPLACE INTO resource_fencing_counters (resource_type, resource_key, last_fencing_token)
                    VALUES (?, ?, ?)
                    ''',
                    (resource_type, resource_key, next_token),
                )

                payload = validate_resource_lease(
                    {
                        'schema_version': '1.0',
                        'lease_id': lease_id,
                        'owner_run_id': owner_run_id,
                        'resource_type': resource_type,
                        'resource_key': resource_key,
                        'fencing_token': next_token,
                        'lease_start': start_iso,
                        'lease_end': end_iso,
                        'status': 'active',
                    }
                )
                db.execute(
                    '''
                    INSERT INTO resource_leases
                        (lease_id, owner_run_id, resource_type, resource_key, fencing_token,
                         lease_start_ms, lease_end_ms, lease_json, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    ''',
                    (
                        lease_id,
                        owner_run_id,
                        resource_type,
                        resource_key,
                        next_token,
                        now_ms,
                        end_ms,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                return payload

    def verify_fencing_token(
        self,
        *,
        resource_type: str,
        resource_key: str,
        owner_run_id: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        """Verify that (owner_run_id, fencing_token) holds the latest active lease on (resource_type, resource_key)."""
        now_ms = self.clock()
        with self.lock, self._connect() as db:
            with db:
                self._expire_stale_leases(db, now_ms)
                counter_row = db.execute(
                    '''
                    SELECT last_fencing_token FROM resource_fencing_counters
                    WHERE resource_type=? AND resource_key=?
                    ''',
                    (resource_type, resource_key),
                ).fetchone()
                highest_token = int(counter_row['last_fencing_token']) if counter_row else 0
                if fencing_token < highest_token:
                    raise StaleFencingTokenError(
                        f'Stale fencing_token={fencing_token} for ({resource_type}, {resource_key}); '
                        f'latest fencing_token is {highest_token}'
                    )

                row = db.execute(
                    '''
                    SELECT lease_json, status, owner_run_id, fencing_token FROM resource_leases
                    WHERE resource_type=? AND resource_key=? AND fencing_token=?
                    ''',
                    (resource_type, resource_key, fencing_token),
                ).fetchone()
                if not row:
                    raise StaleFencingTokenError(
                        f'No lease found for ({resource_type}, {resource_key}) with fencing_token={fencing_token}'
                    )
                if row['status'] != 'active':
                    raise StaleFencingTokenError(
                        f"Lease on ({resource_type}, {resource_key}) with token={fencing_token} is not active (status={row['status']})"
                    )
                if row['owner_run_id'] != owner_run_id:
                    raise StaleFencingTokenError(
                        f"Lease owner mismatch: expected {row['owner_run_id']!r}, got {owner_run_id!r}"
                    )
                return json.loads(row['lease_json'])

    def release_lease(self, lease_id: str) -> dict[str, Any]:
        with self.lock, self._connect() as db:
            row = db.execute(
                'SELECT lease_json FROM resource_leases WHERE lease_id=?',
                (lease_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'Lease not found: {lease_id}')
            data = json.loads(row['lease_json'])
            data['status'] = 'released'
            with db:
                db.execute(
                    "UPDATE resource_leases SET status='released', lease_json=? WHERE lease_id=?",
                    (json.dumps(data, ensure_ascii=False), lease_id),
                )
            return data

    def preempt_and_revoke_resource(self, resource_type: str, resource_key: str) -> int:
        """Immediately revoke any active lease on (resource_type, resource_key) and advance the fencing counter (PC-02)."""
        with self.lock, self._connect() as db:
            with db:
                rows = db.execute(
                    '''
                    SELECT lease_id, lease_json FROM resource_leases
                    WHERE resource_type=? AND resource_key=? AND status IN ('active', 'revoking')
                    ''',
                    (resource_type, resource_key),
                ).fetchall()
                for row in rows:
                    data = json.loads(row['lease_json'])
                    data['status'] = 'released'
                    db.execute(
                        "UPDATE resource_leases SET status='released', lease_json=? WHERE lease_id=?",
                        (json.dumps(data, ensure_ascii=False), row['lease_id']),
                    )
                counter_row = db.execute(
                    'SELECT last_fencing_token FROM resource_fencing_counters WHERE resource_type=? AND resource_key=?',
                    (resource_type, resource_key),
                ).fetchone()
                new_token = (int(counter_row['last_fencing_token']) + 1) if counter_row else 1
                db.execute(
                    '''
                    INSERT OR REPLACE INTO resource_fencing_counters (resource_type, resource_key, last_fencing_token)
                    VALUES (?, ?, ?)
                    ''',
                    (resource_type, resource_key, new_token),
                )
                return new_token
