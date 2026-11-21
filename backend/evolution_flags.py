"""Canonical feature flags and upstream manifest guards for AXX Evolution 3.0.

Invariants:
- Defaults for all Evolution 3.0 flags are OFF (False) until their phase gate passes.
- Disabling a flag blocks new dispatches for that capability without terminating
  or rolling back already-dispatched operations in flight.
- A feature flag NEVER grants execution permissions, never overrides command_mode,
  and never bypasses CommandService or ActionExecutor.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

EVOLUTION_FLAG_SPECS: dict[str, dict[str, Any]] = {
    'agent_profiles_v1': {
        'phase': 8,
        'gate': 'G8',
        'default': False,
        'description': 'Individual AgentProfile store, 24/9 canonical appearance, and N:N chat memberships.',
    },
    'team_chat_v1': {
        'phase': 11,
        'gate': 'G11',
        'default': False,
        'description': 'Multi-agent team coordination, typed handoffs, and per-conversation SSE EventHub.',
    },
    'code_studio_v1': {
        'phase': 9,
        'gate': 'G9',
        'default': False,
        'description': 'Integrated Code Studio editor, project explorer, diff viewer, and CAS PatchEngine.',
    },
    'code_execution_v1': {
        'phase': 9,
        'gate': 'G9',
        'default': False,
        'description': 'Supervised test runner and approved toolchain execution in isolated Git worktrees.',
    },
    'computer_background_v1': {
        'phase': 10,
        'gate': 'G10',
        'default': False,
        'description': 'Background Interaction Router, AttentionGuardian, Window/Desktop leases, and virtual cursor telemetry.',
    },
    'computer_vm_v1': {
        'phase': 10,
        'gate': 'G10',
        'default': False,
        'description': 'Isolated VM / Windows Sandbox workspace provider with capability probing.',
    },
    'magic_scene_v2': {
        'phase': 2,
        'gate': 'G2',
        'default': False,
        'description': 'SceneDocument v2 with incremental CAS ScenePatch, undo/redo inverse patches, and Diagram Studio.',
    },
    'asset_gate_mcp_v1': {
        'phase': 5,
        'gate': 'G5',
        'default': False,
        'description': 'Content-addressed 3D Asset Registry with license provenance and read-only Asset Gate discovery.',
    },
    'diorama_v1': {
        'phase': 5,
        'gate': 'G5',
        'default': False,
        'description': 'Diorama render mode, per-entity QA checks, and optional Codevember material presets for Magic Pen.',
    },
    'cad_worker_v1': {
        'phase': 3,
        'gate': 'G3',
        'default': False,
        'description': 'Parametric CAD Studio worker producing verified STEP/GLB solids and dimensional diagnostics.',
    },
    'motion_worker_v1': {
        'phase': 4,
        'gate': 'G4',
        'default': False,
        'description': 'Deterministic Motion/Simulation timeline, freeze(t) frame inspection, and synchronized TTS narration.',
    },
    'openvino_worker_v1': {
        'phase': 6,
        'gate': 'G6',
        'default': False,
        'description': 'Opt-in local OpenVINO auxiliary inference worker and isolated splat preview mode.',
    },
}


class StaleFlagRevisionError(ValueError):
    """Raised when a concurrent update modified a feature flag revision."""


class FeatureDisabledError(PermissionError):
    """Raised when a new operation targets a capability whose feature flag is OFF."""


class EvolutionFeatureFlags:
    """Thread-safe, SQLite-backed feature flag registry with CAS revisions and audit log."""

    def __init__(self, db_path: str | Path = ':memory:', clock=None):
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
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS evolution_feature_flags (
                        flag_id TEXT PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
                        phase INTEGER NOT NULL,
                        gate TEXT NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        reason TEXT NOT NULL DEFAULT '',
                        gate_receipt_ref TEXT NOT NULL DEFAULT ''
                    )
                    '''
                )
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS evolution_flag_audit (
                        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        flag_id TEXT NOT NULL,
                        previous_enabled INTEGER NOT NULL,
                        new_enabled INTEGER NOT NULL,
                        revision INTEGER NOT NULL,
                        actor TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        gate_receipt_ref TEXT NOT NULL,
                        changed_at_ms INTEGER NOT NULL
                    )
                    '''
                )
                for flag_id, spec in EVOLUTION_FLAG_SPECS.items():
                    db.execute(
                        '''
                        INSERT OR IGNORE INTO evolution_feature_flags
                            (flag_id, enabled, revision, phase, gate, updated_at_ms, reason, gate_receipt_ref)
                        VALUES (?, ?, 1, ?, ?, ?, 'initial_baseline_default_off', '')
                        ''',
                        (flag_id, 1 if spec['default'] else 0, spec['phase'], spec['gate'], now),
                    )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def is_enabled(self, flag_id: str) -> bool:
        if flag_id not in EVOLUTION_FLAG_SPECS:
            raise ValueError(f'Unknown Evolution 3.0 feature flag: {flag_id}')
        with self.lock, self._connect() as db:
            row = db.execute(
                'SELECT enabled FROM evolution_feature_flags WHERE flag_id=?',
                (flag_id,),
            ).fetchone()
            return bool(row and row['enabled'] == 1)

    def require_enabled_for_new_dispatch(self, flag_id: str) -> None:
        """Gate new dispatches when flag is OFF; never called to kill already-dispatched work."""
        if not self.is_enabled(flag_id):
            spec = EVOLUTION_FLAG_SPECS.get(flag_id, {})
            raise FeatureDisabledError(
                f"FEATURE_DISABLED: '{flag_id}' (Phase {spec.get('phase')}, Gate {spec.get('gate')}) is disabled."
            )

    def get_flag(self, flag_id: str) -> dict[str, Any]:
        if flag_id not in EVOLUTION_FLAG_SPECS:
            raise ValueError(f'Unknown Evolution 3.0 feature flag: {flag_id}')
        spec = EVOLUTION_FLAG_SPECS[flag_id]
        with self.lock, self._connect() as db:
            row = db.execute(
                '''
                SELECT flag_id, enabled, revision, phase, gate, updated_at_ms, reason, gate_receipt_ref
                FROM evolution_feature_flags WHERE flag_id=?
                ''',
                (flag_id,),
            ).fetchone()
            return {
                'flag_id': row['flag_id'],
                'enabled': bool(row['enabled']),
                'revision': int(row['revision']),
                'phase': int(row['phase']),
                'gate': row['gate'],
                'description': spec['description'],
                'updated_at_ms': int(row['updated_at_ms']),
                'reason': row['reason'],
                'gate_receipt_ref': row['gate_receipt_ref'],
                'grants_permissions': False,
            }

    def list_flags(self) -> list[dict[str, Any]]:
        with self.lock:
            return [self.get_flag(flag_id) for flag_id in sorted(EVOLUTION_FLAG_SPECS)]

    def set_flag(
        self,
        flag_id: str,
        enabled: bool,
        *,
        expected_revision: int | None = None,
        actor: str = 'owner',
        reason: str = '',
        gate_receipt_ref: str = '',
    ) -> dict[str, Any]:
        if flag_id not in EVOLUTION_FLAG_SPECS:
            raise ValueError(f'Unknown Evolution 3.0 feature flag: {flag_id}')
        if type(enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError('actor must be a non-empty string')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute(
                    'SELECT enabled, revision FROM evolution_feature_flags WHERE flag_id=?',
                    (flag_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f'Missing flag row: {flag_id}')
                current_rev = int(row['revision'])
                if expected_revision is not None and current_rev != expected_revision:
                    raise StaleFlagRevisionError(
                        f'stale_revision for {flag_id}: expected {expected_revision}, actual {current_rev}'
                    )
                new_rev = current_rev + 1
                new_val = 1 if enabled else 0
                cursor = db.execute(
                    '''
                    UPDATE evolution_feature_flags
                    SET enabled=?, revision=?, updated_at_ms=?, reason=?, gate_receipt_ref=?
                    WHERE flag_id=? AND revision=?
                    ''',
                    (new_val, new_rev, now, str(reason)[:500], str(gate_receipt_ref)[:240], flag_id, current_rev),
                )
                if cursor.rowcount != 1:
                    raise StaleFlagRevisionError(f'stale_revision conflict updating {flag_id}')
                db.execute(
                    '''
                    INSERT INTO evolution_flag_audit
                        (flag_id, previous_enabled, new_enabled, revision, actor, reason, gate_receipt_ref, changed_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (flag_id, int(row['enabled']), new_val, new_rev, actor.strip()[:120], str(reason)[:500], str(gate_receipt_ref)[:240], now),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_flag(flag_id)

    def audit_history(self, flag_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            if flag_id:
                rows = db.execute(
                    '''
                    SELECT audit_id, flag_id, previous_enabled, new_enabled, revision, actor, reason, gate_receipt_ref, changed_at_ms
                    FROM evolution_flag_audit WHERE flag_id=? ORDER BY audit_id DESC LIMIT ?
                    ''',
                    (flag_id, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = db.execute(
                    '''
                    SELECT audit_id, flag_id, previous_enabled, new_enabled, revision, actor, reason, gate_receipt_ref, changed_at_ms
                    FROM evolution_flag_audit ORDER BY audit_id DESC LIMIT ?
                    ''',
                    (max(1, min(limit, 500)),),
                ).fetchall()
            return [
                {
                    'audit_id': int(r['audit_id']),
                    'flag_id': r['flag_id'],
                    'previous_enabled': bool(r['previous_enabled']),
                    'new_enabled': bool(r['new_enabled']),
                    'revision': int(r['revision']),
                    'actor': r['actor'],
                    'reason': r['reason'],
                    'gate_receipt_ref': r['gate_receipt_ref'],
                    'changed_at_ms': int(r['changed_at_ms']),
                }
                for r in rows
            ]


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def verify_upstream_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Validate upstream-lock.json structure, commit SHA pinning discipline, and GPL isolation."""
    path = Path(manifest_path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != '1.0' or not isinstance(payload.get('entries'), list):
        raise ValueError('Invalid upstream-lock.json schema')
    verified_count = 0
    unverified_count = 0
    for entry in payload['entries']:
        repo = entry.get('repository', '')
        if not isinstance(repo, str) or not repo.startswith('https://github.com/'):
            raise ValueError(f'Invalid upstream repository URL: {repo}')
        if entry.get('verified_commit') is True:
            commit = entry.get('commit')
            if not isinstance(commit, str) or len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
                raise ValueError(f'Verified upstream entry must have a 40-hex commit SHA: {repo}')
            verified_count += 1
        else:
            if entry.get('commit') is not None:
                raise ValueError(f'Unverified upstream entry cannot claim a pinned commit: {repo}')
            unverified_count += 1
        if entry.get('label') == 'SOMA' and entry.get('import_status') == 'copied_into_mit_core':
            raise ValueError('GPL-3.0 SOMA code cannot be copied directly into AXX MIT core')
    return {
        'valid': True,
        'total_entries': len(payload['entries']),
        'verified_commits': verified_count,
        'pending_pin_entries': unverified_count,
    }
