param(
    [string]$Out = "shot.png",
    [string]$Match = "CleanBoost"
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class WinCap {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int max);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("shcore.dll")] public static extern int SetProcessDpiAwareness(int value);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

[void][WinCap]::SetProcessDpiAwareness(1)

$script:hwnd = [IntPtr]::Zero
$callback = [WinCap+EnumWindowsProc]{
    param($h, $l)
    if ([WinCap]::IsWindowVisible($h)) {
        $sb = New-Object System.Text.StringBuilder 512
        [void][WinCap]::GetWindowTextW($h, $sb, 512)
        if ($sb.ToString().StartsWith($Match)) {
            $script:hwnd = $h
            return $false
        }
    }
    return $true
}
[void][WinCap]::EnumWindows($callback, [IntPtr]::Zero)

if ($script:hwnd -eq [IntPtr]::Zero) {
    Write-Output "window-not-found"
    exit 1
}

$rect = New-Object WinCap+RECT
[void][WinCap]::GetWindowRect($script:hwnd, [ref]$rect)
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) {
    Write-Output "bad-rect"
    exit 1
}

[void][WinCap]::SetForegroundWindow($script:hwnd)
Start-Sleep -Milliseconds 350

$bmp = New-Object System.Drawing.Bitmap $width, $height
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $gfx.GetHdc()
$ok = [WinCap]::PrintWindow($script:hwnd, $hdc, 2)
$gfx.ReleaseHdc($hdc)
$gfx.Dispose()

if (-not $ok) {
    $gfx2 = [System.Drawing.Graphics]::FromImage($bmp)
    $gfx2.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
    $gfx2.Dispose()
}

$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "saved $Out ${width}x${height}"
