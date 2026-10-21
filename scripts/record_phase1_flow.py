import os
import sys
import time
import subprocess
import ctypes
from pathlib import Path

evidence_dir = Path("c:/Users/luigi/Desktop/Axx assistant/evidence/ux-revision-20261020")
evidence_dir.mkdir(parents=True, exist_ok=True)
video_path = evidence_dir / "phase1_motion.mp4"
screenshot_path = evidence_dir / "phase1_motion.png"

print(f"Recording Phase 1 video to: {video_path}")
if video_path.exists():
    try:
        video_path.unlink()
    except Exception:
        pass

# FFmpeg command capturing screen on Windows via gdigrab
ffmpeg_cmd = [
    "ffmpeg", "-y", "-loglevel", "warning",
    "-f", "gdigrab", "-framerate", "15", "-draw_mouse", "1",
    "-i", "desktop",
    "-t", "16",
    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
    str(video_path)
]

proc = subprocess.Popen(ffmpeg_cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
time.sleep(2)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def interact_phase1():
    # 1. Summon Axx to center of primary screen
    target_x, target_y = 700, 400
    user32.SetCursorPos(target_x, target_y)
    hEvent = kernel32.OpenEventW(0x0002, False, "Local\\AxxResidentSummon-com.axx.desktop")
    if hEvent:
        kernel32.SetEvent(hEvent)
        kernel32.CloseHandle(hEvent)
        print("Summon event triggered to (700, 400)")
    time.sleep(2)

    # 2. Click avatar to open dock / panel
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Clicked on Axx avatar")
    time.sleep(2)

    # 3. Click tools button in dock
    user32.SetCursorPos(target_x + 60, target_y)
    time.sleep(0.5)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Clicked tool button to open panel")
    time.sleep(2)

    # 4. Drag the panel by its header to demonstrate independent movement and elastic tendril
    # The panel header is located around target_x + 120, target_y - 80
    header_x = target_x + 150
    header_y = target_y - 60
    user32.SetCursorPos(header_x, header_y)
    time.sleep(0.5)
    user32.mouse_event(0x0002, 0, 0, 0, 0) # Mouse down
    time.sleep(0.2)

    # Smooth drag to new screen position (stretching tendril)
    for step in range(25):
        user32.SetCursorPos(header_x + step * 10, header_y - step * 5)
        time.sleep(0.04)

    # Reverse direction slightly to demonstrate spring damping without snaps
    for step in range(10):
        user32.SetCursorPos(header_x + 250 - step * 6, header_y - 125 + step * 3)
        time.sleep(0.04)

    user32.mouse_event(0x0004, 0, 0, 0, 0) # Mouse up (position persists)
    print("Panel dragged and released at new position")
    time.sleep(2.5)

try:
    interact_phase1()
except Exception as e:
    print(f"Interaction error: {e}")

proc.wait(timeout=25)
print(f"Video recorded: {video_path} ({video_path.stat().st_size} bytes)")

subprocess.run([
    "ffmpeg", "-y", "-ss", "00:00:09", "-i", str(video_path),
    "-vframes", "1", "-q:v", "2", str(screenshot_path)
], check=True)
print(f"Screenshot extracted: {screenshot_path}")
