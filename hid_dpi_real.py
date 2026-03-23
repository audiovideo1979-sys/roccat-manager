"""
Try multiple methods to actually change the mouse DPI.
The feature report on 0xff01 only updates a cache.
Need to find the real command path.
"""
import hid
import time
import sys

VENDOR_ID = 0x10F5

def find_all(pid=None, usage_page=None):
    results = []
    seen = set()
    for d in hid.enumerate():
        if d['vendor_id'] != VENDOR_ID:
            continue
        if pid and d['product_id'] != pid:
            continue
        if usage_page and d['usage_page'] != usage_page:
            continue
        key = d['path']
        if key not in seen:
            seen.add(key)
            results.append(d)
    return results

def try_dpi_change(label, dev, method, report_id, payload):
    """Try a DPI change method and pause so user can feel it."""
    print(f"\n--- {label} ---")
    try:
        if method == 'feature':
            dev.send_feature_report(payload)
        elif method == 'output':
            dev.write(payload)
        print(f"  Sent OK. Move mouse for 3 seconds...")
        time.sleep(3)
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False

# Target DPI: 0x06 = 300 DPI (very slow, unmistakable)
TARGET_DPI = 0x06

print("Each test sets DPI to 300 (very slow) for 3 seconds.")
print("Tell me which test makes the mouse slow!\n")

# === Test 1: Write to dongle via feature report 0x06 ===
dongle_devs = find_all(pid=0x5017, usage_page=0xFF03)
if dongle_devs:
    dev = hid.device()
    dev.open_path(dongle_devs[0]['path'])
    dev.set_nonblocking(1)

    # Read current dongle report 0x06
    data = list(dev.get_feature_report(0x06, 512))
    print(f"Dongle 0x06 current: {' '.join(f'{b:02x}' for b in data[:48])}")

    # Try writing modified data to dongle
    # Based on Swarm II data: 06 01 44 08 11 01 01 3c ff ff ff ff 14 32 50 14 32 50
    # Construct a command with modified DPI
    cmd = list(data[:64])
    # Try setting byte patterns that might contain DPI
    # Method A: write the report as-is with modified DPI bytes
    saved = list(data[:64])

    try_dpi_change("Test 1a: Dongle feature report 0x06 (modify bytes 12-14 as DPI)",
                   dev, 'feature', 0x06, cmd)

    # Method B: Try a Kone Pro style command via dongle
    # Profile select: [0x04, profile, 0x80, 0x00]
    cmd04 = [0x04, 0x00, 0x80, 0x00] + [0x00] * 60
    try_dpi_change("Test 1b: Dongle feature 0x04 profile select", dev, 'feature', 0x04, cmd04)

    # Method C: Output report to dongle with DPI command
    # From monitor: INPUT was 08 00 53 03 0b 11 3c 01...
    # Try sending similar as OUTPUT
    cmd08 = [0x08, 0x00, 0x53, 0x03, 0x0b, TARGET_DPI, 0x3c, 0x01] + [0xff]*4 + [0x00]*52
    try_dpi_change("Test 1c: Dongle output 0x08 with DPI command", dev, 'output', 0x08, cmd08)

    dev.close()

# === Test 2: Write to mouse IF=1 (0xff00) ===
print("\n=== Mouse IF=1 (Usage 0xff00) ===")
mouse_if1 = find_all(pid=0x5019, usage_page=0xFF00)
if mouse_if1:
    dev = hid.device()
    dev.open_path(mouse_if1[0]['path'])
    dev.set_nonblocking(1)

    # Kone Pro uses 69-byte profile data on report 0x06
    # Try constructing a profile with modified DPI
    # Kone Pro format: byte 6 = active DPI switch, bytes 7-16 = 5 DPI stages (LE16, val=dpi/50)
    profile = [0x06] + [0x00] * 68
    profile[6] = 0x00  # active DPI switch 0
    # DPI stage 0 = 300 DPI -> 300/50 = 6
    profile[7] = TARGET_DPI
    profile[8] = 0x00
    # DPI stage 1 = 2500
    profile[9] = 0x32
    profile[10] = 0x00
    # Fill other stages
    for i in range(3):
        profile[11 + i*2] = 0x50
        profile[12 + i*2] = 0x00
    # Polling rate
    profile[29] = 0x03  # 1000Hz

    try_dpi_change("Test 2a: Mouse IF=1 feature 0x06 (Kone Pro format)", dev, 'feature', 0x06, profile)

    # Try output report with DPI
    out_cmd = [0x06, TARGET_DPI, 0xff, 0x00, 0x00, 0x32, 0xff, 0xff, 0x00, 0x50, 0x00, 0xff, 0x00, 0x64, 0xff, 0xff, 0xff] + [0x00] * 47
    try_dpi_change("Test 2b: Mouse IF=1 output 0x06 with DPI data", dev, 'output', 0x06, out_cmd)

    # Try report 0x0D (used by eruption for LED, might also carry config)
    cmd0d = [0x0D, TARGET_DPI] + [0x00] * 62
    try_dpi_change("Test 2c: Mouse IF=1 feature 0x0D", dev, 'feature', 0x0D, cmd0d)

    dev.close()

# === Test 3: Write to mouse IF=2 (0xff02) ===
print("\n=== Mouse IF=2 (Usage 0xff02) ===")
mouse_if2 = find_all(pid=0x5019, usage_page=0xFF02)
if mouse_if2:
    dev = hid.device()
    dev.open_path(mouse_if2[0]['path'])
    dev.set_nonblocking(1)

    # Try similar DPI commands
    out_cmd = [0x06, TARGET_DPI, 0xff, 0x00, 0x00] + [0x00] * 59
    try_dpi_change("Test 3a: Mouse IF=2 feature 0x06 with DPI", dev, 'feature', 0x06, out_cmd)

    out_cmd2 = [0x06, TARGET_DPI, 0xff, 0x00, 0x00] + [0x00] * 59
    try_dpi_change("Test 3b: Mouse IF=2 output 0x06 with DPI", dev, 'output', 0x06, out_cmd2)

    dev.close()

# === Test 4: Write to mouse IF=0 (0xff01) but with report 0x08 ===
print("\n=== Mouse IF=0 (Usage 0xff01) report 0x08 ===")
mouse_if0 = find_all(pid=0x5019, usage_page=0xFF01)
if mouse_if0:
    dev = hid.device()
    dev.open_path(mouse_if0[0]['path'])
    dev.set_nonblocking(1)

    # Report 0x08 had: 08 01 ff 00 00 32 ff ff 00...
    # Byte 1 might be active stage, try setting DPI via 0x08
    data08 = list(dev.get_feature_report(0x08, 512))
    data08[1] = TARGET_DPI  # or maybe byte 1 is active stage
    try_dpi_change("Test 4a: Mouse IF=0 feature 0x08 (modify byte 1)", dev, 'feature', 0x08, data08[:64])

    # Try both 0x06 and 0x08 together
    data06 = list(dev.get_feature_report(0x06, 512))
    data06[1] = TARGET_DPI
    dev.send_feature_report(data06[:64])
    data08 = list(dev.get_feature_report(0x08, 512))
    data08[1] = TARGET_DPI
    try_dpi_change("Test 4b: Mouse IF=0 both 0x06 and 0x08 modified", dev, 'feature', 0x08, data08[:64])

    # Restore
    data06[1] = 0x14
    dev.send_feature_report(data06[:64])
    data08[1] = 0x01
    dev.send_feature_report(data08[:64])

    dev.close()

print("\n\nAll tests done. Which test number made the mouse slow?")
