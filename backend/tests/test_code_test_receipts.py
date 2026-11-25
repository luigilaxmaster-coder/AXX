"""Real Windows process custody, bounded logs, cancellation, and durable test effect identity."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from backend.code_studio.projects import CodeProjectService, CodeConflictError
from backend.code_studio.test_runner import SupervisedTestRunner


@unittest.skipUnless(os.name=='nt','Windows Job Object acceptance')
class TestReceiptLifecycleTests(unittest.TestCase):
    def test_retry_is_read_only_and_timeout_cancel_and_output_limits_are_failed_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);projects=CodeProjectService(root/'state.db')
            try:
                projects.register_project('p',str(root));runner=SupervisedTestRunner(projects)
                (root/'once.py').write_text("from pathlib import Path\np=Path('effects.txt')\np.write_text((p.read_text() if p.exists() else '')+'x')\nprint('ok')\n")
                args=dict(report_id='once',project_id='p',workspace_id='p',command=[sys.executable,'once.py'])
                first=runner.run_test_command(**args);self.assertTrue(first['passed'],first)
                retry=runner.run_test_command(**args)
                self.assertEqual(retry['stdout_hash'],first['stdout_hash'])
                self.assertEqual((root/'effects.txt').read_text(),'x')
                with self.assertRaises(CodeConflictError):runner.run_test_command(**{**args,'command':[sys.executable,'different.py']})
                (root/'noisy.py').write_text("import sys\nsys.stdout.write('x'*1000000)\n")
                noisy=runner.run_test_command(**{**args,'report_id':'noisy','command':[sys.executable,'noisy.py']})
                self.assertFalse(noisy['passed']);self.assertEqual(noisy['execution_status'],'output_limit')
                self.assertTrue(noisy['cleanup_verified']);self.assertLessEqual(len(noisy['stdout_preview']),4000)
                (root/'slow.py').write_text('import time\ntime.sleep(30)\n')
                start=time.monotonic()
                timeout=runner.run_test_command(**{**args,'report_id':'timeout','command':[sys.executable,'slow.py'],'timeout_sec':1})
                self.assertLess(time.monotonic()-start,5)
                self.assertEqual(timeout['execution_status'],'timeout');self.assertFalse(timeout['passed'])
                cancel=threading.Event();timer=threading.Timer(.2,cancel.set);timer.start()
                try:
                    receipt=runner.run_test_command(**{**args,'report_id':'cancel','command':[sys.executable,'slow.py'],'cancel_event':cancel})
                finally:timer.cancel()
                self.assertEqual(receipt['execution_status'],'cancelled');self.assertFalse(receipt['passed'])
                self.assertTrue(receipt['cleanup_verified'])
            finally:projects.close()
