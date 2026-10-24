@echo off
rem CleanBoost launcher - double click this file.
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "main.py"
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "main.py"
    exit /b %errorlevel%
)

echo Python 3.10 or newer is required.
echo Download it from https://www.python.org/downloads/windows/
pause
