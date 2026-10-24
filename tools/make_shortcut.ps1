# Creates a Desktop shortcut for CleanBoost with the app icon.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$main = Join-Path $root "main.py"
$icon = Join-Path $root "assets\icon.ico"

if (-not (Test-Path $main)) {
    Write-Error "main.py not found next to the tools folder."
    exit 1
}

$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Error "Python was not found on PATH. Install Python 3.10+ first."
        exit 1
    }
    $pythonw = $python
    Write-Warning "pythonw.exe not found; using python.exe (a console window may appear)."
}

$desktop = [Environment]::GetFolderPath("Desktop")
if (-not (Test-Path $desktop)) {
    Write-Error "Desktop folder not found."
    exit 1
}

$linkPath = Join-Path $desktop "CleanBoost.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $main + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$icon,0"
$shortcut.Description = "CleanBoost - clean junk, free up space, speed up Windows"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Output "Shortcut created: $linkPath"
Write-Output "Target: $pythonw `"$main`""
