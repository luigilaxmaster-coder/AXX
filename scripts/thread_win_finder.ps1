Add-Type @"
using System;
using System.Collections.Generic;
using System.Text;
using System.Diagnostics;
using System.Runtime.InteropServices;

public class ThreadWinFinder {
    public delegate bool EnumThreadDelegate(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumThreadWindows(int dwThreadId, EnumThreadDelegate lpfn, IntPtr lParam);

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

    public static List<string> FindWindowsForProcess(int pid) {
        var results = new List<string>();
        Process p;
        try {
            p = Process.GetProcessById(pid);
        } catch {
            return results;
        }

        foreach (ProcessThread pt in p.Threads) {
            int tid = pt.Id;
            EnumThreadWindows(tid, (hwnd, lParam) => {
                var sbTitle = new StringBuilder(256);
                GetWindowText(hwnd, sbTitle, 256);
                var sbClass = new StringBuilder(256);
                GetClassName(hwnd, sbClass, 256);
                RECT r;
                GetWindowRect(hwnd, out r);
                bool vis = IsWindowVisible(hwnd);
                results.Add(string.Format("TID: {0} | HWND: 0x{1:X} | Vis: {2} | Rect: ({3},{4})-({5},{6}) [{7}x{8}] | Title: '{9}' | Class: '{10}'",
                    tid, hwnd.ToInt64(), vis, r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top, sbTitle, sbClass));
                return true;
            }, IntPtr.Zero);
        }
        return results;
    }
}
"@

$axxProc = Get-Process -Name Axx -ErrorAction SilentlyContinue
if ($axxProc) {
    $res = [ThreadWinFinder]::FindWindowsForProcess($axxProc.Id)
    Write-Host "Found $($res.Count) windows in Axx process threads:"
    $res | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "No Axx process found."
}
