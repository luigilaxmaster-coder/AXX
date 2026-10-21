Add-Type @"
using System;
using System.Runtime.InteropServices;

public class KeySender {
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    public static void SendCtrlShiftD(IntPtr hwnd) {
        SetForegroundWindow(hwnd);
        System.Threading.Thread.Sleep(100);
        const byte VK_CONTROL = 0x11;
        const byte VK_SHIFT = 0x10;
        const byte VK_D = 0x44;
        const uint KEYEVENTF_KEYUP = 0x0002;

        keybd_event(VK_CONTROL, 0, 0, 0);
        keybd_event(VK_SHIFT, 0, 0, 0);
        keybd_event(VK_D, 0, 0, 0);

        keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0);
    }
}
"@

$axxHwnd = [IntPtr]0x310BCA
[KeySender]::SendCtrlShiftD($axxHwnd)
Write-Host "Sent Ctrl+Shift+D to $axxHwnd"
