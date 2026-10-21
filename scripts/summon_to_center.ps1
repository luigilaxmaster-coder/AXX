Add-Type @"
using System;
using System.Runtime.InteropServices;

public class Summoner {
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern IntPtr OpenEvent(uint dwDesiredAccess, bool bInheritHandle, string lpName);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetEvent(IntPtr hEvent);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool CloseHandle(IntPtr hObject);

    public static bool Summon(int x, int y) {
        SetCursorPos(x, y);
        IntPtr hEvent = OpenEvent(0x0002, false, "Local\\AxxResidentSummon-com.axx.desktop"); // EVENT_MODIFY_STATE = 0x0002
        if (hEvent == IntPtr.Zero) {
            Console.WriteLine("Could not open summon event.");
            return false;
        }
        bool ok = SetEvent(hEvent);
        CloseHandle(hEvent);
        return ok;
    }
}
"@

$ok = [Summoner]::Summon(650, 400)
Write-Host "Summon triggered: $ok"
