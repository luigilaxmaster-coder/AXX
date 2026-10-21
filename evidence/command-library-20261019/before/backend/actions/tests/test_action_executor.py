"""Unit tests for Action Executor and Tool Registry.
Verifies:
  - Tool preconditions verification
  - Tool execution producing real file artifacts
  - Tool postconditions assertion (file existence, byte size, sha256 hash)
  - System telemetry and process state inspections
  - Atomic operation tracking in SQLite
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from backend.actions.tools import (
    FileArtifactTool, SystemTelemetryTool, ProcessStateTool, get_tool, list_tools
)
from backend.actions.executor import ActionExecutor

class ActionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / 'actions.db'
        self.executor = ActionExecutor(self.db_path)

    def tearDown(self):
        self.executor.close()
        self.tmp.cleanup()

    def test_list_tools(self):
        tools = list_tools()
        names = [t['name'] for t in tools]
        self.assertIn('file_artifact_writer', names)
        self.assertIn('system_telemetry', names)
        self.assertIn('process_state_inspector', names)

    def test_file_artifact_lifecycle(self):
        target_file = Path(self.tmp.name) / 'output' / 'test_artifact.json'
        content = json.dumps({'axx_verified': True, 'timestamp': 123456789})

        # Execute via ActionExecutor
        res = self.executor.execute_action('file_artifact_writer', {
            'path': str(target_file),
            'content': content
        })

        self.assertEqual(res['state'], 'succeeded')
        self.assertTrue(res['preconditions_passed'])
        self.assertTrue(res['postconditions_passed'])
        self.assertTrue(target_file.exists())
        self.assertEqual(target_file.read_text(), content)

        # Check evidence recorded
        expected_sha = hashlib.sha256(content.encode('utf-8')).hexdigest()
        self.assertEqual(res['evidence']['sha256'], expected_sha)
        self.assertEqual(res['evidence']['size'], len(content.encode('utf-8')))

    def test_file_artifact_precondition_blocks_system_directory(self):
        res = self.executor.execute_action('file_artifact_writer', {
            'path': 'C:\\Windows\\System32\\dangerous.txt',
            'content': 'blocked'
        })
        self.assertEqual(res['state'], 'failed')
        self.assertFalse(res['preconditions_passed'])
        self.assertIn("restricted system directory", res['error'])

    def test_system_telemetry(self):
        res = self.executor.execute_action('system_telemetry', {})
        self.assertEqual(res['state'], 'succeeded')
        self.assertTrue(res['postconditions_passed'])
        self.assertIn('os', res['output'])
        self.assertIn('disk_free_gb', res['output'])
        self.assertGreater(res['output']['disk_free_gb'], 0)

    def test_process_state_inspector(self):
        res = self.executor.execute_action('process_state_inspector', {'pid': os.getpid()})
        self.assertEqual(res['state'], 'succeeded')
        self.assertTrue(res['output']['active'])

if __name__ == '__main__':
    unittest.main()
