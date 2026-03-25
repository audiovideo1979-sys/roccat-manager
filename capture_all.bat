@echo off
echo === Capturing ALL USB hubs ===
echo Run as Administrator!
echo.
echo 1. Change a DPI value in Swarm II
echo 2. Wait 2 seconds
echo 3. Press any key here to stop
echo.

start /B "cap1" "C:\Program Files\USBPcap\USBPcapCMD.exe" --extcap-interface USBPcap1 -o "C:\Claude Folder\fresh1.pcap" --snaplen 65535
start /B "cap2" "C:\Program Files\USBPcap\USBPcapCMD.exe" --extcap-interface USBPcap2 -o "C:\Claude Folder\fresh2.pcap" --snaplen 65535
start /B "cap3" "C:\Program Files\USBPcap\USBPcapCMD.exe" --extcap-interface USBPcap3 -o "C:\Claude Folder\fresh3.pcap" --snaplen 65535
start /B "cap4" "C:\Program Files\USBPcap\USBPcapCMD.exe" --extcap-interface USBPcap4 -o "C:\Claude Folder\fresh4.pcap" --snaplen 65535
start /B "cap5" "C:\Program Files\USBPcap\USBPcapCMD.exe" --extcap-interface USBPcap5 -o "C:\Claude Folder\fresh5.pcap" --snaplen 65535

echo All captures started. Make your DPI change now!
pause

taskkill /F /IM USBPcapCMD.exe >nul 2>&1
echo Captures stopped.
pause
