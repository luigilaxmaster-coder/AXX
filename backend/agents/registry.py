"""SQLite AgentRegistry store for AgentProfiles, Permissions, and Teams with CAS revisions (PR-11 / Gate G8).

Enforces Invariants:
- PRAGMA foreign_keys=ON on every connection.
- Short BEGIN IMMEDIATE transactions; never holds a DB lock across network/LLM calls.
- CAS UPDATE ... WHERE revision=? raises StaleAgentRevisionError (HTTP 409 stale_revision) on conflict (E2E-02).
- Never mutates the global AXX profile (agent-profile.js / chat_settings) when creating, updating, or disabling agents (AGENT-01).
"""
from __future__ import annotations

from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from backend.agents.policy import apply_provider_switch_policy
from backend.agents.profiles import (
    AgentProfileValidationError,
    AvatarFormAdapter,
    ID_RE,
    validate_agent_profile,
)


class StaleAgentRevisionError(ValueError):
    """Raised when a concurrent update modified an AgentProfile or Team revision (HTTP 409 stale_revision)."""


class AgentNotFoundError(LookupError):
    """Raised when an agent_id or team_id does not exist."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _behavior_json(validated: dict[str, Any]) -> str:
    return json.dumps({k: validated[k] for k in ('personality', 'autonomy', 'collaboration') if k in validated},
                      ensure_ascii=False)


def _check_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AgentProfileValidationError(f'Invalid {field}: {value!r}')
    return value


class AgentRegistry:
    """Thread-safe SQLite repository for individual AgentProfiles, grants, and reusable teams."""

    def __init__(self, db_path: str | Path = ':memory:', clock=None):
        self.db_path = str(db_path)
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.lock = threading.RLock()
        self.avatar_adapter = AvatarFormAdapter()
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
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.executescript(
                    '''
                    CREATE TABLE IF NOT EXISTS agent_profiles (
                        agent_id TEXT PRIMARY KEY,
                        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
                        name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
                        role TEXT NOT NULL CHECK(length(role) BETWEEN 1 AND 240),
                        description TEXT NOT NULL DEFAULT '',
                        instructions TEXT NOT NULL DEFAULT '',
                        appearance_json TEXT NOT NULL DEFAULT '{}',
                        intelligence_json TEXT NOT NULL DEFAULT '{}',
                        voice_json TEXT NOT NULL DEFAULT '{}',
                        workspace_json TEXT NOT NULL DEFAULT '{}',
                        permissions_json TEXT NOT NULL DEFAULT '{}',
                        limits_json TEXT NOT NULL DEFAULT '{}',
                        memory_scope TEXT NOT NULL DEFAULT 'agent',
                        enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                        draining INTEGER NOT NULL DEFAULT 0 CHECK(draining IN (0, 1)),
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        disabled_at_ms INTEGER,
                        CHECK(json_valid(appearance_json)),
                        CHECK(json_valid(intelligence_json)),
                        CHECK(json_valid(voice_json)),
                        CHECK(json_valid(workspace_json)),
                        CHECK(json_valid(permissions_json)),
                        CHECK(json_valid(limits_json))
                    );

                    CREATE TABLE IF NOT EXISTS agent_permissions (
                        grant_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
                        tool_id TEXT NOT NULL,
                        resource_pattern TEXT NOT NULL,
                        operation_kinds_json TEXT NOT NULL,
                        approval_mode TEXT NOT NULL CHECK(approval_mode IN ('ask','auto_safe','deny')),
                        expires_at_ms INTEGER,
                        granted_by TEXT NOT NULL,
                        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
                        CHECK(json_valid(operation_kinds_json))
                    );
                    CREATE INDEX IF NOT EXISTS idx_agent_perm_agent ON agent_permissions(agent_id);

                    CREATE TABLE IF NOT EXISTS agent_teams (
                        team_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        purpose TEXT NOT NULL DEFAULT '',
                        mode TEXT NOT NULL DEFAULT 'collaboration' CHECK(mode IN ('consultation', 'collaboration')),
                        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
                        created_at_ms INTEGER NOT NULL,
                        disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0, 1))
                    );

                    CREATE TABLE IF NOT EXISTS agent_team_members (
                        team_id TEXT NOT NULL REFERENCES agent_teams(team_id) ON DELETE CASCADE,
                        agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
                        role TEXT NOT NULL CHECK(role IN ('lead','member','reviewer')),
                        PRIMARY KEY(team_id, agent_id)
                    );
                    '''
                )
                # Acts 3.1 additive migration: optional personality/autonomy/collaboration sections.
                if 'behavior_json' not in {r[1] for r in db.execute('PRAGMA table_info(agent_profiles)')}:
                    db.execute("ALTER TABLE agent_profiles ADD COLUMN behavior_json TEXT NOT NULL DEFAULT '{}'")

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def create_profile(self, profile_spec: dict[str, Any]) -> dict[str, Any]:
        spec = copy.deepcopy(profile_spec)
        spec.setdefault('schema_version', '1.0')
        spec['revision'] = 1
        validated = validate_agent_profile(spec)
        now = self.clock()

        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('SELECT 1 FROM agent_profiles WHERE agent_id=?', (validated['agent_id'],)).fetchone():
                    raise AgentProfileValidationError(f"AgentProfile '{validated['agent_id']}' already exists")
                db.execute(
                    '''
                    INSERT INTO agent_profiles
                        (agent_id, revision, name, role, description, instructions,
                         appearance_json, intelligence_json, voice_json, workspace_json,
                         permissions_json, limits_json, memory_scope, enabled, draining,
                         created_at_ms, updated_at_ms, disabled_at_ms, behavior_json)
                    VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    ''',
                    (
                        validated['agent_id'],
                        validated['name'],
                        validated['role'],
                        validated['description'],
                        validated['instructions'],
                        json.dumps(validated['appearance'], ensure_ascii=False),
                        json.dumps(validated['intelligence'], ensure_ascii=False),
                        json.dumps(validated['voice'], ensure_ascii=False),
                        json.dumps(validated['workspace'], ensure_ascii=False),
                        json.dumps(validated['permissions'], ensure_ascii=False),
                        json.dumps(validated['limits'], ensure_ascii=False),
                        validated['memory_scope'],
                        1 if validated['enabled'] else 0,
                        now,
                        now,
                        None if validated['enabled'] else now,
                        _behavior_json(validated),
                    ),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_profile(validated['agent_id'])

    def get_profile(self, agent_id: str) -> dict[str, Any]:
        _check_id(agent_id, 'agent_id')
        with self.lock, self._connect() as db:
            row = db.execute('SELECT * FROM agent_profiles WHERE agent_id=?', (agent_id,)).fetchone()
            if not row:
                raise AgentNotFoundError(f'AgentProfile not found: {agent_id}')
            return self._row_to_profile(row)

    def list_profiles(self, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            query = 'SELECT * FROM agent_profiles'
            if not include_disabled:
                query += ' WHERE enabled=1'
            query += ' ORDER BY created_at_ms ASC, agent_id ASC'
            rows = db.execute(query).fetchall()
            return [self._row_to_profile(r) for r in rows]

    def update_profile(
        self,
        agent_id: str,
        updates: dict[str, Any],
        *,
        expected_revision: int,
    ) -> dict[str, Any]:
        """CAS update of an AgentProfile by expected_revision (E2E-02)."""
        _check_id(agent_id, 'agent_id')
        if type(expected_revision) is not int or expected_revision < 1:
            raise AgentProfileValidationError('expected_revision must be an integer >= 1')

        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM agent_profiles WHERE agent_id=?', (agent_id,)).fetchone()
                if not row:
                    raise AgentNotFoundError(f'AgentProfile not found: {agent_id}')
                current_rev = int(row['revision'])
                if current_rev != expected_revision:
                    raise StaleAgentRevisionError(
                        f'stale_revision for {agent_id}: expected {expected_revision}, actual {current_rev}'
                    )
                current = self._row_to_profile(row)
                merged = {k: v for k, v in current.items() if k not in ('thumbnail', 'draining', 'created_at_ms', 'updated_at_ms', 'disabled_at_ms')}
                for key, val in updates.items():
                    if key in ('agent_id', 'schema_version', 'revision'):
                        continue
                    if key in ('personality', 'autonomy', 'collaboration'):
                        merged[key] = copy.deepcopy(val)  # Acts sections replace, so a cleared option really clears
                    elif isinstance(val, dict) and isinstance(merged.get(key), dict):
                        merged[key] = {**merged[key], **copy.deepcopy(val)}
                    else:
                        merged[key] = copy.deepcopy(val)
                next_rev = current_rev + 1
                merged['revision'] = next_rev
                validated = validate_agent_profile(merged)
                now = self.clock()

                if validated['appearance'] != current['appearance']:
                    self.avatar_adapter.invalidate_cache(
                        form_id=current['appearance']['form_id'],
                        palette_id=current['appearance']['palette_id'],
                    )

                cursor = db.execute(
                    '''
                    UPDATE agent_profiles
                    SET revision=?, name=?, role=?, description=?, instructions=?,
                        appearance_json=?, intelligence_json=?, voice_json=?, workspace_json=?,
                        permissions_json=?, limits_json=?, memory_scope=?, enabled=?,
                        updated_at_ms=?, disabled_at_ms=?, behavior_json=?
                    WHERE agent_id=? AND revision=?
                    ''',
                    (
                        next_rev,
                        validated['name'],
                        validated['role'],
                        validated['description'],
                        validated['instructions'],
                        json.dumps(validated['appearance'], ensure_ascii=False),
                        json.dumps(validated['intelligence'], ensure_ascii=False),
                        json.dumps(validated['voice'], ensure_ascii=False),
                        json.dumps(validated['workspace'], ensure_ascii=False),
                        json.dumps(validated['permissions'], ensure_ascii=False),
                        json.dumps(validated['limits'], ensure_ascii=False),
                        validated['memory_scope'],
                        1 if validated['enabled'] else 0,
                        now,
                        None if validated['enabled'] else (row['disabled_at_ms'] or now),
                        _behavior_json(validated),
                        agent_id,
                        current_rev,
                    ),
                )
                if cursor.rowcount != 1:
                    raise StaleAgentRevisionError(f'stale_revision conflict updating {agent_id}')
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_profile(agent_id)

    def switch_provider(
        self,
        agent_id: str,
        *,
        expected_revision: int,
        new_provider_ref: str,
        new_model_id: str,
        prior_session_tokens: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Switch provider/model with CAS revision, revoking prior session tokens while preserving identity & grants (AGENT-04)."""
        current = self.get_profile(agent_id)
        if current['revision'] != expected_revision:
            raise StaleAgentRevisionError(
                f"stale_revision for {agent_id}: expected {expected_revision}, actual {current['revision']}"
            )
        policy_res = apply_provider_switch_policy(
            {k: v for k, v in current.items() if k not in ('thumbnail', 'draining', 'created_at_ms', 'updated_at_ms', 'disabled_at_ms')},
            new_provider_ref=new_provider_ref,
            new_model_id=new_model_id,
            prior_session_tokens=prior_session_tokens,
        )
        updated = self.update_profile(
            agent_id,
            {'intelligence': policy_res['profile']['intelligence']},
            expected_revision=expected_revision,
        )
        return {
            'profile': updated,
            'transferred_session_tokens': policy_res['transferred_session_tokens'],
            'revoked_session_count': policy_res['revoked_session_count'],
            'permissions_unchanged': policy_res['permissions_unchanged'],
        }

    def disable_profile(self, agent_id: str, *, revoke_grants: bool = True) -> dict[str, Any]:
        """Mark an agent draining/disabled and optionally revoke its active grants (T-AG-008)."""
        _check_id(agent_id, 'agent_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT revision FROM agent_profiles WHERE agent_id=?', (agent_id,)).fetchone()
                if not row:
                    raise AgentNotFoundError(f'AgentProfile not found: {agent_id}')
                next_rev = int(row['revision']) + 1
                db.execute(
                    '''
                    UPDATE agent_profiles
                    SET enabled=0, draining=1, revision=?, updated_at_ms=?, disabled_at_ms=?
                    WHERE agent_id=?
                    ''',
                    (next_rev, now, now, agent_id),
                )
                if revoke_grants:
                    db.execute('DELETE FROM agent_permissions WHERE agent_id=?', (agent_id,))
                    db.execute(
                        '''
                        UPDATE agent_profiles
                        SET permissions_json=json_set(permissions_json, '$.tool_grant_refs', json('[]'))
                        WHERE agent_id=?
                        ''',
                        (agent_id,),
                    )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_profile(agent_id)

    def grant_permission(
        self,
        *,
        grant_id: str,
        agent_id: str,
        tool_id: str,
        resource_pattern: str,
        operation_kinds: list[str],
        approval_mode: str = 'ask',
        expires_at_ms: int | None = None,
        granted_by: str = 'owner',
    ) -> dict[str, Any]:
        _check_id(grant_id, 'grant_id')
        _check_id(agent_id, 'agent_id')
        _check_id(tool_id, 'tool_id')
        if approval_mode not in ('ask', 'auto_safe', 'deny'):
            raise AgentProfileValidationError(f'Invalid approval_mode: {approval_mode!r}')
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO agent_permissions
                        (grant_id, agent_id, tool_id, resource_pattern, operation_kinds_json,
                         approval_mode, expires_at_ms, granted_by, revision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ''',
                    (
                        grant_id,
                        agent_id,
                        tool_id,
                        str(resource_pattern)[:400],
                        json.dumps([str(k) for k in operation_kinds]),
                        approval_mode,
                        int(expires_at_ms) if expires_at_ms is not None else None,
                        str(granted_by)[:120],
                    ),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'grant_id': grant_id, 'agent_id': agent_id, 'tool_id': tool_id, 'approval_mode': approval_mode}

    def revoke_permission(self, agent_id: str, grant_id: str) -> bool:
        """Delete one grant; the next Act turn or tool dispatch re-reads grants and is blocked (ACT-14)."""
        _check_id(agent_id, 'agent_id')
        _check_id(grant_id, 'grant_id')
        with self.lock, self._connect() as db:
            with db:
                removed = db.execute('DELETE FROM agent_permissions WHERE agent_id=? AND grant_id=?',
                                     (agent_id, grant_id)).rowcount
        return removed == 1

    def list_permissions(self, agent_id: str) -> list[dict[str, Any]]:
        _check_id(agent_id, 'agent_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            rows = db.execute(
                'SELECT * FROM agent_permissions WHERE agent_id=? ORDER BY grant_id ASC',
                (agent_id,),
            ).fetchall()
            result = []
            for r in rows:
                exp = r['expires_at_ms']
                if exp is not None and int(exp) <= now:
                    continue
                result.append({
                    'grant_id': r['grant_id'],
                    'agent_id': r['agent_id'],
                    'tool_id': r['tool_id'],
                    'resource_pattern': r['resource_pattern'],
                    'operation_kinds': json.loads(r['operation_kinds_json']),
                    'approval_mode': r['approval_mode'],
                    'expires_at_ms': int(exp) if exp is not None else None,
                    'granted_by': r['granted_by'],
                })
            return result

    def create_team(
        self,
        *,
        team_id: str,
        title: str,
        members: list[dict[str, str]],
        purpose: str = '',
        mode: str = 'collaboration',
    ) -> dict[str, Any]:
        _check_id(team_id, 'team_id')
        if mode not in ('consultation', 'collaboration'):
            raise AgentProfileValidationError("team mode must be 'consultation' or 'collaboration'")
        if not isinstance(members, list) or not members:
            raise AgentProfileValidationError('Team requires at least one member')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    '''
                    INSERT INTO agent_teams (team_id, title, purpose, mode, revision, created_at_ms, disabled)
                    VALUES (?, ?, ?, ?, 1, ?, 0)
                    ''',
                    (team_id, str(title).strip()[:120], str(purpose).strip()[:500], mode, now),
                )
                for m in members:
                    aid = _check_id(m.get('agent_id'), 'member.agent_id')
                    mrole = m.get('role', 'member')
                    if mrole not in ('lead', 'member', 'reviewer'):
                        raise AgentProfileValidationError(f'Invalid team member role: {mrole!r}')
                    db.execute(
                        'INSERT INTO agent_team_members (team_id, agent_id, role) VALUES (?, ?, ?)',
                        (team_id, aid, mrole),
                    )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_team(team_id)

    def get_team(self, team_id: str) -> dict[str, Any]:
        _check_id(team_id, 'team_id')
        with self.lock, self._connect() as db:
            trow = db.execute('SELECT * FROM agent_teams WHERE team_id=?', (team_id,)).fetchone()
            if not trow:
                raise AgentNotFoundError(f'Team not found: {team_id}')
            mrows = db.execute(
                'SELECT agent_id, role FROM agent_team_members WHERE team_id=? ORDER BY role, agent_id',
                (team_id,),
            ).fetchall()
            return {
                'team_id': trow['team_id'],
                'title': trow['title'],
                'purpose': trow['purpose'],
                'mode': trow['mode'],
                'revision': int(trow['revision']),
                'disabled': bool(trow['disabled']),
                'created_at_ms': int(trow['created_at_ms']),
                'members': [{'agent_id': r['agent_id'], 'role': r['role']} for r in mrows],
            }

    def _row_to_profile(self, row: sqlite3.Row) -> dict[str, Any]:
        appearance = json.loads(row['appearance_json'])
        thumb = self.avatar_adapter.get_thumbnail(
            int(appearance.get('form_id', 0)),
            int(appearance.get('palette_id', 0)),
            material_preset=str(appearance.get('material_preset', 'obsidian')),
            reduce_motion=bool(appearance.get('reduce_motion', False)),
        )
        return {
            'schema_version': '1.0',
            'agent_id': row['agent_id'],
            'revision': int(row['revision']),
            'name': row['name'],
            'role': row['role'],
            'description': row['description'],
            'instructions': row['instructions'],
            'enabled': bool(row['enabled']),
            'draining': bool(row['draining']),
            'appearance': appearance,
            'thumbnail': thumb,
            'intelligence': json.loads(row['intelligence_json']),
            'voice': json.loads(row['voice_json']),
            'workspace': json.loads(row['workspace_json']),
            'permissions': json.loads(row['permissions_json']),
            'limits': json.loads(row['limits_json']),
            'memory_scope': row['memory_scope'],
            **json.loads(row['behavior_json'] or '{}'),
            'created_at_ms': int(row['created_at_ms']),
            'updated_at_ms': int(row['updated_at_ms']),
            'disabled_at_ms': int(row['disabled_at_ms']) if row['disabled_at_ms'] is not None else None,
        }
