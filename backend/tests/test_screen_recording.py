import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
from backend.screen_recording import ScreenRecordingService, desktop_bounds, validate_region

class ScreenRecordingTests(unittest.TestCase):
    def test_desktop_bounds_uses_physical_scope(self):
        entered = []
        def metric(index):
            self.assertEqual(entered, ['physical'])
            return {76: 0, 77: 0, 78: 3840, 79: 1080}[index]
        user = SimpleNamespace(GetSystemMetrics=Mock(side_effect=metric))
        @contextmanager
        def scope():
            entered.append('physical')
            try:
                yield user
            finally:
                entered.pop()
        with patch('backend.screen_recording.physical_dpi_context', scope):
            self.assertEqual(desktop_bounds(), (0, 0, 3840, 1080))
        self.assertEqual(entered, [])

    def test_record_scope_covers_capture_and_restores_on_error(self):
        entered = []
        @contextmanager
        def scope():
            entered.append('physical')
            try:
                yield
            finally:
                entered.pop()
        with tempfile.TemporaryDirectory() as root:
            service = ScreenRecordingService(Path(root))
            def record(*args):
                self.assertEqual(entered, ['physical'])
                raise RuntimeError('capture unavailable')
            with patch('backend.screen_recording.physical_dpi_context', scope), patch.object(service, '_record_physical', side_effect=record) as worker:
                service._record({'x': 1920, 'y': 0, 'width': 1920, 'height': 1080}, 30, 'balanced', 0, 1)
            worker.assert_called_once()
            self.assertEqual(entered, [])
            self.assertEqual(service.status()['state'], 'error')
            self.assertIn('capture unavailable', service.status()['error'])
            service.close()

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
