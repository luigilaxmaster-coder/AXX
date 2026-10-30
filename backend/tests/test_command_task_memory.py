"""Command receipts retain their admitted task epoch without widening execution authority."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.commands import ApprovalRequired, CommandService
from backend.memory import task_memory


class CommandTaskMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.db = sqlite3.connect(self.root / 'state.db')
        task_memory.ensure(self.db)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.commands.close()
        self.executor.close()
        self.temp.cleanup()

    def forget(self, finish=True):
        self.db.execute('BEGIN IMMEDIATE')
        ref = task_memory.begin_forget(self.db, 'a', 'forget-a', 0)
        self.db.commit()
        if finish:
            self.db.execute('BEGIN IMMEDIATE')
            task_memory.finish_forget(self.db, ref, {})
            self.db.commit()
        return ref

    def test_legacy_generation_zero_is_tagged_manual_has_no_scope_and_replay_is_fixed(self):
        first = self.commands.prepare('axx.system.telemetry', {}, operation_id='first', conversation_id='a')
        self.assertEqual(first['memory_scope'], {'task_id': 'a', 'generation': 0})
        self.assertNotIn('memory_scope', self.commands.prepare('axx.system.telemetry', {}))
        self.forget()
        replay = self.commands.prepare('axx.system.telemetry', {}, operation_id='first', conversation_id='a')
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['memory_scope'], first['memory_scope'])
        self.assertEqual(self.commands.get('first')['memory_scope'], first['memory_scope'])

    def test_missing_or_old_reference_rejected_new_reference_admitted_and_b_unchanged(self):
        old = task_memory.snapshot(self.db, 'a')
        self.forget()
        for scope in (None, old, {'task_id': 'b', 'generation': 0}):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.commands.prepare('axx.system.telemetry', {}, conversation_id='a', memory_scope=scope)
        current = task_memory.snapshot(self.db, 'a')
        prepared = self.commands.prepare('axx.system.telemetry', {}, conversation_id='a', memory_scope=current)
        self.assertEqual(prepared['memory_scope'], current)
        self.assertEqual(prepared['inputs'], {})
        b = self.commands.prepare('axx.system.telemetry', {}, conversation_id='b')
        self.assertEqual(b['memory_scope'], {'task_id': 'b', 'generation': 0})

    def test_prepared_before_forgetting_is_rejected_before_executor_and_remains_a_receipt(self):
        command = self.commands.prepare('axx.system.telemetry', {}, conversation_id='a')
        self.forget(finish=False)
        with patch.object(self.executor, 'execute_action') as dispatch:
            result = self.commands.execute(command['operation_id'])
            dispatch.assert_not_called()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')
        self.assertEqual(result['memory_scope'], command['memory_scope'])
        self.assertEqual(self.executor.list_operations(), [])

    def test_scope_does_not_bypass_approval_and_prepare_adopts_caller_transaction(self):
        file = self.executor.workspace_root / 'test.txt'
        file.write_text('scope test', encoding='utf-8')
        scope = task_memory.snapshot(self.db, 'a')
        self.commands.db.execute('BEGIN IMMEDIATE')
        command = self.commands.prepare('axx.file.sha256', {'path': str(file)}, conversation_id='a', memory_scope=scope)
        self.assertTrue(self.commands.db.in_transaction)
        self.assertIsNone(self.db.execute('SELECT 1 FROM command_runs WHERE operation_id=?', (command['operation_id'],)).fetchone())
        self.commands.db.commit()
        self.assertTrue(command['requires_approval'])
        with self.assertRaises(ApprovalRequired): self.commands.execute(command['operation_id'])
        result = self.commands.execute(command['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded')
        self.assertEqual(result['memory_scope'], scope)

    def test_forget_during_dispatch_callback_is_rechecked_before_executor(self):
        command = self.commands.prepare('axx.system.telemetry', {}, conversation_id='a')
        self.commands.dispatch_guard = lambda operation: self.forget(finish=False)
        with patch.object(self.executor, 'execute_action') as dispatch:
            result = self.commands.execute(command['operation_id'])
            dispatch.assert_not_called()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')

    def test_same_generation_rotated_chat_context_rejects_prepared_command(self):
        self.db.execute('CREATE TABLE chat_conversations(id TEXT PRIMARY KEY,connect_id TEXT,memory_context_required INTEGER)')
        with self.db:
            self.db.execute('INSERT INTO chat_conversations VALUES (?,?,0)', ('b', 'old-context'))
        ref = task_memory.snapshot(self.db, 'b')
        old = self.commands.prepare('axx.system.telemetry', {}, conversation_id='b', memory_scope=ref,
                                    memory_context_id='old-context')
        with self.db:
            self.db.execute('UPDATE chat_conversations SET connect_id=?,memory_context_required=1 WHERE id=?', ('new-context', 'b'))
        with patch.object(self.executor, 'execute_action') as dispatch:
            result = self.commands.execute(old['operation_id'])
            dispatch.assert_not_called()
        self.assertEqual(result['error']['code'], 'DISPATCH_REJECTED')
        with self.assertRaises(ValueError): self.commands.prepare('axx.system.telemetry', {}, conversation_id='b', memory_scope=ref)
        current = self.commands.prepare('axx.system.telemetry', {}, conversation_id='b', memory_scope=ref,
                                        memory_context_id='new-context')
        self.assertEqual(current['memory_scope'], ref)
        self.assertEqual(current['memory_context_id'], 'new-context')


if __name__ == '__main__':
    unittest.main()
