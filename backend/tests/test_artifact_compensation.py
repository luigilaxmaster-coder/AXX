"""Only synthetic files in an owned temporary directory; no UI/input/deletion."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.actions import artifact_compensation as comp
from backend.actions.executor import ActionExecutor
from backend.commands import ApprovalRequired, CommandService


class ArtifactCompensationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)

    def tearDown(self):
        self.commands.close(); self.executor.close(); self.temp.cleanup()

    def write(self, operation_id='source', path='original.txt', content='synthetic owned artifact'):
        prepared = self.commands.prepare('axx.artifact.write', {'path': path, 'content': content},
            operation_id=operation_id, conversation_id='source-task')
        result = self.commands.execute(prepared['operation_id'], approved=True)
        self.assertEqual(result['state'], 'succeeded', result)
        return result

    def eligible(self, operation_id='source'):
        preview = self.commands.compensation_preview(operation_id)
        self.assertTrue(preview['available'], preview)
        return preview

    def prepare(self, preview, operation_id):
        return self.commands.prepare_compensation(preview['source_operation_id'], preview['source_receipt_hash'],
            preview['compensation']['revision'], action=preview['action'], operation_id=operation_id)

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_real_creation_quarantine_restore_preserves_bytes_identity_and_source_receipt(self):
        source = self.write()
        source_row = self.commands.db.execute("SELECT result_json FROM command_runs WHERE operation_id='source'").fetchone()[0]
        original = self.executor.workspace_root / 'original.txt'
        preview = self.eligible()
        creation = source['evidence']['creation_receipt']
        self.assertTrue(creation['verified'])
        self.assertEqual(creation['birth_identity'], comp._birth(creation['identity']))
        prepared = self.prepare(preview, 'apart')
        self.assertEqual(prepared['state'], 'awaiting_approval')
        self.assertEqual(prepared['source_operation_id'], 'source')
        self.assertEqual(prepared['delivery_mode'], 'background')
        with self.assertRaises(ApprovalRequired):
            self.commands.execute('apart')
        moved = self.commands.execute('apart', approved=True)
        self.assertEqual(moved['state'], 'succeeded', moved)
        self.assertFalse(original.exists())
        target = Path(moved['output']['quarantine_path'])
        self.assertEqual(target.read_text(), 'synthetic owned artifact')
        self.assertEqual(moved['output']['identity'], creation['identity'])
        self.assertFalse(self.commands.get('source')['compensation']['available_current'])
        self.assertTrue(self.commands.execute('apart', approved=True)['replayed'])
        restored_preview = self.eligible()
        self.assertEqual(restored_preview['action'], 'restore')
        self.assertEqual(restored_preview['compensation']['revision'], 1)
        self.prepare(restored_preview, 'put-back')
        restored = self.commands.execute('put-back', approved=True)
        self.assertEqual(restored['state'], 'succeeded', restored)
        self.assertEqual(original.read_text(), 'synthetic owned artifact')
        self.assertFalse(target.exists())
        self.assertEqual(self.commands.db.execute("SELECT result_json FROM command_runs WHERE operation_id='source'").fetchone()[0], source_row)

    def test_platform_unavailable_is_honest_and_historical_receipts_are_ineligible(self):
        source = self.write()
        action_id = source['action_operation_id']
        with self.executor.db:
            row = self.executor.get_operation(action_id)
            row['evidence'].pop('creation_receipt', None)
            self.executor.db.execute('UPDATE operations SET result_json=? WHERE operation_id=?', (json.dumps(row), action_id))
        self.assertFalse(self.commands.compensation_preview('source')['available'])
        with patch.object(comp, 'native_available', return_value=False):
            self.assertFalse(self.commands.compensation_preview('source')['available'])
        self.assertTrue((self.executor.workspace_root / 'original.txt').exists())

    def test_quarantine_namespace_rejects_generic_writer_before_and_at_effect(self):
        from backend.actions.tools import FileArtifactTool
        for path in ('.axx-quarantine/new.txt', 'nested/.AXX-QUARANTINE/new.txt'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.commands.prepare('axx.artifact.write', {'path': path, 'content': 'must not enter backups'})
            absolute = self.executor.workspace_root / path
            self.assertFalse(FileArtifactTool().verify_preconditions({'path': str(absolute), 'content': 'x'})[0])
            self.assertFalse(FileArtifactTool().execute({'path': str(absolute), 'content': 'x'}).success)
            self.assertFalse(absolute.exists())
            self.assertFalse(absolute.parent.exists())
        source = self.root / 'source.txt'
        source.write_text('synthetic input')
        with self.assertRaisesRegex(ValueError, 'cuarentena'):
            self.commands.prepare('axx.file.bundle', {'paths': [str(source)], 'destination': '.axx-quarantine/nested'})

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_rename_buffer_is_terminated_and_does_not_replace_existing_names(self):
        import ctypes
        self.write(); self.prepare(self.eligible(), 'terminated-buffer')
        original_kernel = comp._kernel
        calls = []
        class KernelProxy:
            def __init__(self, kernel): self.kernel = kernel
            def __getattr__(self, key): return getattr(self.kernel, key)
            def SetFileInformationByHandle(self, handle, kind, buffer, size):
                header = comp.RenameInfo.from_buffer(buffer)
                name = ctypes.string_at(ctypes.addressof(buffer) + comp.RenameInfo.name.offset, header.length)
                terminator = ctypes.string_at(ctypes.addressof(buffer) + comp.RenameInfo.name.offset + header.length, 2)
                calls.append((kind, header.flags, terminator, name.decode('utf-16-le')))
                return self.kernel.SetFileInformationByHandle(handle, kind, buffer, size)
        with patch.object(comp, '_kernel', side_effect=lambda: KernelProxy(original_kernel())):
            result = self.commands.execute('terminated-buffer', approved=True)
        self.assertEqual(result['state'], 'succeeded', result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], (3, 0, b'\0\0'))
        self.assertEqual(calls[0][3], result['output']['quarantine_path'])

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_mutation_same_bytes_replacement_and_links_never_move_foreign_files(self):
        for kind in ('modified', 'same-bytes-replacement', 'hardlink'):
            with self.subTest(kind=kind):
                operation_id = 'source-' + kind
                result = self.write(operation_id, kind + '.txt')
                preview = self.eligible(operation_id)
                prepared = self.prepare(preview, 'undo-' + kind)
                target = Path(result['output']['path'])
                if kind == 'modified':
                    target.write_text('user modified this output')
                elif kind == 'same-bytes-replacement':
                    target.rename(target.with_suffix('.saved-original'))
                    target.write_text('synthetic owned artifact')
                else:
                    os.link(target, target.with_suffix('.other-name'))
                self.assertFalse(self.commands.compensation_preview(operation_id)['available'])
                outcome = self.commands.execute(prepared['operation_id'], approved=True)
                self.assertNotEqual(outcome['state'], 'succeeded')
                self.assertTrue(target.exists())
                self.assertFalse(Path(preview['compensation']['quarantine_path']).exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_exact_receipt_conversation_and_revision_are_required(self):
        self.write()
        preview = self.eligible()
        for fields in ({'source_receipt_hash': '0'*64}, {'expected_revision': 1}):
            body = {'source_operation_id': 'source', 'source_receipt_hash': preview['source_receipt_hash'], 'expected_revision': 0} | fields
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.commands.prepare_compensation(**body)
        with self.assertRaises(ValueError):
            self.commands.prepare('axx.artifact.quarantine', {'source_operation_id': 'source',
                'source_receipt_hash': preview['source_receipt_hash'], 'expected_revision': 0}, conversation_id='another-task')
        for fields in ({'path': str(self.root)}, {'expected_revision': True}, {'source_operation_id': '../other'}):
            args = {'source_operation_id': 'source', 'source_receipt_hash': preview['source_receipt_hash'], 'expected_revision': 0} | fields
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.commands.prepare('axx.artifact.quarantine', args)

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_stale_prepare_cannot_repeat_after_quarantine_restore_cycle(self):
        self.write()
        preview = self.eligible()
        self.prepare(preview, 'stale')
        self.prepare(preview, 'first')
        self.assertEqual(self.commands.execute('first', approved=True)['state'], 'succeeded')
        self.prepare(self.eligible(), 'restore')
        self.assertEqual(self.commands.execute('restore', approved=True)['state'], 'succeeded')
        self.assertEqual(self.eligible()['compensation']['revision'], 2)
        stale = self.commands.execute('stale', approved=True)
        self.assertEqual(stale['state'], 'failed', stale)
        self.assertEqual(stale['evidence']['diagnostic_code'], 'COMPENSATION_REVISION_CHANGED')
        self.assertTrue((self.executor.workspace_root / 'original.txt').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_stale_owner_cas_cannot_overwrite_newer_restoration_proof(self):
        self.write(); self.prepare(self.eligible(), 'first')
        self.assertEqual(self.commands.execute('first', approved=True)['state'], 'succeeded')
        stale = comp.relationship(self.commands.db, 'source')
        stale_operation = stale['operation_id']
        self.prepare(self.eligible(), 'restore')
        self.assertEqual(self.commands.execute('restore', approved=True)['state'], 'succeeded')
        current = comp.relationship(self.commands.db, 'source')
        stale.update(state='present', revision=0)
        with self.assertRaisesRegex(ValueError, 'COMPENSATION_CLAIM_CHANGED'):
            with self.commands.db:
                comp._cas_save(self.commands.db, 'source', stale, stale_operation, 1, ('quarantined',))
        self.assertEqual(comp.relationship(self.commands.db, 'source'), current)
        proof = self.commands.get('source')['compensation']
        self.assertTrue(proof['available_current'])
        self.assertGreater(proof['verification']['verified_at'], 0)
        self.assertEqual(proof['verification']['verification'], 'windows_handle_rename_sha256')

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_both_destination_collisions_preserve_all_bytes(self):
        self.write()
        p = self.eligible(); self.prepare(p, 'quarantine-collision')
        destination = Path(p['compensation']['quarantine_path'])
        destination.parent.mkdir()
        destination.write_text('foreign destination')
        failed = self.commands.execute('quarantine-collision', approved=True)
        self.assertEqual(failed['state'], 'failed', failed)
        self.assertEqual(destination.read_text(), 'foreign destination')
        original = self.executor.workspace_root / 'original.txt'
        self.assertEqual(original.read_text(), 'synthetic owned artifact')
        destination.rename(destination.with_suffix('.preserved'))
        self.prepare(self.eligible(), 'quarantine-ok')
        self.assertEqual(self.commands.execute('quarantine-ok', approved=True)['state'], 'succeeded')
        self.prepare(self.eligible(), 'restore-collision')
        original.write_text('user occupied the original path')
        failed = self.commands.execute('restore-collision', approved=True)
        self.assertEqual(failed['state'], 'failed', failed)
        self.assertEqual(original.read_text(), 'user occupied the original path')
        self.assertEqual(destination.read_text(), 'synthetic owned artifact')

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_native_handle_prevents_write_delete_and_parent_replacement_during_hash(self):
        self.write(); self.prepare(self.eligible(), 'guarded')
        original, parent = self.executor.workspace_root / 'original.txt', self.executor.workspace_root
        reader = comp._hash_handle
        attempts = []
        def guarded(kernel, handle, cancelled):
            result = reader(kernel, handle, cancelled)
            if not attempts:
                attempts.append(True)
                with self.assertRaises(PermissionError):
                    with original.open('wb') as stream:
                        stream.write(b'must be denied')
                with self.assertRaises(PermissionError):
                    original.rename(parent / 'foreign-move.txt')
                with self.assertRaises(PermissionError):
                    parent.rename(self.root / 'foreign-parent')
            return result
        with patch.object(comp, '_hash_handle', side_effect=guarded):
            moved = self.commands.execute('guarded', approved=True)
        self.assertEqual(moved['state'], 'succeeded', moved)
        self.assertEqual(attempts, [True])

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_unknown_after_native_move_reconciles_across_restart_without_rename(self):
        self.write(); p = self.eligible(); self.prepare(p, 'interrupted')
        mover = comp.rename_owned
        calls = []
        def interrupted(*args, **kwargs):
            calls.append(True)
            mover(*args, **kwargs)
            raise OSError('synthetic lost acknowledgement')
        with patch.object(comp, 'rename_owned', side_effect=interrupted):
            result = self.commands.execute('interrupted', approved=True)
            self.assertEqual(result['state'], 'unknown', result)
            self.assertTrue(self.commands.execute('interrupted', approved=True)['replayed'])
        self.assertEqual(calls, [True])
        self.commands.close(); self.executor.close()
        self.executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        self.commands = CommandService(self.executor)
        self.assertFalse(self.commands.compensation_preview('source')['available'])
        with self.assertRaisesRegex(ValueError, 'COMPENSATION_RECONCILE_REQUIRED'):
            self.commands.review_unknown('interrupted', reviewed=True)
        with patch.object(comp, 'rename_owned', side_effect=AssertionError('Never repeat effect')):
            reconciled = self.commands.reconcile('interrupted')
        self.assertEqual(reconciled['state'], 'succeeded', reconciled)
        self.assertFalse(reconciled['evidence']['redispatched'])
        self.assertEqual(reconciled['output']['revision'], 1)
        self.assertEqual(self.executor.get_operation(reconciled['action_operation_id'])['state'], 'succeeded')
        self.assertEqual(self.commands.compensation_preview('source')['action'], 'restore')

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_new_service_cannot_reconcile_or_replace_another_live_claim(self):
        self.write(); self.prepare(self.eligible(), 'move-a')
        entered, release = threading.Event(), threading.Event()
        mover = comp.rename_owned
        def held(*args, **kwargs):
            if threading.current_thread().name == 'first-move':
                entered.set(); self.assertTrue(release.wait(8))
            return mover(*args, **kwargs)
        results = []
        other_executor = other = None
        try:
            with patch.object(comp, 'rename_owned', side_effect=held):
                thread = threading.Thread(name='first-move', target=lambda: results.append(self.commands.execute('move-a', approved=True)))
                thread.start(); self.assertTrue(entered.wait(5))
                other_executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
                other = CommandService(other_executor)
                self.assertEqual(other.get('move-a')['state'], 'unknown')
                with self.assertRaisesRegex(ValueError, 'COMPENSATION_OWNER_STILL_ACTIVE'):
                    other.reconcile('move-a')
                self.assertFalse(other.compensation_preview('source')['available'])
                release.set(); thread.join(6)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results[0]['state'], 'succeeded', results)
            relationship = comp.relationship(other.db, 'source')
            self.assertEqual((relationship['state'], relationship['revision']), ('quarantined', 1))
            self.assertFalse((self.executor.workspace_root / 'original.txt').exists())
            self.assertEqual(other.compensation_preview('source')['action'], 'restore')
        finally:
            release.set()
            if other: other.close()
            if other_executor: other_executor.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows ancestry handles required')
    def test_writer_parent_junction_swap_cannot_create_outside_workspace(self):
        import _winapi
        from backend.actions import tools
        parent = self.executor.workspace_root / 'nested'
        parent.mkdir()
        outside = self.root / 'outside'
        outside.mkdir()
        self.commands.prepare('axx.artifact.write', {'path': 'nested/new.txt', 'content': 'synthetic'},
            operation_id='junction-writer', conversation_id='source-task')
        original_execute = tools.FileArtifactTool._execute_protected
        original_check = tools.artifact_path_error
        attempts = []
        def attack_check(path):
            result = original_check(path)
            if result is None and not attempts:
                attempts.append(True)
                parent.rename(self.executor.workspace_root / 'saved-parent')
                _winapi.CreateJunction(str(outside), str(parent))
            return result
        def attacked(tool, inputs):
            with patch.object(tools, 'artifact_path_error', side_effect=attack_check):
                return original_execute(tool, inputs)
        with patch.object(tools.FileArtifactTool, '_execute_protected', new=attacked):
            result = self.commands.execute('junction-writer', approved=True)
        self.assertNotEqual(result['state'], 'succeeded', result)
        self.assertEqual(attempts, [True])
        self.assertFalse((outside / 'new.txt').exists())
        self.assertTrue(parent.is_dir())

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_unknown_before_effect_reconciles_failure_without_any_move(self):
        self.write(); p = self.eligible(); self.prepare(p, 'not-moved')
        with patch.object(comp, 'rename_owned', side_effect=OSError('synthetic pre-body interruption')):
            self.assertEqual(self.commands.execute('not-moved', approved=True)['state'], 'unknown')
        with patch.object(comp, 'rename_owned', side_effect=AssertionError('Never repeat effect')):
            reconciled = self.commands.reconcile('not-moved')
        self.assertEqual(reconciled['state'], 'failed')
        self.assertEqual(reconciled['output']['revision'], 0)
        self.assertFalse(Path(p['compensation']['quarantine_path']).exists())
        self.assertEqual((self.executor.workspace_root / 'original.txt').read_text(), 'synthetic owned artifact')

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_dead_owner_allows_readback_but_unknown_owner_liveness_does_not(self):
        import psutil
        self.write(); self.prepare(self.eligible(), 'dead-owner')
        with patch.object(comp, 'rename_owned', side_effect=OSError('synthetic crash before effect')):
            self.assertEqual(self.commands.execute('dead-owner', approved=True)['state'], 'unknown')
        record = comp.relationship(self.commands.db, 'source')
        record['owner'] = {'pid': 2147483647, 'started': 0, 'nonce': 'fixture', 'active': True}
        with self.commands.db:
            comp._save(self.commands.db, 'source', record)
        with patch('psutil.Process', side_effect=psutil.AccessDenied(2147483647)), self.assertRaisesRegex(ValueError, 'COMPENSATION_OWNER_STILL_ACTIVE'):
            self.commands.reconcile('dead-owner')
        with patch('psutil.Process', side_effect=psutil.NoSuchProcess(2147483647)), \
                patch.object(comp, 'rename_owned', side_effect=AssertionError('Do not redispatch')):
            result = self.commands.reconcile('dead-owner')
        self.assertEqual(result['state'], 'failed')
        self.assertFalse(result['evidence']['redispatched'])

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_ambiguous_recovery_never_marks_success_or_repeats_effect(self):
        self.write(); p = self.eligible(); self.prepare(p, 'ambiguous')
        mover = comp.rename_owned
        def interrupted(*args, **kwargs):
            mover(*args, **kwargs)
            raise OSError('synthetic lost acknowledgement')
        with patch.object(comp, 'rename_owned', side_effect=interrupted):
            self.assertEqual(self.commands.execute('ambiguous', approved=True)['state'], 'unknown')
        (self.executor.workspace_root / 'original.txt').write_text('a new user file')
        with patch.object(comp, 'rename_owned', side_effect=AssertionError('Never repeat effect')), self.assertRaises(ValueError):
            self.commands.reconcile('ambiguous')
        self.assertEqual(self.commands.get('ambiguous')['state'], 'unknown')
        self.assertEqual(Path(p['compensation']['quarantine_path']).read_text(), 'synthetic owned artifact')

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_cancel_before_native_move_preserves_original_and_explicit_retry_is_new(self):
        self.write(); self.prepare(self.eligible(), 'cancelled')
        entered, release = threading.Event(), threading.Event()
        reader = comp._hash_handle
        def held(*args):
            entered.set(); self.assertTrue(release.wait(5))
            return reader(*args)
        results = []
        with patch.object(comp, '_hash_handle', side_effect=held):
            thread = threading.Thread(target=lambda: results.append(self.commands.execute('cancelled', approved=True)))
            thread.start(); self.assertTrue(entered.wait(5))
            self.commands.cancel('cancelled'); release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0]['state'], 'cancelled', results)
        self.assertTrue((self.executor.workspace_root / 'original.txt').exists())
        self.assertEqual(self.eligible()['compensation']['revision'], 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows NTFS compensation only')
    def test_two_services_claim_compensation_once(self):
        other_executor = ActionExecutor(self.root / 'state.db', self.root / 'artifacts')
        other = CommandService(other_executor)
        try:
            self.write(); p = self.eligible()
            self.prepare(p, 'first-owner')
            other.prepare_compensation('source', p['source_receipt_hash'], 0, operation_id='second-owner')
            calls, results = [], []
            mover = comp.rename_owned
            def recorded(*args, **kwargs):
                calls.append(True)
                return mover(*args, **kwargs)
            with patch.object(comp, 'rename_owned', side_effect=recorded):
                threads = [threading.Thread(target=lambda: results.append(self.commands.execute('first-owner', approved=True))),
                    threading.Thread(target=lambda: results.append(other.execute('second-owner', approved=True)))]
                for thread in threads: thread.start()
                for thread in threads: thread.join(8)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(calls, [True])
            self.assertEqual(sorted(row['state'] for row in results), ['failed', 'succeeded'])
        finally:
            other.close(); other_executor.close()


if __name__ == '__main__':
    unittest.main()
