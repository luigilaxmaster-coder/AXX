import unittest

from scripts.check_author_policy import OWNER_EMAIL, validate_log


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


if __name__ == "__main__":
    unittest.main()
