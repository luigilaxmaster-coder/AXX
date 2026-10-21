import os
import sys
import time
import subprocess
from pathlib import Path

def record_after(output_mp4, duration_sec=16, fps=10):
    output_mp4 = Path(output_mp4)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    
    ps_script = f"""
$ErrorActionPreference = 'Stop'
$code = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;
using System.Threading;
using System.IO;
using System.Runtime.InteropServices;

public class PipeCapturer {{
    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr OpenDesktop(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetThreadDesktop(IntPtr hDesktop);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool CloseDesktop(IntPtr hDesktop);

    [DllImport("gdi32.dll")]
    public static extern bool BitBlt(IntPtr hdcDest, int nXDest, int nYDest, int nWidth, int nHeight, IntPtr hdcSrc, int nXSrc, int nYSrc, uint dwRop);

    [DllImport("user32.dll")]
    public static extern IntPtr GetDesktopWindow();

    [DllImport("user32.dll")]
    public static extern IntPtr GetWindowDC(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);

    public static void RecordToPipe(int totalFrames, int delayMs, Stream output) {{
        Thread t = new Thread(() => {{
            try {{
                IntPtr hDesk = OpenDesktop("Default", 0, false, 0x01FF);
                if (hDesk != IntPtr.Zero) {{
                    SetThreadDesktop(hDesk);
                }}

                Rectangle bounds = SystemInformation.VirtualScreen;
                using (Bitmap bitmap = new Bitmap(bounds.Width, bounds.Height)) {{
                    using (Graphics g = Graphics.FromImage(bitmap)) {{
                        for (int i = 0; i < totalFrames; i++) {{
                            IntPtr hdcDest = g.GetHdc();
                            IntPtr hwndDesk = GetDesktopWindow();
                            IntPtr hdcSrc = GetWindowDC(hwndDesk);
                            BitBlt(hdcDest, 0, 0, bounds.Width, bounds.Height, hdcSrc, bounds.X, bounds.Y, 0x00CC0020 | 0x40000000);
                            ReleaseDC(hwndDesk, hdcSrc);
                            g.ReleaseHdc(hdcDest);

                            bitmap.Save(output, ImageFormat.Bmp);
                            output.Flush();
                            Thread.Sleep(delayMs);
                        }}
                    }}
                }}

                if (hDesk != IntPtr.Zero) {{
                    CloseDesktop(hDesk);
                }}
            }} catch (Exception ex) {{
                Console.Error.WriteLine("Error: " + ex);
            }}
        }});
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
    }}
}}
'@

Add-Type -TypeDefinition $code -ReferencedAssemblies System.Windows.Forms, System.Drawing
$stdout = [Console]::OpenStandardOutput()
[PipeCapturer]::RecordToPipe({int(duration_sec * fps)}, {int(1000 / fps)}, $stdout)
"""
    tmp_ps = Path("scripts/pipe_capture.ps1")
    tmp_ps.write_text(ps_script, encoding='utf-8')

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-f", "image2pipe", "-vcodec", "bmp", "-framerate", str(fps),
        "-i", "-",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
        str(output_mp4.resolve())
    ]

    ps_cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(tmp_ps.resolve())]

    print(f"Starting pipe capture for {duration_sec}s -> {output_mp4}...")
    ps_proc = subprocess.Popen(ps_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ff_proc = subprocess.Popen(ffmpeg_cmd, stdin=ps_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ps_proc.stdout.close()

    return ps_proc, ff_proc

if __name__ == '__main__':
    out = "evidence/ux-revision-20261020/axx_after.mp4"
    sec = 16
    ps_p, ff_p = record_after(out, duration_sec=sec)
    
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    time.sleep(1)
    
    # 1. Trigger summon to DISPLAY2 (2360, 510)
    user32.SetCursorPos(2360, 510)
    hEvent = kernel32.OpenEventW(0x0002, False, "Local\\AxxResidentSummon-com.axx.desktop")
    if hEvent:
        kernel32.SetEvent(hEvent)
        kernel32.CloseHandle(hEvent)
        print("Summon event triggered")
    time.sleep(2)
    
    # 2. Click avatar to open dock
    user32.SetCursorPos(2360, 510)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Clicked Axx avatar")
    time.sleep(2)

    # 3. Click tools button in dock
    user32.SetCursorPos(2420, 510)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Clicked tools button to open panel")
    time.sleep(2)

    # 4. Drag the panel by its header to demonstrate independent movement and elastic tendril
    header_x = 2480
    header_y = 440
    user32.SetCursorPos(header_x, header_y)
    time.sleep(0.3)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    print("Panel header grabbed")
    time.sleep(0.2)

    for step in range(20):
        user32.SetCursorPos(header_x + step * 8, header_y - step * 5)
        time.sleep(0.04)

    for step in range(8):
        user32.SetCursorPos(header_x + 160 - step * 5, header_y - 100 + step * 3)
        time.sleep(0.04)

    user32.mouse_event(0x0004, 0, 0, 0, 0)
    print("Panel released at new persistent position")
    time.sleep(2)

    # 5. Press Esc to demonstrate smooth folding/dismissal
    user32.keybd_event(0x1B, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(0x1B, 0, 2, 0)
    print("Escape key sent to fold panel")
    time.sleep(2)

    ff_out, ff_err = ff_p.communicate()
    ps_p.wait()
    print(f"FFmpeg exit: {ff_p.returncode}")
    if ff_err:
        print(f"FFmpeg log: {ff_err.decode(errors='replace')}")
    out_path = Path(out)
    if out_path.exists():
        print(f"SUCCESS: Video saved to {out_path} ({out_path.stat().st_size} bytes)")
        shot_path = out_path.with_suffix('.png')
        subprocess.run([
            "ffmpeg", "-y", "-ss", "00:00:08", "-i", str(out_path),
            "-vframes", "1", "-q:v", "2", str(shot_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Screenshot saved to {shot_path}")
    else:
        print("FAILED to create video")
