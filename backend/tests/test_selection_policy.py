"""Human selection corrections narrow reuse without granting command authority."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.memory import selection_policy, task_memory


class SelectionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'policy.db'
        self.db = sqlite3.connect(self.path)
        self.db.execute('CREATE TABLE skill_versions(id TEXT,version INTEGER,payload TEXT,PRIMARY KEY(id,version))')
        selection_policy.ensure(self.db)
        self.skill = {'id': 'skill.a', 'version': 1, 'project_id': '', 'templates': [{'command_id': 'requires-approval'}]}
        with self.db:
            self.db.execute('INSERT INTO skill_versions VALUES (?,?,?)', (self.skill['id'], 1, json.dumps(self.skill)))
        self.a, self.b = (task_memory.snapshot(self.db, name) for name in ('a', 'b'))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def apply(self, action, *, project='p', folder=None, scope=None, operation=None, revision=None, skill=None):
        selected = skill or self.skill
        if revision is None: revision = selection_policy.read(self.db, selected['id'])['revision']
        if operation is None: operation = selected['id'] + '-' + action + '-' + str(revision)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = selection_policy.apply(self.db, selected, action, project, folder,
                scope or self.a, operation, revision)
            self.assertTrue(self.db.in_transaction)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def test_default_and_project_restriction_only_narrow_scope(self):
        default = selection_policy.read(self.db, self.skill['id'])
        self.assertEqual(default, {'revision': 0, 'retired': False, 'folder_preferences': []})
        rule = self.apply('restrict_project')
        self.assertEqual(rule['project_id'], 'p')
        self.assertTrue(selection_policy.allowed(self.skill, rule, 'p'))
        self.assertFalse(selection_policy.allowed(self.skill, rule, 'other', automatic=False))
        with self.assertRaises(ValueError): self.apply('restrict_project', project='other')
        with self.assertRaises(ValueError): self.apply('restrict_project', project='')
        with self.assertRaises(ValueError): self.apply('restrict_project', folder='extra')
        scoped = self.skill | {'id': 'skill.scoped', 'project_id': 'other'}
        with self.db:
            self.db.execute('INSERT INTO skill_versions VALUES (?,?,?)', (scoped['id'], 1, json.dumps(scoped)))
        with self.assertRaises(ValueError): self.apply('restrict_project', project='p', skill=scoped)

    def test_retirement_blocks_automatic_selection_but_allows_explicit_review(self):
        rule = self.apply('retire_procedure')
        self.assertTrue(rule['retired'])
        self.assertFalse(selection_policy.allowed(self.skill, rule, 'p'))
        self.assertFalse(selection_policy.allowed(self.skill, rule, 'p', automatic=0))
        self.assertTrue(selection_policy.allowed(self.skill, rule, 'p', automatic=False))
        self.assertEqual(self.skill['templates'], [{'command_id': 'requires-approval'}])
        self.assertNotIn('grants', rule)
        self.assertTrue(self.apply('prefer_folder', folder='C:\\work')['retired'])

    def test_folder_preference_is_exact_pair_without_descendant_or_scope_expansion(self):
        rule = self.apply('prefer_folder', folder='C:\\work')
        self.assertTrue(selection_policy.preferred(rule, 'p', 'C:\\work'))
        self.assertFalse(selection_policy.preferred(rule, 'other', 'C:\\work'))
        self.assertFalse(selection_policy.preferred(rule, 'p', 'C:\\work\\child'))
        self.assertTrue(selection_policy.allowed(self.skill, rule, 'other', 'C:\\work\\child'))
        self.assertEqual(rule['folder_preferences'], [{'project_id': 'p', 'folder': 'C:\\work'}])
        with self.assertRaises(ValueError): self.apply('prefer_folder')

    def test_replay_revision_version_validation_and_minimal_history(self):
        first = self.apply('restrict_project', operation='same-op', revision=0)
        replay = self.apply('restrict_project', operation='same-op', revision=0)
        self.assertEqual(replay, first)
        with self.assertRaises(ValueError): self.apply('retire_procedure', operation='same-op', revision=0)
        with self.assertRaises(ValueError): self.apply('retire_procedure', revision=0)
        with self.db:
            self.db.execute('INSERT INTO skill_versions VALUES (?,?,?)', (self.skill['id'], 2, json.dumps(self.skill | {'version': 2})))
        with self.assertRaises(ValueError): self.apply('retire_procedure')
        with self.assertRaises(ValueError): selection_policy.apply(self.db, self.skill, 'retire_procedure', 'p', None, self.a, 'outside-txn', 1)
        with self.assertRaises(ValueError): self.apply('unknown-action')
        history = ' '.join(str(row) for row in self.db.execute('SELECT * FROM skill_selection_operations'))
        self.assertNotIn('templates', history)
        self.assertNotIn('requires-approval', history)

    def test_forgotten_origin_hides_folder_and_never_reactivates_b_policy_is_preserved(self):
        rule_a = self.apply('prefer_folder', folder='C:\\PRIVATE_A')
        skill_b = self.skill | {'id': 'skill.b'}
        with self.db:
            self.db.execute('INSERT INTO skill_versions VALUES (?,?,?)', (skill_b['id'], 1, json.dumps(skill_b)))
        rule_b = self.apply('prefer_folder', folder='C:\\B', scope=self.b, skill=skill_b)
        self.db.execute('BEGIN IMMEDIATE')
        pending = task_memory.begin_forget(self.db, 'a', 'forget-a', 0)
        self.db.commit()
        blocked = selection_policy.read(self.db, self.skill['id'])
        self.assertTrue(blocked['retired'])
        self.assertTrue(blocked['requires_review'])
        self.assertEqual(blocked['folder_preferences'], [])
        self.assertNotIn('PRIVATE_A', json.dumps(blocked))
        self.assertEqual(selection_policy.read(self.db, skill_b['id']), rule_b)
        self.db.execute('BEGIN IMMEDIATE')
        task_memory.finish_forget(self.db, pending, {})
        self.db.commit()
        self.assertEqual(selection_policy.read(self.db, self.skill['id']), blocked)
        self.apply('prefer_folder', folder='C:\\new', scope=self.b, revision=rule_a['revision'])
        self.assertTrue(selection_policy.read(self.db, self.skill['id'])['retired'])
        self.assertFalse(selection_policy.preferred(selection_policy.read(self.db, self.skill['id']), 'p', 'C:\\new'))


if __name__ == '__main__':
    unittest.main()
