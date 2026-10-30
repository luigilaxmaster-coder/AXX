"""Targeted window metadata uses fake Win32 functions, never the real desktop."""
import copy
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

from backend import computer_vision as vision
from backend.actions import windows_automation as uia


class WindowTitleScopeTests(unittest.TestCase):
    def setUp(self):
        self.user = Mock()
        self.user.IsWindow.return_value = True
        def identity(hwnd, pointer):
            pointer._obj.value = 20
            return 30
        self.user.GetWindowThreadProcessId.side_effect = identity
        self.user.GetWindowTextLengthW.return_value = len('Selected title')
        def title(hwnd, buffer, maximum):
            buffer.value = 'Selected title'
            return len(buffer.value)
        self.user.GetWindowTextW.side_effect = title
        self.api = patch.object(uia, '_windows_api', return_value=(self.user, Mock()))
        self.birth = patch.object(uia, 'process_started', return_value='birth')
        self.api.start(); self.birth.start()
        self.addCleanup(self.api.stop); self.addCleanup(self.birth.stop)

    def test_title_reads_only_the_selected_hwnd_after_identity_checks(self):
        self.assertEqual(uia.read_window_title(10, 20, 'birth'), 'Selected title')
        self.assertEqual(self.user.GetWindowTextW.call_args.args[0], 10)
        self.assertTrue(all(call.args[0] == 10 for call in self.user.GetWindowTextLengthW.call_args_list))
        self.assertEqual(self.user.GetWindowThreadProcessId.call_count, 2)
        self.user.EnumWindows.assert_not_called()
        self.user.SetForegroundWindow.assert_not_called()

    def test_foreign_pid_or_process_birth_never_reads_title(self):
        def foreign(hwnd, pointer):
            pointer._obj.value = 99
            return 30
        self.user.GetWindowThreadProcessId.side_effect = foreign
        with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth')
        self.user.GetWindowTextW.assert_not_called()
        self.user.GetWindowTextLengthW.assert_not_called()
        self.user.GetWindowThreadProcessId.side_effect = lambda hwnd, pointer: setattr(pointer._obj, 'value', 20) or 30
        with patch.object(uia, 'process_started', return_value='replacement'):
            with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth')
        self.user.GetWindowTextW.assert_not_called()

    def test_cancelled_or_changed_window_cannot_publish_title(self):
        event = threading.Event(); event.set()
        with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth', event)
        self.user.GetWindowTextW.assert_not_called()
        event.clear()
        read = self.user.GetWindowTextW.side_effect
        def cancel(*args):
            value = read(*args); event.set()
            return value
        self.user.GetWindowTextW.side_effect = cancel
        with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth', event)
        self.user.GetWindowTextW.side_effect = read
        with patch.object(uia, 'process_started', side_effect=['birth', 'replacement']):
            with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth')

    def test_title_bounds_and_change_are_rejected(self):
        self.user.GetWindowTextLengthW.return_value = 2049
        with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth')
        self.user.GetWindowTextW.assert_not_called()
        self.user.GetWindowTextLengthW.side_effect = [len('Selected title'), len('Selected title') + 1]
        with self.assertRaises(ValueError): uia.read_window_title(10, 20, 'birth')

    def test_close_rechecks_title_before_posting_close(self):
        def changed_title(hwnd, buffer, maximum):
            buffer.value = 'Different title'
            return len(buffer.value)
        self.user.GetWindowTextW.side_effect = changed_title
        with patch.object(uia, 'list_windows', return_value=[{'window_id': 10, 'pid': 20, 'title': 'Selected title'}]), \
             patch.object(uia, 'process_name', return_value='fixture.exe'):
            with self.assertRaises(ValueError):
                uia.close_window(10, 20, expected_title='Selected title')
        self.user.PostMessageW.assert_not_called()

    def test_close_rejects_oversized_title_even_when_prefix_matches(self):
        prefix = 'A' * 2048
        self.user.GetWindowTextLengthW.return_value = 2049
        def truncated_title(hwnd, buffer, maximum):
            buffer.value = prefix[:maximum - 1]
            return len(buffer.value)
        self.user.GetWindowTextW.side_effect = truncated_title
        with patch.object(uia, 'list_windows', return_value=[{'window_id': 10, 'pid': 20, 'title': prefix}]), \
             patch.object(uia, 'process_name', return_value='fixture.exe'):
            with self.assertRaises(ValueError):
                uia.close_window(10, 20, expected_title=prefix)
        self.user.PostMessageW.assert_not_called()

    def test_close_rejects_pid_replacement_during_title_read(self):
        changed = {'value': False}
        def identity(hwnd, pointer):
            pointer._obj.value = 99 if changed['value'] else 20
            return 30
        def title(hwnd, buffer, maximum):
            buffer.value = 'Selected title'
            changed['value'] = True
            return len(buffer.value)
        self.user.GetWindowThreadProcessId.side_effect = identity
        self.user.GetWindowTextW.side_effect = title
        self.user.PostMessageW.return_value = True
        with patch.object(uia, 'list_windows', side_effect=[[{'window_id': 10, 'pid': 20, 'title': 'Selected title'}], []]), \
             patch.object(uia, 'process_name', return_value='fixture.exe'):
            with self.assertRaises(ValueError):
                uia.close_window(10, 20, expected_title='Selected title')
        self.user.PostMessageW.assert_not_called()

    def test_close_rejects_reused_pid_and_hwnd_with_different_birth(self):
        self.user.PostMessageW.return_value = True
        with patch.object(uia, 'list_windows', side_effect=[[{'window_id': 10, 'pid': 20, 'title': 'Selected title'}], []]), \
             patch.object(uia, 'process_name', return_value='fixture.exe'), \
             patch.object(uia, 'process_started', return_value='new-birth'):
            with self.assertRaises(ValueError):
                uia.close_window(10, 20, expected_title='Selected title', expected_process_started='birth')
        self.user.PostMessageW.assert_not_called()

    def test_close_rejects_title_changed_during_process_name_check(self):
        current_title = {'value': 'Selected title'}
        self.user.GetWindowTextLengthW.side_effect = lambda _hwnd: len(current_title['value'])
        def title(_hwnd, buffer, _maximum):
            buffer.value = current_title['value']
            return len(buffer.value)
        self.user.GetWindowTextW.side_effect = title
        def process_name(_pid):
            current_title['value'] = 'Different title'
            return 'fixture.exe'
        self.user.PostMessageW.return_value = True
        with patch.object(uia, 'list_windows', side_effect=[[{'window_id': 10, 'pid': 20, 'title': 'Selected title'}], []]), \
             patch.object(uia, 'process_name', side_effect=process_name):
            with self.assertRaises(ValueError):
                uia.close_window(10, 20, expected_title='Selected title', expected_process_started='birth')
        self.user.PostMessageW.assert_not_called()


class TargetedVisionTests(unittest.TestCase):
    def frame(self):
        geometry = {'window_bounds': {'x': 0, 'y': 0, 'width': 300, 'height': 200}, 'monitors': []}
        observed = {'window_title': 'Selected title', 'controls': [], 'observation': geometry | {
            'observation_id': 'selected-snapshot', 'window_id': 10, 'pid': 20, 'process_started': 'birth'}}
        shot = {'jpeg': b'synthetic-frame', 'width': 300, 'height': 200, 'image_bounds': geometry['window_bounds'],
                'hash': 'synthetic-hash', 'at': time.monotonic()}
        return geometry, observed, shot

    def test_vision_inventory_never_requests_foreign_window_titles(self):
        geometry, observed, shot = self.frame()
        grant = {'window_id': 10, 'pid': 20, 'birth': 'birth'}
        rows = [{'window_id': 11, 'pid': 21, 'title': 'FOREIGN_PRIVATE_TITLE'},
                {'window_id': 10, 'pid': 20, 'title': 'IGNORED_INVENTORY_TITLE'}]
        emitted = []
        with patch.object(uia, 'list_windows', return_value=rows) as inventory, \
                patch.object(uia, 'observe_geometry', return_value=geometry), \
                patch.object(uia, 'process_started', return_value='birth'), \
                patch.object(uia, 'read_window_title', return_value='Selected title') as title, \
                patch.object(uia, 'read_window_content', return_value=observed) as content, \
                patch.object(vision, 'capture', return_value=shot), patch.object(uia, 'focus_window') as focus:
            _, output = vision.observe(grant, threading.Event(), on_observation=lambda value: emitted.append(value['observation']['observation_id']))
        inventory.assert_called_once_with(include_untitled=True, include_titles=False)
        self.assertEqual(title.call_args.args, (10, 20, 'birth'))
        self.assertEqual(content.call_args.args, (10, 20, 'Selected title'))
        self.assertEqual(emitted, ['selected-snapshot'])
        self.assertNotIn('FOREIGN_PRIVATE_TITLE', json.dumps(output))
        self.assertNotIn('IGNORED_INVENTORY_TITLE', json.dumps(output))
        focus.assert_not_called()

    def test_hook_identifies_owned_uia_snapshot_before_geometry_failure(self):
        geometry, observed, _ = self.frame()
        observed = copy.deepcopy(observed)
        observed['observation']['window_bounds']['width'] += 1
        owned = []
        with patch.object(uia, 'list_windows', return_value=[{'window_id': 10, 'pid': 20}]), \
                patch.object(uia, 'observe_geometry', return_value=geometry), \
                patch.object(uia, 'process_started', return_value='birth'), \
                patch.object(uia, 'read_window_title', return_value='Selected title'), \
                patch.object(uia, 'read_window_content', return_value=observed), patch.object(vision, 'capture') as capture:
            with self.assertRaisesRegex(ValueError, 'geometría'):
                vision.observe({'window_id': 10, 'pid': 20, 'birth': 'birth'}, threading.Event(),
                    on_observation=lambda value: owned.append(value['observation']['observation_id']))
        self.assertEqual(owned, ['selected-snapshot'])
        capture.assert_not_called()


if __name__ == '__main__': unittest.main()
