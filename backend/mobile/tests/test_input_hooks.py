"""Hook ownership without touching the machine's physical input path."""
import unittest
from types import SimpleNamespace
from backend.mobile.windows_input import WindowsInput


class InputHooksTests(unittest.TestCase):
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
