@echo off
echo === Simple USB Capture ===
echo Run as Administrator!
echo.
echo This will try each hub. When you see device list with "Kone XP Air",
echo just press Enter to capture ALL devices on that hub.
echo Then change DPI in Swarm II, wait 2 sec, press Ctrl+C.
echo.
echo If you DON'T see Kone XP Air, press Q to quit and try next hub.
echo.

set /p HUB="Which hub? (1-5): "
echo.
echo Capturing USBPcap%HUB% to fresh_cap.pcap...
"C:\Program Files\USBPcap\USBPcapCMD.exe" -d \\.\USBPcap%HUB% -o "C:\Claude Folder\fresh_cap.pcap" -A
echo.
echo Done!
pause
