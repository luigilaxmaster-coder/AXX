"""Unit, security, and integration tests for Phase 9 — AXX Code Studio Core (PR-13 & PR-14 / Gate G9).

Covers:
- SEC-03: Canonical path confinement, '..' traversal block, Windows ADS/UNC block, secret file block,
  and Windows junction/symlink block.
- CODE-01: Binary rejection, large-file read-only degraded mode, exact CRLF/LF & BOM preservation, and CAS save conflict.
- CODE-02: Isolated per-agent git worktrees and dirty-file protection during primary workspace integration.
- CODE-03: Validated CodeChangeSet v1 proposal, atomic multi-file apply, supervised test receipt, and atomic rollback.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.code_studio.git_workspace import DirtyWorktreeError, GitWorkspaceService
from backend.code_studio.patch_engine import CodeChangeSetValidationError, CodePatchEngine, validate_code_changeset
from backend.code_studio.projects import (
    BinaryFileError,
    CodeConflictError,
    CodeProjectService,
    CodeSecurityError,
    resolve_scoped_project_path,
)
from backend.code_studio.test_runner import SupervisedTestRunner, UnauthorizedToolchainError


class CodeStudioCoreTests(unittest.TestCase):
    def test_git_metadata_is_blocked_case_insensitively_at_every_depth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.git').mkdir()
            config = root / '.git/config'
            config.write_bytes(b'synthetic config; do not modify')
            for name in ('.git', '.git/config', '.GIT/CONFIG', 'nested/.git/hooks/post-checkout',
                         '.git./config', '.git /config'):
                with self.subTest(path=name), self.assertRaises(CodeSecurityError):
                    resolve_scoped_project_path(root, name)
            for selected_root in (root / '.git', root / '.GIT' / 'hooks'):
                with self.subTest(root=str(selected_root)), self.assertRaises(CodeSecurityError):
                    resolve_scoped_project_path(selected_root, 'config')
            self.assertEqual(config.read_bytes(), b'synthetic config; do not modify')
            self.assertEqual(resolve_scoped_project_path(root, '.github/workflows/check.yml'),
                             (root / '.github/workflows/check.yml').resolve())

    def test_project_registration_cannot_retarget_or_erase_saved_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); first=root/'first'; second=root/'second'; first.mkdir(); second.mkdir()
            (first/'sample.py').write_bytes(b'VALUE = 1\n')
            service=CodeProjectService(root/'state.db'); self.addCleanup(service.close)
            service.register_project('stable',first)
            original=service.read_document('stable','sample.py')
            service.save_document('stable','sample.py','VALUE = 2\n',expected_sha256=original['sha256'])
            service.register_project('stable',first)
            with service._connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM code_time_machine_snapshots').fetchone()[0],2)
                self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
            with self.assertRaises(CodeSecurityError):
                service.register_project('stable',second)
            self.assertEqual(service.get_project_root('stable'),first.resolve())

    def test_sec03_path_traversal_ads_secrets_and_junctions_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'proj'
            outside = Path(tmp) / 'outside'
            root.mkdir()
            outside.mkdir()
            (root / 'src').mkdir()
            (root / 'src' / 'app.py').write_text('print("ok")\n', encoding='utf-8')
            (outside / 'secret.txt').write_text('top-secret', encoding='utf-8')

            # Valid path resolves inside root
            resolved = resolve_scoped_project_path(root, 'src/app.py')
            self.assertEqual(resolved, (root / 'src' / 'app.py').resolve())

            # Traversal blocked
            with self.assertRaises(CodeSecurityError):
                resolve_scoped_project_path(root, '../outside/secret.txt')
            with self.assertRaises(CodeSecurityError):
                resolve_scoped_project_path(root, 'src/../../outside/secret.txt')

            # Windows ADS / colon / absolute / UNC blocked
            with self.assertRaises(CodeSecurityError):
                resolve_scoped_project_path(root, 'src/app.py:hidden_stream')
            with self.assertRaises(CodeSecurityError):
                resolve_scoped_project_path(root, '\\\\server\\share\\file.py')

            # Secret files blocked
            (root / '.env').write_text('API_KEY=123', encoding='utf-8')
            with self.assertRaises(CodeSecurityError):
                resolve_scoped_project_path(root, '.env')

            # Windows directory junction (mklink /J) escaping root is blocked as a reparse point
            junction_path = root / 'escape_junction'
            proc = subprocess.run(
                ['cmd', '/c', 'mklink', '/J', str(junction_path), str(outside)],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0 and junction_path.exists():
                with self.assertRaises(CodeSecurityError):
                    resolve_scoped_project_path(root, 'escape_junction/secret.txt')

    def test_code01_encoding_eol_preservation_binary_large_file_and_cas_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 1. CRLF + UTF-8 with BOM file
            crlf_bom_bytes = b'\xef\xbb\xbfdef hello():\r\n    return 1\r\n'
            (root / 'win_module.py').write_bytes(crlf_bom_bytes)
            orig_sha = hashlib.sha256(crlf_bom_bytes).hexdigest()

            # 2. Binary file
            (root / 'image.bin').write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')

            # 3. Large file (> max_editable_bytes)
            (root / 'huge.log').write_text('A' * 2048, encoding='utf-8')

            svc = CodeProjectService(':memory:', max_editable_bytes=512)
            self.addCleanup(svc.close)
            svc.register_project('p1', root)

            # Binary file rejected
            with self.assertRaises(BinaryFileError):
                svc.read_document('p1', 'image.bin')

            # Large file opens in read-only degraded mode
            huge_doc = svc.read_document('p1', 'huge.log')
            self.assertTrue(huge_doc['read_only_degraded'])
            self.assertTrue(huge_doc['truncated'])
            self.assertEqual(len(huge_doc['content']), 512)

            # Read CRLF + UTF-8-SIG file
            doc = svc.read_document('p1', 'win_module.py')
            self.assertEqual(doc['encoding'], 'utf-8-sig')
            self.assertEqual(doc['line_ending'], 'CRLF')
            self.assertEqual(doc['sha256'], orig_sha)

            # Save preserving BOM + CRLF
            saved = svc.save_document(
                'p1',
                'win_module.py',
                'def hello():\n    return 2\n',
                expected_sha256=orig_sha,
            )
            on_disk = (root / 'win_module.py').read_bytes()
            self.assertEqual(on_disk, b'\xef\xbb\xbfdef hello():\r\n    return 2\r\n')
            self.assertEqual(saved['new_sha256'], hashlib.sha256(on_disk).hexdigest())

            # Stale expected_sha256 raises CodeConflictError without corrupting disk
            with self.assertRaises(CodeConflictError):
                svc.save_document(
                    'p1',
                    'win_module.py',
                    'def hello():\n    return 999\n',
                    expected_sha256=orig_sha,
                )
            self.assertEqual((root / 'win_module.py').read_bytes(), on_disk)

    def test_code03_changeset_apply_test_receipt_and_atomic_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f1 = root / 'calc.py'
            f2 = root / 'helper.py'
            f1_initial = b'def add(a, b):\n    return a + b\n'
            f2_initial = b'VERSION = "1.0"\r\n'
            f1.write_bytes(f1_initial)
            f2.write_bytes(f2_initial)
            f1_base_sha = hashlib.sha256(f1_initial).hexdigest()
            f2_base_sha = hashlib.sha256(f2_initial).hexdigest()

            svc = CodeProjectService(':memory:')
            self.addCleanup(svc.close)
            svc.register_project('proj-calc', root)
            engine = CodePatchEngine(svc)
            runner = SupervisedTestRunner(svc)

            # Propose multi-file CodeChangeSet
            cs = engine.propose_changeset(
                changeset_id='cs-100',
                project_id='proj-calc',
                workspace_id='wt-main',
                agent_id='axx-coder',
                base_commit='508bceabc718905db9bcf4042992d91f4c6c0705',
                branch='axx/agent/axx-coder/calc',
                file_edits=[
                    {'path': 'calc.py', 'new_content': 'def add(a, b):\n    return int(a) + int(b)\n'},
                    {'path': 'helper.py', 'new_content': 'VERSION = "1.1"\n'},
                ],
            )
            validate_code_changeset(cs)
            self.assertEqual(cs['status'], 'proposed')

            # Apply atomically
            applied = engine.apply_changeset('cs-100')
            self.assertEqual(applied['status'], 'applied')
            self.assertIn(b'int(a) + int(b)', f1.read_bytes())
            # helper.py preserved CRLF line endings
            self.assertEqual(f2.read_bytes(), b'VERSION = "1.1"\r\n')

            # SupervisedTestRunner blocks inline python -c and unauthorized tools
            with self.assertRaises(UnauthorizedToolchainError):
                runner.run_test_command(
                    report_id='rep-bad',
                    project_id='proj-calc',
                    workspace_id='wt-main',
                    command=[sys.executable, '-c', 'print(1)'],
                )

            # Run a real test script file and verify cryptographic receipt
            (root / 'test_calc.py').write_text(
                'import unittest, calc\n'
                'class T(unittest.TestCase):\n'
                '    def test_add(self):\n'
                '        self.assertEqual(calc.add("2", 3), 5)\n'
                'if __name__ == "__main__":\n'
                '    unittest.main()\n',
                encoding='utf-8',
            )
            receipt = runner.run_test_command(
                report_id='rep-100',
                project_id='proj-calc',
                workspace_id='wt-main',
                command=[sys.executable, 'test_calc.py'],
            )
            self.assertTrue(receipt['passed'])
            self.assertEqual(receipt['exit_code'], 0)
            self.assertEqual(len(receipt['stdout_hash']), 64)

            # Atomic rollback restores exact original bytes and hashes for both files
            rolled = engine.rollback_changeset('cs-100')
            self.assertEqual(rolled['status'], 'rolled_back')
            self.assertEqual(hashlib.sha256(f1.read_bytes()).hexdigest(), f1_base_sha)
            self.assertEqual(hashlib.sha256(f2.read_bytes()).hexdigest(), f2_base_sha)

    def test_code02_isolated_git_worktrees_and_dirty_file_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            wt_dir = Path(tmp) / 'worktrees'
            repo.mkdir()

            subprocess.run(['git', 'init'], cwd=str(repo), check=True, capture_output=True, env=os.environ.copy())
            subprocess.run(['git', 'config', 'user.email', 'owner@example.com'], cwd=str(repo), check=True, env=os.environ.copy())
            subprocess.run(['git', 'config', 'user.name', 'Owner'], cwd=str(repo), check=True, env=os.environ.copy())

            (repo / 'a.py').write_text('A = 1\n', encoding='utf-8')
            (repo / 'b.py').write_text('B = 1\n', encoding='utf-8')
            subprocess.run(['git', 'add', 'a.py', 'b.py'], cwd=str(repo), check=True, env=os.environ.copy())
            subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=str(repo), check=True, capture_output=True, env=os.environ.copy())

            svc = CodeProjectService(':memory:')
            self.addCleanup(svc.close)
            svc.register_project('repo-1', repo)
            engine = CodePatchEngine(svc)
            git_ws = GitWorkspaceService(svc, engine, worktrees_base_dir=wt_dir)

            # Create two concurrent isolated agent worktrees
            wt_a = git_ws.create_agent_worktree(
                workspace_id='wt-agent-a',
                project_id='repo-1',
                agent_id='agent-a',
                task_slug='edit-a',
            )
            wt_b = git_ws.create_agent_worktree(
                workspace_id='wt-agent-b',
                project_id='repo-1',
                agent_id='agent-b',
                task_slug='edit-b',
            )
            self.assertEqual(wt_a['branch_name'], 'axx/agent/agent-a/edit-a')
            self.assertEqual(wt_b['branch_name'], 'axx/agent/agent-b/edit-b')

            # Both agents edit inside their isolated worktrees; primary repo remains untouched
            git_ws.propose_and_apply_in_worktree(
                changeset_id='cs-a',
                workspace_id='wt-agent-a',
                file_edits=[{'path': 'a.py', 'new_content': 'A = 2\n'}],
            )
            git_ws.propose_and_apply_in_worktree(
                changeset_id='cs-b',
                workspace_id='wt-agent-b',
                file_edits=[{'path': 'b.py', 'new_content': 'B = 2\n'}],
            )
            self.assertEqual((repo / 'a.py').read_text(encoding='utf-8'), 'A = 1\n')
            self.assertEqual((repo / 'b.py').read_text(encoding='utf-8'), 'B = 1\n')

            # User edits b.py locally in primary repo (dirty working copy)
            (repo / 'b.py').write_text('B = 999  # user dirty edit\n', encoding='utf-8')

            # Integrating cs-a succeeds because a.py is clean
            integrated_a = git_ws.integrate_into_primary_workspace('cs-a')
            self.assertEqual(integrated_a['status'], 'integrated')
            self.assertEqual((repo / 'a.py').read_text(encoding='utf-8'), 'A = 2\n')

            # Integrating cs-b is blocked by DirtyWorktreeError and preserves user's dirty edit on b.py
            with self.assertRaises(DirtyWorktreeError):
                git_ws.integrate_into_primary_workspace('cs-b')
            self.assertEqual((repo / 'b.py').read_text(encoding='utf-8'), 'B = 999  # user dirty edit\n')

            with self.assertRaises(DirtyWorktreeError):
                git_ws.remove_agent_worktree('wt-agent-a')
            self.assertEqual((Path(wt_a['worktree_path']) / 'a.py').read_text(), 'A = 2\n')
            with self.assertRaises(FileExistsError):
                git_ws.create_agent_worktree(workspace_id='wt-agent-a', project_id='repo-1',
                                             agent_id='agent-a', task_slug='edit-a')
            self.assertEqual((Path(wt_a['worktree_path']) / 'a.py').read_text(), 'A = 2\n')
            # Commit fixture edits before testing non-destructive removal.
            for wt in (wt_a, wt_b):
                subprocess.run(['git', '-C', wt['worktree_path'], 'add', '.'], check=True, capture_output=True, env=os.environ.copy())
                subprocess.run(['git', '-C', wt['worktree_path'], 'commit', '-m', 'Fixture edit'], check=True, capture_output=True, env=os.environ.copy())
                git_ws.remove_agent_worktree(wt['workspace_id'])


if __name__ == '__main__':
    unittest.main()
