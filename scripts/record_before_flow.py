import os
import sys
import time
import subprocess
import ctypes
from pathlib import Path

evidence_dir = Path("c:/Users/luigi/Desktop/Axx assistant/evidence/ux-revision-20261020")
evidence_dir.mkdir(parents=True, exist_ok=True)
video_path = evidence_dir / "axx_before.mp4"
screenshot_path = evidence_dir / "axx_before.png"

print(f"Recording before video to: {video_path}")
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
    "-t", "18",
    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
    str(video_path)
]

proc = subprocess.Popen(ffmpeg_cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
time.sleep(2)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def summon_and_interact():
    hEvent = kernel32.OpenEventW(0x0002, False, "Local\\AxxResidentSummon-com.axx.desktop")
    if hEvent:
        kernel32.SetEvent(hEvent)
        kernel32.CloseHandle(hEvent)
        print("Summon event triggered")
    time.sleep(2)

    user32.SetCursorPos(2360, 510)
    time.sleep(1)
    
    # Left click to trigger dock/tools
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Clicked on Axx avatar")
    time.sleep(2)

    # Click tool button
    user32.SetCursorPos(2420, 510)
    time.sleep(0.5)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Clicked tool button")
    time.sleep(2)

    # Drag
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    for dx in range(10):
        user32.SetCursorPos(2420 + dx * 10, 510 - dx * 5)
        time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Dragged")
    time.sleep(2)

    # Press Esc to close
    user32.keybd_event(0x1B, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(0x1B, 0, 2, 0)
    print("Pressed Escape")

try:
    summon_and_interact()
except Exception as e:
    print(f"Interaction error: {e}")

proc.wait(timeout=25)
print(f"Video recorded: {video_path} ({video_path.stat().st_size} bytes)")

subprocess.run([
    "ffmpeg", "-y", "-ss", "00:00:04", "-i", str(video_path),
    "-vframes", "1", "-q:v", "2", str(screenshot_path)
], check=True)
print(f"Screenshot extracted: {screenshot_path}")
