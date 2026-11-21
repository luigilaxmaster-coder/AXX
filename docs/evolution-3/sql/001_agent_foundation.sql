-- AXX EVOLUTION 3.0: DDL DE DISEÑO, NO EJECUTAR DIRECTAMENTE SOBRE INSTALACIÓN REAL.
-- Adaptar a esquema/locks/transacciones/migrador REAL, verificar PRAGMA foreign_keys=ON en cada conexión.
-- IMPORTANTE: se creó para validación de sintaxis en DB efímera con tabla legacy simulada.
-- Conserva chat_conversations; no altera mensajes/TTL, permisos ni Connect IDs.

CREATE TABLE IF NOT EXISTS agent_profiles (
    agent_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
    role TEXT NOT NULL CHECK(length(role) BETWEEN 1 AND 240),
    instructions TEXT NOT NULL DEFAULT '',
    appearance_json TEXT NOT NULL DEFAULT '{}',
    intelligence_json TEXT NOT NULL DEFAULT '{}',
    voice_json TEXT NOT NULL DEFAULT '{}',
    workspace_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    disabled_at_ms INTEGER,
    CHECK(json_valid(appearance_json)),
    CHECK(json_valid(intelligence_json)),
    CHECK(json_valid(voice_json)),
    CHECK(json_valid(workspace_json))
);

CREATE TABLE IF NOT EXISTS agent_conversation_links (
    conversation_id TEXT NOT NULL,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
    membership_role TEXT NOT NULL CHECK(membership_role IN ('lead','member')),
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY(conversation_id, agent_id),
    FOREIGN KEY(conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agent_conversation_by_agent ON agent_conversation_links(agent_id);

CREATE TABLE IF NOT EXISTS agent_teams (
    team_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    created_at_ms INTEGER NOT NULL,
    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS agent_team_members (
    team_id TEXT NOT NULL REFERENCES agent_teams(team_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
    role TEXT NOT NULL CHECK(role IN ('lead','member','reviewer')),
    PRIMARY KEY(team_id,agent_id)
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

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
    -- ID de chat se retiene como scalar: cleanup y revocación explícitos al expirar chat.
    -- NO FK here to avoid blocking ChatStore TTL purge; hooks must scrub dependent data.
    conversation_id TEXT,
    goal_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN
        ('queued','validated','planned','ready','leased','running','waiting_input',
         'waiting_approval','verifying','completed','failed','cancelled','interrupted','unknown','blocked')),
    permission_snapshot_hash TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    stopped_at_ms INTEGER,
    deadline_at_ms INTEGER,
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0)
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_by_chat ON agent_runs(conversation_id,created_at_ms);
CREATE INDEX IF NOT EXISTS idx_agent_runs_by_status ON agent_runs(status,updated_at_ms);

CREATE TABLE IF NOT EXISTS agent_tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE RESTRICT,
    parent_task_id TEXT REFERENCES agent_tasks(task_id),
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
    graph_version INTEGER NOT NULL CHECK(graph_version > 0),
    task_spec_json TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt >= 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    CHECK(json_valid(task_spec_json))
);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_by_run ON agent_tasks(run_id,state);

CREATE TABLE IF NOT EXISTS agent_handoffs (
    handoff_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
    from_agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id),
    to_agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id),
    operation_id TEXT NOT NULL UNIQUE,
    contract_hash TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    CHECK(json_valid(contract_json))
);

CREATE TABLE IF NOT EXISTS agent_event_cursors (
    conversation_id TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL DEFAULT 0 CHECK(last_seq >= 0)
);
CREATE TABLE IF NOT EXISTS agent_events (
    event_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK(seq > 0),
    run_id TEXT,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    UNIQUE(conversation_id,seq),
    CHECK(json_valid(payload_json))
);
CREATE INDEX IF NOT EXISTS idx_agent_events_replay ON agent_events(conversation_id,seq);

CREATE TABLE IF NOT EXISTS agent_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES agent_runs(run_id) ON DELETE SET NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    provenance_json TEXT NOT NULL,
    visibility_scope TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    CHECK(json_valid(provenance_json))
);

CREATE TABLE IF NOT EXISTS agent_workspaces (
    workspace_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK(kind IN
        ('git_worktree','browser','vm_local','vm_remote','project_view')),
    root_ref TEXT NOT NULL,
    project_id TEXT,
    permissions_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runtime_leases (
    lease_id TEXT PRIMARY KEY,
    owner_run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE RESTRICT,
    resource_type TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    fencing_token INTEGER NOT NULL CHECK(fencing_token > 0),
    lease_start_ms INTEGER NOT NULL,
    lease_expiry_ms INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active','revoking','released','expired','unknown')),
    UNIQUE(resource_type,resource_key,fencing_token)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_one_active_lease
    ON agent_runtime_leases(resource_type,resource_key)
    WHERE state='active';

CREATE TABLE IF NOT EXISTS code_projects (
    project_id TEXT PRIMARY KEY,
    project_root_ref TEXT NOT NULL,
    git_root_ref TEXT,
    project_revision INTEGER NOT NULL DEFAULT 1 CHECK(project_revision > 0),
    created_at_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS code_changesets (
    changeset_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES code_projects(project_id),
    workspace_id TEXT NOT NULL REFERENCES agent_workspaces(workspace_id),
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id),
    base_commit TEXT NOT NULL,
    branch TEXT NOT NULL,
    diff_sha256 TEXT NOT NULL,
    changeset_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('proposed','validated','applied','conflict','failed','integrated')),
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    CHECK(json_valid(changeset_json))
);
CREATE INDEX IF NOT EXISTS idx_code_changesets_project ON code_changesets(project_id,created_at_ms);

CREATE TABLE IF NOT EXISTS agent_routines (
    routine_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_profiles(agent_id),
    schedule_json TEXT NOT NULL,
    work_spec_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    created_at_ms INTEGER NOT NULL,
    CHECK(json_valid(schedule_json)),
    CHECK(json_valid(work_spec_json))
);

-- LIMPIEZA A IMPLEMENTAR EN REPO: ChatStore TTL/forget debe retirar links, context refs,
-- event cursors/events y depurar referencias/transcripciones de runs de chats borrados.
-- No exponer datos de ejecución huérfanos en UI tras olvido de conversación.
-- Este script NO reemplaza journal de CommandService ni authorization del host.
