"""
Capture USB traffic while SWARM II saves a profile change.

Usage:
  1. Open SWARM II and navigate to a profile
  2. Run this script
  3. When prompted, make a small change (e.g. DPI) in SWARM II and click save
  4. Press Enter when done
  5. Script saves the capture to swarm_capture.pcap
"""
import subprocess, os, sys, time

USBPCAP = r"C:\Program Files\USBPcap\USBPcapCMD.exe"
IFACE = r"\\.\USBPcap1"
OUTFILE = "swarm_capture.pcap"

if os.path.exists(OUTFILE):
    os.remove(OUTFILE)

print("=" * 60)
print("ROCCAT USB Capture")
print("=" * 60)
print()
print("Starting USB capture on USBPcap1...")
print()

# Start capture - capture ALL data (no snaplen limit)
proc = subprocess.Popen(
    [USBPCAP, "-d", IFACE, "-o", OUTFILE, "-A", "--snaplen", "65535"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE
)

time.sleep(1)
print("CAPTURING! Now do the following:")
print("  1. In SWARM II, change a DPI value (e.g. 800 -> 850)")
print("  2. Click the save/apply button")
print("  3. Wait 2-3 seconds")
print("  4. Press ENTER here when done")
print()

input(">>> Press ENTER after making the change in SWARM II... ")

print()
print("Stopping capture...")
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

time.sleep(0.5)
size = os.path.getsize(OUTFILE) if os.path.exists(OUTFILE) else 0
print("Captured: %s (%d bytes)" % (OUTFILE, size))

if size > 100:
    print("SUCCESS - Got USB traffic! Analyze with:")
    print('  tshark -r swarm_capture.pcap -Y "usb.transfer_type==0x02" -T fields -e usb.src -e usb.dst -e usb.data_len -e usb.capdata')
    print("  or open in Wireshark")
else:
    print("WARNING - Very little data captured.")
    print("The dongle might be on a different USBPcap interface,")
    print("or USBPcap needs a reboot to load its driver.")
    print("Try: reboot, then run this again.")
