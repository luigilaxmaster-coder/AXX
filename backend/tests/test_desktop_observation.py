import copy
import math
import time
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from PIL import Image

from backend.actions import windows_automation as uia
from backend.actions.desktop_observation import observe_desktop


class DesktopObservationTests(unittest.TestCase):
    def setUp(self):
        self.result = {'window_title': 'Fixture', 'truncated': False,
                       'controls': [{'control_id': 'a'*64, 'name': 'Enabled', 'enabled': True, 'offscreen': False,
                                     'patterns': ['Toggle', 'ExpandCollapse', 'SelectionItem', 'RangeValue', 'Scroll', 'Value', 'Grid']}],
                       'observation': {'observation_id': 'fixture-observation', 'session_id': uia.OBSERVATION_SESSION_ID,
                                       'completed_monotonic': time.monotonic(), 'window_id': 123, 'pid': 42,
                                       'process_started': '123456789', 'window_bounds': {'x': -100, 'y': 10, 'width': 100, 'height': 100}}}
        uia._remember_observation(self.result)

    def test_client_cannot_forge_or_mutate_observation(self):
        self.result['window_title'] = 'Forged'
        observed = uia.get_observation('fixture-observation', 123, 42)
        self.assertEqual(observed['window_title'], 'Fixture')
        observed['window_title'] = 'Forged copy'
        self.assertEqual(uia.get_observation('fixture-observation', 123, 42)['window_title'], 'Fixture')
        for args in [('forged', 123, 42), ('fixture-observation', 124, 42), ('fixture-observation', 123, 43)]:
            with self.assertRaises(ValueError):
                uia.get_observation(*args)

    def test_expired_and_prior_session_tokens_are_rejected(self):
        with patch.object(uia.time, 'monotonic', return_value=self.result['observation']['completed_monotonic']+16):
            with self.assertRaisesRegex(ValueError, 'STALE_OBSERVATION'):
                uia.get_observation('fixture-observation', 123, 42)
        with patch.object(uia, 'OBSERVATION_SESSION_ID', 'another-session'):
            with self.assertRaisesRegex(ValueError, 'STALE_OBSERVATION'):
                uia.get_observation('fixture-observation', 123, 42)

    def test_state_dispatch_binds_observed_identity_and_geometry(self):
        for pattern, value in [('Value', 'Texto seguro'), ('Toggle', True), ('SelectionItem', False), ('ExpandCollapse', 'expanded'),
                               ('RangeValue', 25), ('Scroll', {'horizontal': -1, 'vertical': 50})]:
            with self.subTest(pattern=pattern), patch.object(uia, '_uia', return_value={'success': True}) as call:
                uia.set_control_state(123, 42, 'a'*64, 'fixture-observation', pattern, value)
                payload = call.call_args.args[0]
                self.assertEqual(payload['expected_process_started'], '123456789')
                self.assertEqual(payload['expected_title'], 'Fixture')
                self.assertEqual(payload['expected_bounds']['x'], -100)
                self.assertEqual(payload['state'], value)
                self.assertEqual(payload['_observation_deadline'],
                                 self.result['observation']['completed_monotonic'] + uia.OBSERVATION_MAX_AGE)

    def test_invalid_states_never_dispatch(self):
        for pattern, value in [('Toggle', 1), ('SelectionItem', 'true'), ('ExpandCollapse', 'toggle'),
                               ('RangeValue', math.nan), ('RangeValue', True), ('Scroll', {'vertical': 50}),
                               ('Scroll', {'horizontal': -2, 'vertical': 50}), ('Invoke', True), ('Value', 'x'*8193), ('Value', '\x00')]:
            with self.subTest(pattern=pattern, value=value), patch.object(uia, '_uia') as call:
                with self.assertRaises(ValueError):
                    uia.set_control_state(123, 42, 'a'*64, 'fixture-observation', pattern, value)
                call.assert_not_called()

    def test_incomplete_ambiguous_disabled_and_unsupported_controls_abstain(self):
        for change in ['truncated', 'duplicate', 'disabled', 'unsupported']:
            result = copy.deepcopy(self.result)
            if change == 'truncated': result['truncated'] = True
            if change == 'duplicate': result['controls'] *= 2
            if change == 'disabled': result['controls'][0]['enabled'] = False
            if change == 'unsupported': result['controls'][0]['patterns'] = []
            uia._remember_observation(result)
            with self.subTest(change=change), patch.object(uia, '_uia') as call:
                with self.assertRaises(ValueError):
                    uia.set_control_state(123, 42, 'a'*64, 'fixture-observation', 'Toggle', True)
                call.assert_not_called()

    def test_cache_is_bounded(self):
        for index in range(70):
            result = copy.deepcopy(self.result)
            result['observation']['observation_id'] = f'bounded-{index}'
            uia._remember_observation(result)
        self.assertLessEqual(len(uia._observations), 64)

    def test_grid_read_is_bounded_and_uses_observed_identity(self):
        with patch.object(uia, '_uia', return_value={'success': True}) as call:
            uia.read_control_grid(123, 42, 'a'*64, 'fixture-observation', rows=2, columns=3)
            self.assertEqual(call.call_args.args[0]['expected_process_started'], '123456789')
        for kwargs in [{'row': -1}, {'rows': 21}, {'rows': 20, 'columns': 20}, {'columns': True}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                uia.read_control_grid(123, 42, 'a'*64, 'fixture-observation', **kwargs)

    def test_capture_reuses_magic_pen_and_keeps_physical_transform(self):
        self.result['observation'].update(monitors=[{'id':'left','x':-100,'y':0,'width':100,'height':200}], minimized=False)
        service = Mock()
        service.capture.return_value = {'id':'capture-id','revision':1,'source':{'sha256':'digest','captured_at':time.time(), 'x':-100,'y':0,'width':100,'height':200}}
        service.original.return_value = Image.new('RGB', (100, 200), 'white')
        uia._remember_observation(self.result)
        with patch.object(uia, 'inspect_controls', return_value=self.result), patch.object(uia, 'observe_geometry', return_value=self.result['observation']), patch.object(uia, 'process_started', return_value='123456789'), patch.object(uia, 'list_windows', return_value=[{'window_id':123,'pid':42,'title':'Fixture'}]):
            result = observe_desktop(123, 42, capture_service=service, monitor_id='left')
        service.capture.assert_called_once_with({'monitor':'left'})
        self.assertEqual(result['observation']['screenshot']['transform']['offset_x'], -100)
        self.assertTrue(result['observation']['screenshot']['local_only'])
        self.assertNotIn('preview', result)

    def test_capture_refuses_disconnected_producer(self):
        with patch.object(uia, 'inspect_controls', return_value=self.result):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_UNAVAILABLE'):
                observe_desktop(123, 42, monitor_id='left')


if __name__ == '__main__':
    unittest.main()
