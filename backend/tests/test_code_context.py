"""Real Git/files/SQLite coverage for bounded context and incremental Act changes."""
import hashlib
import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.agents.http_api import EvolutionHttpRuntime
from backend.code_studio.context import incremental_content, parse_model_edits
from backend.code_studio.projects import CodeConflictError, CodeSecurityError
from backend.tests.test_acts_code_tools import git_repo


class CodeContextTests(unittest.TestCase):
    def test_git_keeps_empty_environment_config_after_a_windows_environment_roundtrip(self):
        with patch.dict(os.environ, {'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':''}):
            with patch.dict(os.environ, {'AXX_TEST_ROUNDTRIP':'yes'}):
                pass
            self.assertEqual(len(self.rt.code_git.get_head_commit(self.repo)),40)
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.repo = git_repo(root)
        self.rt = EvolutionHttpRuntime(root / 'state.db', storage_dir=root / 'evolution')
        self.rt.code_projects.register_project('p', str(self.repo))

    def tearDown(self):
        self.rt.close()
        self.tmp.cleanup()

    def test_packet_is_bounded_provenance_bearing_persistent_and_redacted(self):
        path = self.repo / 'settings.py'
        path.write_text('api_key = "sk-proj-' + 'x' * 32 + '"\ndef hello():\n    return 1\n', encoding='utf-8')
        packet = self.rt.code_context.build('p', [{'path': 'settings.py'}], act_id='dev')
        doc = packet['files'][0]
        self.assertTrue(doc['redacted'])
        self.assertNotIn('x' * 32, json.dumps(packet))
        self.assertEqual(doc['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(doc['symbols'][0]['name'], 'hello')
        self.assertEqual(self.rt.code_context.get(packet['packet_sha256']), packet)
        with self.assertRaises(CodeSecurityError):
            self.rt.code_context.build('p', [{'path': '.git/config'}])
        with self.assertRaises(ValueError):
            self.rt.code_context.build('p', [{'path': 'calc.py'}] * 9)
        path.write_text('x = "' + 'a' * 65000 + '"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '64 KB'):
            self.rt.code_context.build('p', [{'path': 'settings.py'}])

    def test_multifile_hunks_preserve_bom_crlf_and_fail_all_before_writing(self):
        (self.repo / 'other.py').write_bytes(b'\xef\xbb\xbfvalue = 1\r\n')
        # Worktree checkout comes from the committed fixture; use calc.py + test_calc.py.
        wt = self.rt.code_git.create_agent_worktree(workspace_id='w', project_id='p', agent_id='dev', task_slug='fix')
        root = Path(wt['worktree_path'])
        (root / 'other.py').write_bytes((self.repo / 'other.py').read_bytes())
        edits = []
        for path, old, new in [('calc.py', 'a - b', 'a + b'), ('other.py', 'value = 1', 'value = 2')]:
            edits.append({'path': path, 'expected_base_sha256': hashlib.sha256((root / path).read_bytes()).hexdigest(),
                          'hunks': [{'old_text': old, 'new_text': new}]})
        bad = json.loads(json.dumps(edits))
        bad[1]['expected_base_sha256'] = '0' * 64
        with self.assertRaises(CodeConflictError):
            self.rt.code_git.propose_and_apply_in_worktree(changeset_id='bad', workspace_id='w', file_edits=bad)
        self.assertIn('a - b', (root / 'calc.py').read_text())
        self.rt.code_git.propose_and_apply_in_worktree(changeset_id='good', workspace_id='w', file_edits=edits)
        self.assertIn('a + b', (root / 'calc.py').read_text())
        self.assertEqual((root / 'other.py').read_bytes(), b'\xef\xbb\xbfvalue = 2\r\n')
        self.assertIn('a - b', (self.repo / 'calc.py').read_text())

    def test_model_proposals_are_bound_to_selected_files_and_hashes(self):
        packet = self.rt.code_context.build('p', [{'path': 'calc.py'}], act_id='dev')
        edit = {'path': 'calc.py', 'expected_base_sha256': packet['files'][0]['sha256'],
                'hunks': [{'old_text': 'a - b', 'new_text': 'a + b'}]}
        proposal = {'context_sha256': packet['packet_sha256'], 'file_edits': [edit]}
        self.assertEqual(parse_model_edits(json.dumps(proposal), packet), [edit])
        proposal['file_edits'][0]['path'] = 'test_calc.py'
        with self.assertRaises(CodeSecurityError):
            parse_model_edits(json.dumps(proposal), packet)
        proposal['context_sha256'] = '0' * 64
        with self.assertRaises(CodeConflictError):
            parse_model_edits(json.dumps(proposal), packet)
        part = self.rt.code_context.build('p', [{'path': 'calc.py', 'start_line': 2, 'end_line': 2}])
        with self.assertRaises(CodeSecurityError):
            parse_model_edits('```python\nreturn 7\n```', part)
        with self.assertRaises(CodeConflictError):
            incremental_content('x x', {'hunks': [{'old_text': 'x', 'new_text': 'y'}]})


if __name__ == '__main__':
    unittest.main()
