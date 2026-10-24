"""Internal cancellation is checked before registration/dispatch and after responses."""
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.inference.adapter import InferenceAdapter


class AdapterCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.adapter = InferenceAdapter({'allow_paid': False, 'providers': []}, Path(self.temp.name) / 'state.db')
        self.addCleanup(self.adapter.close)
        self.event = threading.Event()
        self.request = {'request_id': 'cancel-test', 'messages': [{'role': 'user', 'content': 'test'}]}

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

    def test_invalid_internal_event_does_not_reach_router(self):
        result = self.adapter.route(self.request, cancel_event={'cancelled': True})
        self.assertEqual(result['error']['code'], 'INVALID_REQUEST')
        self.assertFalse(self.adapter.active_requests)


if __name__ == '__main__': unittest.main()
