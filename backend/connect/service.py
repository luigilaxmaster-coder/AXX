"""Deterministic Axx Connect bridge, reusing the existing executor and policy.

No model, chat route, shell or arbitrary Python/JavaScript is reachable here.
Tasks are durable and idempotent. A claimed UI task interrupted by restart is
unknown and cannot be silently repeated. Writes retain the existing UI approval.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
import re
import sqlite3
import threading
import time
import uuid

from backend.commands import ADAPTERS, TERMINAL, ApprovalRequired
from backend.connect.registry import VERSION, UI_CAPABILITIES, augment_registry, describe, validate, validate_ui, tool_descriptors, concrete_action_arguments

ID_PATTERN = r'[A-Za-z0-9_.-]{1,128}'


def checked_id(value, name='operation_id'):
    if not isinstance(value, str) or not re.fullmatch(ID_PATTERN, value):
        raise ValueError(name + ' inválido')
    return value


class ConnectService:
    ADMISSION_TIMEOUT_SECONDS = 30

    def __init__(self, commands, memory):
        self.commands, self.memory = commands, memory
        augment_registry(commands)
        self.lock = threading.RLock()
        self.closed = False
        self.ui_seen = 0.0
        self.ui_handlers = set()
        self.workers = {}
        self.rejected_admissions = {}
        self.db = sqlite3.connect(str(commands.executor.db_path), timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS connect_tasks (
                operation_id TEXT PRIMARY KEY, command_id TEXT NOT NULL, inputs_json TEXT NOT NULL,
                origin TEXT NOT NULL, parent_execution_id TEXT, delegation_depth INTEGER NOT NULL,
                result_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)''')
            self.db.execute('CREATE TABLE IF NOT EXISTS connect_cancellations (operation_id TEXT PRIMARY KEY, created_at REAL NOT NULL)')
            for row in self.db.execute('SELECT * FROM connect_tasks').fetchall():
                result = json.loads(row['result_json'])
                if result['state'] in ('running', 'claimed'):
                    result.update(state='unknown', postconditions_passed=False,
                                  error={'code': 'RESTARTED', 'message': 'Efecto posible interrumpido; reconciliar antes de repetir.'})
                    self.db.execute('UPDATE connect_tasks SET result_json=?,updated_at=? WHERE operation_id=?',
                                    (json.dumps(result), time.time(), row['operation_id']))
                elif result['state'] == 'queued':
                    result.update(state='expired', error={'code': 'RESTARTED', 'message': 'No se ejecutó antes del reinicio.'})
                    self.db.execute('UPDATE connect_tasks SET result_json=?,updated_at=? WHERE operation_id=?',
                                    (json.dumps(result), time.time(), row['operation_id']))

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            # Worker actions use CommandService's own DB. A running effect is not
            # killed without adapter cancellation; its persisted result survives.
            self.db.close()
            workers = list(self.workers.values())
        deadline = time.monotonic() + 5
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(max(0, deadline - time.monotonic()))

    def _ui_available(self, key):
        return time.monotonic() - self.ui_seen < 8 and key in self.ui_handlers

    def status(self):
        with self.lock:
            enabled = sum(bool(entry.get('execution_enabled')) for key, entry in self.commands.commands.items() if key not in UI_CAPABILITIES)
            return {'name': 'Axx Connect', 'version': VERSION, 'executor': 'ready' if not self.closed else 'closed',
                    'model_authentication': 'consult_provider_status_separately', 'plugin_installation': 'requires_host_verification',
                    'ui_connected': time.monotonic() - self.ui_seen < 8,
                    'capability_count': len(self.commands.commands), 'backend_enabled': enabled,
                    'ui_enabled': [key for key in UI_CAPABILITIES if self._ui_available(key)],
                    'arbitrary_shell': False, 'planner_delegation': False, 'internet_listener': False,
                    'artifact_root': str(self.commands.executor.workspace_root)}

    def capabilities(self, query='', limit=100, offset=0):
        result = self.commands.search(query, limit, offset)
        result['commands'] = [describe(self.commands, entry, self._ui_available(entry['id'])) for entry in result['commands']]
        result['counts']['ui_enabled'] = sum(self._ui_available(key) for key in UI_CAPABILITIES)
        result['counts']['ui_total'] = len(UI_CAPABILITIES)
        return result

    def _save(self, result):
        if self.closed:
            return result
        self.db.execute('UPDATE connect_tasks SET result_json=?,updated_at=? WHERE operation_id=?',
                        (json.dumps(result, ensure_ascii=False, allow_nan=False), time.time(), result['operation_id']))
        self.db.commit()
        return result

    def _row(self, operation_id):
        return self.db.execute('SELECT * FROM connect_tasks WHERE operation_id=?', (operation_id,)).fetchone()

    def _trace(self, result):
        # CommandService/ActionExecutor persist parameter values and evidence in
        # their existing DB. No raw model prompt or token is added to logs.
        if result.get('state') != 'succeeded' or result.get('postconditions_passed') is not True:
            return
        key = result['command_id']
        if key not in ADAPTERS or not self.memory:
            return
        adapter = ADAPTERS[key]
        recipe_id = 'connect-' + key.replace('.', '-')
        try:
            if self.memory.find_recipe(recipe_id):
                return
            args = {name: '$inputs.' + name for name in result['inputs']}
            schema = self.commands.commands[key]['parameters']
            self.memory.register_recipe(id=recipe_id, intent_key=recipe_id,
                steps=[{'tool': adapter['tool'], 'args': args}], schema=schema, status='verified',
                preconditions=['Same registry adapter/version, executor scope, validated parameters and current permissions',
                               'axx-adapter-version:' + str(result.get('adapter_version'))],
                postconditions=['ActionExecutor.verify_postconditions passed; source operation ' + result['operation_id']])
            result['procedure_id'] = recipe_id
        except Exception as exc:
            result['memory_warning'] = type(exc).__name__

    def execute(self, body, *, admission=None, chat_policy=None):
        """Validate, then durably admit under an optional caller-owned guard.

        Lock order is service -> admission. The guard must not call this service
        while already held; workers and executor waits run after it is released.
        """
        schema = next(item['inputSchema'] for item in tool_descriptors() if item['name'] == 'axx_execute_action')
        validate(schema, body)
        key = body['command_id']
        operation_id = checked_id(body['operation_id'])
        if key not in self.commands.commands:
            raise ValueError('Capacidad desconocida')
        origin = body.get('origin', 'mcp')
        depth = body.get('delegation_depth', 0)
        parent = body.get('parent_execution_id')
        if parent is not None:
            checked_id(parent, 'parent_execution_id')
        if depth and (origin != 'axx-provider' or not parent):
            raise ValueError('Delegación inválida')
        if parent == operation_id:
            raise ValueError('No se permite una ejecución como su propio padre')
        if key.startswith(('axx.chat', 'axx.provider', 'axx.connect.chat')):
            raise ValueError('La planificación recursiva no es una herramienta')
        inputs = body['inputs']
        with self.lock:
            if self.closed:
                raise ValueError('Servicio cerrado')
            # A rejected caller must not even consume a CommandService prepare.
            # Re-enter at the durable admission point after potentially slow
            # preparation; no provider lock is held while that work waits.
            with (admission() if admission is not None else nullcontext()):
                pass
            previous = self._row(operation_id)
            if previous:
                if previous['command_id'] != key or json.loads(previous['inputs_json']) != inputs or previous['origin'] != origin or previous['parent_execution_id'] != parent or previous['delegation_depth'] != depth:
                    raise ValueError('operation_id vinculado a otra solicitud')
                return self.get_task(operation_id) | {'replayed': True}
            prepared = None
            cancelled = self.db.execute('SELECT 1 FROM connect_cancellations WHERE operation_id=?', (operation_id,)).fetchone()
            if cancelled:
                result = {'operation_id': operation_id, 'command_id': key, 'inputs': inputs, 'state': 'cancelled',
                    'postconditions_passed': False, 'output': None, 'evidence': {}, 'cancel_requested': True,
                    'error': {'code': 'CANCELLED', 'message': 'Cancelado antes de preparar; no se ha ejecutado.'}}
            elif key in UI_CAPABILITIES:
                validate_ui(key, inputs)
                available = self._ui_available(key)
                state = 'queued' if available else 'blocked'
                result = {'operation_id': operation_id, 'command_id': key, 'inputs': inputs, 'state': state,
                    'postconditions_passed': False, 'output': None, 'evidence': {}, 'cancel_requested': False,
                    'error': None if available else {'code': 'UI_UNAVAILABLE', 'message': 'Axx nativo no anuncia este handler activo.'}}
            else:
                # Existing policy, including immutable approved writes, remains
                # the only route to the registered action executor.
                reused = None
                if key in ADAPTERS and self.memory:
                    recipe_id = 'connect-' + key.replace('.', '-')
                    recipe = self.memory.find_recipe(recipe_id)
                    version = describe(self.commands, self.commands.commands[key]).get('adapter_version')
                    if (recipe and len(recipe.steps) == 1 and recipe.steps[0].get('tool') == ADAPTERS[key]['tool']
                            and recipe.schema == self.commands.commands[key]['parameters']
                            and 'axx-adapter-version:' + str(version) in recipe.preconditions):
                        expected = {name: '$inputs.' + name for name in inputs}
                        if recipe.steps[0].get('args') == expected:
                            # Resolve the verified recipe, then re-enter the same
                            # validation/approval path; recipes grant no permission.
                            inputs = {name: inputs[value[8:]] for name, value in expected.items()}
                            reused = {'id': recipe.id, 'version': recipe.version, 'environment': recipe.env_fingerprint}
                prepared = self.commands.prepare(key, inputs, 'text', operation_id, **(chat_policy or {}))
                result = prepared | {'inputs': inputs, 'procedure_reused': reused is not None}
                if reused:
                    result['procedure_id'] = reused['id']
                    result['procedure'] = reused
            result.update(origin=origin, parent_execution_id=parent, delegation_depth=depth,
                          adapter_version=describe(self.commands, self.commands.commands[key]).get('adapter_version'),
                          created_at=time.time(), attempts=1, goal=key, model_usage=None)
            now, inserted = time.time(), False
            try:
                if admission is not None:
                    # Never spend SQLite's usual ten-second busy wait holding
                    # the provider/account lock. Preparation remains inert.
                    self.db.execute('PRAGMA busy_timeout=0')
                with (admission() if admission is not None else nullcontext()) as recheck:
                    if callable(recheck):
                        recheck()
                    self.db.execute('INSERT INTO connect_tasks VALUES(?,?,?,?,?,?,?,?,?)',
                        (operation_id, key, json.dumps(inputs, sort_keys=True), origin, parent, depth, json.dumps(result, ensure_ascii=False), now, now))
                    self.db.commit()
                    inserted = True
                    if callable(recheck):
                        recheck()
            except Exception as exc:
                self.db.rollback()
                if admission is not None:
                    self.db.execute('PRAGMA busy_timeout=10000')
                    if inserted:
                        result.update(state='cancelled', cancel_requested=True, postconditions_passed=False,
                            admission_rejected=True, error={'code': getattr(exc, 'code', 'ADMISSION_REJECTED'),
                                'message': 'La admisión fue rechazada antes de programar el efecto.'})
                        # Fail closed even if persisting the rejection fails:
                        # ui_claim/get_task cannot revive the committed queue.
                        # A restart already expires every unclaimed queued row.
                        self.rejected_admissions[operation_id] = dict(result)
                    if prepared and not prepared.get('replayed') and prepared['state'] in ('prepared', 'awaiting_approval'):
                        self.commands.cancel(operation_id)
                    if inserted:
                        self._save(result)
                raise
            finally:
                if admission is not None:
                    self.db.execute('PRAGMA busy_timeout=10000')
            # The worker cannot acquire service.lock until the guard has exited.
            # Subsequent account updates do not revoke this already-admitted task.
            if key not in UI_CAPABILITIES and result['state'] == 'prepared':
                self._start_worker(operation_id)
            return self.get_task(operation_id)

    def _start_worker(self, operation_id):
        def work():
            try:
                deadline = time.monotonic() + self.ADMISSION_TIMEOUT_SECONDS
                while True:
                    with self.lock:
                        if self.closed:
                            return
                        pending = self.get_task(operation_id)
                        if not pending or pending['state'] in TERMINAL:
                            return
                    try:
                        result = self.commands.execute(operation_id, approved=False)
                        break
                    except ValueError as exc:
                        if not str(exc).startswith('BUSY:'):
                            raise
                        # BUSY is raised before CommandService acquires its
                        # execution gate: no effect was dispatched by this
                        # attempt. Only this admission failure can be retried.
                        with self.lock:
                            if self.closed:
                                return
                            pending = self.get_task(operation_id)
                            if not pending or pending['state'] in TERMINAL:
                                return
                            if time.monotonic() >= deadline:
                                cancelled = self.commands.cancel(operation_id)
                                pending.update(cancelled)
                                if cancelled['state'] == 'cancelled':
                                    pending.update(state='expired', postconditions_passed=False, admission_expired=True,
                                        executor_state='cancelled', error={'code': 'BUSY_TIMEOUT',
                                            'message': 'Caducó esperando el ejecutor; se canceló antes de ejecutar.'})
                                elif cancelled['state'] not in TERMINAL:
                                    pending.update(state='unknown', postconditions_passed=False,
                                        error={'code': 'BUSY_TIMEOUT', 'message': 'El ejecutor seguía ocupado. Reconciliar el efecto antes de repetir.'})
                                self._save(pending)
                                return
                        time.sleep(.05)
                with self.lock:
                    if not self.closed:
                        row = self._row(operation_id)
                        current = json.loads(row['result_json'])
                        current.update(result)
                        self._trace(current)
                        self._save(current)
            except ApprovalRequired:
                pass
            except Exception as exc:
                with self.lock:
                    if not self.closed:
                        row = self._row(operation_id)
                        result = json.loads(row['result_json'])
                        self._save(result | {'state': 'unknown', 'postconditions_passed': False,
                            'error': {'code': 'EXECUTION_UNCERTAIN', 'message': type(exc).__name__}})
        thread = threading.Thread(target=work, name='axx-connect-' + operation_id[:12], daemon=True)
        self.workers[operation_id] = thread
        thread.start()

    def get_task(self, operation_id):
        checked_id(operation_id)
        with self.lock:
            if operation_id in self.rejected_admissions:
                return dict(self.rejected_admissions[operation_id])
            row = self._row(operation_id)
            if not row:
                cancelled = self.db.execute('SELECT 1 FROM connect_cancellations WHERE operation_id=?', (operation_id,)).fetchone()
                return {'operation_id': operation_id, 'state': 'cancelled', 'cancel_requested': True,
                        'postconditions_passed': False} if cancelled else None
            result = json.loads(row['result_json'])
            key = result['command_id']
            if key not in UI_CAPABILITIES:
                current = self.commands.get(operation_id)
                if current and current['state'] != result['state'] and not (result.get('admission_expired') or result.get('admission_rejected')):
                    result.update(current)
                    self._trace(result)
                    self._save(result)
            elif result['state'] in ('queued', 'claimed') and time.time() - row['updated_at'] > 30:
                result.update(state='unknown' if result['state'] == 'claimed' else 'expired', postconditions_passed=False,
                              error={'code': 'UI_TIMEOUT', 'message': 'No se repite el efecto; reconciliar el estado en Axx.'})
                self._save(result)
            return result

    def cancel_task(self, operation_id):
        checked_id(operation_id)
        with self.lock:
            result = self.get_task(operation_id)
            if not result:
                self.db.execute('INSERT OR IGNORE INTO connect_cancellations VALUES(?,?)', (operation_id, time.time()))
                self.db.commit()
                return {'operation_id': operation_id, 'state': 'cancelled', 'cancel_requested': True, 'postconditions_passed': False}
            if result['state'] in TERMINAL:
                return result | {'cancellation_note': 'La cancelación no revierte efectos ya consumados.'}
            result['cancel_requested'] = True
            if result['command_id'] not in UI_CAPABILITIES:
                current = self.commands.cancel(operation_id)
                result.update(current)
            elif result['state'] == 'queued':
                result.update(state='cancelled', error={'code': 'CANCELLED', 'message': 'Cancelado antes de ejecutar.'})
            else:
                result['cancellation_note'] = 'La UI puede haber consumado el efecto; se conserva el resultado y no se presume rollback.'
            return self._save(result)

    def ui_claim(self, handlers=None):
        with self.lock:
            self.ui_seen = time.monotonic()
            if handlers is not None:
                if not isinstance(handlers, list) or any(key not in UI_CAPABILITIES for key in handlers):
                    raise ValueError('Lista de handlers UI inválida')
                self.ui_handlers = set(handlers)
            tasks = []
            # One claim per poll keeps ordering and prevents an unbounded UI loop.
            for row in self.db.execute('SELECT operation_id FROM connect_tasks ORDER BY created_at').fetchall():
                result = self.get_task(row['operation_id'])
                if result['state'] != 'queued' or result['command_id'] not in self.ui_handlers:
                    continue
                result.update(state='claimed', claim_id=uuid.uuid4().hex)
                self._save(result)
                tasks.append(result)
                break
            return {'tasks': tasks, 'version': VERSION}

    def ui_complete(self, body):
        validate({'type': 'object', 'properties': {'operation_id': {'type': 'string'}, 'claim_id': {'type': 'string'},
            'state': {'type': 'string', 'enum': ['succeeded', 'failed', 'unknown', 'blocked', 'cancelled']},
            'snapshot': {'type': 'object'}, 'evidence': {'type': 'object'}, 'output': {}, 'error': {}},
            'required': ['operation_id', 'claim_id', 'state', 'snapshot', 'evidence'], 'additionalProperties': False}, body)
        with self.lock:
            result = self.get_task(body['operation_id'])
            if not result or result['command_id'] not in UI_CAPABILITIES or result.get('claim_id') != body['claim_id']:
                raise ValueError('Claim UI no válido')
            if result['state'] != 'claimed':
                return result | {'replayed': True}
            state = body['state']
            # A dispatch receipt, empty object or model sentence cannot verify a
            # UI effect. The native adapter supplies a fresh authority snapshot.
            verified = state == 'succeeded' and bool(body['snapshot']) and body['evidence'].get('verified') is True
            if state == 'succeeded' and not verified:
                state = 'unknown'
            result.update(state=state, postconditions_passed=verified, output=body.get('output'),
                          evidence=body['evidence'] | {'snapshot': body['snapshot']}, error=body.get('error'),
                          duration_ms=round((time.time() - result['created_at']) * 1000, 2))
            return self._save(result)

    def dispatch(self, name, arguments, request_id, call_id, *, admission=None):
        descriptors = {entry['name']: entry for entry in tool_descriptors()}
        if name not in descriptors:
            raise ValueError('Herramienta no permitida')
        validate(descriptors[name]['inputSchema'], arguments)
        if name in {'axx_status', 'axx_list_capabilities', 'axx_get_task', 'axx_cancel_task'}:
            with self.lock:
                # Read/cancel admission is brief; the actual operation below
                # never inherits the account lock or a long-running wait.
                with (admission() if admission is not None else nullcontext()):
                    pass
                if name == 'axx_status':
                    return self.status()
                if name == 'axx_list_capabilities':
                    return self.capabilities(arguments.get('query', ''), arguments.get('limit', 100), arguments.get('offset', 0))
                if name == 'axx_get_task':
                    return self.get_task(arguments['operation_id'])
                checked_id(request_id, 'request_id')
                target = self.get_task(arguments['operation_id'])
                # Model callbacks can cancel only effects admitted to THIS run.
                # Reject unknown IDs rather than creating a tombstone capable
                # of suppressing a future native/MCP/other-run operation.
                if not target or target.get('origin') != 'axx-provider' or target.get('parent_execution_id') != request_id:
                    raise ValueError('La operación no pertenece a esta ejecución de Axx.')
                return self.cancel_task(arguments['operation_id'])
        checked_id(request_id, 'request_id')
        # A model cannot assert a trusted origin/parent/depth or approve a write.
        arguments = concrete_action_arguments(name, arguments)
        arguments.update(origin='axx-provider', parent_execution_id=request_id, delegation_depth=1)
        chat_policy = None
        with self.lock:
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if {'chat_conversations','connect_runs'} <= tables:
                chat_policy = {'command_mode': 'ask'}
                row = self.db.execute('SELECT c.id,c.mode FROM chat_conversations c JOIN connect_runs r ON r.conversation_id=c.connect_id WHERE r.request_id=?', (request_id,)).fetchone()
                if row:
                    chat_policy = {'conversation_id': row[0], 'command_mode': row[1]}
        result = self.execute(arguments, admission=admission, chat_policy=chat_policy)
        # Short, bounded waiting gives the model actual read-only executor output
        # in ordinary cases. Long operations return a queryable identifier.
        deadline = time.monotonic() + 2
        while result and result['state'] in ('prepared', 'running', 'queued', 'claimed') and time.monotonic() < deadline:
            time.sleep(.05)
            result = self.get_task(result['operation_id'])
        return result
