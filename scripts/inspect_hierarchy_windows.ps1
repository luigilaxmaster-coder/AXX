Add-Type @"
using System;
using System.Collections.Generic;
using System.Text;
using System.Diagnostics;
using System.Runtime.InteropServices;

public class WinInspector {
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

    [DllImport("user32.dll")]
    public static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<string> FindWindows(int[] pids) {
        var results = new List<string>();
        var pidSet = new HashSet<int>(pids);
        EnumWindows((hwnd, lParam) => {
            uint pid;
            GetWindowThreadProcessId(hwnd, out pid);
            if (pidSet.Contains((int)pid)) {
                var sbTitle = new StringBuilder(256);
                GetWindowText(hwnd, sbTitle, 256);
                var sbClass = new StringBuilder(256);
                GetClassName(hwnd, sbClass, 256);
                RECT r;
                GetWindowRect(hwnd, out r);
                bool vis = IsWindowVisible(hwnd);
                int exStyle = GetWindowLong(hwnd, -20);
                int style = GetWindowLong(hwnd, -16);
                results.Add(string.Format("PID: {0} | HWND: 0x{1:X} | Vis: {2} | Rect: ({3},{4})-({5},{6}) [{7}x{8}] | Title: '{9}' | Class: '{10}' | Style: 0x{11:X} | ExStyle: 0x{12:X}",
                    pid, hwnd.ToInt64(), vis, r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top, sbTitle, sbClass, style, exStyle));
            }
            return true;
        }, IntPtr.Zero);
        return results;
    }
}
"@

$pids = @(16108, 21284)
# Also add any children of 21284
$edgeChildren = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq 21284 }
foreach ($ec in $edgeChildren) { $pids += [int]$ec.ProcessId }

$res = [WinInspector]::FindWindows($pids)
Write-Host "Found $($res.Count) windows:"
$res | ForEach-Object { Write-Host $_ }
