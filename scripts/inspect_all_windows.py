import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32

hDesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
if hDesk:
    user32.SetThreadDesktop(hDesk)
    print("Attached to Default desktop successfully!")
else:
    print("Could not open Default desktop, err:", ctypes.GetLastError())

def enum_windows():
    results = []
    def proc(hwnd, _):
        if not user32.IsWindow(hwnd):
            return True
        vis = bool(user32.IsWindowVisible(hwnd))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        
        len_title = user32.GetWindowTextLengthW(hwnd)
        tbuff = ctypes.create_unicode_buffer(len_title + 1)
        user32.GetWindowTextW(hwnd, tbuff, len_title + 1)
        
        cbuff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cbuff, 256)
        
        results.append({
            'hwnd': hwnd,
            'pid': pid.value,
            'vis': vis,
            'title': tbuff.value,
            'class': cbuff.value,
            'rect': (rect.left, rect.top, w, h)
        })
        return True
    
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(proc)
    user32.EnumWindows(cb, 0)
    return results

windows = enum_windows()
print(f"Total top-level windows found: {len(windows)}")
pids_map = {p.pid: p.name() for p in psutil.process_iter(['pid', 'name'])}

for w in windows:
    pname = pids_map.get(w['pid'], 'unknown')
    if w['pid'] == 1972 or 'axx' in pname.lower():
        print("FOUND PID 1972/Axx WINDOW:", w, "Process:", pname)
    elif 'webview' in pname.lower():
        print("FOUND WEBVIEW WINDOW:", w, "Process:", pname)
