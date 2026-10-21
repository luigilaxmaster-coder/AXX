"""Controlled regressions for file creation, inspection and uncertain effects."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.actions.tools import FileArtifactTool, ProcessStateTool, get_tool


class ExecutorGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')

    def tearDown(self):
        self.executor.close()
        self.tmp.cleanup()

    def test_existing_file_is_never_overwritten(self):
        target = self.executor.workspace_root / 'existing.txt'
        target.write_text('preserve me', encoding='utf-8')
        result = self.executor.execute_action('file_artifact_writer', {'path': 'existing.txt', 'content': 'replace'})
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(target.read_text(encoding='utf-8'), 'preserve me')

    def test_invalid_content_does_not_create_directories(self):
        target = self.root / 'must-not-exist' / 'artifact.txt'
        valid, _ = FileArtifactTool().verify_preconditions({'path': str(target), 'content': None})
        self.assertFalse(valid)
        self.assertFalse(target.parent.exists())

    def test_windows_special_names_and_streams_are_rejected_before_io(self):
        for name in ('NUL.txt', 'AUX', 'COM1.log', 'safe.txt:private', 'trailing. ', 'bad?.txt'):
            with self.subTest(name=name):
                valid, _ = FileArtifactTool().verify_preconditions({'path': str(self.root / name), 'content': 'x'})
                self.assertFalse(valid)

    @unittest.skipUnless(os.name == 'nt', 'Windows native process inspection')
    def test_current_process_is_active_without_tasklist(self):
        with patch('subprocess.run', side_effect=PermissionError('tasklist unavailable')):
            result = ProcessStateTool().execute({'pid': os.getpid()})
        self.assertTrue(result.success, result.error)
        self.assertTrue(result.output['active'])

    def test_process_pid_must_fit_windows_dword(self):
        self.assertFalse(ProcessStateTool().verify_preconditions({'pid': 2**32})[0])

    @unittest.skipUnless(os.name == 'nt', 'Windows exit codes are 32-bit')
    def test_terminated_process_exit_259_is_not_reported_active(self):
        # Keep the handle open so Windows retains the terminated process object.
        with subprocess.Popen([sys.executable, '-c', 'raise SystemExit(259)']) as process:
            self.assertEqual(process.wait(timeout=5), 259)
            result = ProcessStateTool().execute({'pid': process.pid})
            self.assertTrue(result.success, result.error)
            self.assertFalse(result.output['active'])

    def test_verifier_crash_preserves_unknown_effect_and_replay(self):
        tool = get_tool('file_artifact_writer')
        args = {'path': 'uncertain.txt', 'content': 'real effect'}
        with patch.object(tool, 'verify_postconditions', side_effect=OSError('verification unavailable')):
            result = self.executor.execute_action('file_artifact_writer', args, 'uncertain-write')
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(result['postconditions_passed'])
        self.assertEqual((self.executor.workspace_root / 'uncertain.txt').read_text(), 'real effect')
        replay = self.executor.execute_action('file_artifact_writer', args, 'uncertain-write')
        self.assertEqual(replay['state'], 'unknown')
        self.assertTrue(replay['replayed'])

    def test_execution_crash_after_effect_is_unknown(self):
        tool = get_tool('file_artifact_writer')
        def interrupted(inputs, workspace):
            Path(inputs['path']).write_text(inputs['content'])
            raise OSError('worker interrupted after effect')
        with patch.object(tool, 'execute_in_workspace', side_effect=interrupted):
            result = self.executor.execute_action('file_artifact_writer', {'path': 'interrupted.txt', 'content': 'keep'}, 'interrupted')
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(self.executor.get_operation('interrupted')['state'], 'unknown')


if __name__ == '__main__':
    unittest.main()
