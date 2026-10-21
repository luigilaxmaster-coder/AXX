import ctypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

h_winsta = user32.GetProcessWindowStation()
buff = ctypes.create_unicode_buffer(256)
user32.GetUserObjectInformationW(h_winsta, 2, buff, 256, None)
print("Window Station:", buff.value)

h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
user32.GetUserObjectInformationW(h_desk, 2, buff, 256, None)
print("Thread Desktop:", buff.value)

# Try OpenInputDesktop
h_input = user32.OpenInputDesktop(0, False, 0x01FF) # GENERIC_ALL
print("OpenInputDesktop:", h_input)
if h_input:
    user32.GetUserObjectInformationW(h_input, 2, buff, 256, None)
    print("Input Desktop:", buff.value)
