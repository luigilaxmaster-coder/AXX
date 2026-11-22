"""Real files and deterministic interleaving at the atomic-replace boundary."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from backend.code_studio.projects import CodeProjectService, CodeConflictError, atomic_write_bytes
from backend.code_studio.patch_engine import CodePatchEngine


class CodeMutationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.file = self.root / 'a.py'; self.file.write_bytes(b'A = 1\r\n')
        self.service = CodeProjectService(':memory:'); self.addCleanup(self.service.close)
        self.service.register_project('p', self.root); self.engine = CodePatchEngine(self.service)
        self.initial_sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.engine.propose_changeset(changeset_id='cs', project_id='p', workspace_id='w', agent_id='coder',
            base_commit='0'*40, branch='audit', file_edits=[{'path':'a.py','new_content':'A = 2\n'}])

    def assert_serialized(self, operation, module):
        base = hashlib.sha256(self.file.read_bytes()).hexdigest()
        ready, proceed = threading.Event(), threading.Event(); main = threading.current_thread()
        def paused_write(path, payload):
            if threading.current_thread() is not main:
                ready.set()
                if not proceed.wait(5): raise TimeoutError('test writer was not released')
            return atomic_write_bytes(path, payload)
        admitted = False
        with patch(module + '.atomic_write_bytes', side_effect=paused_write), ThreadPoolExecutor(1) as pool:
            future = pool.submit(operation)
            try:
                self.assertTrue(ready.wait(5), 'Mutation did not reach its disk write')
                if self.service.lock.acquire(blocking=False):
                    try:
                        self.service.save_document('p','a.py','A = 999\n',expected_sha256=base)
                        admitted = True
                    finally: self.service.lock.release()
            finally: proceed.set()
            future.result(timeout=5)
        self.assertFalse(admitted, 'A successful user save was allowed and then overwritten by the other mutation')
        with self.assertRaises(CodeConflictError):
            self.service.save_document('p','a.py','A = 999\n',expected_sha256=base)

    def test_apply_excludes_a_concurrent_save(self):
        self.assert_serialized(lambda:self.engine.apply_changeset('cs'),'backend.code_studio.patch_engine')

    def test_rollback_excludes_a_concurrent_save(self):
        self.engine.apply_changeset('cs')
        self.assert_serialized(lambda:self.engine.rollback_changeset('cs'),'backend.code_studio.patch_engine')

    def test_restore_excludes_a_concurrent_save(self):
        self.engine.apply_changeset('cs')
        self.assert_serialized(lambda:self.service.restore_snapshot('p','a.py',self.initial_sha),'backend.code_studio.projects')

    def test_force_must_be_an_actual_boolean(self):
        self.engine.apply_changeset('cs'); self.file.write_bytes(b'A = 999\r\n')
        for force in ('false','true',0,1,None):
            with self.subTest(force=force), self.assertRaisesRegex(ValueError, "force must be a boolean"):
                self.engine.rollback_changeset('cs',force=force)
            self.assertEqual(self.file.read_bytes(),b'A = 999\r\n')
        with self.assertRaises(CodeConflictError): self.engine.rollback_changeset('cs',force=False)

    def test_http_rejects_string_force_without_overwriting_external_edit(self):
        from backend.tests.test_evolution3_full_functional_audit import _start_bound_server, _stop_bound_server, _HttpTestClient
        services = _start_bound_server(self.root / 'http-state.db', self.root / 'runtime')
        try:
            server = services[0]; runtime = server.evolution_runtime
            for flag in ('code_studio_v1','code_execution_v1'):
                runtime.flags.set_flag(flag,True,reason='isolated regression')
            runtime.code_projects.register_project('http-p',self.root)
            runtime.code_patches.propose_changeset(changeset_id='http-cs',project_id='http-p',workspace_id='w',agent_id='coder',
                base_commit='0'*40,branch='audit',file_edits=[{'path':'a.py','new_content':'A = 2\n'}])
            runtime.code_patches.apply_changeset('http-cs');self.file.write_bytes(b'A = 999\r\n')
            code,_ = _HttpTestClient(server.server_port,server.host_token).request('POST','/axx-api/code/v1/changesets/rollback',{'changeset_id':'http-cs','force':'false'})
            self.assertEqual(code,400);self.assertEqual(self.file.read_bytes(),b'A = 999\r\n')
        finally:_stop_bound_server(*services)

    def corrupt_snapshot(self, path, sha):
        with self.service._connect() as db, db:
            db.execute('UPDATE code_time_machine_snapshots SET raw_blob=? WHERE project_id=? AND relative_path=? AND sha256=?',
                       (b'CORRUPT SNAPSHOT','p',path,sha))

    def test_restore_checks_snapshot_before_overwriting_a_file(self):
        self.engine.apply_changeset('cs'); before=self.file.read_bytes()
        self.corrupt_snapshot('a.py',self.initial_sha)
        with self.assertRaisesRegex(RuntimeError,'Snapshot.*mismatch'):
            self.service.restore_snapshot('p','a.py',self.initial_sha)
        self.assertEqual(self.file.read_bytes(),before)

    def test_rollback_checks_all_snapshots_before_any_write(self):
        other=self.root/'b.py';other.write_bytes(b'B = 1\r\n');old_sha=hashlib.sha256(other.read_bytes()).hexdigest()
        self.engine.propose_changeset(changeset_id='multi',project_id='p',workspace_id='w',agent_id='coder',base_commit='0'*40,branch='audit',
            file_edits=[{'path':'a.py','new_content':'A = 2\n'},{'path':'b.py','new_content':'B = 2\n'}])
        self.engine.apply_changeset('multi');before=[self.file.read_bytes(),other.read_bytes()]
        self.corrupt_snapshot('b.py',old_sha)
        with self.assertRaisesRegex(RuntimeError,'Snapshot.*mismatch'):self.engine.rollback_changeset('multi')
        self.assertEqual([self.file.read_bytes(),other.read_bytes()],before)

    def test_save_verifies_actual_replaced_bytes_before_success(self):
        import os
        replace=os.replace
        def externally_changed(source,target):
            replace(source,target);Path(target).write_bytes(b'EXTERNAL EDIT\r\n')
        with patch('backend.code_studio.projects.os.replace',side_effect=externally_changed):
            with self.assertRaises(CodeConflictError):
                self.service.save_document('p','a.py','A = 2\n',expected_sha256=self.initial_sha)
        self.assertEqual(self.file.read_bytes(),b'EXTERNAL EDIT\r\n')
        with self.service._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM code_time_machine_snapshots WHERE operation_id='op-save:after'").fetchone()[0],0)
