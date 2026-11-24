"""Native Win32 window for Act computer-use tests: a standard BUTTON and STATIC that Windows exposes to UI Automation.

Pressing «Saludar» changes the label to «Hola desde el Act». No network, no files; it exits when closed or killed.
"""
import ctypes as C
from ctypes import wintypes as W

user, kernel = C.windll.user32, C.windll.kernel32
WNDPROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
user.DefWindowProcW.argtypes = (W.HWND, W.UINT, W.WPARAM, W.LPARAM)
user.DefWindowProcW.restype = C.c_ssize_t
user.CreateWindowExW.restype = W.HWND
user.CreateWindowExW.argtypes = (W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int,
                                 W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
BUTTON_ID, label = 101, None


class WNDCLASS(C.Structure):
    _fields_ = [('style', W.UINT), ('proc', WNDPROC), ('cls', C.c_int), ('wnd', C.c_int), ('instance', W.HINSTANCE),
                ('icon', W.HICON), ('cursor', W.HANDLE), ('background', W.HBRUSH), ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]


@WNDPROC
def proc(hwnd, msg, wparam, lparam):
    if msg == 0x0111 and (wparam & 0xFFFF) == BUTTON_ID:  # WM_COMMAND from the button
        user.SetWindowTextW(label, 'Hola desde el Act')
        return 0
    if msg == 0x0002:  # WM_DESTROY
        user.PostQuitMessage(0)
        return 0
    return user.DefWindowProcW(hwnd, msg, wparam, lparam)


instance = kernel.GetModuleHandleW(None)
cls = WNDCLASS(0, proc, 0, 0, instance, None, user.LoadCursorW(None, C.c_void_p(32512)), C.c_void_p(16), None, 'AxxActFixture')
user.RegisterClassW(C.byref(cls))
main = user.CreateWindowExW(0x8, 'AxxActFixture', 'AXX Act native fixture', 0x10CF0000, 200, 200, 380, 220, None, None, instance, None)
label = user.CreateWindowExW(0, 'STATIC', 'Pendiente', 0x50000000, 20, 20, 320, 30, main, None, instance, None)
user.CreateWindowExW(0, 'BUTTON', 'Saludar', 0x50010000, 20, 80, 140, 40, main, C.c_void_p(BUTTON_ID), instance, None)
msg = W.MSG()
while user.GetMessageW(C.byref(msg), None, 0, 0) > 0:
    user.TranslateMessage(C.byref(msg))
    user.DispatchMessageW(C.byref(msg))
