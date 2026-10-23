import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.demonstration import DemonstrationService, MAX_RECORDS


WINDOW = {'window_id': 123, 'pid': 456, 'title': 'Fixture'}


def event(**changes):
    value = {'type': 'event', 'kind': 'invoke', 'window_id': 123, 'pid': 456,
             'selector': {'runtime_id': [42, 1], 'automation_id': 'save',
                          'control_type': 'ControlType.Button', 'name': 'Save', 'is_password': False}}
    value.update(changes)
    return value


class Process:
    def __init__(self, rows, hold=False):
        self.input = io.BytesIO(b''.join((json.dumps(r) + '\n').encode() for r in rows))
        self.hold = hold
        self.done = threading.Event()
        self.returncode = None
        self.stdout = self
        self.terminated = False

    def readline(self, maximum):
        line = self.input.readline(maximum)
        if not line and self.hold:
            self.done.wait(5)
        return line

    def close(self):
        self.input.close()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -1
        self.done.set()

    def kill(self):
        self.terminate()

    def wait(self, timeout):
        return self.returncode


class DemonstrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.db'
        self.service = DemonstrationService(self.path)
        self.windows = patch('backend.demonstration.list_windows', return_value=[WINDOW]).start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def start(self, rows, hold=False, **body):
        process = Process(rows, hold)
        with patch.object(self.service, '_launch', return_value=process) as launch:
            record = self.service.start({'window_id': 123, 'pid': 456, **body})
        return record, process, launch

    def finish(self):
        self.service.thread.join(3)
        self.assertFalse(self.service.thread.is_alive())
        return self.service.status()

    def test_scoped_semantic_events_are_candidate_reference_not_authority(self):
        row, process, launch = self.start([{'type': 'ready'}, event(), {'type': 'end', 'reason': 'time_limit'}])
        result = self.finish()
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['reason'], 'time_limit')
        self.assertEqual(result['event_count'], 1)
        self.assertEqual(result['events'][0]['selector']['name'], 'Save')
        self.assertFalse(result['reference']['execution_authority'])
        self.assertFalse(result['verified'])
        self.assertEqual(launch.call_args.args[0]['pid'], 456)
        self.assertTrue(process.terminated)
        self.assertEqual(self.service.get(row['id']), result)
        self.assertNotIn('events', self.service.list()[0])

    def test_password_values_edit_content_and_wrong_scope_are_omitted(self):
        password = event()
        password['selector'].update(is_password=True, name='secret', value='secret')
        edit = event(value='secret', new_value='secret', kind='enabled', state=True)
        edit['selector'].update(control_type='ControlType.Edit', name='secret', value='secret')
        unknown = event()
        del unknown['selector']['is_password']
        self.start([password, unknown, event(pid=999), event(window_id=999), event(kind='value'), edit,
                    {'type': 'end', 'reason': 'time_limit'}])
        result = self.finish()
        self.assertEqual(result['event_count'], 1)
        self.assertNotIn('secret', json.dumps(result))
        self.assertTrue(result['events'][0]['state'])

    def test_explicit_scope_and_limits_required_before_launch(self):
        with patch.object(self.service, '_launch') as launch:
            for body in ({}, {'window_id': True, 'pid': 456}, {'window_id': 123, 'pid': 9},
                         {'window_id': 123, 'pid': 456, 'max_seconds': 301},
                         {'window_id': 123, 'pid': 456, 'max_events': 501}):
                with self.assertRaises(ValueError):
                    self.service.start(body)
            launch.assert_not_called()

    def test_event_limit_kills_worker_and_does_not_overstore(self):
        self.start([event(), event(), event()], max_events=2)
        result = self.finish()
        self.assertEqual(result['event_count'], 2)
        self.assertEqual(result['reason'], 'event_limit')

    def test_invalid_or_oversized_stdout_is_bounded(self):
        self.start([{'unexpected': 'x' * 9000}])
        self.assertEqual(self.finish()['reason'], 'output_limit')
        self.start([['not a protocol object']])
        self.assertEqual(self.finish()['status'], 'failed')

    def test_cancel_clears_observations_and_stops_process(self):
        record, process, _ = self.start([{'type': 'ready'}, event()], hold=True)
        result = self.service.stop({'id': record['id'], 'cancel': True})
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['events'], [])
        self.assertNotIn('reference', result)
        self.assertTrue(process.terminated)

    def test_parallel_start_wrong_stop_and_watchdog(self):
        record, process, _ = self.start([], hold=True)
        with self.assertRaises(ValueError):
            self.service.start({'window_id': 123, 'pid': 456})
        with self.assertRaises(ValueError):
            self.service.stop({'id': 'other'})
        self.service._deadline(record['id'], process)
        self.assertEqual(self.finish()['reason'], 'time_limit')

    def test_empty_provider_and_window_loss_are_explicit(self):
        self.start([{'type': 'ready'}, {'type': 'end', 'reason': 'window_lost'}])
        result = self.finish()
        self.assertEqual(result['reason'], 'window_lost')
        self.assertEqual(result['observation_status'], 'no_observations')
        self.assertFalse(result['verified'])

    def test_restart_does_not_resume_recording_and_storage_is_bounded(self):
        self.start([event(), {'type': 'end', 'reason': 'time_limit'}])
        record = self.finish()
        self.service.close()
        record['status'] = 'recording'
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE demonstrations SET payload=?', (json.dumps(record),))
        db.close()
        self.service = DemonstrationService(self.path)
        self.assertEqual(self.service.status()['status'], 'interrupted')
        self.assertIsNone(self.service.process)
        for i in range(MAX_RECORDS + 2):
            item = copy.deepcopy(record)
            item.update(id=f'{i:032x}', status='stopped', started_at=i)
            self.service._save(item)
        self.assertEqual(len(self.service.list()), MAX_RECORDS)

    def test_shutdown_interrupts_worker_and_close_is_idempotent(self):
        _, process, _ = self.start([], hold=True)
        self.service.close()
        self.assertTrue(process.terminated)
        self.assertFalse(self.service.thread.is_alive())
        self.service.close()
        self.service = DemonstrationService(self.path)
        self.assertEqual(self.service.list()[0]['status'], 'interrupted')

    def test_inventory_reports_only_real_commands_no_app_specific_claims(self):
        from backend.commands import ADAPTERS
        with patch('backend.demonstration.installed_apps', return_value=[{'name': 'AutoCAD', 'app_id': 'cad'}]):
            result = self.service.inventory()
        self.assertEqual(result['command_ids'], sorted(ADAPTERS))
        self.assertEqual(result['windows'], [WINDOW])
        self.assertEqual(result['capabilities']['app_specific_adapters'], [])
        self.assertFalse(result['capabilities']['recorded_replay'])
        with patch('backend.demonstration.installed_apps', side_effect=ValueError):
            self.assertEqual(self.service.inventory()['errors'], ['installed_apps_unavailable'])

    @unittest.skipUnless(os.name == 'nt', 'Native Windows compile smoke')
    def test_native_callback_compiles_and_invalid_window_is_rejected(self):
        script = (Path(__file__).parents[1] / 'actions/uia_observer.ps1').read_text(encoding='utf-8')
        compile_part = script.split('    Add-Type -ReferencedAssemblies', 1)[1].split('\n    $observer =', 1)[0]
        command = (' $ErrorActionPreference="Stop"; Add-Type -AssemblyName UIAutomationClient; '
                   'Add-Type -AssemblyName UIAutomationTypes; Add-Type -ReferencedAssemblies' +
                   compile_part + '; [AxxObserver].FullName')
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertIn(b'AxxObserver', result.stdout)
        # An impossible target exercises the packaged worker without observing user windows.
        process = self.service._launch({'window_id': 1, 'pid': os.getpid(), 'parent_pid': os.getpid(),
                                        'max_seconds': 1, 'max_events': 1})
        try:
            process.wait(timeout=15)
            result = json.loads(process.stdout.read(8192))
            self.assertEqual(result, {'type': 'end', 'reason': 'observer_error'})
        finally:
            self.service._terminate(process)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
