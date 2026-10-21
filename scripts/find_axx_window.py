import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

def enum_windows_proc(hwnd, extra):
    vis = bool(user32.IsWindowVisible(hwnd))
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value
    
    cls_buff = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buff, 256)
    cls_name = cls_buff.value
    
import psutil

axx_pids = set()
for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and 'axx' in p.info['name'].lower():
        axx_pids.add(p.info['pid'])

print(f"Found Axx related PIDs: {axx_pids}")

def enum_windows_proc(hwnd, extra):
    vis = bool(user32.IsWindowVisible(hwnd))
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    
    if pid.value in axx_pids:
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value
        cls_buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buff, 256)
        print(f'MATCH: HWND={hwnd} PID={pid.value} Vis={vis} Title="{title}" Class="{cls_buff.value}" Rect=[{rect.left}, {rect.top}, {w}x{h}]')
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
