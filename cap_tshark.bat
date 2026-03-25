@echo off
echo === Wireshark USB Capture ===
echo Run as Administrator!
echo.
echo 1. Change DPI in Swarm II
echo 2. Wait 2 seconds
echo 3. Press Ctrl+C here to stop
echo.

"C:\Program Files\Wireshark\tshark.exe" -D 2>&1 | findstr USBPcap
echo.
set /p HUB="Enter the interface number for USBPcap (from list above): "
echo.
echo Capturing on interface %HUB%...
"C:\Program Files\Wireshark\tshark.exe" -i %HUB% -w "C:\Claude Folder\tshark_cap.pcapng"
echo Done!
pause
