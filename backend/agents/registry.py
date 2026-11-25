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
import unicodedata
import uuid
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


def checked_team_graph(graph: Any, member_ids: list[str]) -> dict[str, Any] | None:
    """Act Team graph: nodes are the members (with canvas position and an optional task), edges are handoffs.

    Edges must form a DAG over members; the pipeline runs it in topological order and each Act only receives the
    verified output of the Acts connected upstream of it."""
    if graph is None:
        return None
    if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('edges', []), list):
        raise AgentProfileValidationError('team graph must be {nodes: [...], edges: [...]}')
    members = set(member_ids)
    nodes: dict[str, dict[str, Any]] = {}
    for raw in graph['nodes']:
        aid = _check_id((raw or {}).get('agent_id'), 'graph.node.agent_id')
        if aid not in members or aid in nodes:
            raise AgentProfileValidationError(f'graph node {aid!r} must be one team member, once')
        x, y = raw.get('x', 0), raw.get('y', 0)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
            raise AgentProfileValidationError('graph node position must be numeric')
        instruction = raw.get('instruction', '')
        if not isinstance(instruction, str):
            raise AgentProfileValidationError('graph node instruction must be text')
        nodes[aid] = {'agent_id': aid, 'x': round(max(0.0, min(float(x), 4000.0)), 1),
                      'y': round(max(0.0, min(float(y), 4000.0)), 1), 'instruction': instruction.strip()[:600]}
    if set(nodes) != members:
        raise AgentProfileValidationError('every team member needs exactly one graph node')
    edges: list[dict[str, str]] = []
    incoming: dict[str, int] = {aid: 0 for aid in nodes}
    outgoing: dict[str, list[str]] = {aid: [] for aid in nodes}
    for raw in graph.get('edges', []):
        src, dst = (raw or {}).get('from'), (raw or {}).get('to')
        if src not in nodes or dst not in nodes or src == dst:
            raise AgentProfileValidationError('graph edges must join two different team members')
        if any(e['from'] == src and e['to'] == dst for e in edges):
            raise AgentProfileValidationError('duplicate graph edge')
        label = (raw or {}).get('label', '')
        if not isinstance(label, str):
            raise AgentProfileValidationError('graph edge label must be text')
        transfer = (raw or {}).get('transfer', 'full')
        if transfer not in ('full', 'summary', 'artifact_only'):
            raise AgentProfileValidationError('graph edge transfer must be full, summary or artifact_only')
        edge: dict[str, str] = {'from': src, 'to': dst}
        clean_label = label.strip()[:80]
        if clean_label:
            edge['label'] = clean_label
        if transfer != 'full':
            edge['transfer'] = transfer
        edges.append(edge)
        incoming[dst] += 1
        outgoing[src].append(dst)
    if len(edges) > 64:
        raise AgentProfileValidationError('a team graph allows at most 64 connections')
    queue, seen = [aid for aid, n in incoming.items() if n == 0], 0
    while queue:  # Kahn: a cycle leaves nodes that are never released
        aid = queue.pop(); seen += 1
        for nxt in outgoing[aid]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                queue.append(nxt)
    if seen != len(nodes):
        raise AgentProfileValidationError('team graph connections must not form a cycle')
    return {'nodes': list(nodes.values()), 'edges': edges}


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

                    CREATE TABLE IF NOT EXISTS act_artifacts (
                        artifact_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        act_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
                        project_id TEXT NOT NULL DEFAULT '',
                        artifact_type TEXT NOT NULL,
                        path_or_ref TEXT NOT NULL,
                        sha256 TEXT NOT NULL DEFAULT '',
                        revision INTEGER NOT NULL DEFAULT 1,
                        verification_status TEXT NOT NULL DEFAULT 'pending',
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at_ms INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_act_artifacts_run ON act_artifacts(run_id);
                    CREATE TABLE IF NOT EXISTS agent_memory_entries (
                        memory_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE CASCADE,
                        content TEXT NOT NULL,
                        source_ref TEXT NOT NULL,
                        revision INTEGER NOT NULL DEFAULT 1,
                        created_at_ms INTEGER NOT NULL,
                        expires_at_ms INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_agent_memory_owner ON agent_memory_entries(agent_id, expires_at_ms);
                    '''
                )
                # Acts 3.1 additive migrations
                if 'behavior_json' not in {r[1] for r in db.execute('PRAGMA table_info(agent_profiles)')}:
                    db.execute("ALTER TABLE agent_profiles ADD COLUMN behavior_json TEXT NOT NULL DEFAULT '{}'")
                if 'team_meta_json' not in {r[1] for r in db.execute('PRAGMA table_info(agent_teams)')}:
                    db.execute("ALTER TABLE agent_teams ADD COLUMN team_meta_json TEXT NOT NULL DEFAULT '{}'")

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    @staticmethod
    def _check_identity_unique(db, profile):
        normalize = lambda value: unicodedata.normalize('NFKC', value or '').strip().casefold()
        keys = {normalize(profile['name']), normalize((profile.get('collaboration') or {}).get('mention'))} - {''}
        for row in db.execute('SELECT agent_id, name, behavior_json FROM agent_profiles WHERE agent_id!=?', (profile['agent_id'],)):
            mention = (json.loads(row['behavior_json']).get('collaboration') or {}).get('mention')
            occupied = {normalize(row['name']), normalize(mention)} - {''}
            if keys & occupied:
                raise AgentProfileValidationError('El nombre o alias ya pertenece a otro Act; elige uno único.')

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
                self._check_identity_unique(db, validated)
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

    def list_private_memories(self, agent_id: str) -> list[dict[str, Any]]:
        self.get_profile(agent_id)
        with self.lock, self._connect() as db:
            with db:
                db.execute('DELETE FROM agent_memory_entries WHERE agent_id=? AND expires_at_ms<=?', (agent_id, self.clock()))
                return [dict(r) for r in db.execute('SELECT * FROM agent_memory_entries WHERE agent_id=? '
                                                   'ORDER BY created_at_ms, memory_id', (agent_id,))]

    def save_private_memory(self, agent_id: str, *, content: str, source_ref: str = 'owner_note',
                            memory_id: str | None = None, expected_revision: int = 0, ttl_days: int = 90) -> dict[str, Any]:
        from backend.agents.profiles import SECRET_LEAK_RE
        self.get_profile(agent_id)
        if (not isinstance(content, str) or not 1 <= len(content.strip()) <= 2000
                or not isinstance(source_ref, str) or not 1 <= len(source_ref) <= 160
                or type(ttl_days) is not int or not 1 <= ttl_days <= 90 or type(expected_revision) is not int):
            raise AgentProfileValidationError('Memory needs 1..2000 characters, a source and a TTL of 1..90 days')
        if SECRET_LEAK_RE.search(content) or SECRET_LEAK_RE.search(source_ref):
            raise AgentProfileValidationError('No guardes credenciales o tokens en la memoria del Act.')
        memory_id = _check_id(memory_id or 'mem-' + uuid.uuid4().hex, 'memory_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('DELETE FROM agent_memory_entries WHERE agent_id=? AND expires_at_ms<=?', (agent_id, now))
                old = db.execute('SELECT * FROM agent_memory_entries WHERE memory_id=?', (memory_id,)).fetchone()
                if old and old['agent_id'] != agent_id:
                    raise PermissionError('This memory belongs to another Act')
                if (old['revision'] if old else 0) != expected_revision:
                    raise StaleAgentRevisionError('The memory changed; reload it before editing')
                if not old and db.execute('SELECT count(*) FROM agent_memory_entries WHERE agent_id=?', (agent_id,)).fetchone()[0] >= 32:
                    raise AgentProfileValidationError('Each Act supports up to 32 explicit private memories')
                db.execute('INSERT INTO agent_memory_entries VALUES (?, ?, ?, ?, ?, ?, ?) '
                           'ON CONFLICT(memory_id) DO UPDATE SET content=excluded.content, source_ref=excluded.source_ref, '
                           'revision=excluded.revision, expires_at_ms=excluded.expires_at_ms',
                           (memory_id, agent_id, content.strip(), source_ref, expected_revision + 1,
                            old['created_at_ms'] if old else now, now + ttl_days * 86400000))
                result = dict(db.execute('SELECT * FROM agent_memory_entries WHERE memory_id=?', (memory_id,)).fetchone())
                db.execute('COMMIT')
                return result
            except Exception:
                db.execute('ROLLBACK')
                raise

    def forget_private_memory(self, agent_id: str, memory_id: str, *, expected_revision: int) -> dict[str, Any]:
        self.get_profile(agent_id)
        _check_id(memory_id, 'memory_id')
        with self.lock, self._connect() as db:
            with db:
                row = db.execute('SELECT agent_id, revision FROM agent_memory_entries WHERE memory_id=?', (memory_id,)).fetchone()
                if row is not None and (row['agent_id'] != agent_id or row['revision'] != expected_revision):
                    raise StaleAgentRevisionError('The memory changed or belongs to another Act')
                db.execute('DELETE FROM agent_memory_entries WHERE memory_id=? AND agent_id=?', (memory_id, agent_id))
        return {'memory_id': memory_id, 'forgotten': True}

    def export_agent_package(self, agent_id: str) -> dict[str, Any]:
        from backend.agents.profiles import export_agent_package
        return export_agent_package(self.get_profile(agent_id))

    def import_agent_package(self, package_data: dict[str, Any], *, new_agent_id: str | None = None) -> dict[str, Any]:
        from backend.agents.profiles import import_agent_package
        clean = import_agent_package(package_data)['profile']
        clean['agent_id'] = new_agent_id or 'act-import-' + uuid.uuid4().hex[:12]
        _check_id(clean['agent_id'], 'new_agent_id')
        clean['enabled'] = False
        original = clean['name']
        # Importing alongside the source creates an independently addressable Act.
        with self.lock, self._connect() as db:
            for index in range(100):
                try:
                    self._check_identity_unique(db, clean)
                    break
                except AgentProfileValidationError:
                    clean.setdefault('collaboration', {}).pop('mention', None)
                    clean['name'] = original[:55] + f' (importado {index + 1})'
            else:
                raise AgentProfileValidationError('No unique name available for imported Act')
        return self.create_profile(clean)

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
                if (validated['name'] != current['name'] or (validated.get('collaboration') or {}).get('mention')
                        != (current.get('collaboration') or {}).get('mention')):
                    self._check_identity_unique(db, validated)
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
        coordinator_agent_id: str | None = None,
        budget_usd: float = 5.0,
        max_concurrency: int = 2,
        delegation_rules: str = '',
        shared_memory_policy: str = 'explicit_shared',
        workspace_scope: str = '',
        review_criteria: str = '',
        graph: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _check_id(team_id, 'team_id')
        meta = self._team_meta(members, coordinator_agent_id, budget_usd, max_concurrency, delegation_rules,
                               shared_memory_policy, workspace_scope, review_criteria, graph)
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
                    INSERT INTO agent_teams (team_id, title, purpose, mode, revision, created_at_ms, disabled, team_meta_json)
                    VALUES (?, ?, ?, ?, 1, ?, 0, ?)
                    ''',
                    (team_id, str(title).strip()[:120], str(purpose).strip()[:500], mode, now, json.dumps(meta, ensure_ascii=False)),
                )
                self._insert_team_members(db, team_id, members)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_team(team_id)

    @staticmethod
    def _team_meta(members, coordinator_agent_id, budget_usd, max_concurrency, delegation_rules,
                   shared_memory_policy, workspace_scope, review_criteria, graph) -> dict[str, Any]:
        if not isinstance(members, list) or not members:
            raise AgentProfileValidationError('Team requires at least one member')
        if coordinator_agent_id is not None:
            _check_id(coordinator_agent_id, 'coordinator_agent_id')
        meta = {
            'coordinator_agent_id': coordinator_agent_id,
            'budget_usd': max(0.0, float(budget_usd)),
            'max_concurrency': max(1, min(int(max_concurrency), 8)),
            'delegation_rules': str(delegation_rules)[:1000],
            'shared_memory_policy': str(shared_memory_policy or 'explicit_shared')[:64],
            'workspace_scope': str(workspace_scope)[:400],
            'review_criteria': str(review_criteria)[:1000],
        }
        checked = checked_team_graph(graph, [(m or {}).get('agent_id') for m in members])
        if checked is not None:
            meta['graph'] = checked
        return meta

    @staticmethod
    def _insert_team_members(db, team_id: str, members: list[dict[str, str]]) -> None:
        for m in members:
            aid = _check_id(m.get('agent_id'), 'member.agent_id')
            mrole = m.get('role', 'member')
            if mrole not in ('lead', 'member', 'reviewer'):
                raise AgentProfileValidationError(f'Invalid team member role: {mrole!r}')
            db.execute('INSERT INTO agent_team_members (team_id, agent_id, role) VALUES (?, ?, ?)', (team_id, aid, mrole))

    def update_team(self, *, team_id: str, expected_revision: int, title: str, members: list[dict[str, str]],
                    purpose: str = '', coordinator_agent_id: str | None = None, budget_usd: float = 5.0,
                    max_concurrency: int = 2, delegation_rules: str = '', shared_memory_policy: str = 'explicit_shared',
                    workspace_scope: str = '', review_criteria: str = '', graph: dict[str, Any] | None = None) -> dict[str, Any]:
        """Replace a team's members, settings and graph; a stale editor (revision mismatch) is rejected, never merged."""
        _check_id(team_id, 'team_id')
        meta = self._team_meta(members, coordinator_agent_id, budget_usd, max_concurrency, delegation_rules,
                               shared_memory_policy, workspace_scope, review_criteria, graph)
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT revision FROM agent_teams WHERE team_id=?', (team_id,)).fetchone()
                if not row:
                    raise AgentNotFoundError(f'Team not found: {team_id}')
                if int(row['revision']) != int(expected_revision):
                    raise StaleAgentRevisionError(f"Team {team_id} changed (revision {row['revision']}); reload it before saving")
                db.execute('UPDATE agent_teams SET title=?, purpose=?, team_meta_json=?, revision=revision+1 WHERE team_id=?',
                           (str(title).strip()[:120], str(purpose).strip()[:500], json.dumps(meta, ensure_ascii=False), team_id))
                db.execute('DELETE FROM agent_team_members WHERE team_id=?', (team_id,))
                self._insert_team_members(db, team_id, members)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_team(team_id)

    def delete_team(self, team_id: str) -> bool:
        """Remove the team definition only; its past runs, artifacts and events stay recorded."""
        _check_id(team_id, 'team_id')
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                return db.execute('DELETE FROM agent_teams WHERE team_id=?', (team_id,)).rowcount > 0

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
            meta = json.loads(trow['team_meta_json'] or '{}') if 'team_meta_json' in trow.keys() else {}
            return {
                'team_id': trow['team_id'],
                'title': trow['title'],
                'purpose': trow['purpose'],
                'mode': trow['mode'],
                'revision': int(trow['revision']),
                'disabled': bool(trow['disabled']),
                'created_at_ms': int(trow['created_at_ms']),
                'members': [{'agent_id': r['agent_id'], 'role': r['role']} for r in mrows],
                **meta,
            }

    def list_teams(self, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            query = 'SELECT team_id FROM agent_teams'
            if not include_disabled:
                query += ' WHERE disabled=0'
            query += ' ORDER BY created_at_ms ASC, team_id ASC'
            rows = db.execute(query).fetchall()
            return [self.get_team(r['team_id']) for r in rows]

    def record_artifact(
        self,
        *,
        artifact_id: str,
        run_id: str,
        act_id: str,
        artifact_type: str,
        path_or_ref: str,
        sha256: str = '',
        project_id: str = '',
        revision: int = 1,
        verification_status: str = 'verified',
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _check_id(artifact_id, 'artifact_id')
        _check_id(run_id, 'run_id')
        _check_id(act_id, 'act_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute(
                    '''
                    INSERT OR REPLACE INTO act_artifacts
                        (artifact_id, run_id, act_id, project_id, artifact_type, path_or_ref, sha256,
                         revision, verification_status, metadata_json, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        artifact_id,
                        run_id,
                        act_id,
                        str(project_id)[:160],
                        str(artifact_type)[:80],
                        str(path_or_ref)[:600],
                        str(sha256)[:64],
                        int(revision),
                        str(verification_status)[:40],
                        json.dumps(metadata or {}, ensure_ascii=False),
                        now,
                    ),
                )
        return next(a for a in self.list_artifacts(run_id=run_id) if a['artifact_id'] == artifact_id)

    def list_artifacts(self, *, run_id: str | None = None, act_id: str | None = None) -> list[dict[str, Any]]:
        with self.lock, self._connect() as db:
            if run_id:
                rows = db.execute('SELECT * FROM act_artifacts WHERE run_id=? ORDER BY created_at_ms DESC', (run_id,)).fetchall()
            elif act_id:
                rows = db.execute('SELECT * FROM act_artifacts WHERE act_id=? ORDER BY created_at_ms DESC', (act_id,)).fetchall()
            else:
                rows = db.execute('SELECT * FROM act_artifacts ORDER BY created_at_ms DESC LIMIT 200').fetchall()
            return [
                {
                    'artifact_id': r['artifact_id'],
                    'run_id': r['run_id'],
                    'act_id': r['act_id'],
                    'project_id': r['project_id'],
                    'artifact_type': r['artifact_type'],
                    'path_or_ref': r['path_or_ref'],
                    'sha256': r['sha256'],
                    'revision': int(r['revision']),
                    'verification_status': r['verification_status'],
                    'metadata': json.loads(r['metadata_json'] or '{}'),
                    'created_at_ms': int(r['created_at_ms']),
                }
                for r in rows
            ]

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
