import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32

def enum_thread_wnd(hwnd, extra):
    vis = bool(user32.IsWindowVisible(hwnd))
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value
    
    cls_buff = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls_buff, 256)
    cls_name = cls_buff.value
    
    print(f"THREAD WND: HWND={hwnd} Vis={vis} Title='{title}' Class='{cls_name}' Rect=[{rect.left}, {rect.top}, {w}x{h}]")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
cb = WNDENUMPROC(enum_thread_wnd)

for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and p.info['name'].lower() == 'axx.exe':
        print(f"Axx process: {p.pid}")
        try:
            proc = psutil.Process(p.pid)
            for t in proc.threads():
                user32.EnumThreadWindows(t.id, cb, 0)
        except Exception as e:
            print("Error:", e)
