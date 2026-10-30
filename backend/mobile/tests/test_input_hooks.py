"""Hook ownership without touching the machine's physical input path."""
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock,patch
from backend.mobile.windows_input import WindowsInput


class InputHooksTests(unittest.TestCase):
    def test_cached_indicator_can_grant_control_but_never_bypass_lease_expiry(self):
        native=WindowsInput.__new__(WindowsInput)
        material=bytes([17,39,83,255])*(128*128)
        native.active=False;native.table=None;native.material_at=0;native.abort=threading.Event()
        native.user=SimpleNamespace(GetAsyncKeyState=lambda _:0)
        native._set_hooks=Mock();native._cancel=Mock()
        with patch('backend.mobile.windows_input.time.monotonic',return_value=100):
            with self.assertRaises(ValueError):native._execute('grant',('lease',3,'remote'))
            native.table=material
            native._execute('grant',('lease',3,'remote'))
            self.assertTrue(native.active);self.assertIs(native.table,material)
            self.assertEqual(native.deadline,103)
            native._set_hooks.assert_called_once_with(True)
        for now in range(102,122,2):
            with patch('backend.mobile.windows_input.time.monotonic',return_value=now):native._execute('renew',('lease',3))
            self.assertEqual(native.deadline,now+3)
            self.assertEqual(native.material_at,0)
        with patch('backend.mobile.windows_input.time.monotonic',return_value=native.deadline):
            with self.assertRaises(ValueError):native._check('lease')
        native._cancel.assert_called_once_with('expired_or_revoked')

    def test_automation_and_unknown_sources_still_require_desktop_heartbeat(self):
        for source in ['axx_automation','direct_pointer','unknown']:
            with self.subTest(source=source):
                native=WindowsInput.__new__(WindowsInput)
                native.active=False;native.table=bytes(128*128*4);native.material_at=0;native.abort=threading.Event()
                native.user=SimpleNamespace(GetAsyncKeyState=lambda _:0)
                native._set_hooks=Mock();native._cancel=Mock()
                with patch('backend.mobile.windows_input.time.monotonic',return_value=100):
                    with self.assertRaises(ValueError):native._execute('grant',('lease',30,source))
                    native._set_hooks.assert_not_called()
                    native.material_at=99;native._execute('grant',('lease',30,source))
                with patch('backend.mobile.windows_input.time.monotonic',return_value=104):native._execute('renew',('lease',30))
                self.assertEqual(native.material_at,99)
                self.assertEqual(native.deadline,134)
                with patch('backend.mobile.windows_input.time.monotonic',return_value=105):
                    with self.assertRaises(ValueError):native._check('lease')
                native._cancel.assert_called_once_with('expired_or_revoked')

    def test_hooks_only_exist_during_requested_control_and_cleanup_is_idempotent(self):
        installed=[];removed=[]
        native=WindowsInput.__new__(WindowsInput)
        native.hooks=[];native.callbacks=(None,'mouse','keyboard')
        native.kernel=SimpleNamespace(GetModuleHandleW=lambda _:1)
        def install(kind,callback,instance,thread):
            installed.append((kind,callback));return kind
        native.user=SimpleNamespace(SetWindowsHookExW=install,UnhookWindowsHookEx=removed.append)
        native._set_hooks(False);self.assertEqual(installed,[])
        native._set_hooks(True);native._set_hooks(True)
        self.assertEqual(installed,[(14,'mouse'),(13,'keyboard')])
        native._set_hooks(False);native._set_hooks(False)
        self.assertEqual(removed,[14,13]);self.assertEqual(native.hooks,[])

    def test_partial_hook_installation_is_rolled_back(self):
        removed=[]
        native=WindowsInput.__new__(WindowsInput)
        native.hooks=[];native.callbacks=(None,'mouse','keyboard')
        native.kernel=SimpleNamespace(GetModuleHandleW=lambda _:1)
        native.user=SimpleNamespace(SetWindowsHookExW=lambda kind,*_:14 if kind==14 else 0,UnhookWindowsHookEx=removed.append)
        with self.assertRaises(OSError):native._set_hooks(True)
        self.assertEqual(removed,[14]);self.assertEqual(native.hooks,[])
