"""Find which USBPcap interface has the ROCCAT dongle by generating HID traffic."""
import subprocess, os, time, threading, hid

USBPCAP = r"C:\Program Files\USBPcap\USBPcapCMD.exe"
VENDOR = 0x10F5
DONGLE_PID = 0x5017

def generate_hid_traffic():
    """Read from the dongle to generate USB traffic."""
    time.sleep(0.3)  # let captures start
    try:
        devs = hid.enumerate(VENDOR, DONGLE_PID)
        for d in devs:
            if d["usage_page"] == 0xFF03:
                h = hid.device()
                h.open_path(d["path"])
                for _ in range(5):
                    h.get_feature_report(0x06, 64)
                    time.sleep(0.1)
                h.close()
                print("  [HID] Generated traffic on dongle 0xFF03")
                return
    except Exception as e:
        print("  [HID] Error: %s" % e)

# Start traffic generator in background
t = threading.Thread(target=generate_hid_traffic, daemon=True)
t.start()

results = []
procs = []
files = []

# Start all captures simultaneously
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
        procs.append((i, proc))
        files.append(outfile)
    except Exception as e:
        print("USBPcap%d: failed to start: %s" % (i, e))

# Wait for traffic
time.sleep(3)
t.join(timeout=2)

# Stop all captures
for i, proc in procs:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except:
        proc.kill()

# Check sizes
for i, proc in procs:
    outfile = "test_cap_%d.pcap" % i
    size = os.path.getsize(outfile) if os.path.exists(outfile) else 0
    print("USBPcap%d: %d bytes%s" % (i, size, " <<<< HAS TRAFFIC" if size > 100 else ""))

# Cleanup
for f in files:
    if os.path.exists(f):
        os.remove(f)
