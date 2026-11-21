"""Transactional EventHub with Per-Conversation Monotonic Sequence, SSE Last-Event-ID Replay & Flight Recorder (PR-17 / ORCH-03 / E2E-11).

Enforces Invariants:
- ORCH-03: Every RuntimeEvent v1 has a strictly monotonic per-conversation integer seq (1, 2, 3...).
  SSE reconnection via Last-Event-ID replays exact gapless events or falls back to a consistent snapshot
  when the requested seq was pruned.
- E2E-11: Flight Recorder exports the full causal trace of events and receipts with automatic secret redaction.
"""
from __future__ import annotations

from contextlib import closing
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
VALID_EVENT_TYPES = frozenset({
    'agent.created',
    'agent.updated',
    'run.queued',
    'run.started',
    'task.started',
    'task.progress',
    'tool.prepared',
    'approval.requested',
    'approval.resolved',
    'tool.dispatched',
    'tool.verified',
    'artifact.created',
    'handoff.created',
    'handoff.completed',
    'run.failed',
    'run.unknown',
    'run.completed',
    'run.cancelled',
})
SECRET_KEY_SUBSTRINGS = ('api_key', 'secret', 'token', 'password', 'authorization', 'dpapi', 'private_key')
SECRET_VALUE_RE = re.compile(r'(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|AIzaSy[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,})')


class RuntimeEventValidationError(ValueError):
    """Raised when a RuntimeEvent payload violates schemas/runtime-event.schema.json."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def redact_secrets(value: Any) -> Any:
    """Recursively redact sensitive keys and raw credential tokens from event payloads (E2E-11)."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            k_lower = str(k).lower()
            if any(sub in k_lower for sub in SECRET_KEY_SUBSTRINGS):
                cleaned[k] = '[REDACTED_SECRET]'
            else:
                cleaned[k] = redact_secrets(v)
        return cleaned
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub('[REDACTED_TOKEN]', value)
    return value


def validate_runtime_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Strictly validate a RuntimeEvent v1 against schemas/runtime-event.schema.json."""
    if not isinstance(payload, dict):
        raise RuntimeEventValidationError('RuntimeEvent must be a JSON object')

    required = {
        'schema_version',
        'event_id',
        'seq',
        'conversation_id',
        'run_id',
        'agent_id',
        'type',
        'timestamp',
        'payload',
    }
    missing = required - set(payload.keys())
    if missing:
        raise RuntimeEventValidationError(f'Missing required RuntimeEvent fields: {sorted(missing)}')
    unknown = set(payload.keys()) - required
    if unknown:
        raise RuntimeEventValidationError(f'Unknown RuntimeEvent fields: {sorted(unknown)}')

    if payload.get('schema_version') != '1.0':
        raise RuntimeEventValidationError("schema_version must be '1.0'")

    for field in ('event_id', 'conversation_id', 'run_id', 'agent_id'):
        val = payload.get(field)
        if not isinstance(val, str) or not ID_RE.fullmatch(val):
            raise RuntimeEventValidationError(f'Invalid {field}: {val!r}')

    seq = payload.get('seq')
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise RuntimeEventValidationError('seq must be an integer >= 1')

    if payload.get('type') not in VALID_EVENT_TYPES:
        raise RuntimeEventValidationError(f"Invalid event type: {payload.get('type')!r}")

    ts = payload.get('timestamp')
    if not isinstance(ts, str) or not ts.strip():
        raise RuntimeEventValidationError('timestamp must be an ISO-8601 string')

    ev_payload = payload.get('payload')
    if not isinstance(ev_payload, dict) or len(ev_payload) > 48:
        raise RuntimeEventValidationError('payload must be a JSON object with <= 48 properties')

    return copy.deepcopy(payload)


class EventHub:
    """SQLite-backed transactional event hub with per-conversation monotonic sequence & SSE replay (ORCH-03)."""

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
                    CREATE TABLE IF NOT EXISTS runtime_events (
                        event_id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        seq INTEGER NOT NULL CHECK(seq >= 1),
                        run_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        event_json TEXT NOT NULL,
                        created_at_ms INTEGER NOT NULL,
                        UNIQUE(conversation_id, seq)
                    );
                    CREATE INDEX IF NOT EXISTS idx_runtime_events_conv_seq
                        ON runtime_events(conversation_id, seq);

                    CREATE TABLE IF NOT EXISTS runtime_event_counters (
                        conversation_id TEXT PRIMARY KEY,
                        last_seq INTEGER NOT NULL DEFAULT 0,
                        min_retained_seq INTEGER NOT NULL DEFAULT 1
                    );
                    '''
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def publish_event(
        self,
        *,
        conversation_id: str,
        run_id: str,
        agent_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish a secret-redacted RuntimeEvent v1 with the next monotonic seq for conversation_id."""
        now_ms = self.clock()
        ts_iso = datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        safe_payload = redact_secrets(dict(payload or {}))

        with self.lock, self._connect() as db:
            with db:
                row = db.execute(
                    'SELECT last_seq, min_retained_seq FROM runtime_event_counters WHERE conversation_id=?',
                    (conversation_id,),
                ).fetchone()
                next_seq = (int(row['last_seq']) + 1) if row else 1
                min_retained = int(row['min_retained_seq']) if row else 1

                db.execute(
                    '''
                    INSERT OR REPLACE INTO runtime_event_counters (conversation_id, last_seq, min_retained_seq)
                    VALUES (?, ?, ?)
                    ''',
                    (conversation_id, next_seq, min_retained),
                )

                ev_id = event_id or f'evt-{conversation_id}-{next_seq}'
                event_obj = validate_runtime_event(
                    {
                        'schema_version': '1.0',
                        'event_id': ev_id,
                        'seq': next_seq,
                        'conversation_id': conversation_id,
                        'run_id': run_id,
                        'agent_id': agent_id,
                        'type': event_type,
                        'timestamp': ts_iso,
                        'payload': safe_payload,
                    }
                )
                db.execute(
                    '''
                    INSERT INTO runtime_events
                        (event_id, conversation_id, seq, run_id, agent_id, type, event_json, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        ev_id,
                        conversation_id,
                        next_seq,
                        run_id,
                        agent_id,
                        event_type,
                        json.dumps(event_obj, ensure_ascii=False),
                        now_ms,
                    ),
                )
                return event_obj

    def prune_events_before(self, conversation_id: str, min_retained_seq: int) -> None:
        """Simulate retention pruning while updating min_retained_seq so SSE reconnect triggers snapshot fallback."""
        with self.lock, self._connect() as db:
            with db:
                db.execute(
                    'DELETE FROM runtime_events WHERE conversation_id=? AND seq < ?',
                    (conversation_id, int(min_retained_seq)),
                )
                db.execute(
                    'UPDATE runtime_event_counters SET min_retained_seq=? WHERE conversation_id=?',
                    (int(min_retained_seq), conversation_id),
                )

    def replay_sse(
        self,
        conversation_id: str,
        *,
        last_event_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Replay gapless events after Last-Event-ID, or return a snapshot fallback if pruned (ORCH-03)."""
        last_seq = 0
        if last_event_id is not None:
            s_val = str(last_event_id).strip()
            if s_val.isdigit():
                last_seq = int(s_val)
            else:
                with self.lock, self._connect() as db:
                    ev_row = db.execute(
                        'SELECT seq FROM runtime_events WHERE conversation_id=? AND event_id=?',
                        (conversation_id, s_val),
                    ).fetchone()
                    last_seq = int(ev_row['seq']) if ev_row else 0

        with self.lock, self._connect() as db:
            counter = db.execute(
                'SELECT last_seq, min_retained_seq FROM runtime_event_counters WHERE conversation_id=?',
                (conversation_id,),
            ).fetchone()
            if not counter:
                return {'snapshot_required': False, 'events': [], 'sse_frames': []}

            min_retained = int(counter['min_retained_seq'])
            latest_seq = int(counter['last_seq'])
            snapshot_required = last_seq > 0 and (last_seq + 1) < min_retained

            rows = db.execute(
                '''
                SELECT event_json FROM runtime_events
                WHERE conversation_id=? AND seq > ?
                ORDER BY seq ASC
                ''',
                (conversation_id, last_seq),
            ).fetchall()
            events = [json.loads(r['event_json']) for r in rows]

        sse_frames = [
            f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            for ev in events
        ]
        result: dict[str, Any] = {
            'conversation_id': conversation_id,
            'last_seq_requested': last_seq,
            'latest_seq': latest_seq,
            'snapshot_required': snapshot_required,
            'events': events,
            'sse_frames': sse_frames,
        }
        if snapshot_required:
            result['snapshot'] = {
                'conversation_id': conversation_id,
                'min_retained_seq': min_retained,
                'latest_seq': latest_seq,
                'reason': 'requested_last_event_id_was_pruned',
            }
        return result

    def export_flight_recorder(self, conversation_id: str, *, run_id: str | None = None) -> dict[str, Any]:
        """Export a complete, secret-redacted Flight Recorder trace for a conversation/run (E2E-11)."""
        with self.lock, self._connect() as db:
            if run_id:
                rows = db.execute(
                    'SELECT event_json FROM runtime_events WHERE conversation_id=? AND run_id=? ORDER BY seq ASC',
                    (conversation_id, run_id),
                ).fetchall()
            else:
                rows = db.execute(
                    'SELECT event_json FROM runtime_events WHERE conversation_id=? ORDER BY seq ASC',
                    (conversation_id,),
                ).fetchall()
            events = [redact_secrets(json.loads(r['event_json'])) for r in rows]

        return {
            'schema_version': '1.0',
            'conversation_id': conversation_id,
            'run_id': run_id,
            'event_count': len(events),
            'events': events,
            'secrets_redacted': True,
        }
