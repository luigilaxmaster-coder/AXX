"""Internal cancellation is checked before registration/dispatch and after responses."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.inference.adapter import ActiveRequest, InferenceAdapter, worker_main


class AdapterCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.adapter = InferenceAdapter({'allow_paid': False, 'providers': []}, Path(self.temp.name) / 'state.db')
        self.addCleanup(self.adapter.close)
        self.event = threading.Event()
        self.request = {'request_id': 'cancel-test', 'messages': [{'role': 'user', 'content': 'test'}]}

    def test_serialized_worker_budget_stays_within_protocol_after_clock_rounding(self):
        clock = 442.007
        self.assertGreater((clock + 70) - clock, 70)
        encode = json.dumps
        for budget in (1., 70.):
            with self.subTest(budget=budget):
                active = ActiveRequest('rounding-fixture', clock + budget, self.event)
                with patch('backend.inference.adapter.time.monotonic', return_value=clock), \
                     patch('backend.inference.adapter.json.dumps', wraps=encode) as encoded, \
                     patch('backend.inference.adapter.spawn_managed_process', side_effect=OSError('fixture-before-spawn')) as spawn:
                    with self.assertRaisesRegex(OSError, 'fixture-before-spawn'):
                        self.adapter._worker_result(active, self.request)
                remaining = encoded.call_args.args[0]['remaining_seconds']
                self.assertGreater(remaining, 0)
                self.assertLessEqual(remaining, budget)
                self.assertEqual(remaining, budget)
                self.assertEqual(active.deadline_mono, clock + budget)
                spawn.assert_called_once()

    def test_worker_still_rejects_budget_above_protocol_limit_before_routing(self):
        payload = json.dumps({'config': {'allow_paid': False, 'providers': []}, 'request': self.request,
                              'remaining_seconds': (442.007 + 70) - 442.007}).encode()
        with io.TextIOWrapper(io.BytesIO(payload)) as stdin, io.TextIOWrapper(io.BytesIO()) as stdout, \
             patch('backend.inference.adapter.sys.stdin', stdin), \
             patch('backend.inference.adapter.sys.stdout', stdout), \
             patch('backend.inference.adapter.Router') as router:
            code = worker_main(str(Path(self.temp.name) / 'worker.db'))
            response = json.loads(stdout.buffer.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(response['ok'])
        self.assertEqual(response['error']['code'], 'INVALID_REQUEST')
        self.assertIs(response['error']['upstream_attempted'], False)
        router.assert_not_called()

    def test_pre_cancelled_request_never_registers_or_starts_worker(self):
        self.event.set()
        with patch.object(self.adapter, '_worker_result') as worker:
            result = self.adapter.route(self.request, cancel_event=self.event)
        self.assertEqual(result['error']['code'], 'CANCELLED')
        self.assertIs(result['error']['upstream_attempted'], False)
        self.assertFalse(self.adapter.active_requests)
        worker.assert_not_called()

    def test_cancellation_while_waiting_for_registration_prevents_dispatch(self):
        results = []
        with patch.object(self.adapter, '_worker_result') as worker:
            with self.adapter.lock:
                thread = threading.Thread(target=lambda: results.append(self.adapter.route(self.request, cancel_event=self.event)))
                thread.start()
                self.event.set()
            thread.join(3)
        self.assertEqual(results[0]['error']['code'], 'CANCELLED')
        self.assertIs(results[0]['error']['upstream_attempted'], False)
        worker.assert_not_called()

    def test_cancel_after_validation_before_worker_never_dispatches(self):
        validate = self.adapter.router.validate_request
        def then_cancel(request):
            validate(request)
            self.event.set()
        with patch.object(self.adapter.router, 'validate_request', side_effect=then_cancel), patch.object(self.adapter, '_worker_result') as worker:
            result = self.adapter.route(self.request, cancel_event=self.event)
        self.assertEqual(result['error']['code'], 'CANCELLED')
        self.assertIs(result['error']['upstream_attempted'], False)
        worker.assert_not_called()
        self.assertFalse(self.adapter.active_requests)

    def test_cancel_during_process_creation_never_sends_child_input(self):
        class Input:
            writes = []
            def write(self, data): self.writes.append(data)
            def close(self): pass
        class Process:
            stdin = Input()
            stdout = io.BytesIO()
            stderr = io.BytesIO()
            returncode = 1
            def poll(self): return 1
        process = Process()
        def spawn(*args, **kwargs):
            self.event.set()
            return process, None
        with patch('backend.inference.adapter.spawn_managed_process', side_effect=spawn):
            result = self.adapter.route(self.request, cancel_event=self.event)
        self.assertEqual(result['error']['code'], 'CANCELLED')
        self.assertEqual(process.stdin.writes, [])

    def test_event_after_child_input_kills_inflight_worker(self):
        event = self.event
        class Input:
            def write(self, data): event.set()
            def close(self): pass
        class Process:
            stdin = Input()
            stdout = io.BytesIO()
            stderr = io.BytesIO()
            returncode = None
            stopped = False
            def poll(self): return 1 if self.stopped else None
        process = Process()
        with patch('backend.inference.adapter.spawn_managed_process', return_value=(process, None)), \
                patch('backend.inference.adapter.terminate_process_tree', side_effect=lambda p, job: setattr(p, 'stopped', True)) as terminate:
            result = self.adapter.route(self.request, cancel_event=self.event)
        self.assertEqual(result['error']['code'], 'CANCELLED')
        terminate.assert_called_once_with(process, None)
        self.assertFalse(self.adapter.active_requests)

    def test_late_router_response_cannot_override_event(self):
        self.adapter.router.transport = lambda *args: None  # Select injected router path; no network.
        def finish(*args, **kwargs):
            self.event.set()
            return {'choices': [{'message': {'role': 'assistant', 'content': 'late answer'}}]}
        with patch.object(self.adapter.router, 'chat', side_effect=finish):
            result = self.adapter.route(self.request, cancel_event=self.event)
        self.assertEqual(result['error']['code'], 'CANCELLED')
        self.assertNotIn('message', result)

    def assert_late_failed_worker_cancelled(self, accounting):
        """Exercise real pipe collection, with cancellation after child exit."""
        event, input_sent = threading.Event(), threading.Event()
        canary = 'SYNTHETIC_CANCELLED_ERROR_CANARY'
        error = {'code': 'UPSTREAM_TEMPORARY', 'message': canary,
                 'retryable': True, **accounting}
        written = []

        class Input:
            def write(self, data):
                written.append(json.loads(data))
                input_sent.set()
            def close(self): pass

        class Process:
            def __init__(self, response, cancel_on_exit=False):
                self.stdin = Input()
                self.stdout = io.BytesIO(json.dumps(response).encode('utf-8'))
                self.stderr = io.BytesIO()
                self.returncode = 1 if not response['ok'] else 0
                self.cancel_on_exit = cancel_on_exit
            def poll(self):
                if not input_sent.wait(1):
                    raise AssertionError('The fixture worker never received input')
                if self.cancel_on_exit:
                    event.set()
                return self.returncode

        failed = Process({'ok': False, 'error': error}, cancel_on_exit=True)
        succeeded = Process({'ok': True, 'result': {
            'choices': [{'message': {'role': 'assistant', 'content': 'capacity reused'}}]}})
        with patch('backend.inference.adapter.spawn_managed_process',
                   side_effect=[(failed, None), (succeeded, None)]) as spawn:
            result = self.adapter.route(dict(self.request, sensitivity='approved_sensitive'), cancel_event=event)
            self.assertTrue(event.is_set())
            self.assertEqual(result['error']['code'], 'CANCELLED')
            self.assertEqual(result['error']['message'], 'Request cancelled; late response discarded')
            self.assertFalse(result['error']['retryable'])
            self.assertNotIn(canary, json.dumps(result))
            for key in ('upstream_attempted', 'upstream_attempts', 'attempt_budget_used'):
                if key in accounting:
                    if isinstance(accounting[key], bool):
                        self.assertIs(result['error'][key], accounting[key])
                    else:
                        self.assertEqual(result['error'][key], accounting[key])
                else:
                    self.assertNotIn(key, result['error'])
            self.assertFalse(self.adapter.active_requests)
            self.assertFalse(self.adapter.conversation_locks)
            # The same identity and conversation can immediately use the released slot.
            reused = self.adapter.route(self.request)
            self.assertTrue(reused['ok'], reused)
            self.assertEqual(reused['message']['content'], 'capacity reused')
            self.assertEqual(spawn.call_count, 2)
        self.assertEqual(len(written), 2)
        self.assertIs(written[0]['request']['axx_sensitive'], True)
        self.assertFalse(self.adapter.active_requests)
        self.assertFalse(self.adapter.conversation_locks)

    def test_late_failed_worker_cancel_preserves_consumed_attempts(self):
        self.assert_late_failed_worker_cancelled({
            'upstream_attempted': True, 'upstream_attempts': 1, 'attempt_budget_used': 1})

    def test_late_failed_worker_cancel_does_not_invent_unknown_attempts(self):
        self.assert_late_failed_worker_cancelled({})

    def test_invalid_internal_event_does_not_reach_router(self):
        result = self.adapter.route(self.request, cancel_event={'cancelled': True})
        self.assertEqual(result['error']['code'], 'INVALID_REQUEST')
        self.assertFalse(self.adapter.active_requests)


if __name__ == '__main__': unittest.main()
