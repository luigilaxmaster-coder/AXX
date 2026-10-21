import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from backend.screen_recording import ScreenRecordingService, validate_region

class ScreenRecordingTests(unittest.TestCase):
    def test_cancel_countdown_and_reject_duplicate_start(self):
        with tempfile.TemporaryDirectory() as root, patch('backend.screen_recording.desktop_bounds', return_value=(0,0,1920,1080)):
            service=ScreenRecordingService(Path(root))
            options={'region':{'x':0,'y':0,'width':200,'height':160},'countdown':5}
            try:
                recording=service.start(options)
                with self.assertRaises(ValueError):service.start(options)
                service.control(recording['id'],'stop')
                service.close()
                self.assertEqual(service.status()['state'],'ready')
                self.assertFalse(list(Path(root).rglob('*.mp4')))
            finally:service.close()

    def test_region_normalization_and_limits(self):
        self.assertEqual(validate_region({'x':-100,'y':5,'width':101,'height':83},(-200,0,400,300)),{'x':-100,'y':5,'width':100,'height':82})
        for region in ({'x':0,'y':0,'width':1,'height':100},{'x':True,'y':0,'width':100,'height':100},{'x':300,'y':0,'width':100,'height':100}):
            with self.assertRaises(ValueError): validate_region(region,(-200,0,400,300))

    def test_state_rejects_stale_controls_and_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as root:
            service=ScreenRecordingService(Path(root))
            with self.assertRaises(ValueError):service.control('old','pause')
            with self.assertRaises(ValueError):service.control('','shell')
            with self.assertRaises(ValueError):service.open_result('old')
            self.assertEqual(service.status()['state'],'ready')
            service.close()

if __name__=='__main__':unittest.main()
