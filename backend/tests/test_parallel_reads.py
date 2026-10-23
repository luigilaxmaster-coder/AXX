from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.actions.executor import ActionExecutor
from backend.actions.tools import get_tool
from backend.commands import CommandService


class ParallelReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.addCleanup(lambda: self.executor.close())
        self.addCleanup(lambda: self.commands.close())
        self.paths = []
        for index in range(3):
            path = self.root / f'file-{index}.txt'
            path.write_text(str(index), encoding='utf-8')
            self.paths.append(str(path))

    def prepare(self, index):
        return self.commands.prepare('axx.file.sha256', {'path': self.paths[index]}, operation_id=f'read-{index}')['operation_id']

    def test_two_reads_overlap_and_persist_independent_receipts(self):
        operations = [self.prepare(i) for i in range(2)]
        tool = get_tool('file_inspection')
        original = tool.execute_cancellable
        barrier = threading.Barrier(2)
        def overlap(*args):
            barrier.wait(3)
            return original(*args)
        with patch.object(tool, 'execute_cancellable', side_effect=overlap), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.commands.execute, op, True, allow_parallel_read=True) for op in operations]
            results = [future.result(5) for future in futures]
        self.assertEqual([r['state'] for r in results], ['succeeded', 'succeeded'])
        self.assertEqual(len(self.executor.list_operations()), 2)
        self.assertNotEqual(results[0]['evidence']['files'][0]['sha256'], results[1]['evidence']['files'][0]['sha256'])

    def test_duplicate_dispatch_and_effects_are_blocked_while_read_is_active(self):
        operation = self.prepare(0)
        write = self.commands.prepare('axx.artifact.write', {'path': 'effect.txt', 'content': 'effect'})['operation_id']
        entered, release = threading.Event(), threading.Event()
        tool = get_tool('file_inspection'); original = tool.execute_cancellable
        def blocked(*args):
            entered.set()
            if not release.wait(3): raise RuntimeError('test release timeout')
            return original(*args)
        with patch.object(tool, 'execute_cancellable', side_effect=blocked), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.commands.execute, operation, True, allow_parallel_read=True)
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaisesRegex(ValueError, 'BUSY'):
                    self.commands.execute(operation, True, allow_parallel_read=True)
                with self.assertRaisesRegex(ValueError, 'BUSY'):
                    self.commands.execute(write, True)
                self.assertFalse((self.executor.workspace_root / 'effect.txt').exists())
            finally:
                release.set()
            self.assertEqual(future.result(5)['state'], 'succeeded')
        self.assertEqual(len(self.executor.list_operations()), 1)
        self.assertTrue(self.commands.execute(operation, True, allow_parallel_read=True)['replayed'])

    def test_third_read_is_rejected_without_reserving_an_executor_operation(self):
        operations = [self.prepare(i) for i in range(3)]
        entered, release = threading.Barrier(3), threading.Event()
        tool = get_tool('file_inspection'); original = tool.execute_cancellable
        def blocked(*args):
            entered.wait(3)
            if not release.wait(3): raise RuntimeError('test release timeout')
            return original(*args)
        with patch.object(tool, 'execute_cancellable', side_effect=blocked), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.commands.execute, op, True, allow_parallel_read=True) for op in operations[:2]]
            try:
                entered.wait(3)
                with self.assertRaisesRegex(ValueError, 'BUSY'):
                    self.commands.execute(operations[2], True, allow_parallel_read=True)
                self.assertEqual(self.commands.get(operations[2])['state'], 'awaiting_approval')
                self.assertEqual(len(self.executor.list_operations()), 2)
            finally:
                release.set()
            self.assertTrue(all(f.result(5)['state'] == 'succeeded' for f in futures))

    def test_cancel_effect_waiting_on_legacy_parallel_read_prevents_dispatch(self):
        operation = self.commands.prepare('axx.artifact.write', {'path': 'cancelled.txt', 'content': 'effect'})['operation_id']
        entered, waiting, release = threading.Event(), threading.Event(), threading.Event()
        tool = get_tool('file_inspection'); original = tool.execute_cancellable
        original_wait = self.executor.wait_for_reads
        def blocked(*args):
            entered.set()
            if not release.wait(3): raise RuntimeError('test release timeout')
            return original(*args)
        def observe_wait():
            waiting.set()
            return original_wait()
        with patch.object(tool, 'execute_cancellable', side_effect=blocked), patch.object(self.executor, 'wait_for_reads', side_effect=observe_wait), ThreadPoolExecutor(max_workers=2) as pool:
            read = pool.submit(self.executor.execute_action, 'file_inspection', {'path': self.paths[0]}, 'legacy-read', allow_parallel_read=True)
            try:
                self.assertTrue(entered.wait(2))
                effect = pool.submit(self.commands.execute, operation, True)
                self.assertTrue(waiting.wait(2))
                self.commands.cancel(operation)
            finally:
                release.set()
            self.assertEqual(read.result(5)['state'], 'succeeded')
            self.assertEqual(effect.result(5)['state'], 'cancelled')
        self.assertFalse((self.executor.workspace_root / 'cancelled.txt').exists())
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_parallel_flag_never_authorizes_writes_shell_or_gui_effects(self):
        write = self.commands.prepare('axx.artifact.write', {'path': 'effect.txt', 'content': 'effect'})['operation_id']
        with self.assertRaises(ValueError):
            self.commands.execute(write, True, allow_parallel_read=True)
        with self.assertRaises(ValueError):
            self.executor.execute_action('file_artifact_writer', {'path': 'effect.txt', 'content': 'effect'}, allow_parallel_read=True)
        self.assertFalse((self.executor.workspace_root / 'effect.txt').exists())

    def test_cancel_one_read_does_not_cancel_other_branch(self):
        operations = [self.prepare(i) for i in range(2)]
        entered = threading.Event()
        tool = get_tool('file_inspection'); original = tool.execute_cancellable
        def cancellable(inputs, workspace, cancelled):
            if inputs['path'] == self.paths[0]:
                entered.set()
                if not cancelled.wait(3): raise RuntimeError('cancellation timeout')
            return original(inputs, workspace, cancelled)
        with patch.object(tool, 'execute_cancellable', side_effect=cancellable), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.commands.execute, operations[0], True, allow_parallel_read=True)
            self.assertTrue(entered.wait(2))
            second = pool.submit(self.commands.execute, operations[1], True, allow_parallel_read=True)
            self.commands.cancel(operations[0])
            self.assertEqual(first.result(5)['state'], 'cancelled')
            self.assertEqual(second.result(5)['state'], 'succeeded')

    def test_default_executor_effect_waits_for_read_body_and_receipt(self):
        entered, release = threading.Event(), threading.Event()
        tool = get_tool('file_inspection'); original = tool.execute_cancellable
        def blocked(*args):
            entered.set()
            if not release.wait(3): raise RuntimeError('test release timeout')
            return original(*args)
        with patch.object(tool, 'execute_cancellable', side_effect=blocked), ThreadPoolExecutor(max_workers=2) as pool:
            read = pool.submit(self.executor.execute_action, 'file_inspection', {'path': self.paths[0]}, 'read', allow_parallel_read=True)
            try:
                self.assertTrue(entered.wait(2))
                effect = pool.submit(self.executor.execute_action, 'file_artifact_writer', {'path': 'effect.txt', 'content': 'effect'}, 'write')
                self.assertFalse(effect.done())
                self.assertFalse((self.executor.workspace_root / 'effect.txt').exists())
            finally:
                release.set()
            self.assertEqual(read.result(5)['state'], 'succeeded')
            self.assertEqual(effect.result(5)['state'], 'succeeded')

    def test_completed_parallel_read_replays_after_restart_without_duplicate_dispatch(self):
        operation = self.prepare(0)
        result = self.commands.execute(operation, True, allow_parallel_read=True)
        self.assertEqual(result['state'], 'succeeded')
        self.commands.close(); self.executor.close()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        with patch.object(get_tool('file_inspection'), 'execute_cancellable', side_effect=AssertionError('must not run')):
            replay = self.commands.execute(operation, True, allow_parallel_read=True)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['evidence'], result['evidence'])
        self.assertEqual(len(self.executor.list_operations()), 1)

    def test_expired_preparation_renews_same_identity_and_still_requires_approval(self):
        operation = self.commands.prepare('axx.artifact.write', {'path': 'renewed.txt', 'content': 'same inputs'})['operation_id']
        with self.commands.db:
            self.commands.db.execute('UPDATE command_runs SET expires_at=0 WHERE operation_id=?', (operation,))
        self.assertEqual(self.commands.execute(operation, True)['state'], 'expired')
        renewed = self.commands.renew(operation)
        self.assertEqual(renewed['operation_id'], operation)
        self.assertEqual(renewed['state'], 'awaiting_approval')
        self.assertFalse((self.executor.workspace_root / 'renewed.txt').exists())
        with self.assertRaises(ValueError):
            self.commands.execute(operation)
        self.assertEqual(self.commands.execute(operation, True)['state'], 'succeeded')

    def test_renewal_never_revives_cancelled_operation_or_repeats_existing_effect(self):
        cancelled = self.prepare(0)
        self.commands.cancel(cancelled)
        self.assertEqual(self.commands.renew(cancelled)['state'], 'cancelled')
        operation = self.commands.prepare('axx.artifact.write', {'path': 'already.txt', 'content': 'once'})['operation_id']
        action_id = 'cmd-' + hashlib.sha256(operation.encode()).hexdigest()
        self.executor.execute_action('file_artifact_writer', {'path': 'already.txt', 'content': 'once'}, action_id)
        with self.assertRaises(ValueError):
            self.commands.renew(operation)
        self.assertEqual(len(self.executor.list_operations()), 1)


if __name__ == '__main__':
    unittest.main()
