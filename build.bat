@echo off
REM Build ROCCAT Manager into a single Windows .exe.
REM   build.bat          -> windowed app (no console), dist\ROCCAT Manager.exe
REM   build.bat debug    -> same app but with a console window that shows startup errors
setlocal
cd /d "%~dp0"

echo(
echo === Installing build dependencies (first time takes a minute) ===
python -m pip install --upgrade pip
python -m pip install flask frida hidapi pywebview pythonnet pyinstaller
if errorlevel 1 (
    echo(
    echo Dependency install failed. Make sure "python" is on your PATH ^(64-bit^).
    pause
    exit /b 1
)

if /I "%~1"=="debug" (
    set "RM_DEBUG=1"
    echo(
    echo === Building DEBUG build ^(console visible^) ===
) else (
    set "RM_DEBUG="
    echo(
    echo === Building windowed build ===
)

python -m PyInstaller --noconfirm --clean roccat_manager.spec
if errorlevel 1 (
    echo(
    echo Build FAILED. Copy the red error text above and send it to Claude.
    pause
    exit /b 1
)

echo(
echo === Done ===
echo Your app:  "%~dp0dist\ROCCAT Manager.exe"
echo Double-click it, or pin it to your taskbar. Profiles are saved under
echo   %%APPDATA%%\ROCCAT Manager\profiles
echo(
pause
