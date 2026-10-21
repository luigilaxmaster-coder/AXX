Add-Type @"
using System;
using System.Collections.Generic;
using System.Text;
using System.Runtime.InteropServices;

public class WinFinder {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

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

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<string> FindWindowsForPid(uint targetPid) {
        var results = new List<string>();
        EnumWindows((hwnd, lParam) => {
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
                results.Add(string.Format("HWND: 0x{0:X} | Vis: {1} | Rect: ({2},{3})-({4},{5}) [{6}x{7}] | Title: '{8}' | Class: '{9}'",
                    hwnd.ToInt64(), vis, r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top, sbTitle, sbClass));
            }
            return true;
        }, IntPtr.Zero);
        return results;
    }
}
"@

$axxPid = (Get-Process -Name Axx).Id
Write-Host "Searching for PID $axxPid..."
$res = [WinFinder]::FindWindowsForPid($axxPid)
if ($res.Count -eq 0) {
    Write-Host "No windows found for PID $axxPid."
} else {
    $res | ForEach-Object { Write-Host $_ }
}
