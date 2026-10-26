"""Boundary tests use real executor/files/SQLite; UI completion is controlled."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.memory.procedural_memory import ProceduralMemory
from backend.connect.service import ConnectService
from backend.connect.registry import dynamic_tools, UI_CAPABILITIES, read_only_aliases, tool_descriptors


class ConnectServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'state.db'
        self.executor = ActionExecutor(self.db, workspace_root=self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.memory = ProceduralMemory(self.db)
        self.service = ConnectService(self.commands, self.memory)

    def tearDown(self):
        for worker in self.service.workers.values():
            worker.join(3)
        self.service.close()
        self.memory.close()
        self.commands.close()
        self.executor.close()
        self.tmp.cleanup()

    def body(self, key='axx.system.telemetry', inputs=None, op='test-op'):
        return {'command_id': key, 'inputs': inputs or {}, 'operation_id': op}

    def terminal(self, op):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = self.service.get_task(op)
            if result['state'] in ('succeeded', 'failed', 'unknown', 'blocked', 'cancelled', 'expired'):
                return result
            time.sleep(.02)
        self.fail('Operation did not finish')

    def test_real_telemetry_and_verified_procedure_then_replay(self):
        self.service.execute(self.body())
        result = self.terminal('test-op')
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        self.assertGreater(result['output']['disk_total_gb'], 0)
        self.assertTrue(self.memory.find_recipe('connect-axx-system-telemetry'))
        replay = self.service.execute(self.body())
        self.assertTrue(replay['replayed'])
        count = self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]
        self.assertEqual(count, 1)

    def test_write_requires_existing_approval_and_idempotent_content_hash(self):
        body = self.body('axx.artifact.write', {'path': 'verified.txt', 'content': 'Axx Connect'}, 'file-op')
        prepared = self.service.execute(body)
        self.assertEqual(prepared['state'], 'awaiting_approval')
        path = self.executor.workspace_root / 'verified.txt'
        self.assertFalse(path.exists())
        self.commands.execute('file-op', approved=True)  # Existing UI policy path.
        result = self.service.get_task('file-op')
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['evidence']['sha256'])
        self.assertEqual(path.read_text(), 'Axx Connect')
        self.assertTrue(self.service.execute(body)['replayed'])
        with self.assertRaises(ValueError):
            self.service.execute(body | {'inputs': {'path': 'verified.txt', 'content': 'different'}})

    def test_verified_procedure_survives_restart_and_preserves_write_approval(self):
        first = self.body('axx.artifact.write', {'path': 'first.txt', 'content': 'first verified'}, 'first-file')
        self.service.execute(first)
        self.commands.execute('first-file', approved=True)
        self.assertEqual(self.service.get_task('first-file')['state'], 'succeeded')
        recipe = self.memory.find_recipe('connect-axx-artifact-write')
        self.assertIsNotNone(recipe)
        original_version = recipe.version
        self.service.close(); self.memory.close(); self.commands.close(); self.executor.close()
        self.executor = ActionExecutor(self.db, workspace_root=self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.memory = ProceduralMemory(self.db)
        self.service = ConnectService(self.commands, self.memory)
        repeated = self.service.execute(self.body('axx.artifact.write', {'path': 'second.txt', 'content': 'second needs authorization'}, 'second-file'))
        self.assertTrue(repeated['procedure_reused'])
        self.assertEqual(repeated['procedure']['version'], original_version)
        self.assertEqual(repeated['state'], 'awaiting_approval')
        self.assertFalse((self.executor.workspace_root / 'second.txt').exists())
        self.service.cancel_task('second-file')
        self.assertFalse((self.executor.workspace_root / 'second.txt').exists())
        self.assertEqual(self.memory.find_recipe('connect-axx-artifact-write').version, original_version)

    def test_model_cannot_approve_or_reenter_planner(self):
        with self.assertRaises(ValueError):
            self.service.execute(self.body() | {'approved': True})
        with self.assertRaises(ValueError):
            self.service.execute(self.body('axx.chat', {}))
        with self.assertRaises(ValueError):
            self.service.execute(self.body() | {'origin': 'axx-provider', 'parent_execution_id': 'parent', 'delegation_depth': 2})
        with self.assertRaises(ValueError):
            self.service.execute(self.body() | {'origin': 'axx-provider', 'parent_execution_id': 'test-op', 'delegation_depth': 1})
        with self.assertRaises(ValueError):
            self.service.dispatch('turn/start', {}, 'parent', 'call')
        result = self.service.dispatch('axx_execute_action', self.body('axx.system.telemetry'), 'parent', 'call')
        self.assertEqual(result['origin'], 'axx-provider')
        self.assertEqual(result['parent_execution_id'], 'parent')
        self.assertEqual(result['delegation_depth'], 1)

    def test_generated_read_only_aliases_reuse_exact_executor_and_validation(self):
        aliases = read_only_aliases()
        required = {'axx_system_telemetry': 'axx.system.telemetry', 'axx_process_inspect': 'axx.process.inspect', 'axx_desktop_list_apps': 'axx.desktop.list_apps', 'axx_desktop_list_windows': 'axx.desktop.list_windows', 'axx_desktop_window_inspect': 'axx.desktop.window.inspect', 'axx_desktop_cli_anything_scan': 'axx.desktop.cli_anything.scan', 'axx_desktop_window_find': 'axx.desktop.window.find', 'axx_architecture_status': 'axx.architecture.status'}
        self.assertLessEqual(required.items(), aliases.items())
        metadata = {item['name']: item for item in tool_descriptors()}
        for name in aliases:
            self.assertTrue(metadata[name]['annotations']['readOnlyHint'])
            self.assertFalse(metadata[name]['annotations']['destructiveHint'])
            self.assertIn('operation_id', metadata[name]['inputSchema']['required'])
        self.assertTrue(metadata['axx_execute_action']['annotations']['destructiveHint'])
        result = self.service.dispatch('axx_system_telemetry', {'operation_id': 'alias-read'}, 'provider-turn', 'call1')
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['postconditions_passed'])
        self.assertEqual(result['command_id'], 'axx.system.telemetry')
        self.assertEqual(result['origin'], 'axx-provider')
        self.assertEqual(self.executor.db.execute('SELECT tool_name FROM operations').fetchone()[0], 'system_telemetry')
        replay = self.service.dispatch('axx_system_telemetry', {'operation_id': 'alias-read'}, 'provider-turn', 'call1')
        self.assertTrue(replay['replayed'])
        self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
        for invalid in ({'operation_id': 'alias-invalid', 'pid': True}, {'operation_id': 'alias-invalid', 'approved': True}, {'pid': 1}):
            with self.assertRaises(ValueError):
                self.service.dispatch('axx_process_inspect', invalid, 'provider-turn', 'call2')

    def test_denied_admission_never_prepares_persists_or_schedules_an_action(self):
        @contextmanager
        def denied():
            raise ValueError('ACCOUNT_CHANGED')
            yield  # pragma: no cover - context-manager protocol only.

        with patch.object(self.commands, 'prepare', side_effect=AssertionError('must not prepare')) as prepare:
            for name, arguments in (
                    ('axx_execute_action', self.body(op='denied-generic')),
                    ('axx_system_telemetry', {'operation_id': 'denied-alias'}),
                    ('axx_execute_action', self.body('axx.ui.local', {'action': 'time'}, 'denied-ui'))):
                with self.assertRaisesRegex(ValueError, 'ACCOUNT_CHANGED'):
                    self.service.dispatch(name, arguments, 'provider-turn', 'call', admission=denied)
            self.assertFalse(prepare.called)
        self.assertEqual(self.service.db.execute('SELECT COUNT(*) FROM connect_tasks').fetchone()[0], 0)
        self.assertEqual(self.commands.db.execute('SELECT COUNT(*) FROM command_runs').fetchone()[0], 0)
        self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
        self.assertFalse(self.service.workers)

    def test_admission_changed_during_preparation_cancels_inert_prepare_without_worker(self):
        entries = []
        @contextmanager
        def admission():
            entries.append(len(entries) + 1)
            if len(entries) == 2:
                raise ValueError('ACCOUNT_CHANGED')
            yield lambda: None

        with self.assertRaisesRegex(ValueError, 'ACCOUNT_CHANGED'):
            self.service.execute(self.body(op='changed-after-prepare'), admission=admission)
        self.assertEqual(entries, [1, 2])
        self.assertEqual(self.commands.get('changed-after-prepare')['state'], 'cancelled')
        self.assertIsNone(self.service.get_task('changed-after-prepare'))
        self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
        self.assertFalse(self.service.workers)

    def test_expired_admission_after_commit_cannot_schedule_or_claim_effects(self):
        def expiring():
            @contextmanager
            def admission():
                checks = []
                def recheck():
                    checks.append(True)
                    if len(checks) == 2:
                        raise ValueError('DEADLINE_EXCEEDED')
                yield recheck
            return admission

        self.service.ui_claim(['axx.ui.local'])
        for body in (self.body(op='expired-backend'),
                     self.body('axx.ui.local', {'action': 'time'}, 'expired-ui')):
            with self.assertRaisesRegex(ValueError, 'DEADLINE_EXCEEDED'):
                self.service.execute(body, admission=expiring())
            result = self.service.get_task(body['operation_id'])
            self.assertEqual(result['state'], 'cancelled')
            self.assertTrue(result['admission_rejected'])
            self.assertTrue(self.service.execute(body)['replayed'])
        self.assertEqual(self.commands.get('expired-backend')['state'], 'cancelled')
        self.assertFalse(self.service.ui_claim()['tasks'])
        self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
        self.assertFalse(self.service.workers)

    def test_admission_guard_is_free_during_prepare_worker_and_dispatch_wait(self):
        gate = threading.Lock()
        entered, release = threading.Event(), threading.Event()
        observations, results, failures = [], [], []
        @contextmanager
        def admission():
            with gate:
                yield lambda: None
        def assert_free(phase):
            free = gate.acquire(blocking=False)
            observations.append((phase, free))
            if free:
                gate.release()
        prepare, execute = self.commands.prepare, self.executor.execute_action
        def controlled_prepare(*args, **kwargs):
            assert_free('prepare')
            return prepare(*args, **kwargs)
        def controlled_effect(*args, **kwargs):
            assert_free('worker')
            entered.set()
            if not release.wait(2):
                raise RuntimeError('Controlled effect release timed out')
            return execute(*args, **kwargs)
        def dispatch():
            try:
                results.append(self.service.dispatch('axx_system_telemetry', {'operation_id': 'guarded-read'},
                    'provider-turn', 'call', admission=admission))
            except Exception as exc:
                failures.append(exc)
        self.commands.prepare, self.executor.execute_action = controlled_prepare, controlled_effect
        worker = threading.Thread(target=dispatch)
        try:
            worker.start()
            self.assertTrue(entered.wait(2))
            assert_free('dispatcher-wait')
            self.assertEqual(self.service.status()['executor'], 'ready')
            release.set(); worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(failures)
            self.assertEqual(results[0]['state'], 'succeeded')
            self.assertEqual(observations, [('prepare', True), ('worker', True), ('dispatcher-wait', True)])
        finally:
            release.set(); worker.join(3)
            self.commands.prepare, self.executor.execute_action = prepare, execute

    def test_rejected_committed_ui_admission_stays_closed_if_rejection_save_fails(self):
        @contextmanager
        def admission():
            checks = []
            def recheck():
                checks.append(True)
                if len(checks) == 2:
                    raise ValueError('DEADLINE_EXCEEDED')
            yield recheck
        self.service.ui_claim(['axx.ui.local'])
        body = self.body('axx.ui.local', {'action': 'time'}, 'rejection-save-failed')
        with patch.object(self.service, '_save', side_effect=sqlite3.OperationalError('controlled write failure')):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.execute(body, admission=admission)
        self.assertEqual(self.service.get_task(body['operation_id'])['state'], 'cancelled')
        self.assertFalse(self.service.ui_claim()['tasks'])
        self.service.close(); self.service = ConnectService(self.commands, self.memory)
        self.service.ui_claim(['axx.ui.local'])
        self.assertEqual(self.service.get_task(body['operation_id'])['state'], 'expired')
        self.assertFalse(self.service.ui_claim()['tasks'])

    def test_read_and_cancel_admission_guard_does_not_cover_the_operation(self):
        gate = threading.Lock()
        @contextmanager
        def admission():
            with gate:
                yield lambda: None
        def checked_result(*args, **kwargs):
            free = gate.acquire(blocking=False)
            self.assertTrue(free)
            if free:
                gate.release()
            return {'admitted': True}
        for name, arguments, method in (
                ('axx_status', {}, 'status'),
                ('axx_list_capabilities', {}, 'capabilities'),
                ('axx_get_task', {'operation_id': 'read-task'}, 'get_task')):
            with patch.object(self.service, method, side_effect=checked_result):
                self.assertTrue(self.service.dispatch(name, arguments, 'provider-turn', 'call', admission=admission)['admitted'])
        self.service.ui_claim(['axx.ui.local'])
        self.service.dispatch('axx_execute_action', self.body('axx.ui.local', {'action': 'time'}, 'owned-cancel'),
            'provider-turn', 'call')
        with patch.object(self.service, 'cancel_task', side_effect=checked_result):
            self.assertTrue(self.service.dispatch('axx_cancel_task', {'operation_id': 'owned-cancel'},
                'provider-turn', 'cancel', admission=admission)['admitted'])

    def test_busy_durable_admission_never_waits_on_sqlite_under_guard(self):
        gate = threading.Lock()
        blocker = sqlite3.connect(str(self.db))
        prepare, cancel = self.commands.prepare, self.commands.cancel
        @contextmanager
        def admission():
            with gate:
                yield lambda: None
        def prepare_then_block(*args, **kwargs):
            result = prepare(*args, **kwargs)
            blocker.execute('BEGIN IMMEDIATE')
            return result
        def cancel_after_guard(*args, **kwargs):
            self.assertFalse(gate.locked())
            blocker.rollback()
            return cancel(*args, **kwargs)
        try:
            with patch.object(self.commands, 'prepare', side_effect=prepare_then_block), \
                    patch.object(self.commands, 'cancel', side_effect=cancel_after_guard):
                started = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError):
                    self.service.execute(self.body(op='sqlite-blocked'), admission=admission)
                self.assertLess(time.monotonic() - started, 1)
            self.assertIsNone(self.service.get_task('sqlite-blocked'))
            self.assertEqual(self.commands.get('sqlite-blocked')['state'], 'cancelled')
            self.assertEqual(self.service.db.execute('PRAGMA busy_timeout').fetchone()[0], 10000)
            self.assertFalse(self.service.workers)
        finally:
            blocker.rollback(); blocker.close()

    def test_provider_cancellation_scoped_to_admitted_run_and_rejects_foreign_ids(self):
        self.service.ui_claim(['axx.ui.local'])
        body = self.body('axx.ui.local', {'action': 'note', 'text': 'Owned by run B'}, 'shared-operation')
        admitted = self.service.dispatch('axx_execute_action', body, 'run-B', 'call-B')
        self.assertEqual(admitted['state'], 'queued')
        self.assertEqual(admitted['parent_execution_id'], 'run-B')
        with self.assertRaises(ValueError):
            self.service.dispatch('axx_execute_action', body, 'run-A', 'call-A')
        with self.assertRaises(ValueError):
            self.service.dispatch('axx_cancel_task', {'operation_id': 'shared-operation'}, 'run-A', 'cancel-A')
        self.assertEqual(self.service.get_task('shared-operation')['state'], 'queued')
        self.assertFalse(self.service.get_task('shared-operation')['cancel_requested'])
        own = self.service.dispatch('axx_cancel_task', {'operation_id': 'shared-operation'}, 'run-B', 'cancel-B')
        self.assertEqual(own['state'], 'cancelled')

        native = self.commands.prepare('axx.artifact.write', {'path': 'native.txt', 'content': 'Unrelated native approval'}, 'text', 'native-operation')
        self.assertEqual(native['state'], 'awaiting_approval')
        with self.assertRaises(ValueError):
            self.service.dispatch('axx_cancel_task', {'operation_id': 'native-operation'}, 'run-A', 'cancel-native')
        self.assertEqual(self.commands.get('native-operation')['state'], 'awaiting_approval')
        with self.assertRaises(ValueError):
            self.service.dispatch('axx_cancel_task', {'operation_id': 'not-admitted'}, 'run-A', 'cancel-unknown')
        self.assertIsNone(self.service.get_task('not-admitted'))
        self.assertIsNone(self.service.db.execute('SELECT 1 FROM connect_cancellations WHERE operation_id=?', ('not-admitted',)).fetchone())
        later = self.service.dispatch('axx_system_telemetry', {'operation_id': 'not-admitted'}, 'run-B', 'later-admitted')
        self.assertEqual(later['state'], 'succeeded')

    def test_overlapping_backend_reads_wait_for_admission_then_execute_once(self):
        entered, release = threading.Event(), threading.Event()
        original = self.executor.execute_action
        calls = []
        def controlled_first(*args, **kwargs):
            calls.append(args[2])
            if len(calls) == 1:
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Controlled executor release timed out')
            return original(*args, **kwargs)
        self.executor.execute_action = controlled_first
        try:
            self.service.execute(self.body(op='first-overlap'))
            self.assertTrue(entered.wait(2))
            self.service.execute(self.body(op='second-overlap'))
            time.sleep(.15)
            waiting = self.service.get_task('second-overlap')
            self.assertEqual(waiting['state'], 'prepared')
            self.assertEqual(len(calls), 1)
            release.set()
            self.assertEqual(self.terminal('first-overlap')['state'], 'succeeded')
            self.assertEqual(self.terminal('second-overlap')['state'], 'succeeded')
            self.assertEqual(len(calls), 2)
            self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 2)
        finally:
            release.set()

    def test_cancelling_waiting_admission_prevents_its_effect(self):
        entered, release = threading.Event(), threading.Event()
        original = self.executor.execute_action
        calls = []
        def controlled_first(*args, **kwargs):
            calls.append(args[2])
            if len(calls) == 1:
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Controlled executor release timed out')
            return original(*args, **kwargs)
        self.executor.execute_action = controlled_first
        try:
            self.service.execute(self.body(op='first-held'))
            self.assertTrue(entered.wait(2))
            self.service.execute(self.body(op='second-cancelled'))
            self.assertEqual(self.service.cancel_task('second-cancelled')['state'], 'cancelled')
            release.set()
            self.assertEqual(self.terminal('first-held')['state'], 'succeeded')
            self.service.workers['second-cancelled'].join(2)
            self.assertEqual(self.service.get_task('second-cancelled')['state'], 'cancelled')
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
        finally:
            release.set()

    def test_busy_admission_deadline_expires_without_effect_and_stays_terminal(self):
        self.service.ADMISSION_TIMEOUT_SECONDS = .1
        self.assertTrue(self.commands.execution_gate.acquire(blocking=False))
        try:
            self.service.execute(self.body(op='busy-expiry'))
            result = self.terminal('busy-expiry')
            self.assertEqual(result['state'], 'expired')
            self.assertEqual(result['error']['code'], 'BUSY_TIMEOUT')
            self.assertTrue(result['admission_expired'])
            self.assertEqual(self.commands.get('busy-expiry')['state'], 'cancelled')
            self.assertEqual(self.service.get_task('busy-expiry')['state'], 'expired')
            self.assertTrue(self.service.execute(self.body(op='busy-expiry'))['replayed'])
            self.assertEqual(self.executor.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
        finally:
            self.commands.execution_gate.release()

    def test_ui_absent_and_documentary_are_blocked(self):
        result = self.service.execute(self.body('axx.ui.local', {'action': 'time'}))
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(result['error']['code'], 'UI_UNAVAILABLE')
        result = self.service.execute(self.body('axx.blender.fixture', {}, 'blender'))
        self.assertEqual(result['state'], 'blocked')
        self.assertFalse(result['postconditions_passed'])

    def test_ui_queue_claim_not_success_and_bad_or_empty_proof_unknown(self):
        self.service.ui_claim(['axx.ui.local'])
        result = self.service.execute(self.body('axx.ui.local', {'action': 'time'}))
        self.assertEqual(result['state'], 'queued')
        task = self.service.ui_claim()['tasks'][0]
        self.assertEqual(task['state'], 'claimed')
        with self.assertRaises(ValueError):
            self.service.ui_complete({'operation_id': 'test-op', 'claim_id': 'wrong', 'state': 'succeeded', 'snapshot': {'a': 1}, 'evidence': {'verified': True}})
        result = self.service.ui_complete({'operation_id': 'test-op', 'claim_id': task['claim_id'], 'state': 'succeeded', 'snapshot': {}, 'evidence': {'verified': True}})
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(result['postconditions_passed'])
        self.assertTrue(self.service.execute(self.body('axx.ui.local', {'action': 'time'}))['replayed'])
        self.assertFalse(self.service.ui_claim()['tasks'])

    def test_cancellation_before_prepare_and_before_ui_claim(self):
        self.service.cancel_task('before')
        result = self.service.execute(self.body(op='before'))
        self.assertEqual(result['state'], 'cancelled')
        self.service.ui_claim(['axx.ui.local'])
        self.service.execute(self.body('axx.ui.local', {'action': 'note', 'text': 'test'}, 'note'))
        result = self.service.cancel_task('note')
        self.assertEqual(result['state'], 'cancelled')
        self.assertFalse(self.service.ui_claim()['tasks'])

    def test_restart_claimed_unknown_no_reexecution(self):
        self.service.ui_claim(['axx.ui.local'])
        body = self.body('axx.ui.local', {'action': 'todo', 'text': 'do once'})
        self.service.execute(body)
        self.service.ui_claim()
        self.service.close()
        self.service = ConnectService(self.commands, self.memory)
        self.assertEqual(self.service.get_task('test-op')['state'], 'unknown')
        self.service.ui_claim(['axx.ui.local'])
        self.assertTrue(self.service.execute(body)['replayed'])
        self.assertFalse(self.service.ui_claim()['tasks'])

    def test_schema_validation_and_generated_registry(self):
        self.assertIn('axx.ui.reader', self.commands.commands)
        for inputs in ({'action': 'timer'}, {'action': 'timer', 'ms': True}, {'action': 'note', 'text': ''}, {'action': 'execute', 'code': 'evil'}):
            with self.assertRaises(ValueError):
                self.service.execute(self.body('axx.ui.local', inputs))
        specs = dynamic_tools(self.commands)
        self.assertEqual(len(specs), 1)
        self.assertEqual((specs[0]['type'], specs[0]['name']), ('namespace', 'axx'))
        self.assertEqual(len(specs[0]['tools']), 5 + len(read_only_aliases()))
        self.assertTrue(all(s['type'] == 'function' and s['deferLoading'] is False for s in specs[0]['tools']))
        descriptions = self.service.capabilities('axx.ui', 100)['commands']
        self.assertEqual(sum(item['source']['kind'] == 'ui_adapter' for item in descriptions), len(UI_CAPABILITIES))
        self.assertTrue(all('handler' in item and 'input_schema' in item for item in descriptions))


if __name__ == '__main__':
    unittest.main()
