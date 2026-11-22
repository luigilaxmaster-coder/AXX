"""Disk-backed restart, actual process termination, compensation and draft CAS."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.code_studio.projects import CodeProjectService, CodeConflictError, atomic_write_bytes
from backend.code_studio.patch_engine import CodePatchEngine


class CodeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'state.db'
        for name in ('a','b'):(self.root/(name+'.py')).write_bytes((name.upper()+' = 1\r\n').encode())
        self.service=CodeProjectService(self.db);self.addCleanup(self.service.close)
        self.service.register_project('p',self.root);self.engine=CodePatchEngine(self.service)

    def propose(self):
        return self.engine.propose_changeset(changeset_id='cs',project_id='p',workspace_id='w',agent_id='user',
            base_commit='0'*40,branch='audit',file_edits=[{'path':n+'.py','new_content':n.upper()+' = 2\n'} for n in ('a','b')])

    def test_default_timestamp_is_current_utc(self):
        before=datetime.now(timezone.utc);row=self.propose();after=datetime.now(timezone.utc)
        self.assertLessEqual(before,datetime.fromisoformat(row['created_at']))
        self.assertLessEqual(datetime.fromisoformat(row['created_at']),after)

    def test_changeset_id_cannot_replace_existing_approval_or_history(self):
        original=self.propose()
        with self.assertRaises(CodeConflictError):self.propose()
        self.assertEqual(self.engine.get_changeset('cs'),original)
        self.engine.apply_changeset('cs')
        with self.assertRaises(CodeConflictError):self.propose()
        self.assertEqual(self.engine.get_changeset('cs')['status'],'applied')

    def test_real_process_exit_after_first_file_recovers_on_restart(self):
        self.propose();self.service.close()
        script="""
import os,sys
from pathlib import Path
from unittest.mock import patch
from backend.code_studio.projects import CodeProjectService,atomic_write_bytes
from backend.code_studio.patch_engine import CodePatchEngine
p=CodeProjectService(sys.argv[1]);e=CodePatchEngine(p)
def interrupted(path,raw):
    atomic_write_bytes(path,raw)
    if Path(path).name=='a.py':os._exit(23)
with patch('backend.code_studio.recovery.atomic_write_bytes',side_effect=interrupted):e.apply_changeset('cs')
"""
        process=subprocess.run([sys.executable,'-c',script,str(self.db)],capture_output=True,timeout=20)
        self.assertEqual(process.returncode,23,process.stderr.decode(errors='replace'))
        self.assertEqual((self.root/'a.py').read_bytes(),b'A = 2\r\n')
        self.assertEqual((self.root/'b.py').read_bytes(),b'B = 1\r\n')
        self.service=CodeProjectService(self.db);self.addCleanup(self.service.close)
        self.assertEqual((self.root/'a.py').read_bytes(),b'A = 1\r\n')
        self.assertEqual((self.root/'b.py').read_bytes(),b'B = 1\r\n')
        self.assertEqual(self.service.recovery.list('p')[0]['state'],'rolled_back')
        self.assertEqual(CodePatchEngine(self.service).get_changeset('cs')['status'],'proposed')

    def test_io_failure_compensates_all_written_files(self):
        self.propose();failed=False
        def fail_once(path,raw):
            nonlocal failed
            if Path(path).name=='b.py' and not failed:
                failed=True;raise OSError('controlled disk failure')
            atomic_write_bytes(path,raw)
        with patch('backend.code_studio.recovery.atomic_write_bytes',side_effect=fail_once):
            with self.assertRaises(OSError):self.engine.apply_changeset('cs')
        for n in ('a','b'):self.assertEqual((self.root/(n+'.py')).read_bytes(),(n.upper()+' = 1\r\n').encode())
        self.assertEqual(self.service.recovery.list('p')[0]['state'],'rolled_back')

    def test_another_live_process_is_not_recovered_until_it_exits(self):
        self.propose();ready=self.root/'ready'
        script="""
import sys,time
from pathlib import Path
from unittest.mock import patch
from backend.code_studio.projects import CodeProjectService,atomic_write_bytes
from backend.code_studio.patch_engine import CodePatchEngine
p=CodeProjectService(sys.argv[1])
def pause(path,raw):
    atomic_write_bytes(path,raw)
    if Path(path).name=='a.py':
        Path(sys.argv[2]).touch()
        time.sleep(30)
with patch('backend.code_studio.recovery.atomic_write_bytes',side_effect=pause):CodePatchEngine(p).apply_changeset('cs')
"""
        child=subprocess.Popen([sys.executable,'-c',script,str(self.db),str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+10
            while not ready.exists() and time.monotonic()<deadline and child.poll() is None:time.sleep(.02)
            self.assertTrue(ready.exists(),'Child did not reach the write boundary')
            other=CodeProjectService(self.db)
            try:
                self.assertEqual(other.recovery.list('p')[0]['state'],'prepared')
                self.assertEqual((self.root/'a.py').read_bytes(),b'A = 2\r\n')
                with self.assertRaises(CodeConflictError):other.recovery.assert_writable('p')
                child.kill();child.wait(timeout=10)
                other.recovery.recover('p')
                self.assertEqual((self.root/'a.py').read_bytes(),b'A = 1\r\n')
                self.assertEqual(other.recovery.list('p')[0]['state'],'rolled_back')
            finally:other.close()
        finally:
            if child.poll() is None:child.kill()
            child.wait(timeout=10)

    def test_committed_group_is_preserved_after_process_exit(self):
        self.propose();self.service.close()
        child=subprocess.run([sys.executable,'-c',
            "import os,sys;from backend.code_studio.projects import CodeProjectService;from backend.code_studio.patch_engine import CodePatchEngine;p=CodeProjectService(sys.argv[1]);CodePatchEngine(p).apply_changeset('cs');os._exit(24)",
            str(self.db)],capture_output=True,timeout=20)
        self.assertEqual(child.returncode,24,child.stderr.decode(errors='replace'))
        self.service=CodeProjectService(self.db);self.addCleanup(self.service.close)
        for n in ('a','b'):self.assertEqual((self.root/(n+'.py')).read_bytes(),(n.upper()+' = 2\r\n').encode())
        self.assertEqual(self.service.recovery.list('p')[0]['state'],'committed')
        self.assertEqual(CodePatchEngine(self.service).get_changeset('cs')['status'],'applied')

    def test_external_edit_blocks_recovery_until_hash_bound_review(self):
        self.propose()
        def conflict(path,raw):
            if Path(path).name=='b.py':
                Path(path).write_bytes(b'EXTERNAL\r\n');raise OSError('controlled external edit')
            atomic_write_bytes(path,raw)
        with patch('backend.code_studio.recovery.atomic_write_bytes',side_effect=conflict):
            with self.assertRaises(OSError):self.engine.apply_changeset('cs')
        rows=self.service.recovery.list('p');self.assertEqual(rows[0]['state'],'recovery_conflict')
        self.assertEqual((self.root/'a.py').read_bytes(),b'A = 2\r\n')
        self.assertEqual((self.root/'b.py').read_bytes(),b'EXTERNAL\r\n')
        with self.assertRaises(CodeConflictError):
            self.service.save_document('p','a.py','A = 3\n',expected_sha256=hashlib.sha256(b'A = 2\r\n').hexdigest())
        hashes={f['path']:f['current_sha'] for f in rows[0]['files']}
        with self.service._connect() as db,db:
            db.execute("UPDATE code_file_transaction_items SET after_blob=? WHERE path='a.py'",(b'CORRUPT',))
        self.service.recovery.recover('p')
        self.assertIn('checksum mismatch',self.service.recovery.list('p')[0]['error'])
        self.assertEqual((self.root/'a.py').read_bytes(),b'A = 2\r\n')
        with self.assertRaises(CodeConflictError):self.service.recovery.acknowledge(rows[0]['transaction_id'],{},True)
        self.service.recovery.acknowledge(rows[0]['transaction_id'],hashes,True)
        self.assertEqual((self.root/'b.py').read_bytes(),b'EXTERNAL\r\n')
        self.service.save_document('p','a.py','A = 3\n',expected_sha256=hashes['a.py'])

    def test_group_is_reverified_before_committing_success(self):
        self.propose()
        def changed_earlier_file(path,raw):
            atomic_write_bytes(path,raw)
            if Path(path).name=='b.py':(self.root/'a.py').write_bytes(b'EXTERNAL\r\n')
        with patch('backend.code_studio.recovery.atomic_write_bytes',side_effect=changed_earlier_file):
            with self.assertRaises(CodeConflictError):self.engine.apply_changeset('cs')
        self.assertEqual((self.root/'a.py').read_bytes(),b'EXTERNAL\r\n')
        self.assertEqual(self.engine.get_changeset('cs')['status'],'proposed')
        self.assertEqual(self.service.recovery.list('p')[0]['state'],'recovery_conflict')

    def test_drafts_survive_restart_and_do_not_modify_project_files(self):
        doc=self.service.read_document('p','a.py');args=dict(content='A = "ñ😃"\n',base_content=doc['content'],base_sha256=doc['sha256'],encoding=doc['encoding'],line_ending=doc['line_ending'])
        self.assertEqual(self.service.save_draft('p','a.py',expected_revision=0,**args)['revision'],1)
        self.service.close();self.service=CodeProjectService(self.db);self.addCleanup(self.service.close)
        row=self.service.get_draft('p','a.py');self.assertEqual(row['content'],args['content'])
        self.assertEqual((self.root/'a.py').read_bytes(),b'A = 1\r\n')
        with self.assertRaises(CodeConflictError):self.service.save_draft('p','a.py',expected_revision=0,**args)
        self.assertEqual(self.service.save_draft('p','a.py',expected_revision=1,content=None)['revision'],2)
        with self.assertRaises(CodeConflictError):self.service.save_draft('p','a.py',expected_revision=0,**args)
        self.assertEqual(self.service.get_draft('p','a.py')['revision'],2)
        self.assertEqual(self.service.list_drafts('p'),[])
