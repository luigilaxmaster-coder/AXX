"""Offline recipient admission; only synthetic loopback HTTP and owned children."""
import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.inference.adapter import InferenceAdapter, SourceDestinationPolicy, SOURCE_CHANNEL, worker_main
from backend.inference.router import Router, UpstreamError, profile_id


class SourceDestinationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {'UNUSED_SOURCE_POLICY_TEST': 'synthetic-offline-only'})
        environment.start(); self.addCleanup(environment.stop)
        self.providers = [dict(name=name, model='model-' + name, base_url='https://' + name + '.example/v1',
            enabled=True, free_confirmed=True, billing_allowed=False, cost_evidence='free_tier',
            route_kind='direct', capabilities=['text'], context_window=32768, allow_sensitive=True,
            api_key_env='UNUSED_SOURCE_POLICY_TEST', auth_optional=True, daily_attempt_limit=100) for name in ('a', 'b', 'c')]
        self.config = {'providers': self.providers, 'max_attempts': 2}
        self.calls = []
        self.current = {profile_id(p) for p in self.providers[:2]}
        self.cancel = threading.Event()
        self.spawned = []

    def adapter(self, transport=None):
        state = Path(self.temp.name) / 'router.db'
        router = Router(self.config, state=state, transport=transport) if transport else None
        adapter = InferenceAdapter(self.config, state, router_instance=router)
        self.addCleanup(adapter.close)
        return adapter

    def policy(self, ids=None, revalidate=None):
        return SourceDestinationPolicy(ids or self.current, revalidate or (lambda **permission: self.current))

    def request(self, adapter, policy, **kwargs):
        envelope = dict(messages=[{'role': 'user', 'content': 'SYNTHETIC_SOURCE_ONLY'}],
            selection_mode='automatic_free', sensitivity='approved_sensitive', upstream_attempt_budget=2)
        envelope.update(kwargs.pop('envelope', {}))
        result = adapter.route(envelope, cancel_event=self.cancel, source_policy=policy, **kwargs)
        self.assertFalse(adapter.active_requests)
        self.assertFalse(adapter.conversation_locks)
        self.assertNotIn('SYNTHETIC_SOURCE_ONLY', json.dumps(result))
        return result

    def transport(self, provider, payload, timeout):
        self.calls.append(provider['name'])
        if provider['name'] == 'a':
            raise UpstreamError(503)
        return {'choices': [{'message': {'role': 'assistant', 'content': 'synthetic-ok'}}]}

    def test_unapproved_fallback_is_never_reserved_or_called(self):
        adapter = self.adapter(self.transport)
        result = self.request(adapter, self.policy({profile_id(self.providers[0])}))
        self.assertFalse(result['ok'])
        self.assertEqual(self.calls, ['a'])
        self.assertEqual(result['error']['attempt_budget_used'], 1)
        self.assertFalse(adapter.router.db.execute("SELECT 1 FROM usage WHERE name IN ('b','c')").fetchone())

    def test_two_approved_fallbacks_share_the_existing_budget(self):
        result = self.request(self.adapter(self.transport), self.policy())
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.calls, ['a', 'b'])
        self.assertEqual(result['attempt_budget_used'], 2)

    def test_revoke_between_attempts_preserves_first_attempt_and_stops_second(self):
        def transport(provider, payload, timeout):
            self.current = {profile_id(self.providers[0])}
            return self.transport(provider, payload, timeout)
        adapter = self.adapter(transport)
        result = self.request(adapter, self.policy())
        self.assertEqual(result['error']['code'], 'SOURCE_DESTINATION_UNAUTHORIZED')
        self.assertEqual(self.calls, ['a'])
        self.assertEqual(result['error']['attempt_budget_used'], 1)
        self.assertIs(result['error']['upstream_attempted'], True)
        self.assertFalse(adapter.router.db.execute("SELECT 1 FROM usage WHERE name='b'").fetchone())

    def test_new_permissions_do_not_expand_an_admitted_policy(self):
        admitted = {profile_id(self.providers[0])}
        def transport(provider, payload, timeout):
            self.current = {profile_id(p) for p in self.providers}
            return self.transport(provider, payload, timeout)
        result = self.request(self.adapter(transport), self.policy(admitted))
        self.assertFalse(result['ok'])
        self.assertEqual(self.calls, ['a'])

    def test_json_cannot_replace_internal_policy(self):
        adapter = self.adapter(self.transport)
        forged = {'allowed_profile_ids': [profile_id(self.providers[1])]}
        self.assertEqual(self.request(adapter, forged)['error']['code'], 'INVALID_REQUEST')
        self.assertEqual(self.calls, [])
        result = self.request(adapter, self.policy({profile_id(self.providers[0])}), envelope={'source_policy': forged})
        self.assertFalse(result['ok'])
        self.assertEqual(self.calls, ['a'])

    def test_blocked_revalidation_rechecks_cancel_before_admission(self):
        entered, release = threading.Event(), threading.Event()
        adapter = self.adapter(self.transport)
        checks = []
        def validate(**permission):
            checks.append(True)
            if len(checks) == 2:
                entered.set()
                if not release.wait(3): raise AssertionError('Fixture did not release admission')
            return self.current
        results = []
        thread = threading.Thread(target=lambda: results.append(self.request(adapter, self.policy(revalidate=validate))))
        thread.start()
        self.assertTrue(entered.wait(3)); self.cancel.set(); release.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]['error']['code'], 'CANCELLED')
        self.assertEqual(self.calls, [])
        self.assertFalse(adapter.router.db.execute('SELECT 1 FROM usage').fetchone())

    def test_deadline_expiring_during_inline_guard_prevents_reservation(self):
        clock, checks = [0.0], []
        def validate(**permission):
            checks.append(True)
            if len(checks) == 2: clock[0] = 71.0
            return self.current
        adapter = self.adapter(self.transport)
        with patch('backend.inference.adapter.time.monotonic', side_effect=lambda: clock[0]):
            result = self.request(adapter, self.policy(revalidate=validate))
        self.assertEqual(result['error']['code'], 'DEADLINE_EXCEEDED')
        self.assertEqual(self.calls, [])
        self.assertFalse(adapter.router.db.execute('SELECT 1 FROM usage').fetchone())

    def fake_worker(self, statements):
        script = ("import sys,json,time\n"
                  "sys.stdin.buffer.readline();sys.stdin.buffer.readline()\n" + statements)
        def spawn(*args, **kwargs):
            process = subprocess.Popen([sys.executable, '-u', '-c', script], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.spawned.append(process)
            return process, None
        return patch('backend.inference.adapter.spawn_managed_process', side_effect=spawn)

    def test_admission_frame_spoof_replay_extra_and_eof_fail_closed(self):
        identity = profile_id(self.providers[0])
        valid = dict(source_attempt=1, ordinal=1, profile_id=identity, nonce='1' * 32)
        for kind in ('ordinal', 'nonce', 'extra', 'duplicate', 'replay', 'eof'):
            with self.subTest(kind=kind):
                frame = dict(valid)
                if kind == 'ordinal': frame['ordinal'] = 2
                if kind == 'nonce': frame['nonce'] = 'not-a-nonce'
                if kind == 'extra': frame['private'] = 'SYNTHETIC_DIAGNOSTIC_CANARY'
                emit = "sys.stdout.write(" + repr(json.dumps(frame) + '\n') + ");sys.stdout.flush()\n"
                if kind == 'duplicate':
                    raw = json.dumps(frame).replace('"ordinal": 1', '"ordinal": 2, "ordinal": 1') + '\n'
                    emit = 'sys.stdout.write(' + repr(raw) + ');sys.stdout.flush()\n'
                script = '' if kind == 'eof' else emit
                if kind == 'replay': script += 'sys.stdin.buffer.readline()\n' + emit
                script += 'time.sleep(2)\n' if kind != 'eof' else ''
                adapter = self.adapter()
                with self.fake_worker(script):
                    result = self.request(adapter, self.policy())
                self.assertFalse(result['ok'])
                self.assertNotIn('SYNTHETIC_DIAGNOSTIC_CANARY', json.dumps(result))
                self.assertFalse(adapter.router.db.execute('SELECT 1 FROM usage').fetchone())

    def test_small_split_frame_is_not_buffered_behind_worker_wait(self):
        frame = dict(source_attempt=1, ordinal=1, profile_id=profile_id(self.providers[0]), nonce='2' * 32)
        encoded = json.dumps(frame) + '\n'
        terminal = {'ok': True, 'result': {'choices': [{'message': {'role': 'assistant', 'content': 'synthetic-ok'}}],
            'axx_router': {'upstream_attempted': False, 'upstream_attempts': 0, 'attempt_budget_used': 0}}}
        script = ("sys.stdout.write(" + repr(encoded[:8]) + ");sys.stdout.flush()\n"
                  "sys.stdout.write(" + repr(encoded[8:]) + ");sys.stdout.flush()\n"
                  "reply=json.loads(sys.stdin.buffer.readline())\n"
                  "assert reply['permitted'] is True\n"
                  "sys.stdout.write(" + repr(json.dumps(terminal) + '\n') + ");sys.stdout.flush()\n")
        with self.fake_worker(script):
            result = self.request(self.adapter(), self.policy())
        self.assertTrue(result['ok'], result)

    def test_early_admission_frame_cannot_block_a_full_initial_input_pipe(self):
        identity = profile_id(self.providers[0])
        frame = dict(source_attempt=1, ordinal=1, profile_id=identity, nonce='6' * 32)
        script = ('import sys,json,time\n'
                  'sys.stdin.buffer.readline()\n'
                  'sys.stdout.write(' + repr(json.dumps(frame) + '\n') + ');sys.stdout.flush()\n'
                  'time.sleep(10)\n')
        for mode in ('deadline', 'cancel'):
            with self.subTest(mode=mode):
                initial_started, frame_read, ack_started = threading.Event(), threading.Event(), threading.Event()
                processes, results, errors = [], [], []
                def spawn(*args, **kwargs):
                    process = subprocess.Popen([sys.executable, '-u', '-c', script], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    processes.append(process)
                    stdin, stdout = process.stdin, process.stdout
                    class Input:
                        def write(self, data):
                            (initial_started if data.startswith(SOURCE_CHANNEL) else ack_started).set()
                            return stdin.write(data)
                        def flush(self): return stdin.flush()
                        def close(self): return stdin.close()
                    class Output:
                        def readline(self, limit):
                            result = stdout.readline(limit)
                            if result: frame_read.set()
                            return result
                        def close(self): return stdout.close()
                    process.stdin, process.stdout = Input(), Output()
                    return process, None
                adapter = self.adapter()
                request_id = 'source-early-frame-' + mode
                def route():
                    try:
                        results.append(self.request(adapter, self.policy(), envelope={'request_id': request_id,
                            'deadline_ms': 10000, 'messages': [{'role': 'user', 'content': 'x' * (512 * 1024)}]}))
                    except BaseException as exc:
                        errors.append(exc)
                thread = threading.Thread(target=route, daemon=True)
                with patch('backend.inference.adapter.spawn_managed_process', side_effect=spawn):
                    thread.start()
                    try:
                        self.assertTrue(initial_started.wait(2))
                        self.assertTrue(frame_read.wait(2))
                        # The old implementation enters its ACK write while
                        # BufferedWriter's lock belongs to the blocked writer.
                        ack_started.wait(.25)
                        if mode == 'cancel':
                            self.cancel.set()
                        else:
                            adapter.active_requests[request_id].deadline_mono = time.monotonic() + .1
                        thread.join(1)
                        finished_before_cleanup = not thread.is_alive()
                        children_ended_before_cleanup = all(process.poll() is not None for process in processes)
                    finally:
                        # Bound RED too: terminate only the synthetic child
                        # this fixture created, releasing both blocked writes.
                        for process in processes:
                            if process.poll() is None:
                                process.kill()
                            process.wait(timeout=2)
                        thread.join(2)
                self.assertFalse(thread.is_alive(), 'Fixture cleanup could not release its child pipes')
                self.assertEqual(errors, [])
                self.assertTrue(finished_before_cleanup, 'ACK write bypassed cancellation/deadline polling')
                self.assertTrue(children_ended_before_cleanup)
                self.assertFalse(ack_started.is_set(), 'Admission was processed before initial input completed')
                self.assertEqual(results[0]['error']['code'], 'CANCELLED' if mode == 'cancel' else 'DEADLINE_EXCEEDED')

    def test_ack_stall_after_initial_flush_preserves_deadline_and_cancel(self):
        """Deterministic full-pipe stand-in; this does not measure OS pipe capacity."""
        frame = dict(source_attempt=1, ordinal=1, profile_id=profile_id(self.providers[0]), nonce='7' * 32)
        script = ('import sys,json,time\n'
                  'sys.stdin.buffer.readline();sys.stdin.buffer.readline()\n'
                  'sys.stdout.write(' + repr(json.dumps(frame) + '\n') + ');sys.stdout.flush()\n'
                  'time.sleep(10)\n')
        for mode in ('deadline', 'cancel'):
            with self.subTest(mode=mode):
                ack_started, closed = threading.Event(), threading.Event()
                processes, initial_owners, ack_owners, close_owners, results, errors = [], [], [], [], [], []
                def spawn(*args, **kwargs):
                    process = subprocess.Popen([sys.executable, '-u', '-c', script], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    processes.append(process)
                    stdin = process.stdin
                    class Input:
                        def write(self, data):
                            if data.startswith(SOURCE_CHANNEL):
                                initial_owners.append(threading.get_ident())
                            else:
                                ack_owners.append(threading.get_ident()); ack_started.set()
                                # Model a BufferedWriter/OS-pipe ACK stall that
                                # releases only when this owned child terminates.
                                process.wait(timeout=10)
                            return stdin.write(data)
                        def flush(self): return stdin.flush()
                        def close(self):
                            try: return stdin.close()
                            finally:
                                close_owners.append(threading.get_ident()); closed.set()
                    process.stdin = Input()
                    return process, None
                adapter = self.adapter()
                request_id = 'source-ack-stall-' + mode
                def route():
                    try:
                        results.append(self.request(adapter, self.policy(), envelope={'request_id': request_id, 'deadline_ms': 10000}))
                    except BaseException as exc:
                        errors.append(exc)
                thread = threading.Thread(target=route, daemon=True)
                with patch('backend.inference.adapter.spawn_managed_process', side_effect=spawn):
                    thread.start()
                    try:
                        self.assertTrue(ack_started.wait(2), 'Fixture never reached the post-flush ACK')
                        if mode == 'cancel':
                            self.cancel.set()
                        else:
                            adapter.active_requests[request_id].deadline_mono = time.monotonic() + .1
                        thread.join(1)
                        finished_before_cleanup = not thread.is_alive()
                        children_ended_before_cleanup = all(p.poll() is not None for p in processes)
                        writer_closed_before_cleanup = closed.is_set()
                    finally:
                        # RED must also be bounded and touch only its child.
                        for process in processes:
                            if process.poll() is None: process.kill()
                            process.wait(timeout=2)
                        thread.join(2)
                self.assertFalse(thread.is_alive(), 'Fixture cleanup left a blocked route')
                self.assertEqual(errors, [])
                self.assertTrue(finished_before_cleanup, 'Synchronous ACK prevented deadline/cancel checks')
                self.assertTrue(children_ended_before_cleanup)
                self.assertTrue(writer_closed_before_cleanup, 'The sole writer retained its pipe after child exit')
                self.assertEqual(initial_owners, ack_owners)
                self.assertTrue(all(owner == initial_owners[0] for owner in close_owners))
                self.assertEqual(results[0]['error']['code'], 'CANCELLED' if mode == 'cancel' else 'DEADLINE_EXCEEDED')

    def test_host_guard_blocked_until_cancel_never_grants_a_late_permit(self):
        identity = profile_id(self.providers[0])
        frame = dict(source_attempt=1, ordinal=1, profile_id=identity, nonce='3' * 32)
        marker = Path(self.temp.name) / 'must-not-be-admitted.txt'
        script = ('sys.stdout.write(' + repr(json.dumps(frame) + '\n') + ');sys.stdout.flush()\n'
                  'reply=json.loads(sys.stdin.buffer.readline())\n'
                  'if reply["permitted"]:open(' + repr(str(marker)) + ',"x").write("admitted")\n'
                  'time.sleep(.1)\n')
        entered, release, results, checks = threading.Event(), threading.Event(), [], []
        def validate(**permission):
            checks.append(True)
            if len(checks) == 3:
                entered.set()
                if not release.wait(3): raise AssertionError('Fixture did not release host admission')
            return self.current
        adapter = self.adapter()
        with self.fake_worker(script):
            thread = threading.Thread(target=lambda: results.append(self.request(adapter, self.policy(revalidate=validate))))
            thread.start()
            try:
                self.assertTrue(entered.wait(3)); self.cancel.set()
            finally:
                release.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]['error']['code'], 'CANCELLED')
        self.assertFalse(marker.exists())

    def test_real_policy_lock_wait_ends_before_lock_release_on_cancel_or_deadline(self):
        from backend.tests import test_planning_context as fixtures
        fixture = fixtures.SourcePublicationTests()
        fixture.setUp()
        try:
            provider = dict(fixture.model.config['providers'][0], capabilities=['text'], context_window=32768,
                api_key_env='UNUSED_SOURCE_POLICY_TEST', auth_optional=True, daily_attempt_limit=100,
                free_confirmed=True, billing_allowed=False, cost_evidence='direct_local')
            self.config = {'providers': [provider]}
            self.current = {profile_id(provider)}
            refs = fixture.service.provider_context_for_task('source-task', project_id='project-a')['refs']
            for mode in ('cancel', 'deadline'):
                with self.subTest(mode=mode):
                    requested, held, release, results, checks = threading.Event(), threading.Event(), threading.Event(), [], []
                    def hold_policy():
                        if requested.wait(3):
                            with fixture.service.lock:
                                held.set(); release.wait()
                    holder = threading.Thread(target=hold_policy)
                    holder.start()
                    def validate(**permission):
                        checks.append(True)
                        if len(checks) == 3:
                            requested.set()
                            if not held.wait(2): raise AssertionError('Policy holder did not start')
                        return fixture.service.allowed_provider_profile_ids('source-task', refs,
                            project_id='project-a', **permission)
                    frame = dict(source_attempt=1, ordinal=1, profile_id=profile_id(provider), nonce='4' * 32)
                    script = ('sys.stdout.write(' + repr(json.dumps(frame) + '\n') + ');sys.stdout.flush()\n'
                              'sys.stdin.buffer.readline()\n' 'time.sleep(2)\n')
                    adapter = self.adapter()
                    with self.fake_worker(script):
                        thread = threading.Thread(target=lambda: results.append(self.request(adapter, self.policy(revalidate=validate),
                            envelope={'request_id': 'source-lock-wait', 'deadline_ms': 700 if mode == 'deadline' else 3000})))
                        thread.start()
                        try:
                            self.assertTrue(held.wait(2))
                            if mode == 'cancel':
                                cancelled = []
                                canceller = threading.Thread(target=lambda: cancelled.append(adapter.cancel('source-lock-wait')))
                                canceller.start(); canceller.join(.5)
                                self.assertFalse(canceller.is_alive(), 'cancel was blocked by the adapter lock')
                                self.assertEqual(cancelled, [True])
                            thread.join(1.5)
                            self.assertFalse(thread.is_alive(), 'route waited for policy lock release')
                            self.assertFalse(release.is_set())
                            self.assertTrue(all(p.poll() is not None for p in self.spawned))
                            self.assertEqual(results[0]['error']['code'], 'CANCELLED' if mode == 'cancel' else 'DEADLINE_EXCEEDED')
                            self.assertFalse(adapter.router.db.execute('SELECT 1 FROM usage').fetchone())
                        finally:
                            release.set(); holder.join(2); thread.join(2)
        finally:
            fixture.tearDown()

    def test_worker_rejects_bool_int_substitutions_in_policy_and_permit(self):
        identity = profile_id(self.providers[0])
        nonce = '5' * 32
        frame = dict(source_attempt=1, ordinal=1, profile_id=identity, nonce=nonce, permitted=True)
        for field in ('version', 'permitted', 'source_attempt', 'ordinal'):
            with self.subTest(field=field):
                policy = {'version': 1, 'allowed_profile_ids': [identity]}
                reply = dict(frame)
                if field == 'version': policy['version'] = True
                elif field == 'permitted': reply[field] = 1
                else: reply[field] = True
                data = {'config': {'providers': self.providers}, 'request': {}, 'source_policy': policy}
                stdin = io.BytesIO(SOURCE_CHANNEL + json.dumps(data).encode() + b'\n' + json.dumps(reply).encode() + b'\n')
                stdout, effects = io.BytesIO(), []
                class FakeRouter:
                    def __init__(self, *args, **kwargs): pass
                    def close(self): pass
                    def chat(self, request, **kwargs):
                        kwargs['source_attempt_guard'](identity)
                        effects.append(True)
                        return {}
                with patch('backend.inference.adapter.sys.stdin', SimpleNamespace(buffer=stdin)), \
                        patch('backend.inference.adapter.sys.stdout', SimpleNamespace(buffer=stdout)), \
                        patch('backend.inference.adapter.Router', FakeRouter), \
                        patch('backend.inference.adapter.uuid.uuid4', return_value=SimpleNamespace(hex=nonce)):
                    self.assertEqual(worker_main(str(Path(self.temp.name) / 'unused.db')), 1)
                self.assertEqual(effects, [])

    def test_worker_rejects_nonhashable_destination_ids_before_chat_with_zero_dispatch(self):
        for invalid in ({'synthetic': 'not-an-id'}, ['not-an-id']):
            with self.subTest(invalid=invalid):
                data = {'config': {'providers': self.providers}, 'request': {},
                    'source_policy': {'version': 1, 'allowed_profile_ids': [invalid]}}
                stdin = io.BytesIO(SOURCE_CHANNEL + json.dumps(data).encode() + b'\n')
                stdout, chats = io.BytesIO(), []
                class FakeRouter:
                    def __init__(self, *args, **kwargs): pass
                    def close(self): pass
                    def chat(self, *args, **kwargs):
                        chats.append(True)
                        raise AssertionError('Invalid policy reached Router.chat')
                with patch('backend.inference.adapter.sys.stdin', SimpleNamespace(buffer=stdin)), \
                        patch('backend.inference.adapter.sys.stdout', SimpleNamespace(buffer=stdout)), \
                        patch('backend.inference.adapter.Router', FakeRouter):
                    code = worker_main(str(Path(self.temp.name) / 'unused.db'))
                self.assertEqual(code, 1)
                self.assertEqual(chats, [])
                result = json.loads(stdout.getvalue())
                self.assertEqual(result['error']['code'], 'INVALID_REQUEST')
                self.assertIs(result['error']['upstream_attempted'], False)
                self.assertEqual(result['error']['upstream_attempts'], 0)
                self.assertEqual(result['error']['attempt_budget_used'], 0)
                self.assertEqual(result['dispatch_receipt']['endpoint_receipts'], [])

    def test_live_host_revocation_between_http_attempts_denies_second_endpoint(self):
        calls = []
        outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                name = self.path.split('/')[1]
                self.rfile.read(int(self.headers['Content-Length'])); calls.append(name)
                outer.current = {profile_id(outer.providers[0])}
                self.send_response(503); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'{}')
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 2); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        for provider in self.providers:
            provider['base_url'] = 'http://127.0.0.1:' + str(server.server_port) + '/' + provider['name'] + '/v1'
        self.current = {profile_id(row) for row in self.providers[:2]}
        result = self.request(self.adapter(), self.policy())
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'SOURCE_DESTINATION_UNAUTHORIZED')
        self.assertEqual(result['error']['attempt_budget_used'], 1)
        self.assertIs(result['error']['upstream_attempted'], True)
        self.assertEqual(calls, ['a'])

    def test_real_loopback_worker_admits_two_destinations_without_payload_authority(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                name = self.path.split('/')[1]
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((name, body))
                content = b'{}' if name == 'a' else b'{"choices":[{"message":{"role":"assistant","content":"synthetic-ok"}}]}'
                self.send_response(503 if name == 'a' else 200)
                self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 2); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        for provider in self.providers:
            provider['base_url'] = 'http://127.0.0.1:' + str(server.server_port) + '/' + provider['name'] + '/v1'
        self.current = {profile_id(row) for row in self.providers[:2]}
        result = self.request(self.adapter(), self.policy())
        self.assertTrue(result['ok'], result)
        self.assertEqual([name for name, _ in calls], ['a', 'b'])
        self.assertEqual(result['attempt_budget_used'], 2)
        for _, body in calls:
            self.assertNotIn('source_policy', body)
            self.assertNotIn('allowed_profile_ids', body)


if __name__ == '__main__': unittest.main()
