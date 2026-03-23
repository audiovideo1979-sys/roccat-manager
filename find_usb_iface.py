"""Find which USBPcap interface has the ROCCAT dongle."""
import subprocess, os, time

USBPCAP = r"C:\Program Files\USBPcap\USBPcapCMD.exe"

for i in range(1, 6):
    iface = r"\\.\USBPcap%d" % i
    outfile = "test_cap_%d.pcap" % i
    if os.path.exists(outfile):
        os.remove(outfile)
    try:
        proc = subprocess.Popen(
            [USBPCAP, "-d", iface, "-o", outfile, "-A"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        time.sleep(1.5)
        proc.terminate()
        proc.wait(timeout=3)
        size = os.path.getsize(outfile) if os.path.exists(outfile) else 0
        print("USBPcap%d: size=%d bytes" % (i, size))
    except Exception as e:
        print("USBPcap%d: error=%s" % (i, e))
    finally:
        if os.path.exists(outfile):
            os.remove(outfile)
