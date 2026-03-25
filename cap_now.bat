@echo off
echo === USB Capture - EDIT a DPI value ===
echo Run as Administrator!
echo.
echo 1. EDIT a DPI value in Swarm II (change the number, not just switch stages)
echo 2. Wait 3 seconds after the change
echo 3. Press any key here to stop
echo.

for %%i in (1 2 3 4 5) do (
    start "" /B "C:\Program Files\USBPcap\USBPcapCMD.exe" -d \\.\USBPcap%%i -o "C:\Claude Folder\edit_cap%%i.pcap" -A
)

echo All hubs capturing. EDIT a DPI value now!
pause

taskkill /F /IM USBPcapCMD.exe >nul 2>&1
echo Stopped.

for %%i in (1 2 3 4 5) do (
    for %%f in ("C:\Claude Folder\edit_cap%%i.pcap") do (
        echo edit_cap%%i.pcap: %%~zf bytes
    )
)
pause
