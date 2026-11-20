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

REM Both PCs run the program from Google Drive, so put the new build there too. drivefolders.py finds
REM My Drive on whatever drive letter Google Drive uses here. (No labels/goto: safe with any line endings.)
set "DRIVE_APP="
set "COPIED="
for /f "usebackq delims=" %%P in (`python "ROCCAT_Manager\drivefolders.py" ROCCAT_Manager_Full`) do set "DRIVE_APP=%%P"
echo(
if defined DRIVE_APP copy /Y "dist\ROCCAT Manager.exe" "%DRIVE_APP%\" >nul && set "COPIED=1"
if defined COPIED echo Copied to Google Drive:  "%DRIVE_APP%\ROCCAT Manager.exe"
if defined COPIED echo Run it from there on both PCs. Let Google Drive finish syncing before you switch PCs.
if defined DRIVE_APP if not defined COPIED echo Could not copy it into "%DRIVE_APP%". If ROCCAT Manager is open, close it and run build.bat again.
if not defined DRIVE_APP echo Google Drive folder not found, so the app was not copied there. Start Google Drive for desktop and run build.bat again.
echo(
echo Profiles live in the Google Drive folder "ROCCAT Manager Data" when the app finds it,
echo otherwise in %%APPDATA%%\ROCCAT Manager\profiles on this PC only. The app shows which.
echo(
pause
