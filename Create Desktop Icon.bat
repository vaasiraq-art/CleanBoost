@echo off
rem Put a CleanBoost icon on your Desktop.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "tools\make_shortcut.ps1"
if errorlevel 1 (
    echo.
    echo Could not create the shortcut.
    pause
)
