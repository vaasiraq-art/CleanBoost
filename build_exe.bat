@echo off
rem Build a single-file CleanBoost.exe with PyInstaller.
cd /d "%~dp0"

echo Installing PyInstaller if needed...
python -m pip install --upgrade pyinstaller || goto :error

echo Building...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name CleanBoost ^
    --icon "assets\icon.ico" ^
    main.py || goto :error

echo.
echo Done. Your app is at: dist\CleanBoost.exe
pause
exit /b 0

:error
echo.
echo Build failed. Make sure Python 3.10+ is installed and on PATH.
pause
exit /b 1
