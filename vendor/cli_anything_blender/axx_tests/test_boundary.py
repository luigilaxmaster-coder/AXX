"""Axx boundary tests; authored locally, not part of upstream CLI-Anything."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from backend.actions import cli_blender

class BlenderBoundaryTests(unittest.TestCase):
    def test_rejects_non_basename_and_script_inputs(self):
        with tempfile.TemporaryDirectory(prefix='axx-blender-validation-') as workspace:
            for name in ('../x.png', 'C:\\x.png', 'x.py', 'x.png;calc', '.png', 'x/y.png', "x'.png"):
                with self.subTest(name=name):
                    result=cli_blender.render_fixture(Path(workspace),name)
                    self.assertFalse(result['success'])
                    self.assertIsNone(result['output'])
            self.assertFalse(list(Path(workspace).iterdir()))

    def test_existing_files_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='axx-blender-existing-') as workspace:
            path=Path(workspace)/'existing.png'
            path.write_bytes(b'user-existing-bytes')
            result=cli_blender.render_fixture(Path(workspace),'existing.png')
            self.assertFalse(result['success'])
            self.assertEqual(path.read_bytes(),b'user-existing-bytes')

    def test_actual_blender_render_and_png_postcondition(self):
        cli_blender.find_blender()
        with tempfile.TemporaryDirectory(prefix='axx-blender-render-') as workspace:
            result=cli_blender.render_fixture(Path(workspace),'verified.png')
            self.assertTrue(result['success'],result)
            verified=cli_blender.verify_png(Path(result['output']['path']))
            self.assertEqual((verified['width'],verified['height']),(256,256))
            self.assertEqual(verified['sha256'],result['evidence']['sha256'])
            self.assertEqual(result['evidence']['exit_code'],0)
            self.assertEqual(result['evidence']['upstream_commit'],'34f519533bc175d2fe287ab8316b0dd99bb9cc43')

    def test_cancel_actual_owned_blender_process_discards_output(self):
        with tempfile.TemporaryDirectory(prefix='axx-blender-cancel-') as workspace:
            result=[]
            thread=threading.Thread(target=lambda:result.append(cli_blender.render_fixture(Path(workspace),'cancelled.png')))
            thread.start()
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                with cli_blender._active_lock:
                    active=bool(cli_blender._active)
                if active:break
                time.sleep(.01)
            self.assertTrue(active,'Render process did not enter its controlled lifecycle')
            self.assertEqual(cli_blender.cancel_active(),1)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertFalse(result[0]['success'])
            self.assertIn('cancelled',result[0]['error'])
            self.assertFalse((Path(workspace)/'cancelled.png').exists())

if __name__=='__main__':
    unittest.main(verbosity=2)
