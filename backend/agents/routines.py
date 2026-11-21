"""Autonomous Scheduled Routines with Microphone/Host-Input Block and Import Pause Guard (PR-19 / E2E-07).

Enforces Invariants:
- E2E-07: Autonomous routines can never request or auto-activate 'microphone' or 'host_input'
  capabilities.
- Imported routines ALWAYS start paused (enabled=False, status='paused_on_import') until the user
  explicitly enables them.
- Any routine execution that proposes a workspace or external mutation pauses in 'awaiting_approval'
  and generates an approval card instead of mutating silently.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
FORBIDDEN_ROUTINE_CAPABILITIES = frozenset({'microphone', 'host_input', 'audio_capture', 'sendinput_physical'})


class RoutineSecurityError(PermissionError):
    """Raised when an autonomous routine requests forbidden capabilities like microphone or host_input (E2E-07)."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class AutonomousRoutineService:
    """SQLite-backed autonomous routine manager enforcing E2E-07 privacy and approval invariants."""

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
                    CREATE TABLE IF NOT EXISTS autonomous_routines (
                        routine_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        conversation_id TEXT NOT NULL,
                        schedule_spec TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                        requires_approval INTEGER NOT NULL DEFAULT 1 CHECK(requires_approval IN (0, 1)),
                        capabilities_json TEXT NOT NULL,
                        last_run_at_ms INTEGER,
                        next_run_at_ms INTEGER,
                        status TEXT NOT NULL
                    );
                    '''
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def register_routine(
        self,
        *,
        routine_id: str,
        agent_id: str,
        conversation_id: str,
        schedule_spec: str,
        requested_capabilities: list[str] | None = None,
        enabled: bool = True,
        requires_approval: bool = True,
        imported_from_package: bool = False,
    ) -> dict[str, Any]:
        for field, val in (('routine_id', routine_id), ('agent_id', agent_id), ('conversation_id', conversation_id)):
            if not isinstance(val, str) or not ID_RE.fullmatch(val):
                raise ValueError(f'Invalid {field}: {val!r}')

        caps = [str(c).strip().lower() for c in (requested_capabilities or [])]
        forbidden = [c for c in caps if c in FORBIDDEN_ROUTINE_CAPABILITIES]
        if forbidden:
            raise RoutineSecurityError(
                f'Autonomous routine {routine_id!r} cannot request forbidden capabilities (E2E-07): {forbidden}'
            )

        # Imported routines ALWAYS start disabled/paused until explicitly enabled by the user (E2E-07)
        if imported_from_package:
            effective_enabled = False
            status = 'paused_on_import'
        else:
            effective_enabled = bool(enabled)
            status = 'scheduled' if effective_enabled else 'paused'

        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO autonomous_routines
                        (routine_id, agent_id, conversation_id, schedule_spec, enabled,
                         requires_approval, capabilities_json, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        routine_id,
                        agent_id,
                        conversation_id,
                        schedule_spec,
                        1 if effective_enabled else 0,
                        1 if requires_approval else 0,
                        json.dumps(caps),
                        status,
                    ),
                )
        return self.get_routine(routine_id)

    def get_routine(self, routine_id: str) -> dict[str, Any]:
        with self.lock, self._connect() as db:
            row = db.execute(
                'SELECT * FROM autonomous_routines WHERE routine_id=?',
                (routine_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'Routine not found: {routine_id}')
            return {
                'routine_id': row['routine_id'],
                'agent_id': row['agent_id'],
                'conversation_id': row['conversation_id'],
                'schedule_spec': row['schedule_spec'],
                'enabled': bool(row['enabled']),
                'requires_approval': bool(row['requires_approval']),
                'capabilities': json.loads(row['capabilities_json']),
                'last_run_at_ms': row['last_run_at_ms'],
                'status': row['status'],
            }

    def trigger_routine(
        self,
        routine_id: str,
        *,
        proposes_mutation: bool = True,
    ) -> dict[str, Any]:
        """Trigger a scheduled routine; pauses in awaiting_approval if it proposes any mutation (E2E-07)."""
        routine = self.get_routine(routine_id)
        if not routine['enabled']:
            return {
                'routine_id': routine_id,
                'executed': False,
                'status': routine['status'],
                'reason': 'routine_is_disabled_or_paused',
                'activated_microphone': False,
                'activated_host_input': False,
            }

        now = self.clock()
        if proposes_mutation or routine['requires_approval']:
            next_status = 'awaiting_approval'
            executed = False
        else:
            next_status = 'completed_readonly'
            executed = True

        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    'UPDATE autonomous_routines SET last_run_at_ms=?, status=? WHERE routine_id=?',
                    (now, next_status, routine_id),
                )

        return {
            'routine_id': routine_id,
            'executed': executed,
            'status': next_status,
            'approval_card_created': next_status == 'awaiting_approval',
            'activated_microphone': False,
            'activated_host_input': False,
        }
