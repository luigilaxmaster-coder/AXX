"""Observation-only computer sessions use synthetic frames and never Windows input."""
import copy
import io
import json
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from backend import computer_use as cu
from backend.tests import test_computer_use as fixture


class ObservationOnlyTests(unittest.TestCase):
    setUp = fixture.ComputerUseTests.setUp
    tearDown = fixture.ComputerUseTests.tearDown
    admit = fixture.ComputerUseTests.admit

    def readonly(self, *, scope='window'):
        args = (10, 20) if scope == 'window' else ()
        result = self.service.begin('chat-one', *args, scope=scope, image_authorized=True)
        self.grant = self.service.grants['chat-one']
        self.executor.input_control = None
        return result

    def frame(self):
        observed = copy.deepcopy(self.observed)
        observed['observation'].update(session_id=cu.uia.OBSERVATION_SESSION_ID, completed_monotonic=time.monotonic())
        buffer = io.BytesIO()
        Image.new('RGB', (300, 200), 'white').save(buffer, format='JPEG')
        captured = {'window_bounds': dict(observed['observation']['window_bounds']),
                    'jpeg': cu.base64.b64encode(buffer.getvalue()).decode()}
        geometry = {key: observed['observation'][key] for key in ('window_bounds', 'monitors')}
        return observed, captured, geometry

    def read(self, observed):
        def result(*args, **kwargs):
            cu.uia._remember_observation(observed)
            return copy.deepcopy(observed)
        return result

    def test_default_false_grant_is_explicit_observation_without_background_capture(self):
        with patch.object(cu.vision, 'observe') as observe, patch.object(cu.uia, 'focus_window') as focus:
            result = self.readonly()
            self.assertTrue(result['active'])
            self.assertIs(result['allow_input'], False)
            self.assertIs(self.service.status('chat-one')['allow_input'], False)
            self.assertIsNone(self.grant['shot'])
            observe.assert_not_called(); focus.assert_not_called()
        for value in (1, 0, 'false', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.service.begin('chat-other', 10, 20, image_authorized=True, allow_input=value)

    def test_real_journal_observation_needs_no_owner_and_never_focuses_or_sends_input(self):
        self.readonly()
        observed, captured, geometry = self.frame()
        prepared = self.admit('observe')
        with patch.object(cu.uia, 'read_window_content', side_effect=self.read(observed)), \
                patch.object(cu.uia, 'observe_geometry', return_value=geometry), \
                patch.object(cu.uia, 'capture_window', return_value=captured) as capture, \
                patch.object(cu.uia, 'focus_window', side_effect=AssertionError('No observation focus')) as focus, \
                patch.object(cu, 'execute_action', side_effect=AssertionError('No observation input')) as action:
            result = self.connect.dispatch('axx_execute_action', prepared, 'run-one', 'readonly-call')
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertTrue(result['postconditions_passed'])
        self.assertIs(result['evidence']['allow_input'], False)
        self.assertEqual(capture.call_count, 1)
        focus.assert_not_called(); action.assert_not_called()
        self.assertEqual(len(self.service.image_content(result, self.run)), 1)
        self.assertNotIn(captured['jpeg'], json.dumps(self.commands.operations()))
        self.assertEqual(self.service.status('chat-one')['actions'], 0)

    def test_act_is_rejected_at_admission_claim_and_runtime_even_with_changed_ticket_state(self):
        self.readonly()
        with self.assertRaisesRegex(ValueError, 'solo permite observar'): self.admit()
        prepared = self.admit('observe')
        entry = self.service.admissions[prepared['inputs']['ticket']]
        entry.update(kind='act', arguments={'operation_id': 'observe', 'action': 'click', 'observation_id': 'snapshot'})
        self.grant.update(phase='acting', shot=copy.deepcopy(self.shot), actions=0)
        with self.assertRaisesRegex(ValueError, 'solo permite observar'):
            self.service.claim(prepared['inputs']['ticket'], 'act', self.cancelled)
        event = threading.Event()
        with patch.object(self.service, 'claim', return_value=(entry, self.grant, event)), \
                patch.object(cu.uia, 'focus_window') as focus, patch.object(cu, 'execute_action') as action:
            result = cu.TOOLS['computer_use_act'].execute_with_runtime(prepared['inputs'], self.executor.workspace_root,
                                                                       self.cancelled, self.executor)
        self.assertFalse(result.success)
        self.assertIn('solo permite observar', result.error)
        focus.assert_not_called(); action.assert_not_called()
        self.assertEqual(self.grant['actions'], 0)
        self.grant['allow_input'] = True
        self.assertFalse(self.service.status('chat-one')['allow_input'])
        with self.assertRaisesRegex(ValueError, 'solo permite observar'): self.admit(operation_id='forged-input-flag')
        self.grant.pop('allow_input')
        with self.assertRaisesRegex(ValueError, 'solo permite observar'): self.admit(operation_id='legacy-act')

    def test_readonly_desktop_retargets_observation_without_input_owner_or_focus(self):
        result = self.readonly(scope='desktop')
        self.assertFalse(result['allow_input'])
        observed, captured, geometry = self.frame()
        with patch.object(cu.uia, 'read_window_content', side_effect=self.read(observed)), \
                patch.object(cu.uia, 'observe_geometry', return_value=geometry), \
                patch.object(cu.uia, 'capture_window', return_value=captured), patch.object(cu.uia, 'focus_window') as focus:
            prepared = self.admit('observe', window_id=10, pid=20)
            result = cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'], self.executor.workspace_root,
                                                                           self.cancelled, self.executor)
        self.assertTrue(result.success, result.error)
        focus.assert_not_called()
        self.assertEqual(result.output['image_scope'], 'window')
        self.assertEqual(self.grant['target_title'], 'Fixture')

    def test_stop_expiry_and_process_replacement_during_capture_never_restore_cache(self):
        for mutation in ('stop', 'expiry', 'process'):
            with self.subTest(mutation=mutation):
                self.readonly()
                observed, captured, geometry = self.frame()
                birth = ['birth']
                entered, release = threading.Event(), threading.Event()
                result = []
                prepared = self.admit('observe')
                grant = self.grant
                def capture(*args, **kwargs):
                    entered.set()
                    if not release.wait(5): raise AssertionError('Synthetic capture release timed out')
                    return captured
                def execute():
                    result.append(cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'],
                        self.executor.workspace_root, self.cancelled, self.executor))
                with patch.object(cu.uia, 'read_window_content', side_effect=self.read(observed)), \
                        patch.object(cu.uia, 'observe_geometry', return_value=geometry), \
                        patch.object(cu.uia, 'process_started', side_effect=lambda pid: birth[0]), \
                        patch.object(cu.uia, 'capture_window', side_effect=capture), patch.object(cu.uia, 'focus_window') as focus:
                    worker = threading.Thread(target=execute); worker.start()
                    try:
                        self.assertTrue(entered.wait(3))
                        if mutation == 'stop': self.service.end('chat-one')
                        elif mutation == 'expiry': grant['deadline'] = time.monotonic() - 1
                        else: birth[0] = 'replaced-process'
                    finally:
                        release.set(); worker.join(5)
                    self.assertFalse(worker.is_alive())
                    self.assertFalse(self.service.status('chat-one')['active'])
                self.assertFalse(result[0].success)
                self.assertIsNone(grant['shot'])
                self.assertFalse(self.service.admissions)
                with cu.uia._observation_lock: self.assertNotIn('snapshot', cu.uia._observations)
                focus.assert_not_called()

    def test_only_owned_uia_cache_is_removed_on_failure_stop_and_close(self):
        self.readonly()
        observed, captured, geometry = self.frame()
        unrelated = copy.deepcopy(observed)
        unrelated['observation']['observation_id'] = 'unrelated-session'
        cu.uia._remember_observation(unrelated)
        self.addCleanup(lambda: cu.uia._observations.pop('unrelated-session', None))
        with patch.object(cu.uia, 'read_window_content', side_effect=self.read(observed)), \
                patch.object(cu.uia, 'observe_geometry', return_value=geometry), \
                patch.object(cu.uia, 'capture_window', side_effect=ValueError('Synthetic capture failed')):
            prepared = self.admit('observe')
            result = cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'], self.executor.workspace_root,
                                                                           self.cancelled, self.executor)
        self.assertFalse(result.success)
        with cu.uia._observation_lock:
            self.assertNotIn('snapshot', cu.uia._observations)
            self.assertIn('unrelated-session', cu.uia._observations)
        for stop in (self.service.end, lambda chat: self.service.close()):
            self.service._own_observation(self.grant, observed)
            cu.uia._remember_observation(observed)
            self.grant['shot'] = copy.deepcopy(self.shot)
            stop('chat-one')
            self.assertIsNone(self.grant['shot'])
            with cu.uia._observation_lock:
                self.assertNotIn('snapshot', cu.uia._observations)
                self.assertIn('unrelated-session', cu.uia._observations)
            self.readonly()

    def test_expired_snapshot_and_grant_are_cleared_without_new_capture(self):
        self.readonly()
        self.grant['shot'] = copy.deepcopy(self.shot)
        self.grant['shot']['at'] = time.monotonic() - 61
        with patch.object(cu.uia, 'capture_window') as capture:
            self.assertTrue(self.service.status('chat-one')['active'])
            self.assertIsNone(self.grant['shot'])
            prepared = self.admit('observe')
            self.grant['deadline'] = time.monotonic() - 1
            result = cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'], self.executor.workspace_root,
                                                                           self.cancelled, self.executor)
            self.assertFalse(result.success)
            self.assertFalse(self.service.status('chat-one')['active'])
            capture.assert_not_called()

    def test_cancelled_run_cannot_return_an_earlier_image_and_clears_owned_cache(self):
        self.readonly()
        observed, _, _ = self.frame()
        self.service._own_observation(self.grant, observed)
        cu.uia._remember_observation(observed)
        self.grant['shot'] = copy.deepcopy(self.shot)
        prepared = self.admit('observe')
        result = prepared | {'state': 'succeeded', 'output': {'observation_id': 'snapshot'}}
        self.run['_cancel'].set()
        self.assertEqual(self.service.image_content(result, self.run), [])
        self.assertIsNone(self.grant['shot'])
        with cu.uia._observation_lock: self.assertNotIn('snapshot', cu.uia._observations)
        with patch.object(cu.uia, 'capture_window') as capture:
            with self.assertRaisesRegex(ValueError, 'detenido'): self.admit('observe', operation_id='cancelled-run')
            capture.assert_not_called()

    def test_unavailable_process_identity_stops_before_capture_and_erases_own_frame(self):
        self.readonly()
        observed, _, _ = self.frame()
        self.service._own_observation(self.grant, observed)
        cu.uia._remember_observation(observed)
        self.grant['shot'] = copy.deepcopy(self.shot)
        grant = self.grant
        prepared = self.admit('observe')
        with patch.object(cu.uia, 'process_started', side_effect=OSError('Synthetic identity unavailable')), \
                patch.object(cu.uia, 'capture_window') as capture, patch.object(cu.uia, 'focus_window') as focus:
            result = cu.TOOLS['computer_use_observe'].execute_with_runtime(prepared['inputs'], self.executor.workspace_root,
                                                                           self.cancelled, self.executor)
        self.assertFalse(result.success)
        self.assertFalse(self.service.status('chat-one')['active'])
        self.assertIsNone(grant['shot'])
        with cu.uia._observation_lock: self.assertNotIn('snapshot', cu.uia._observations)
        capture.assert_not_called(); focus.assert_not_called()


if __name__ == '__main__': unittest.main()
