import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
hDesk = user32.OpenDesktopW('Default', 0, False, 0x01FF)
if hDesk:
    user32.SetThreadDesktop(hDesk)

def proc(hwnd, _):
    if user32.IsWindowVisible(hwnd):
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if rect.left <= 1500 and rect.right >= 1400 and rect.top <= 600 and rect.bottom >= 500:
            len_t = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(len_t + 1)
            user32.GetWindowTextW(hwnd, buff, len_t + 1)
            cbuff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cbuff, 256)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            ex_style = user32.GetWindowLongW(hwnd, -20) # GWL_EXSTYLE
            topmost = bool(ex_style & 0x00000008) # WS_EX_TOPMOST
            pname = psutil.Process(pid.value).name() if psutil.pid_exists(pid.value) else 'unknown'
            print(f'HWND {hwnd} PID {pid.value} ({pname}) Topmost={topmost} Rect=[{rect.left},{rect.top},{w}x{h}] Title="{buff.value}" Class="{cbuff.value}"')
    return True

user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(proc), 0)
