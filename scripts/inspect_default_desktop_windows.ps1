Add-Type @"
using System;
using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Runtime.InteropServices;

public class WinDeskInspector {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern IntPtr OpenDesktop(string lpszDesktop, uint dwFlags, bool fInherit, uint dwDesiredAccess);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool SetThreadDesktop(IntPtr hDesktop);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool CloseDesktop(IntPtr hDesktop);

    [DllImport("user32.dll")]
    public static extern bool EnumDesktopWindows(IntPtr hDesktop, EnumWindowsProc lpfn, IntPtr lParam);

    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<string> Inspect(int targetPid) {
        var results = new List<string>();
        Thread t = new Thread(() => {
            IntPtr hDesk = OpenDesktop("Default", 0, false, 0x01FF);
            if (hDesk != IntPtr.Zero) {
                SetThreadDesktop(hDesk);
            }

            EnumDesktopWindows(hDesk, (hwnd, lParam) => {
                uint pid;
                GetWindowThreadProcessId(hwnd, out pid);
                if (pid == targetPid) {
                    var sbTitle = new StringBuilder(256);
                    GetWindowText(hwnd, sbTitle, 256);
                    var sbClass = new StringBuilder(256);
                    GetClassName(hwnd, sbClass, 256);
                    RECT r;
                    GetWindowRect(hwnd, out r);
                    bool vis = IsWindowVisible(hwnd);
                    int exStyle = GetWindowLong(hwnd, -20);
                    results.Add(string.Format("PID: {0} | HWND: 0x{1:X} | Vis: {2} | Rect: ({3},{4})-({5},{6}) [{7}x{8}] | Title: '{9}' | Class: '{10}' | ExStyle: 0x{11:X}",
                        pid, hwnd.ToInt64(), vis, r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top, sbTitle, sbClass, exStyle));
                }
                return true;
            }, IntPtr.Zero);

            if (hDesk != IntPtr.Zero) {
                CloseDesktop(hDesk);
            }
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        return results;
    }
}
"@

$axxProc = Get-Process -Name Axx -ErrorAction SilentlyContinue
if ($axxProc) {
    Write-Host "Inspecting windows on Default desktop for Axx PID $($axxProc.Id)..."
    $res = [WinDeskInspector]::Inspect($axxProc.Id)
    Write-Host "Found $($res.Count) windows:"
    $res | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Axx not running."
}
