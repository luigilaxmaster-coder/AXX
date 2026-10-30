"""Observed-context dispatch receipts use synthetic sources and isolated loopback HTTP."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import sqlite3
import socket
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.action_learning import ActionLearning
from backend.actions.executor import ActionExecutor
from backend.commands import CommandService
from backend.inference.adapter import InferenceAdapter
from backend.inference.router import Router, profile_id
from backend.tests import test_planning_context as planning_fixtures


class SourceDispatchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = planning_fixtures.SourcePublicationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.learning = self.fixture.learning
        self.provider = dict(name='synthetic-local', model='synthetic-model',
            base_url='http://127.0.0.1:1/v1', api_key_env='UNUSED_SOURCE_TEST_KEY',
            enabled=True, free_confirmed=True, billing_allowed=False, cost_evidence='direct_local',
            route_kind='direct', context_window=32768, capabilities=['text'],
            allow_sensitive=True, daily_attempt_limit=100)
        self.adapter = InferenceAdapter({'providers': [self.provider], 'max_attempts': 2}, self.root / 'router.db')
        self.addCleanup(self.adapter.close)
        self.learning.adapter = self.adapter

    def authorize_current_provider(self):
        self.fixture.target['allowed_profile_ids'] = [profile_id(self.provider)]
        self.fixture.service.configure({'observation_targets': [self.fixture.target]})
        self.fixture.service.tick()

    def metadata(self):
        rows = self.learning.budget_db.execute(
            'SELECT source_dispatch_json FROM mission_model_calls WHERE plan_id=?', ('source-plan',)).fetchall()
        self.assertEqual(len(rows), 1)
        return json.loads(rows[0][0]) if rows[0][0] is not None else None

    def assert_no_canaries(self):
        for connection in (self.learning.db, self.adapter.router.db):
            dump = '\n'.join(connection.iterdump())
            for text in ('PRIVATE_SOURCE_RAW', 'SYNTHETIC_RESPONSE_CANARY', 'SYNTHETIC_DIAGNOSTIC_CANARY'):
                self.assertNotIn(text, dump)
        for path in self.root.rglob('*'):
            if path.is_file():
                for text in (b'PRIVATE_SOURCE_RAW', b'SYNTHETIC_RESPONSE_CANARY', b'SYNTHETIC_DIAGNOSTIC_CANARY'):
                    self.assertNotIn(text, path.read_bytes(), str(path))

    def test_eight_column_ledger_migrates_without_changing_legacy_rows(self):
        state = self.root / 'legacy.db'
        with sqlite3.connect(state) as db:
            db.execute('''CREATE TABLE mission_model_calls (plan_id TEXT NOT NULL,request_id TEXT NOT NULL,
                kind TEXT NOT NULL,state TEXT NOT NULL,charge INTEGER NOT NULL,confirmed INTEGER NOT NULL,
                created_at REAL NOT NULL,settled_at REAL,PRIMARY KEY(plan_id,request_id))''')
            old = ('legacy-plan', 'legacy-request', 'plan', 'unknown', 2, 0, 1.0, 2.0)
            db.execute('INSERT INTO mission_model_calls VALUES (?,?,?,?,?,?,?,?)', old)
        db.close()
        executor = ActionExecutor(state, self.root / 'legacy-artifacts')
        commands = CommandService(executor)
        learning = ActionLearning(commands, self.adapter)
        try:
            row = learning.budget_db.execute('SELECT * FROM mission_model_calls').fetchone()
            self.assertEqual(row[:8], old)
            self.assertEqual(len(row), 9)
            self.assertIsNone(row[8])
            plan, _ = learning._new_plan('Explicit synthetic goal', 'new-plan', {}, 'project-a')
            learning._reserve_model_call(plan, 'new-request', 'plan')
            self.assertIsNone(learning.budget_db.execute(
                'SELECT source_dispatch_json FROM mission_model_calls WHERE request_id=?', ('new-request',)).fetchone()[0])
        finally:
            learning.close(); commands.close(); executor.close()

    def test_four_refs_share_one_charge_and_inline_attempts_never_confirm_http(self):
        targets = [self.fixture.target | {'id': 'source-' + str(index)} for index in range(4)]
        self.fixture.service.configure({'observation_targets': targets})
        self.fixture.service.tick()
        self.adapter.router.transport = lambda *args, **kwargs: {
            'dispatch_receipt': {'version': 1, 'endpoint_receipts': [{'profile_id': 'SYNTHETIC_RESPONSE_CANARY'}]},
            'choices': [{'message': {'role': 'assistant', 'content': 'SYNTHETIC_RESPONSE_CANARY'}}]}
        result = self.fixture.response()
        self.assertTrue(result['ok'])
        metadata = self.metadata()
        self.assertEqual(len(metadata['refs']), 4)
        expected = self.fixture.service.provider_context_for_task('source-task', project_id='project-a')['refs']
        self.assertEqual(metadata['refs'], expected)
        self.assertEqual(metadata['task_id'], 'source-task')
        self.assertEqual(metadata['project_id'], 'project-a')
        self.assertEqual(metadata['send_state'], 'runtime_delivered')
        self.assertEqual(metadata['runtime_evidence'], 'inline_test')
        self.assertEqual(metadata['endpoint_receipts'], [])
        self.assertEqual(self.learning.budget_db.execute(
            'SELECT state,charge,confirmed FROM mission_model_calls').fetchall(), [('confirmed', 1, 1)])
        self.assert_no_canaries()

    def test_observer_start_failure_prevents_process_and_input(self):
        def observer(event):
            raise sqlite3.OperationalError('SYNTHETIC_DIAGNOSTIC_CANARY')
        with patch('backend.inference.adapter.spawn_managed_process') as spawn:
            result = self.adapter.route({'messages': [{'role': 'user', 'content': 'synthetic'}]},
                                        dispatch_observer=observer)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'STATE_UNAVAILABLE')
        self.assertNotIn('SYNTHETIC_DIAGNOSTIC_CANARY', json.dumps(result))
        spawn.assert_not_called()
        self.assertFalse(self.adapter.active_requests)
        self.assertFalse(self.adapter.conversation_locks)

    def test_source_backend_without_receipt_support_abstains_before_reservation(self):
        self.learning.adapter = self.fixture.model
        self.fixture.model.supports_dispatch_observer = False
        with patch.object(self.fixture.model, 'route') as route:
            with self.assertRaisesRegex(ValueError, 'recibo'):
                self.fixture.response()
        route.assert_not_called()
        self.assertEqual(self.learning.budget_db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0], 0)

    def test_codex_abstains_even_if_a_future_backend_claims_observer_support(self):
        backend = self.fixture.model
        backend.supports_dispatch_observer = True
        self.learning.workshop = SimpleNamespace(provider=backend)
        self.fixture.plan['planning_settings'] = {'provider_name': '@codex', 'model': 'synthetic-model', 'selection_mode': 'manual'}
        with patch.object(backend, 'generate_plan', create=True) as generate:
            with self.assertRaisesRegex(ValueError, 'recibo'):
                self.fixture.response()
        generate.assert_not_called()
        self.assertEqual(self.learning.budget_db.execute('SELECT COUNT(*) FROM mission_model_calls').fetchone()[0], 0)

    def test_cancel_or_crash_without_terminal_receipt_keeps_unknown(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                # A separate plan/request keeps each dispatch's budget independent.
                if cancelled:
                    plan, _ = self.learning._new_plan('Second explicit goal', 'source-plan-cancelled', {}, 'project-a')
                    plan.update(conversation_id='source-task', operational_context=self.fixture.plan['operational_context'],
                        planning_settings=self.fixture.plan['planning_settings'])
                    self.learning._save(plan)
                    self.fixture.plan = plan
                written = []
                outer = self
                class Input:
                    def write(inner, data):
                        raw = outer.learning.budget_db.execute(
                            'SELECT source_dispatch_json FROM mission_model_calls WHERE plan_id=?',
                            (outer.fixture.plan['operation_id'],)).fetchone()[0]
                        outer.assertEqual(json.loads(raw)['send_state'], 'unknown')
                        written.append(data)
                    def close(inner): pass
                class Process:
                    stdin = Input()
                    stdout = io.BytesIO()
                    stderr = io.BytesIO(b'SYNTHETIC_DIAGNOSTIC_CANARY')
                    returncode = 1
                    stopped = False
                    revoked = False
                    def poll(inner):
                        if cancelled and not inner.revoked:
                            inner.revoked = True
                            outer.fixture.revoke()
                        return None if cancelled and not inner.stopped else 1
                process = Process()
                with patch('backend.inference.adapter.spawn_managed_process', return_value=(process, None)), \
                        patch('backend.inference.adapter.terminate_process_tree',
                              side_effect=lambda proc, job: setattr(proc, 'stopped', True)):
                    with self.assertRaises(ValueError):
                        self.fixture.response()
                row = self.learning.budget_db.execute(
                    'SELECT source_dispatch_json,state,charge,confirmed FROM mission_model_calls WHERE plan_id=?',
                    (self.fixture.plan['operation_id'],)).fetchone()
                metadata = json.loads(row[0])
                self.assertEqual(metadata['send_state'], 'unknown')
                self.assertEqual(metadata['endpoint_receipts'], [])
                self.assertNotIn('runtime_received_at', metadata)
                self.assertEqual(row[1:], ('unknown', 2, 0))
                self.assert_no_canaries()

    def test_http_gateway_receipt_confirms_only_gateway_endpoint(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body = b'{"choices":[{"message":{"role":"assistant","content":"synthetic"}}]}'
                self.send_response(200); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        provider = self.provider | {'kind': 'freellmapi', 'route_kind': 'proxy', 'cost_evidence': 'unknown',
            'model': 'auto:axx_plan', 'api_key_env': 'SOURCE_GATEWAY_FIXTURE',
            'base_url': 'http://127.0.0.1:' + str(server.server_port) + '/v1'}
        router = Router({'providers': [provider]}, self.root / 'gateway.db')
        try:
            receipts = []
            with patch.dict(os.environ, {'SOURCE_GATEWAY_FIXTURE': 'offline-only'}):
                router.chat({'messages': [{'role': 'user', 'content': 'synthetic'}]}, http_receipts=receipts)
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]['endpoint_scope'], 'gateway_endpoint')
            self.assertFalse(receipts[0]['downstream_confirmed'])
            self.assertEqual(receipts[0]['configured_model'], 'auto:axx_plan')
        finally:
            router.close(); server.shutdown(); server.server_close(); thread.join(2)

    def test_http_terminal_receipts_confirm_only_configured_endpoint(self):
        class Handler(BaseHTTPRequestHandler):
            status = 200
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                body = (json.dumps({'model': 'SYNTHETIC_RESPONSE_CANARY', 'provider': 'SYNTHETIC_RESPONSE_CANARY',
                    'choices': [{'message': {'role': 'assistant', 'content': 'SYNTHETIC_RESPONSE_CANARY'}}]}).encode()
                    if self.status == 200 else b'SYNTHETIC_DIAGNOSTIC_CANARY')
                self.send_response(self.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.provider['base_url'] = 'http://127.0.0.1:' + str(server.server_port) + '/v1'
        self.adapter.update_config({'providers': [self.provider], 'max_attempts': 1})
        self.authorize_current_provider()
        original_observe = self.adapter._observe_dispatch
        for status, cancel_late in ((200, False), (400, False), (200, True)):
            with self.subTest(status=status, cancel_late=cancel_late):
                Handler.status = status
                if status != 200 or cancel_late:
                    key = 'source-plan-http-late' if cancel_late else 'source-plan-http-error'
                    plan, _ = self.learning._new_plan('Another explicit goal', key, {}, 'project-a')
                    plan.update(conversation_id='source-task', operational_context=self.fixture.plan['operational_context'],
                        planning_settings=self.fixture.plan['planning_settings'])
                    self.learning._save(plan); self.fixture.plan = plan
                if cancel_late:
                    def after_receipt(active, event, accounting=None):
                        original_observe(active, event, accounting)
                        if event['stage'] == 'runtime_delivered': self.fixture.revoke()
                    with patch.object(self.adapter, '_observe_dispatch', side_effect=after_receipt):
                        with self.assertRaises(ValueError): self.fixture.response()
                    self.learning._save(self.fixture.plan)
                    self.assertTrue(self.fixture.plan['context_invalidated'])
                elif status == 200:
                    self.assertTrue(self.fixture.response()['ok'])
                else:
                    with self.assertRaises(ValueError): self.fixture.response()
                raw = self.learning.budget_db.execute(
                    'SELECT source_dispatch_json FROM mission_model_calls WHERE plan_id=?',
                    (self.fixture.plan['operation_id'],)).fetchone()[0]
                metadata = json.loads(raw)
                self.assertEqual(metadata['send_state'], 'upstream_confirmed')
                self.assertEqual(metadata['runtime_evidence'], 'worker_terminal')
                self.assertEqual(len(metadata['endpoint_receipts']), 1)
                receipt = metadata['endpoint_receipts'][0]
                self.assertEqual(receipt['endpoint_scope'], 'configured_endpoint')
                self.assertEqual(receipt['evidence_kind'], 'http_response_headers')
                self.assertEqual(receipt['status'], status)
                self.assertFalse(receipt['downstream_confirmed'])
                self.assertEqual(receipt['configured_model'], 'synthetic-model')
                self.assertEqual(self.learning.budget_db.execute(
                    'SELECT charge,confirmed FROM mission_model_calls WHERE plan_id=?',
                    (self.fixture.plan['operation_id'],)).fetchone(), (1, 1))
                self.assert_no_canaries()

    def test_worker_attempt_without_http_response_never_confirms_endpoint(self):
        # A bound, non-listening socket reserves this test's port. No unrelated
        # local service can accidentally satisfy the attempted connection.
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1', 0))
            self.provider['base_url'] = 'http://127.0.0.1:' + str(reserved.getsockname()[1]) + '/v1'
            self.adapter.update_config({'providers': [self.provider], 'max_attempts': 1})
            self.authorize_current_provider()
            with self.assertRaises(ValueError): self.fixture.response()
        metadata = self.metadata()
        self.assertEqual(metadata['send_state'], 'runtime_delivered')
        self.assertEqual(metadata['runtime_evidence'], 'worker_terminal')
        self.assertEqual(metadata['endpoint_receipts'], [])
        self.assertEqual(self.learning.budget_db.execute('SELECT charge,confirmed FROM mission_model_calls').fetchone(), (1, 1))
        self.assert_no_canaries()

    def test_forget_null_never_recreates_metadata_and_stages_never_regress(self):
        refs = self.fixture.service.provider_context_for_task('source-task', project_id='project-a')['refs']
        self.fixture.plan['observation_dependencies'] = refs
        request_id = 'synthetic-reserved'
        self.learning._reserve_model_call(self.fixture.plan, request_id, 'plan')
        observer = self.learning._source_dispatch_observer(self.fixture.plan, request_id)
        observer({'stage': 'unknown', 'code': 'CHANNEL_START', 'at': time.time()})
        observer({'stage': 'runtime_delivered', 'code': 'INLINE_TEST', 'at': time.time(), 'endpoint_receipts': []})
        observer({'stage': 'unknown', 'code': 'CHANNEL_START', 'at': time.time()})
        self.assertEqual(self.metadata()['send_state'], 'runtime_delivered')
        with self.learning.budget_db:
            self.learning.budget_db.execute('UPDATE mission_model_calls SET source_dispatch_json=NULL')
        with self.assertRaises(ValueError):
            observer({'stage': 'runtime_delivered', 'code': 'INLINE_TEST', 'at': time.time(), 'endpoint_receipts': []})
        self.assertIsNone(self.metadata())
        self.assertEqual(self.learning.budget_db.execute('SELECT charge FROM mission_model_calls').fetchone()[0], 2)

    def test_callback_uses_no_foreign_locks_and_never_extends_metadata_retention(self):
        self.fixture.service.configure({'profiles': {'discreto': {'retention_days': 1}}})
        self.fixture.now += 31
        self.fixture.service.tick()
        self.fixture.plan['observation_dependencies'] = self.fixture.service.provider_context_for_task(
            'source-task', project_id='project-a')['refs']
        self.learning._reserve_model_call(self.fixture.plan, 'synthetic-reserved', 'plan')
        observer = self.learning._source_dispatch_observer(self.fixture.plan, 'synthetic-reserved')
        before = self.metadata()
        self.assertEqual(before['expires_at'] - before['created_at'], 86400)
        class RejectLock:
            def __enter__(self): raise AssertionError('Transport callback acquired a foreign lock')
            def __exit__(self, *args): pass
        with patch.object(self.learning, 'lock', RejectLock()), patch.object(self.fixture.service, 'lock', RejectLock()), \
                patch.object(self.fixture.service, '_config', side_effect=AssertionError('Callback reread policy')):
            observer({'stage': 'unknown', 'code': 'CHANNEL_START', 'at': time.time()})
        self.assertEqual(self.metadata()['expires_at'], before['expires_at'])

    def test_restart_preserves_unknown_receipt_and_budget_without_repeating_dispatch(self):
        self.fixture.plan['observation_dependencies'] = self.fixture.service.provider_context_for_task(
            'source-task', project_id='project-a')['refs']
        self.learning._reserve_model_call(self.fixture.plan, 'synthetic-reserved', 'plan')
        observer = self.learning._source_dispatch_observer(self.fixture.plan, 'synthetic-reserved')
        observer({'stage': 'unknown', 'code': 'CHANNEL_START', 'at': time.time()})
        before = self.learning.budget_db.execute('SELECT * FROM mission_model_calls').fetchall()
        self.learning.close()
        with patch.object(self.adapter, 'route') as route:
            recovered = ActionLearning(self.fixture.commands, self.adapter)
            try:
                self.assertEqual(recovered.budget_db.execute('SELECT * FROM mission_model_calls').fetchall(), before)
                self.assertEqual(json.loads(before[0][-1])['send_state'], 'unknown')
                self.assertEqual(before[0][4:6], (2, 0))
                route.assert_not_called()
            finally:
                recovered.close()

    def test_inflight_config_change_preserves_sent_profile_receipt_and_charge(self):
        original = dict(self.provider)
        replacement = original | {'model': 'changed-model'}
        for revoke_source in (False, True):
            with self.subTest(revoke_source=revoke_source):
                self.adapter.update_config({'providers': [original], 'max_attempts': 2})
                if revoke_source:
                    plan, _ = self.learning._new_plan('Second explicit goal', 'source-plan-config-revoked', {}, 'project-a')
                    plan.update(conversation_id='source-task', operational_context=self.fixture.plan['operational_context'],
                        planning_settings=self.fixture.plan['planning_settings'])
                    self.learning._save(plan); self.fixture.plan = plan
                written, input_sent = [], threading.Event()
                receipt = {'ordinal': 1, 'profile_id': profile_id(original), 'provider_name': original['name'],
                    'configured_model': original['model'], 'endpoint_scope': 'configured_endpoint',
                    'evidence_kind': 'http_response_headers', 'status': 200, 'at': time.time(), 'downstream_confirmed': False}
                terminal = {'ok': True, 'result': {
                    'choices': [{'message': {'role': 'assistant', 'content': 'SYNTHETIC_RESPONSE_CANARY'}}],
                    'axx_router': {'provider_name': original['name'], 'model': original['model'],
                        'upstream_attempted': True, 'upstream_attempts': 1, 'attempt_budget_used': 1}},
                    'dispatch_receipt': {'version': 1, 'endpoint_receipts': [receipt]}}
                class Input:
                    def write(inner, data):
                        written.append(json.loads(data.split(b'\n')[1])); input_sent.set()
                    def flush(inner): pass
                    def close(inner): pass
                outer = self
                class Process:
                    stdin = Input()
                    stdout = io.BytesIO(json.dumps(terminal).encode() + b'\n')
                    stderr = io.BytesIO()
                    returncode = 0
                    changed = False
                    def poll(inner):
                        if not input_sent.wait(1): raise AssertionError('Worker input was not delivered')
                        if not inner.changed:
                            inner.changed = True
                            outer.adapter.update_config({'providers': [replacement], 'max_attempts': 2})
                            if revoke_source: outer.fixture.revoke()
                        return 0
                with patch('backend.inference.adapter.spawn_managed_process', return_value=(Process(), None)):
                    with self.assertRaises(ValueError): self.fixture.response()
                    self.learning._save(self.fixture.plan)
                    self.assertTrue(self.fixture.plan['context_invalidated'])
                self.assertEqual(written[0]['config']['providers'][0]['model'], original['model'])
                self.assertEqual(self.adapter.config['providers'][0]['model'], replacement['model'])
                row = self.learning.budget_db.execute('''SELECT source_dispatch_json,state,charge,confirmed
                    FROM mission_model_calls WHERE plan_id=?''', (self.fixture.plan['operation_id'],)).fetchone()
                metadata = json.loads(row[0])
                self.assertEqual(metadata['send_state'], 'upstream_confirmed')
                self.assertEqual(metadata['endpoint_receipts'], [receipt])
                self.assertEqual(row[1:], ('confirmed', 1, 1))
                self.assert_no_canaries()


if __name__ == '__main__': unittest.main()
