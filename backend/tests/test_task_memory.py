"""Durable task epochs fence late publications across connections and reopenings."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from backend.memory import task_memory


class TaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'memory.db'
        self.db = sqlite3.connect(self.path)
        task_memory.ensure(self.db)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def forget(self, task='a', operation='forget-a', generation=0):
        self.db.execute('BEGIN IMMEDIATE')
        pending = task_memory.begin_forget(self.db, task, operation, generation)
        self.db.commit()
        return pending

    def test_pending_epoch_is_durable_and_idempotent_and_preserves_b(self):
        old = task_memory.snapshot(self.db, 'a')
        other = task_memory.snapshot(self.db, 'b')
        pending = self.forget()
        self.assertEqual(pending['generation'], 1)
        with closing(sqlite3.connect(self.path)) as second:
            self.assertEqual(task_memory.state(second, 'a'), pending)
            for reference in (old, None):
                with self.assertRaises(ValueError): task_memory.assert_current(second, reference, task_id='a')
            with self.assertRaises(ValueError): task_memory.snapshot(second, 'a')
            self.assertEqual(task_memory.assert_current(second, other), other)
        self.db.execute('BEGIN IMMEDIATE')
        self.assertEqual(task_memory.begin_forget(self.db, 'a', 'forget-a', 0), pending)
        task_memory.finish_forget(self.db, pending, {'forgotten': True})
        self.db.commit()
        current = task_memory.snapshot(self.db, 'a')
        self.assertEqual(current['generation'], 1)
        self.db.execute('BEGIN IMMEDIATE')
        again = task_memory.begin_forget(self.db, 'a', 'forget-a', 0)
        self.db.commit()
        self.assertEqual(again['result'], {'forgotten': True})
        self.assertFalse(again['forgetting'])
        with self.assertRaises(ValueError): task_memory.assert_current(self.db, old)
        with self.assertRaises(ValueError): task_memory.assert_current(self.db, None, task_id='a')

    def test_process_reads_pending_barrier_and_reopen_cannot_resurrect(self):
        old = task_memory.snapshot(self.db, 'a')
        self.forget()
        script = ('import json,sqlite3,sys; from backend.memory.task_memory import state; '
                  'db=sqlite3.connect(sys.argv[1]); print(json.dumps(state(db,"a")))')
        result = subprocess.run([sys.executable, '-c', script, str(self.path)], check=True, capture_output=True, text=True)
        self.assertTrue(json.loads(result.stdout)['forgetting'])
        self.db.close()
        self.db = sqlite3.connect(self.path)
        task_memory.ensure(self.db)
        with self.assertRaises(ValueError): task_memory.assert_current(self.db, old)

    def test_validation_missing_scopes_and_caller_transaction(self):
        self.assertIsNone(task_memory.assert_current(self.db, None))
        self.assertEqual(task_memory.assert_current(self.db, None, task_id='new'), {'task_id': 'new', 'generation': 0})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM memory_task_scopes').fetchone()[0], 0)
        for invalid in ('', 'a' * 161, None, 1):
            with self.subTest(task=invalid), self.assertRaises(ValueError): task_memory.state(self.db, invalid)
        with self.assertRaises(ValueError): task_memory.begin_forget(self.db, 'a', 'op', 0)
        self.db.execute('BEGIN IMMEDIATE')
        for invalid in (-1, True, 1.5):
            with self.subTest(generation=invalid), self.assertRaises(ValueError):
                task_memory.begin_forget(self.db, 'a', 'op', invalid)
        with self.assertRaises(ValueError): task_memory.begin_forget(self.db, 'a', 'op', 1)
        self.db.rollback()

    def test_context_rotation_fences_same_generation_and_legacy_is_optional(self):
        ref = task_memory.snapshot(self.db, 'b')
        self.assertEqual(task_memory.assert_context(self.db, ref, None), ref)
        self.db.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY,connect_id TEXT,memory_context_required INTEGER)')
        with self.db:
            self.db.execute('INSERT INTO chat_conversations VALUES (?,?,0)', ('b', 'old-context'))
        self.assertEqual(task_memory.assert_context(self.db, ref, 'old-context'), ref)
        self.assertEqual(task_memory.assert_context(self.db, ref, None), ref)
        with self.db:
            self.db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?', ('new-context', 'b'))
        for context in (None, 'old-context', '', 1):
            with self.subTest(context=context), self.assertRaises(ValueError):
                task_memory.assert_context(self.db, ref, context)
        self.assertEqual(task_memory.assert_context(self.db, ref, 'new-context'), ref)
        self.assertEqual(task_memory.snapshot(self.db, 'b'), ref)
        with self.db:
            self.db.execute('DROP TABLE chat_conversations')
            self.db.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY,connect_id TEXT)')
            self.db.execute('INSERT INTO chat_conversations VALUES (?,?)', ('b', 'legacy-context'))
        self.assertEqual(task_memory.assert_context(self.db, ref, None), ref)
        self.assertEqual(task_memory.assert_context(self.db, ref, 'legacy-context'), ref)


if __name__ == '__main__':
    unittest.main()
