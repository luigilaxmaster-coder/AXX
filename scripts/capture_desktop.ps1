$code = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;
using System.Threading;
using System.Runtime.InteropServices;

public class ScreenCapturer {
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

    public static void Capture(string outputPath) {
        Thread t = new Thread(() => {
            try {
                IntPtr hDesk = OpenDesktop("Default", 0, false, 0x01FF);
                if (hDesk != IntPtr.Zero) {
                    SetThreadDesktop(hDesk);
                }

                Rectangle bounds = SystemInformation.VirtualScreen;
                using (Bitmap bitmap = new Bitmap(bounds.Width, bounds.Height)) {
                    using (Graphics g = Graphics.FromImage(bitmap)) {
                        IntPtr hdcDest = g.GetHdc();
                        IntPtr hwndDesk = GetDesktopWindow();
                        IntPtr hdcSrc = GetWindowDC(hwndDesk);
                        BitBlt(hdcDest, 0, 0, bounds.Width, bounds.Height, hdcSrc, bounds.X, bounds.Y, 0x00CC0020 | 0x40000000);
                        ReleaseDC(hwndDesk, hdcSrc);
                        g.ReleaseHdc(hdcDest);
                    }

                    bitmap.Save(outputPath, ImageFormat.Png);
                }

                if (hDesk != IntPtr.Zero) {
                    CloseDesktop(hDesk);
                }
            } catch (Exception ex) {
                Console.WriteLine("Error in capture thread: " + ex.ToString());
            }
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
    }
}

'@
Add-Type -TypeDefinition $code -ReferencedAssemblies System.Windows.Forms, System.Drawing

$outPath = "C:\Users\luigi\.gemini\antigravity-ide\brain\c61d2cb8-2930-4017-ba42-771c28675612\current_screen.png"
[ScreenCapturer]::Capture($outPath)
Write-Output "Screenshot saved to $outPath"
