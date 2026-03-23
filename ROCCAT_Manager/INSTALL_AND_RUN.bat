@echo off
title ROCCAT Manager — Setup
echo.
echo  ============================================
echo   ROCCAT Manager — First Time Setup
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python not found. Installing via winget...
    winget install Python.Python.3 --silent
    echo  [!] Restart this script after Python installs.
    pause
    exit
)

echo  [OK] Python found
echo.

:: Install dependencies
echo  Installing Python packages...
pip install flask pywinauto pywin32 --quiet
echo  [OK] Packages installed
echo.

:: Create profile folders
if not exist "%~dp0profiles" mkdir "%~dp0profiles"
echo  [OK] Profile folders ready
echo.

echo  ============================================
echo   Setup complete! Launching ROCCAT Manager...
echo  ============================================
echo.

:: Launch server
start "" python "%~dp0server.py"
timeout /t 2 /nobreak >nul
start "" http://localhost:5555

echo  ROCCAT Manager is running at http://localhost:5555
echo  Close this window to stop the server.
echo.
pause
