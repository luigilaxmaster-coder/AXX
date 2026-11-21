"""N:N Conversation <-> AgentProfile bindings and lossless chat-to-agent conversion (PR-12 / CHAT-01..03 / E2E-01).

Enforces Invariants:
- I-06 / CHAT-01 / E2E-01: Converting an existing chat to an agent or team preserves its
  conversation_id, messages, draft, attachments, group_id, links, Connect IDs, and 90-day TTL.
- CHAT-02: Participating in multiple conversations NEVER grants an agent cross-conversation read access;
  context resolution strictly checks conversation_id and explicit shared group notes.
- CHAT-03 / UR-014: When a conversation is forgotten or deleted, all agent_conversation_links and
  conversation-scoped artifacts/events for that conversation are scrubbed immediately.
"""
from __future__ import annotations

from contextlib import closing
import sqlite3
import threading
import time
from typing import Any

from backend.agents.profiles import AgentProfileValidationError, ID_RE
from backend.agents.registry import AgentNotFoundError, AgentRegistry


class CrossChatAccessDeniedError(PermissionError):
    """Raised when an agent attempts to read messages or context from another conversation without explicit link (CHAT-02)."""


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _check_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AgentProfileValidationError(f'Invalid {field}: {value!r}')
    return value


class ConversationBindingService:
    """Manages N:N memberships between ChatStore conversations and AgentRegistry profiles."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        chat_store=None,
        clock=None,
    ):
        self.registry = registry
        self.chat_store = chat_store
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.lock = threading.RLock()
        self._init_schema()

    def _connect(self):
        return self.registry._connect()

    def _init_schema(self) -> None:
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS agent_conversation_links (
                        conversation_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
                        membership_role TEXT NOT NULL CHECK(membership_role IN ('lead','member','reviewer')),
                        created_at_ms INTEGER NOT NULL,
                        PRIMARY KEY(conversation_id, agent_id)
                    )
                    '''
                )
                db.execute(
                    'CREATE INDEX IF NOT EXISTS idx_agent_conversation_by_agent ON agent_conversation_links(agent_id)'
                )

    def _assert_chat_exists_and_active(self, conversation_id: str) -> dict[str, Any] | None:
        if self.chat_store is None:
            return None
        with self.chat_store.db() as db:
            row = db.execute(
                'SELECT id, title, group_id, mode, created, updated, archived, draft, connect_id, shared_id FROM chat_conversations WHERE id=?',
                (conversation_id,),
            ).fetchone()
            if not row:
                raise LookupError(f'Conversation not found in ChatStore: {conversation_id}')
            return dict(row)

    def bind_agent_to_conversation(
        self,
        conversation_id: str,
        agent_id: str,
        *,
        membership_role: str = 'lead',
    ) -> dict[str, Any]:
        """Link an existing AgentProfile to a conversation without modifying its messages, ID, or Connect state (E2E-01)."""
        _check_id(conversation_id, 'conversation_id')
        _check_id(agent_id, 'agent_id')
        if membership_role not in ('lead', 'member', 'reviewer'):
            raise AgentProfileValidationError(f'Invalid membership_role: {membership_role!r}')

        chat_meta = self._assert_chat_exists_and_active(conversation_id)
        if chat_meta and chat_meta.get('archived'):
            raise PermissionError('Archived conversation must be unarchived before binding a new active agent (§3.6)')

        profile = self.registry.get_profile(agent_id)
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                if membership_role == 'lead':
                    # Demote any existing lead in this conversation to member so there is a deterministic lead
                    db.execute(
                        "UPDATE agent_conversation_links SET membership_role='member' WHERE conversation_id=? AND membership_role='lead'",
                        (conversation_id,),
                    )
                db.execute(
                    '''
                    INSERT OR REPLACE INTO agent_conversation_links
                        (conversation_id, agent_id, membership_role, created_at_ms)
                    VALUES (?, ?, ?, ?)
                    ''',
                    (conversation_id, agent_id, membership_role, now),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

        return {
            'conversation_id': conversation_id,
            'agent_id': agent_id,
            'membership_role': membership_role,
            'agent_revision': profile['revision'],
            'created_at_ms': now,
            'chat_preserved': True,
        }

    def bind_team_to_conversation(self, conversation_id: str, team_id: str) -> list[dict[str, Any]]:
        """Bind all members of a registered AgentTeam to the same conversation thread (§3.4)."""
        _check_id(conversation_id, 'conversation_id')
        team = self.registry.get_team(team_id)
        if team.get('disabled'):
            raise PermissionError(f'Team {team_id} is disabled')
        bindings = []
        for member in team['members']:
            b = self.bind_agent_to_conversation(
                conversation_id,
                member['agent_id'],
                membership_role=member['role'],
            )
            bindings.append(b)
        return bindings

    def unbind_agent_from_conversation(self, conversation_id: str, agent_id: str) -> dict[str, Any]:
        """Reversibly unlink an agent from a conversation while keeping the chat and its messages intact (E2E-01)."""
        _check_id(conversation_id, 'conversation_id')
        _check_id(agent_id, 'agent_id')
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute(
                    'DELETE FROM agent_conversation_links WHERE conversation_id=? AND agent_id=?',
                    (conversation_id, agent_id),
                )
        return {'conversation_id': conversation_id, 'agent_id': agent_id, 'unlinked': True}

    def list_conversation_members(self, conversation_id: str) -> list[dict[str, Any]]:
        _check_id(conversation_id, 'conversation_id')
        with self.lock, self._connect() as db:
            rows = db.execute(
                '''
                SELECT conversation_id, agent_id, membership_role, created_at_ms
                FROM agent_conversation_links
                WHERE conversation_id=?
                ORDER BY CASE membership_role WHEN 'lead' THEN 0 WHEN 'member' THEN 1 ELSE 2 END, created_at_ms ASC
                ''',
                (conversation_id,),
            ).fetchall()
            result = []
            for r in rows:
                try:
                    prof = self.registry.get_profile(r['agent_id'])
                except AgentNotFoundError:
                    continue
                result.append({
                    'conversation_id': r['conversation_id'],
                    'agent_id': r['agent_id'],
                    'membership_role': r['membership_role'],
                    'created_at_ms': int(r['created_at_ms']),
                    'profile': prof,
                })
            return result

    def resolve_authorized_conversation_context(
        self,
        *,
        agent_id: str,
        active_conversation_id: str,
        requested_conversation_id: str,
    ) -> dict[str, Any]:
        """Enforce CHAT-02: an agent bound to multiple chats cannot read another chat's private messages."""
        _check_id(agent_id, 'agent_id')
        _check_id(active_conversation_id, 'active_conversation_id')
        _check_id(requested_conversation_id, 'requested_conversation_id')

        members = self.list_conversation_members(active_conversation_id)
        if not any(m['agent_id'] == agent_id for m in members):
            raise CrossChatAccessDeniedError(
                f'Agent {agent_id} is not a member of active conversation {active_conversation_id}'
            )

        if requested_conversation_id != active_conversation_id:
            # Check whether ChatStore has an explicit user-created chat_links entry from requested -> active
            explicitly_linked = False
            if self.chat_store is not None:
                with self.chat_store.db() as db:
                    row = db.execute(
                        'SELECT 1 FROM chat_links WHERE conversation_id=? AND source_id=?',
                        (active_conversation_id, requested_conversation_id),
                    ).fetchone()
                    explicitly_linked = bool(row)
            if not explicitly_linked:
                raise CrossChatAccessDeniedError(
                    f'Cross-chat privacy violation (CHAT-02): agent {agent_id} in {active_conversation_id} '
                    f'cannot read private conversation {requested_conversation_id} merely by participating in both'
                )

        if self.chat_store is None:
            return {'conversation_id': requested_conversation_id, 'messages': [], 'shared_group_notes': []}

        with self.chat_store.db() as db:
            if requested_conversation_id == active_conversation_id:
                msgs = [
                    r['payload']
                    for r in db.execute(
                        'SELECT payload FROM chat_messages WHERE conversation_id=? AND invalidated=0 ORDER BY at ASC',
                        (active_conversation_id,),
                    ).fetchall()
                ]
            else:
                # Only the explicitly linked excerpt in chat_link_messages is readable
                msgs = [
                    r['payload']
                    for r in db.execute(
                        'SELECT payload FROM chat_link_messages WHERE conversation_id=? AND source_id=? AND invalidated=0 ORDER BY at ASC',
                        (active_conversation_id, requested_conversation_id),
                    ).fetchall()
                ]
            conv_row = db.execute(
                'SELECT group_id FROM chat_conversations WHERE id=?',
                (active_conversation_id,),
            ).fetchone()
            group_id = conv_row['group_id'] if conv_row else None
            notes = []
            if group_id:
                notes = [
                    r['text']
                    for r in db.execute(
                        'SELECT text FROM chat_context WHERE group_id=? AND invalidated=0 ORDER BY at ASC',
                        (group_id,),
                    ).fetchall()
                ]
        return {
            'conversation_id': requested_conversation_id,
            'messages': msgs,
            'shared_group_notes': notes,
        }

    def scrub_forgotten_conversation(self, conversation_id: str) -> dict[str, int]:
        """Scrub all bindings, events, and run references when a chat expires or is forgotten (CHAT-03 / UR-014)."""
        _check_id(conversation_id, 'conversation_id')
        with self.lock, self._connect() as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                c_links = db.execute(
                    'DELETE FROM agent_conversation_links WHERE conversation_id=?',
                    (conversation_id,),
                ).rowcount
                tables = {
                    r[0]
                    for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                c_events = 0
                if 'agent_events' in tables:
                    c_events = db.execute(
                        'DELETE FROM agent_events WHERE conversation_id=?',
                        (conversation_id,),
                    ).rowcount
                if 'agent_event_cursors' in tables:
                    db.execute(
                        'DELETE FROM agent_event_cursors WHERE conversation_id=?',
                        (conversation_id,),
                    )
                if 'task_graph_runs' in tables:
                    db.execute(
                        'DELETE FROM task_graph_runs WHERE conversation_id=?',
                        (conversation_id,),
                    )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return {'removed_links': c_links, 'removed_events': c_events}
