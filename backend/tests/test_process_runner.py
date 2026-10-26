import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.actions import process_runner as runner


@unittest.skipUnless(os.name == 'nt', 'Native Windows process custody')
class ProcessRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='axx-reviewed-process-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = dict(executable=sys.executable, args=['--version'], cwd=str(self.root), timeout_s=5)

    def script(self, source, **inputs):
        fixture = self.root / 'fixture.py'
        fixture.write_text(source, encoding='utf-8')
        return self.inputs | {'args': [str(fixture)]} | inputs

    def test_real_version_is_only_process_exit(self):
        result = runner.ProcessRunTool().execute_cancellable(self.inputs, self.root, threading.Event())
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.output['exit_code'], 0)
        self.assertIn('Python', result.output['stdout'])
        self.assertGreater(int(result.output['process_started']), 0)
        self.assertTrue(result.evidence['cleanup_verified'])
        self.assertEqual(result.output['effect_status'], 'unknown')
        self.assertFalse(result.evidence['application_effect_verified'])
        self.assertFalse(runner.ProcessRunTool().verify_postconditions(self.inputs, result)[0])

    def test_arguments_are_literal_and_new_artifact_hash_is_independent(self):
        inputs = self.script("import pathlib,sys,json\np=pathlib.Path('result.json')\np.write_text(json.dumps(sys.argv[1:],ensure_ascii=False),encoding='utf-8')\n",
                             expected_artifact='result.json')
        values = ['space value', 'áé😀', '$(literal)', '& echo never', '"quotes"', '']
        inputs['args'] += values
        result = runner.ProcessRunTool().execute_cancellable(inputs, self.root, threading.Event())
        self.assertTrue(result.success, result.error)
        data = (self.root / 'result.json').read_bytes()
        self.assertEqual(json.loads(data), values)
        self.assertEqual(result.output['artifact']['sha256'], hashlib.sha256(data).hexdigest())
        self.assertTrue(runner.ProcessRunTool().verify_postconditions(inputs, result)[0])
        self.assertFalse(result.evidence['application_effect_verified'])

    def test_existing_artifact_is_not_overwritten(self):
        path = self.root / 'keep.txt'; path.write_text('keep')
        inputs = self.script("from pathlib import Path\nPath('keep.txt').write_text('changed')", expected_artifact='keep.txt')
        with self.assertRaisesRegex(ValueError, 'ya existe'):
            runner.run_process(inputs, self.root)
        self.assertEqual(path.read_text(), 'keep')

    def test_missing_artifact_does_not_verify_zero_exit(self):
        result = runner.run_process(self.inputs | {'expected_artifact': 'missing.txt'}, self.root)
        self.assertFalse(result['success'])
        self.assertEqual(result['output']['exit_code'], 0)
        self.assertTrue(result['output']['process_completed'])
        self.assertTrue(result['evidence']['effect_uncertain'])

    def test_nonzero_exit_keeps_bounded_stderr_and_unknown_effect(self):
        result = runner.run_process(self.script("import sys\nprint('failure detail',file=sys.stderr)\nsys.exit(7)"), self.root)
        self.assertFalse(result['success'])
        self.assertEqual(result['output']['exit_code'], 7)
        self.assertIn('failure detail', result['output']['stderr'])
        self.assertTrue(result['evidence']['effect_uncertain'])

    def test_timeout_terminates_owned_process(self):
        result = runner.run_process(self.script('import time\ntime.sleep(30)', timeout_s=1), self.root)
        self.assertEqual(result['output']['status'], 'timeout')
        self.assertTrue(result['evidence']['cleanup_verified'])
        self.assertFalse(result['success'])

    def test_output_limit_cannot_deadlock_full_pipes(self):
        result = runner.run_process(self.script("import os\nfor _ in range(500):\n os.write(1,b'x'*4096)\n os.write(2,b'y'*4096)"), self.root)
        self.assertFalse(result['success'])
        self.assertEqual(result['output']['status'], 'output_limit')
        self.assertTrue(result['evidence']['cleanup_verified'])
        self.assertLessEqual(len(result['output']['stdout']), runner.MAX_OUTPUT)
        self.assertLessEqual(len(result['output']['stderr']), runner.MAX_OUTPUT)

    def test_environment_has_no_provider_secrets(self):
        inputs = self.script("import os\nprint(os.environ.get('AXX_FIXTURE_SECRET','absent'))\n")
        with patch.dict(os.environ, {'AXX_FIXTURE_SECRET': 'must-not-forward'}):
            result = runner.run_process(inputs, self.root)
        self.assertIn('absent', result['output']['stdout'])
        self.assertNotIn('must-not-forward', result['output']['stdout'])

    def test_pre_cancel_does_not_spawn(self):
        cancel = threading.Event(); cancel.set()
        with patch.object(runner, '_spawn_owned') as spawn:
            result = runner.run_process(self.inputs, self.root, cancel)
        spawn.assert_not_called()
        self.assertTrue(result['evidence']['cancelled'])

    def test_assignment_failure_never_runs_child_code(self):
        inputs = self.script("from pathlib import Path\nPath('unsafe-start').write_text('ran')")
        with patch.object(runner.WindowsJobObject, 'assign_process', return_value=False):
            with self.assertRaisesRegex(OSError, 'asociarse'):
                runner.run_process(inputs, self.root)
        self.assertFalse((self.root / 'unsafe-start').exists())

    def test_missing_job_limits_reject_before_process_creation(self):
        info = runner.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        with patch.object(runner, '_query_job', return_value=info), patch.object(runner.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(OSError, 'cancelación'):
                runner.run_process(self.inputs, self.root)
        spawn.assert_not_called()

    def test_invalid_arguments_and_paths_fail_before_spawn(self):
        invalid = [dict(timeout_s=True), dict(timeout_s=0), dict(timeout_s=121), dict(args='--version'),
                   dict(args=['nul\0']), dict(args=[True]), dict(env={}), dict(cwd='.'),
                   dict(expected_artifact='../escape'), dict(expected_artifact='C:\\escape'),
                   dict(expected_artifact='\\rooted'), dict(executable='python.exe')]
        with patch.object(runner, '_spawn_owned') as spawn:
            for override in invalid:
                with self.subTest(override=override), self.assertRaises((ValueError, TypeError)):
                    runner.run_process(self.inputs | override, self.root)
        spawn.assert_not_called()

    def test_cancel_terminates_real_child_tree_only(self):
        child = self.root / 'child.py'; child.write_text('import time\ntime.sleep(30)')
        inputs = self.script("import subprocess,sys,pathlib,time\np=subprocess.Popen([sys.executable,'child.py'])\npathlib.Path('child.pid').write_text(str(p.pid))\ntime.sleep(30)")
        cancel, child_handle = threading.Event(), []
        kernel = C.WinDLL('kernel32', use_last_error=True)
        open_process = runner._api(kernel, 'OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE)
        wait = runner._api(kernel, 'WaitForSingleObject', [W.HANDLE, W.DWORD], W.DWORD)
        close = runner._api(kernel, 'CloseHandle', [W.HANDLE], W.BOOL)
        def stop_when_child_exists():
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                try:
                    pid = int((self.root / 'child.pid').read_text())
                    handle = open_process(0x100000, False, pid)
                    if handle:
                        child_handle.append(handle); break
                except (OSError, ValueError):pass
                time.sleep(.01)
            cancel.set()
        watcher = threading.Thread(target=stop_when_child_exists)
        unrelated = subprocess.Popen([sys.executable, str(child)], creationflags=subprocess.CREATE_NO_WINDOW)
        watcher.start()
        try:
            result = runner.run_process(inputs, self.root, cancel)
            watcher.join(5)
            self.assertTrue(child_handle, result)
            self.assertEqual(result['output']['status'], 'cancelled')
            self.assertTrue(result['evidence']['cleanup_verified'])
            self.assertEqual(wait(child_handle[0], 1000), 0)
            self.assertIsNone(unrelated.poll())  # Another owned fixture outside the job remains alive.
        finally:
            unrelated.terminate(); unrelated.wait(timeout=3)
            watcher.join(5)
            for handle in child_handle:close(handle)


if __name__ == '__main__':
    unittest.main()
