import unittest
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.check_author_policy import OWNER_EMAIL, OWNER_NAME, commit_range, main, validate_log


def record(message: str, author_email: str = OWNER_EMAIL, committer_email: str = OWNER_EMAIL,
           author_name: str = "luigilaxmaster-coder", committer_name: str = "luigilaxmaster-coder") -> str:
    return f"abc123\x1f{author_name}\x1f{author_email}\x1f{committer_name}\x1f{committer_email}\x1f{message}\x1e"


class AuthorPolicyTests(unittest.TestCase):
    def test_accepts_owner_commit_without_coauthor(self):
        self.assertEqual(validate_log(record("Fix issue\n")), [])

    def test_rejects_any_coauthor_trailer(self):
        self.assertTrue(validate_log(record("Fix issue\n\nCo-authored-by: helper <bot@example.com>")))

    def test_rejects_non_owner_author_or_committer(self):
        self.assertTrue(validate_log(record("Fix issue", author_email="bot@example.com")))
        self.assertTrue(validate_log(record("Fix issue", committer_email="bot@example.com")))

    def test_rejects_mismatched_author_name(self):
        self.assertTrue(validate_log(record("Fix issue", author_name="Another Name")))

    def test_rejects_empty_range(self):
        self.assertTrue(validate_log(""))

    def test_push_and_pr_ranges_against_real_git_history(self):
        with tempfile.TemporaryDirectory() as temp:
            def git(*args):
                return subprocess.run(['git', '-C', temp, *args], check=True, capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('config', 'user.name', OWNER_NAME)
            git('config', 'user.email', OWNER_EMAIL)
            git('commit', '--allow-empty', '-qm', 'Base')
            base = git('rev-parse', 'HEAD')
            git('update-ref', 'refs/remotes/origin/main', base)
            # A new branch at the default tip (including a root commit) validates just that tip.
            previous = Path.cwd()
            try:
                os.chdir(temp)
                self.assertEqual(commit_range('0' * 40, 'HEAD', 'origin/main'), ['HEAD', '--max-count=1'])
                self.assertEqual(main('0' * 40, 'HEAD', 'origin/main'), 0)
                git('commit', '--allow-empty', '-qm', 'Feature')
                self.assertEqual(commit_range('0' * 40, 'HEAD', 'origin/main'), [f'{base}..HEAD'])
                self.assertEqual(main('0' * 40, 'HEAD', 'origin/main'), 0)
                self.assertEqual(main(base, 'HEAD'), 0)
                with patch('sys.stderr'):
                    self.assertEqual(main('not-a-commit', 'HEAD', 'origin/main'), 2)
                    self.assertEqual(main('0' * 40, 'HEAD'), 2)
                git('commit', '--allow-empty', '-qm', 'Feature\n\nCo-authored-by: helper <bot@example.com>')
                with patch('sys.stderr'):
                    self.assertEqual(main('0' * 40, 'HEAD', 'origin/main'), 1)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
