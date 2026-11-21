"""Declarative TaskGraph DAG engine, state machine, and CommandService journal recovery (PR-01).

Enforces Invariants:
- I-01: Single effect executor (all host/workspace mutations dispatch through CommandService/ActionExecutor).
- I-02: Delegation never expands permissions or depth beyond configured limits.
- I-03: Crash or interruption after dispatch transitions to 'unknown' and blocks automatic re-dispatch
  (ORCH-01, ORCH-02).
"""
from __future__ import annotations

from collections import deque
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

VALID_TASK_STATES = frozenset({
    'submitted',
    'validated',
    'planned',
    'ready',
    'leased',
    'running',
    'waiting_input',
    'waiting_approval',
    'verifying',
    'repairable_failed',
    'interrupted',
    'reconcile',
    'completed',
    'failed',
    'blocked',
    'cancelled',
    'cancelled_with_effects',
    'unknown',
})

TERMINAL_TASK_STATES = frozenset({
    'completed',
    'failed',
    'blocked',
    'cancelled',
    'cancelled_with_effects',
    'unknown',
})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    'submitted': frozenset({'validated', 'cancelled', 'failed'}),
    'validated': frozenset({'planned', 'ready', 'cancelled', 'failed'}),
    'planned': frozenset({'ready', 'waiting_input', 'cancelled', 'failed'}),
    'ready': frozenset({'leased', 'waiting_input', 'cancelled', 'blocked'}),
    'waiting_input': frozenset({'ready', 'cancelled', 'failed'}),
    'leased': frozenset({'running', 'ready', 'cancelled', 'blocked'}),
    'running': frozenset({
        'verifying',
        'waiting_approval',
        'interrupted',
        'cancelled_with_effects',
        'unknown',
        'failed',
    }),
    'waiting_approval': frozenset({'running', 'cancelled', 'blocked', 'failed'}),
    'verifying': frozenset({'completed', 'repairable_failed', 'failed', 'unknown', 'blocked'}),
    'repairable_failed': frozenset({'ready', 'failed', 'cancelled', 'blocked'}),
    'interrupted': frozenset({'reconcile', 'unknown', 'cancelled'}),
    'reconcile': frozenset({'completed', 'ready', 'blocked', 'unknown'}),
    'completed': frozenset(),
    'failed': frozenset(),
    'blocked': frozenset(),
    'cancelled': frozenset(),
    'cancelled_with_effects': frozenset(),
    'unknown': frozenset(),  # Invariant I-03: unknown NEVER transitions back to ready automatically
}

ID_PATTERN = re.compile(r'^[A-Za-z0-9_.:-]{1,160}$')
SHA256_PATTERN = re.compile(r'^[a-f0-9]{64}$')


class TaskGraphError(ValueError):
    """Base error for TaskGraph validation and state transitions."""


class CycleDetectedError(TaskGraphError):
    """Raised when a TaskGraph contains a dependency cycle (ORCH-01)."""


class InvalidTaskTransitionError(TaskGraphError):
    """Raised when an illegal state transition is requested."""


class UnknownEffectBlockedError(RuntimeError):
    """Raised when attempting to re-dispatch or retry a task with unknown effect (ORCH-02 / I-03)."""


class BudgetExceededError(TaskGraphError):
    """Raised when a TaskGraph exceeds its configured cost or task budget (ORCH-04)."""


def _validate_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise TaskGraphError(f'Invalid {field}: {value!r}')
    return value


def _canonical_hash(payload: Any) -> str:
    normalized = json.loads(json.dumps(payload, allow_nan=False))
    raw = json.dumps(normalized, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def validate_input_refs(input_refs: Any) -> list[dict[str, Any]]:
    if input_refs is None:
        return []
    if not isinstance(input_refs, list) or len(input_refs) > 128:
        raise TaskGraphError('input_refs must be a list of at most 128 items')
    validated = []
    for item in input_refs:
        if not isinstance(item, dict):
            raise TaskGraphError('Each input_ref must be an object')
        artifact_id = _validate_id(item.get('artifact_id'), 'input_ref.artifact_id')
        sha256 = item.get('sha256')
        if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
            raise TaskGraphError(f'Invalid sha256 in input_ref {artifact_id}')
        revision = item.get('revision', 1)
        if type(revision) is not int or revision < 1:
            raise TaskGraphError(f'Invalid revision in input_ref {artifact_id}')
        validated.append({'artifact_id': artifact_id, 'sha256': sha256, 'revision': revision})
    return validated


def validate_dag_topology(
    nodes: list[dict[str, Any]],
    *,
    max_delegate_depth: int = 2,
    max_nodes: int = 64,
) -> list[str]:
    """Validate acyclic DAG structure, parent depth, and return deterministic topological order."""
    if not isinstance(nodes, list) or not (1 <= len(nodes) <= max_nodes):
        raise TaskGraphError(f'TaskGraph must contain between 1 and {max_nodes} nodes')
    by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise TaskGraphError('Task node must be an object')
        tid = _validate_id(node.get('task_id'), 'task_id')
        if tid in by_id:
            raise TaskGraphError(f'Duplicate task_id in TaskGraph: {tid}')
        by_id[tid] = node

    # Check parent delegation depth
    for tid, node in by_id.items():
        depth = 0
        curr = node.get('parent_task_id')
        seen_parents = {tid}
        while curr is not None:
            _validate_id(curr, 'parent_task_id')
            if curr not in by_id:
                raise TaskGraphError(f'parent_task_id {curr} for {tid} does not exist in graph')
            if curr in seen_parents:
                raise CycleDetectedError(f'Parent cycle detected involving {tid}')
            seen_parents.add(curr)
            depth += 1
            if depth > max_delegate_depth:
                raise TaskGraphError(
                    f'Delegation depth {depth} for task {tid} exceeds max_delegate_depth={max_delegate_depth}'
                )
            curr = by_id[curr].get('parent_task_id')

    # Kahn's algorithm for deterministic topological sort & cycle detection
    in_degree: dict[str, int] = {tid: 0 for tid in by_id}
    dependents: dict[str, list[str]] = {tid: [] for tid in by_id}
    for tid, node in by_id.items():
        deps = node.get('depends_on') or []
        if not isinstance(deps, list):
            raise TaskGraphError(f'depends_on for {tid} must be a list')
        seen_deps = set()
        for dep in deps:
            _validate_id(dep, 'depends_on')
            if dep == tid:
                raise CycleDetectedError(f'Self-dependency cycle on task {tid}')
            if dep not in by_id:
                raise TaskGraphError(f'Task {tid} depends on unknown task {dep}')
            if dep not in seen_deps:
                seen_deps.add(dep)
                in_degree[tid] += 1
                dependents[dep].append(tid)

    queue = deque(sorted(tid for tid, deg in in_degree.items() if deg == 0))
    topo_order: list[str] = []
    while queue:
        current = queue.popleft()
        topo_order.append(current)
        for nxt in sorted(dependents[current]):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(topo_order) != len(by_id):
        cycling = sorted(set(by_id) - set(topo_order))
        raise CycleDetectedError(f'Cycle detected in TaskGraph involving tasks: {cycling}')
    return topo_order


class _NullClosing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TaskGraphEngine:
    """Persistent, crash-recoverable DAG TaskGraph engine connected to CommandService."""

    def __init__(
        self,
        db_path: str | Path = ':memory:',
        *,
        command_service=None,
        action_executor=None,
        max_parallel_workers: int = 2,
        max_delegate_depth: int = 2,
        clock=None,
    ):
        self.db_path = str(db_path)
        self.command_service = command_service
        self.action_executor = action_executor or getattr(command_service, 'executor', None)
        self.max_parallel_workers = max(1, min(int(max_parallel_workers), 8))
        self.max_delegate_depth = max(0, min(int(max_delegate_depth), 8))
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
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS task_graph_runs (
                        run_id TEXT PRIMARY KEY,
                        conversation_id TEXT,
                        agent_id TEXT NOT NULL,
                        graph_version INTEGER NOT NULL DEFAULT 1 CHECK(graph_version > 0),
                        goal_spec_json TEXT NOT NULL,
                        goal_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        max_cost_usd REAL NOT NULL DEFAULT 0.0,
                        spent_cost_usd REAL NOT NULL DEFAULT 0.0,
                        max_workers INTEGER NOT NULL DEFAULT 2,
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        CHECK(json_valid(goal_spec_json))
                    )
                    '''
                )
                db.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS task_graph_nodes (
                        task_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL REFERENCES task_graph_runs(run_id) ON DELETE CASCADE,
                        parent_task_id TEXT,
                        agent_id TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'executor',
                        graph_version INTEGER NOT NULL DEFAULT 1,
                        depends_on_json TEXT NOT NULL DEFAULT '[]',
                        input_refs_json TEXT NOT NULL DEFAULT '[]',
                        required_capabilities_json TEXT NOT NULL DEFAULT '[]',
                        action_spec_json TEXT NOT NULL DEFAULT '{}',
                        is_pure INTEGER NOT NULL DEFAULT 0 CHECK(is_pure IN (0, 1)),
                        state TEXT NOT NULL,
                        attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt >= 0),
                        max_attempts INTEGER NOT NULL DEFAULT 1 CHECK(max_attempts >= 1),
                        idempotency_key TEXT NOT NULL UNIQUE,
                        lease_id TEXT,
                        operation_id TEXT,
                        dispatched INTEGER NOT NULL DEFAULT 0 CHECK(dispatched IN (0, 1)),
                        result_json TEXT NOT NULL DEFAULT '{}',
                        evidence_json TEXT NOT NULL DEFAULT '{}',
                        unverified_items_json TEXT NOT NULL DEFAULT '[]',
                        error_text TEXT NOT NULL DEFAULT '',
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        CHECK(json_valid(depends_on_json)),
                        CHECK(json_valid(input_refs_json)),
                        CHECK(json_valid(required_capabilities_json)),
                        CHECK(json_valid(action_spec_json)),
                        CHECK(json_valid(result_json)),
                        CHECK(json_valid(evidence_json)),
                        CHECK(json_valid(unverified_items_json))
                    )
                    '''
                )
                db.execute(
                    'CREATE INDEX IF NOT EXISTS idx_task_graph_nodes_run ON task_graph_nodes(run_id, state)'
                )

    def close(self) -> None:
        with self.lock:
            if self._persistent_conn is not None:
                self._persistent_conn.close()
                self._persistent_conn = None

    def create_graph(
        self,
        *,
        run_id: str,
        agent_id: str,
        goal_spec: dict[str, Any],
        nodes: list[dict[str, Any]],
        conversation_id: str | None = None,
        graph_version: int = 1,
        max_cost_usd: float = 0.0,
        max_workers: int | None = None,
    ) -> dict[str, Any]:
        _validate_id(run_id, 'run_id')
        _validate_id(agent_id, 'agent_id')
        if conversation_id is not None:
            _validate_id(conversation_id, 'conversation_id')
        if type(graph_version) is not int or graph_version < 1:
            raise TaskGraphError('graph_version must be a positive integer')
        if not isinstance(goal_spec, dict):
            raise TaskGraphError('goal_spec must be an object')
        if type(max_cost_usd) not in (int, float) or max_cost_usd < 0:
            raise TaskGraphError('max_cost_usd must be non-negative')

        topo_order = validate_dag_topology(
            nodes,
            max_delegate_depth=self.max_delegate_depth,
        )
        workers = max(1, min(int(max_workers or self.max_parallel_workers), 8))
        now = self.clock()
        goal_hash = _canonical_hash(goal_spec)

        prepared_nodes = []
        seen_idem_keys = set()
        for raw in nodes:
            tid = _validate_id(raw['task_id'], 'task_id')
            node_agent = _validate_id(raw.get('agent_id', agent_id), 'node.agent_id')
            role = str(raw.get('role', 'executor')).strip() or 'executor'
            deps = [_validate_id(d, 'depends_on') for d in (raw.get('depends_on') or [])]
            in_refs = validate_input_refs(raw.get('input_refs'))
            req_caps = [str(c) for c in (raw.get('required_capabilities') or [])]
            action_spec = raw.get('action_spec') or {}
            if not isinstance(action_spec, dict):
                raise TaskGraphError(f'action_spec for {tid} must be an object')
            # Validate that if an action_spec requests a host effect, it specifies a command_id or tool_name
            if action_spec.get('kind') == 'command' and not isinstance(action_spec.get('command_id'), str):
                raise TaskGraphError(f'Command task {tid} requires a registered command_id')
            is_pure = bool(raw.get('is_pure', False))
            max_attempts = int(raw.get('max_attempts', 2 if is_pure else 1))
            if max_attempts < 1 or max_attempts > 8:
                raise TaskGraphError(f'Invalid max_attempts for {tid}')
            idem_key = _validate_id(
                raw.get('idempotency_key') or f'{run_id}:{tid}:v{graph_version}',
                'idempotency_key',
            )
            if idem_key in seen_idem_keys:
                raise TaskGraphError(f'Duplicate idempotency_key in graph: {idem_key}')
            seen_idem_keys.add(idem_key)
            initial_state = 'ready' if not deps else 'planned'
            prepared_nodes.append({
                'task_id': tid,
                'parent_task_id': raw.get('parent_task_id'),
                'agent_id': node_agent,
                'role': role,
                'depends_on': deps,
                'input_refs': in_refs,
                'required_capabilities': req_caps,
                'action_spec': action_spec,
                'is_pure': 1 if is_pure else 0,
                'state': initial_state,
                'max_attempts': max_attempts,
                'idempotency_key': idem_key,
            })

        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute(
                    '''
                    INSERT INTO task_graph_runs
                        (run_id, conversation_id, agent_id, graph_version, goal_spec_json, goal_hash,
                         status, max_cost_usd, spent_cost_usd, max_workers, created_at_ms, updated_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, 'ready', ?, 0.0, ?, ?, ?)
                    ''',
                    (
                        run_id,
                        conversation_id,
                        agent_id,
                        graph_version,
                        json.dumps(goal_spec, ensure_ascii=False),
                        goal_hash,
                        float(max_cost_usd),
                        workers,
                        now,
                        now,
                    ),
                )
                for n in prepared_nodes:
                    db.execute(
                        '''
                        INSERT INTO task_graph_nodes
                            (task_id, run_id, parent_task_id, agent_id, role, graph_version,
                             depends_on_json, input_refs_json, required_capabilities_json,
                             action_spec_json, is_pure, state, attempt, max_attempts,
                             idempotency_key, created_at_ms, updated_at_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                        ''',
                        (
                            n['task_id'],
                            run_id,
                            n['parent_task_id'],
                            n['agent_id'],
                            n['role'],
                            graph_version,
                            json.dumps(n['depends_on']),
                            json.dumps(n['input_refs']),
                            json.dumps(n['required_capabilities']),
                            json.dumps(n['action_spec'], ensure_ascii=False),
                            n['is_pure'],
                            n['state'],
                            n['max_attempts'],
                            n['idempotency_key'],
                            now,
                            now,
                        ),
                    )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

        return self.get_graph(run_id) | {'topological_order': topo_order}

    def get_graph(self, run_id: str) -> dict[str, Any]:
        _validate_id(run_id, 'run_id')
        with self.lock, self._connect() as db:
            run_row = db.execute(
                'SELECT * FROM task_graph_runs WHERE run_id=?',
                (run_id,),
            ).fetchone()
            if not run_row:
                raise TaskGraphError(f'TaskGraph run not found: {run_id}')
            node_rows = db.execute(
                'SELECT * FROM task_graph_nodes WHERE run_id=? ORDER BY created_at_ms, task_id',
                (run_id,),
            ).fetchall()
            nodes = [self._row_to_node(r) for r in node_rows]
            return {
                'run_id': run_row['run_id'],
                'conversation_id': run_row['conversation_id'],
                'agent_id': run_row['agent_id'],
                'graph_version': int(run_row['graph_version']),
                'goal_spec': json.loads(run_row['goal_spec_json']),
                'goal_hash': run_row['goal_hash'],
                'status': run_row['status'],
                'max_cost_usd': float(run_row['max_cost_usd']),
                'spent_cost_usd': float(run_row['spent_cost_usd']),
                'max_workers': int(run_row['max_workers']),
                'created_at_ms': int(run_row['created_at_ms']),
                'updated_at_ms': int(run_row['updated_at_ms']),
                'nodes': nodes,
            }

    def get_task(self, task_id: str) -> dict[str, Any]:
        _validate_id(task_id, 'task_id')
        with self.lock, self._connect() as db:
            row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
            if not row:
                raise TaskGraphError(f'Task node not found: {task_id}')
            return self._row_to_node(row)

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> dict[str, Any]:
        return {
            'task_id': row['task_id'],
            'run_id': row['run_id'],
            'parent_task_id': row['parent_task_id'],
            'agent_id': row['agent_id'],
            'role': row['role'],
            'graph_version': int(row['graph_version']),
            'depends_on': json.loads(row['depends_on_json']),
            'input_refs': json.loads(row['input_refs_json']),
            'required_capabilities': json.loads(row['required_capabilities_json']),
            'action_spec': json.loads(row['action_spec_json']),
            'is_pure': bool(row['is_pure']),
            'state': row['state'],
            'attempt': int(row['attempt']),
            'max_attempts': int(row['max_attempts']),
            'idempotency_key': row['idempotency_key'],
            'lease_id': row['lease_id'],
            'operation_id': row['operation_id'],
            'dispatched': bool(row['dispatched']),
            'result': json.loads(row['result_json']),
            'evidence': json.loads(row['evidence_json']),
            'unverified_items': json.loads(row['unverified_items_json']),
            'error': row['error_text'],
            'created_at_ms': int(row['created_at_ms']),
            'updated_at_ms': int(row['updated_at_ms']),
        }

    def ready_tasks(self, run_id: str) -> list[dict[str, Any]]:
        """Promote dependencies-satisfied planned nodes to ready and return up to available worker slots."""
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                run_row = db.execute('SELECT * FROM task_graph_runs WHERE run_id=?', (run_id,)).fetchone()
                if not run_row:
                    raise TaskGraphError(f'TaskGraph run not found: {run_id}')
                node_rows = db.execute('SELECT * FROM task_graph_nodes WHERE run_id=?', (run_id,)).fetchall()
                by_id = {r['task_id']: self._row_to_node(r) for r in node_rows}
                now = self.clock()
                for tid, node in by_id.items():
                    if node['state'] == 'planned':
                        deps = node['depends_on']
                        if any(
                            by_id[d]['state'] in ('failed', 'blocked', 'cancelled', 'cancelled_with_effects', 'unknown')
                            for d in deps
                        ):
                            db.execute(
                                "UPDATE task_graph_nodes SET state='blocked', error_text='Dependency did not complete cleanly', updated_at_ms=? WHERE task_id=?",
                                (now, tid),
                            )
                            node['state'] = 'blocked'
                        elif all(
                            by_id[d]['state'] == 'completed' and bool(by_id[d]['evidence'])
                            for d in deps
                        ):
                            db.execute(
                                "UPDATE task_graph_nodes SET state='ready', updated_at_ms=? WHERE task_id=?",
                                (now, tid),
                            )
                            node['state'] = 'ready'
                if run_row['status'] in ('cancelled', 'failed', 'unknown', 'blocked'):
                    db.execute('COMMIT')
                    return []
                active_count = sum(1 for n in by_id.values() if n['state'] in ('leased', 'running', 'verifying'))
                available_slots = max(0, int(run_row['max_workers']) - active_count)
                ready_list = [
                    n for n in sorted(by_id.values(), key=lambda x: x['task_id'])
                    if n['state'] == 'ready'
                ][:available_slots]
                db.execute('COMMIT')
                return ready_list
            except Exception:
                db.execute('ROLLBACK')
                raise

    def lease_and_start_task(
        self,
        task_id: str,
        *,
        lease_id: str,
        operation_id: str | None = None,
    ) -> dict[str, Any]:
        """Transition ready -> leased -> running, persisting operation_id BEFORE dispatch (I-03)."""
        _validate_id(task_id, 'task_id')
        _validate_id(lease_id, 'lease_id')
        if operation_id is not None:
            _validate_id(operation_id, 'operation_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
                if not row:
                    raise TaskGraphError(f'Task not found: {task_id}')
                state = row['state']
                if state == 'unknown':
                    raise UnknownEffectBlockedError(
                        f'Task {task_id} is in unknown state and cannot be re-dispatched without explicit reconciliation'
                    )
                if state not in ('ready', 'leased'):
                    raise InvalidTaskTransitionError(f'Cannot lease/start task {task_id} from state {state}')
                if row['dispatched'] and not row['is_pure']:
                    raise UnknownEffectBlockedError(
                        f'Impure task {task_id} was already dispatched once; automatic re-dispatch is prohibited'
                    )
                op_id = operation_id or row['operation_id'] or f"op-{row['idempotency_key']}"
                attempt = int(row['attempt']) + 1
                if attempt > int(row['max_attempts']):
                    raise TaskGraphError(f'Task {task_id} exceeded max_attempts={row["max_attempts"]}')
                db.execute(
                    '''
                    UPDATE task_graph_nodes
                    SET state='running', lease_id=?, operation_id=?, attempt=?, dispatched=1, updated_at_ms=?
                    WHERE task_id=?
                    ''',
                    (lease_id, op_id, attempt, now, task_id),
                )
                db.execute(
                    "UPDATE task_graph_runs SET status='running', updated_at_ms=? WHERE run_id=?",
                    (now, row['run_id']),
                )
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_task(task_id)

    def dispatch_task_via_executor(
        self,
        task_id: str,
        *,
        lease_id: str,
        delivery_mode: str | None = None,
    ) -> dict[str, Any]:
        """Execute a task's action strictly through ActionExecutor/CommandService (I-01)."""
        if self.action_executor is None:
            raise TaskGraphError('ActionExecutor is required to dispatch host/workspace tasks')
        node = self.lease_and_start_task(task_id, lease_id=lease_id)
        action_spec = node['action_spec']
        tool_name = action_spec.get('tool_name')
        inputs = action_spec.get('inputs') or {}
        if not isinstance(tool_name, str) or not tool_name:
            raise TaskGraphError(f'Task {task_id} has no registered tool_name for ActionExecutor')
        receipt = self.action_executor.execute_action(
            tool_name,
            inputs,
            operation_id=node['operation_id'],
            delivery_mode=delivery_mode,
        )
        exec_state = receipt.get('state')
        if exec_state == 'succeeded' and receipt.get('postconditions_passed') is True:
            return self.submit_for_verification(
                task_id,
                result=receipt.get('output') if isinstance(receipt.get('output'), dict) else {'value': receipt.get('output')},
                evidence=receipt.get('evidence') or {'operation_id': node['operation_id'], 'verified_by': 'ActionExecutor'},
            )
        if exec_state == 'unknown' or receipt.get('effect_status') == 'unknown':
            return self.mark_unknown(task_id, reason=receipt.get('error') or 'Executor reported unknown effect')
        return self.fail_task(
            task_id,
            error=receipt.get('error') or f'Executor returned state={exec_state}',
            repairable=bool(node['is_pure']),
        )

    def submit_for_verification(
        self,
        task_id: str,
        *,
        result: dict[str, Any],
        evidence: dict[str, Any],
        unverified_items: list[str] | None = None,
        cost_usd: float = 0.0,
    ) -> dict[str, Any]:
        """Transition running -> verifying and record cost against graph budget."""
        _validate_id(task_id, 'task_id')
        if not isinstance(result, dict) or not isinstance(evidence, dict):
            raise TaskGraphError('result and evidence must be objects')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
                if not row:
                    raise TaskGraphError(f'Task not found: {task_id}')
                if row['state'] != 'running':
                    raise InvalidTaskTransitionError(f'Task {task_id} must be running to enter verifying (got {row["state"]})')
                run_row = db.execute('SELECT * FROM task_graph_runs WHERE run_id=?', (row['run_id'],)).fetchone()
                new_spent = float(run_row['spent_cost_usd']) + max(0.0, float(cost_usd))
                max_cost = float(run_row['max_cost_usd'])
                if max_cost > 0 and new_spent > max_cost:
                    db.execute(
                        "UPDATE task_graph_nodes SET state='blocked', error_text='Budget exceeded', updated_at_ms=? WHERE task_id=?",
                        (now, task_id),
                    )
                    db.execute(
                        "UPDATE task_graph_runs SET status='blocked', spent_cost_usd=?, updated_at_ms=? WHERE run_id=?",
                        (new_spent, now, row['run_id']),
                    )
                    db.execute('COMMIT')
                    raise BudgetExceededError(f'TaskGraph {row["run_id"]} exceeded max_cost_usd={max_cost}')
                db.execute(
                    '''
                    UPDATE task_graph_nodes
                    SET state='verifying', result_json=?, evidence_json=?, unverified_items_json=?, updated_at_ms=?
                    WHERE task_id=?
                    ''',
                    (
                        json.dumps(result, ensure_ascii=False),
                        json.dumps(evidence, ensure_ascii=False),
                        json.dumps(list(unverified_items or []), ensure_ascii=False),
                        now,
                        task_id,
                    ),
                )
                db.execute(
                    'UPDATE task_graph_runs SET spent_cost_usd=?, updated_at_ms=? WHERE run_id=?',
                    (new_spent, now, row['run_id']),
                )
                db.execute('COMMIT')
            except Exception:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise
        return self.get_task(task_id)

    def complete_verified_task(
        self,
        task_id: str,
        *,
        verifier_evidence: dict[str, Any],
        unverified_items: list[str] | None = None,
    ) -> dict[str, Any]:
        """Transition verifying -> completed ONLY when independent verifier supplies non-empty evidence."""
        _validate_id(task_id, 'task_id')
        if not isinstance(verifier_evidence, dict) or not verifier_evidence:
            raise TaskGraphError('Independent verifier_evidence is required to mark a task completed')
        if verifier_evidence.get('verified') is not True:
            raise TaskGraphError('verifier_evidence.verified must be True to complete task')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
                if not row:
                    raise TaskGraphError(f'Task not found: {task_id}')
                if row['state'] != 'verifying':
                    raise InvalidTaskTransitionError(
                        f'Prohibited completion without verifying phase: task {task_id} is in state {row["state"]}'
                    )
                merged_evidence = json.loads(row['evidence_json']) | {'verifier': verifier_evidence}
                unverified = list(unverified_items if unverified_items is not None else json.loads(row['unverified_items_json']))
                db.execute(
                    '''
                    UPDATE task_graph_nodes
                    SET state='completed', evidence_json=?, unverified_items_json=?, updated_at_ms=?
                    WHERE task_id=?
                    ''',
                    (
                        json.dumps(merged_evidence, ensure_ascii=False),
                        json.dumps(unverified, ensure_ascii=False),
                        now,
                        task_id,
                    ),
                )
                self._refresh_run_status(db, row['run_id'], now)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_task(task_id)

    def fail_task(self, task_id: str, *, error: str, repairable: bool = False) -> dict[str, Any]:
        _validate_id(task_id, 'task_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
                if not row:
                    raise TaskGraphError(f'Task not found: {task_id}')
                can_retry = (
                    repairable
                    and bool(row['is_pure'])
                    and int(row['attempt']) < int(row['max_attempts'])
                )
                next_state = 'ready' if can_retry else 'failed'
                db.execute(
                    'UPDATE task_graph_nodes SET state=?, error_text=?, updated_at_ms=? WHERE task_id=?',
                    (next_state, str(error)[:1000], now, task_id),
                )
                self._refresh_run_status(db, row['run_id'], now)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_task(task_id)

    def mark_unknown(self, task_id: str, *, reason: str = 'Interrupted after dispatch') -> dict[str, Any]:
        _validate_id(task_id, 'task_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
                if not row:
                    raise TaskGraphError(f'Task not found: {task_id}')
                db.execute(
                    "UPDATE task_graph_nodes SET state='unknown', error_text=?, updated_at_ms=? WHERE task_id=?",
                    (str(reason)[:1000], now, task_id),
                )
                self._refresh_run_status(db, row['run_id'], now)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_task(task_id)

    def cancel_task(self, task_id: str, *, reason: str = 'Cancelled by user') -> dict[str, Any]:
        """Cancel a task: pre-dispatch becomes 'cancelled'; post-dispatch becomes 'cancelled_with_effects' or 'unknown'."""
        _validate_id(task_id, 'task_id')
        now = self.clock()
        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT * FROM task_graph_nodes WHERE task_id=?', (task_id,)).fetchone()
                if not row:
                    raise TaskGraphError(f'Task not found: {task_id}')
                if row['state'] in TERMINAL_TASK_STATES:
                    db.execute('COMMIT')
                    return self._row_to_node(row)
                if row['dispatched'] and not row['is_pure']:
                    target_state = 'cancelled_with_effects'
                else:
                    target_state = 'cancelled'
                db.execute(
                    'UPDATE task_graph_nodes SET state=?, error_text=?, updated_at_ms=? WHERE task_id=?',
                    (target_state, str(reason)[:1000], now, task_id),
                )
                self._refresh_run_status(db, row['run_id'], now)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
        return self.get_task(task_id)

    def reconcile_after_crash(self, run_id: str | None = None) -> dict[str, Any]:
        """Inspect in-flight tasks after process restart against ActionExecutor journal (ORCH-02)."""
        now = self.clock()
        reconciled_unknown: list[str] = []
        requeued_safe: list[str] = []
        completed_from_journal: list[str] = []

        with self.lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                query = "SELECT * FROM task_graph_nodes WHERE state IN ('leased', 'running', 'interrupted')"
                params: tuple[Any, ...] = ()
                if run_id is not None:
                    query += ' AND run_id=?'
                    params = (run_id,)
                rows = db.execute(query, params).fetchall()
                affected_runs = set()
                for row in rows:
                    tid = row['task_id']
                    affected_runs.add(row['run_id'])
                    op_id = row['operation_id']
                    journal_entry = (
                        self.action_executor.get_operation(op_id)
                        if (self.action_executor is not None and op_id)
                        else None
                    )
                    if not row['dispatched'] and journal_entry is None:
                        db.execute(
                            "UPDATE task_graph_nodes SET state='ready', lease_id=NULL, updated_at_ms=? WHERE task_id=?",
                            (now, tid),
                        )
                        requeued_safe.append(tid)
                    elif journal_entry and journal_entry.get('state') == 'succeeded' and journal_entry.get('postconditions_passed') is True:
                        db.execute(
                            '''
                            UPDATE task_graph_nodes
                            SET state='completed', result_json=?, evidence_json=?, updated_at_ms=?
                            WHERE task_id=?
                            ''',
                            (
                                json.dumps({'output': journal_entry.get('output')}, ensure_ascii=False),
                                json.dumps(journal_entry.get('evidence') or {'reconciled_from_journal': op_id}, ensure_ascii=False),
                                now,
                                tid,
                            ),
                        )
                        completed_from_journal.append(tid)
                    elif row['is_pure'] and int(row['attempt']) < int(row['max_attempts']):
                        db.execute(
                            "UPDATE task_graph_nodes SET state='ready', lease_id=NULL, dispatched=0, updated_at_ms=? WHERE task_id=?",
                            (now, tid),
                        )
                        requeued_safe.append(tid)
                    else:
                        db.execute(
                            '''
                            UPDATE task_graph_nodes
                            SET state='unknown', error_text='Crash after dispatch; effect unknown and blocked from automatic retry',
                                updated_at_ms=?
                            WHERE task_id=?
                            ''',
                            (now, tid),
                        )
                        reconciled_unknown.append(tid)
                for rid in affected_runs:
                    self._refresh_run_status(db, rid, now)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise

        return {
            'reconciled_unknown': reconciled_unknown,
            'requeued_safe': requeued_safe,
            'completed_from_journal': completed_from_journal,
        }

    def _refresh_run_status(self, db: sqlite3.Connection, run_id: str, now: int) -> None:
        states = [
            r['state']
            for r in db.execute('SELECT state FROM task_graph_nodes WHERE run_id=?', (run_id,)).fetchall()
        ]
        if not states:
            return
        if all(s == 'completed' for s in states):
            status = 'completed'
        elif any(s == 'unknown' for s in states):
            status = 'unknown'
        elif any(s in ('cancelled', 'cancelled_with_effects') for s in states):
            status = 'cancelled'
        elif any(s == 'failed' for s in states):
            status = 'failed'
        elif any(s == 'blocked' for s in states):
            status = 'blocked'
        elif any(s in ('running', 'leased', 'verifying') for s in states):
            status = 'running'
        else:
            status = 'ready'
        db.execute(
            'UPDATE task_graph_runs SET status=?, updated_at_ms=? WHERE run_id=?',
            (status, now, run_id),
        )
