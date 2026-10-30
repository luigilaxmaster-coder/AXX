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
        with patch('backend.mobile.windows_input.time.monotonic',return_value=102):native._check('lease')
        with patch('backend.mobile.windows_input.time.monotonic',return_value=103):
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
