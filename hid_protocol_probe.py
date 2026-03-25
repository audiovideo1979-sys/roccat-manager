"""
Probe Kone XP Air dongle using known ROCCAT protocol report IDs.
Based on eruption-project and libratbag reverse engineering.

Known report IDs:
  0x01 - Status polling (ready check)
  0x04 - Init / profile query
  0x06 - Profile/DPI configuration
  0x09 - Device info
  0x0d - LED color data
  0x0e - Configuration setup
  0x11 - DPI / poll rate / angle-snapping / debounce
  0x90 - Wireless control command (Kone Pro Air style)
"""
import hid
import time
import sys

VID = 0x10F5
DONGLE_PID = 0x5017
DOCK_PID = 0x5019

def find_device(pid, usage_page=None, interface=None):
    """Find and return device info matching criteria"""
    for d in hid.enumerate():
        if d['vendor_id'] == VID and d['product_id'] == pid:
            if usage_page and d['usage_page'] != usage_page:
                continue
            if interface is not None and d['interface_number'] != interface:
                continue
            return d
    return None

def open_device(info):
    dev = hid.device()
    dev.open_path(info['path'])
    dev.set_nonblocking(1)
    return dev

def hex_dump(data, prefix=""):
    if data:
        print(f"{prefix}{' '.join(f'{b:02x}' for b in data)}")
    else:
        print(f"{prefix}(no data)")

def try_read_feature(dev, report_id, size=256):
    """Try to read a feature report"""
    try:
        data = dev.get_feature_report(report_id, size)
        return data
    except Exception as e:
        return None

def try_send_feature(dev, data):
    """Try to send a feature report"""
    try:
        result = dev.send_feature_report(data)
        return result
    except Exception as e:
        print(f"  send_feature_report error: {e}")
        return None

def try_write(dev, data):
    """Try an output report (hid_write)"""
    try:
        result = dev.write(data)
        return result
    except Exception as e:
        print(f"  hid_write error: {e}")
        return None

def read_input(dev, timeout_ms=200):
    """Read any pending input reports"""
    dev.set_nonblocking(1)
    start = time.time()
    while (time.time() - start) * 1000 < timeout_ms:
        data = dev.read(256)
        if data:
            return data
        time.sleep(0.01)
    return None

def decode_dpi(lsb, msb=0):
    """Decode DPI value from ROCCAT encoding"""
    raw = lsb + (msb << 8)
    return raw * 50

def probe_report(dev, rid, label):
    """Read a feature report and display it"""
    data = try_read_feature(dev, rid)
    if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
        print(f"\n  Report 0x{rid:02x} ({label}): {len(data)} bytes")
        hex_dump(data, "    ")
        return data
    return None

def main():
    print("=== Kone XP Air Protocol Probe ===\n")

    # List all device interfaces
    print("Available interfaces:")
    for d in hid.enumerate():
        if d['vendor_id'] == VID:
            print(f"  PID={d['product_id']:04x} IF={d['interface_number']} "
                  f"UP={d['usage_page']:04x}:{d['usage']:04x} "
                  f"product={d['product_string']}")

    # Try dongle interface 2 (vendor-specific, 0xff03) - this is where eruption sends commands
    print("\n--- Probing Dongle IF2 (UP=0xff03) ---")
    info = find_device(DONGLE_PID, usage_page=0xff03)
    if not info:
        print("  Not found!")
    else:
        dev = open_device(info)

        # Read ALL possible feature reports (0x00 - 0xFF)
        print("\n  Scanning all feature reports 0x00-0xFF...")
        found_reports = {}
        for rid in range(256):
            data = try_read_feature(dev, rid)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                found_reports[rid] = data

        print(f"  Found {len(found_reports)} reports with data:")
        for rid, data in sorted(found_reports.items()):
            print(f"\n    Report 0x{rid:02x}: {len(data)} bytes")
            hex_dump(data, "      ")
            # Try to decode DPI if this is report 0x06 or 0x11
            if rid == 0x06:
                print("      Possible DPI decode (offset 7-16, value*50):")
                for i in range(7, min(17, len(data)), 2):
                    if i+1 < len(data):
                        dpi = decode_dpi(data[i], data[i+1])
                        if 50 <= dpi <= 50000:
                            print(f"        byte[{i}:{i+1}] = {dpi} DPI")
            if rid == 0x11:
                print("      Possible DPI/settings decode:")
                for i in range(2, min(20, len(data))):
                    val = data[i] * 50
                    if 50 <= val <= 50000:
                        print(f"        byte[{i}] = {val} DPI (raw {data[i]})")

        # Try the eruption init sequence
        print("\n  Trying eruption init commands...")

        # Report 0x04: init command
        for i in range(5):
            for j in [0x80, 0x90]:
                cmd = [0x04, i, j, 0x00]
                result = try_send_feature(dev, cmd)
                if result and result > 0:
                    print(f"    Sent 0x04 [{i}, 0x{j:02x}] -> ok ({result})")
                    # Read response
                    time.sleep(0.01)
                    resp = read_input(dev, 100)
                    if resp:
                        hex_dump(resp, f"      Response: ")
                    # Check status
                    status = try_read_feature(dev, 0x01, 4)
                    if status:
                        hex_dump(status, f"      Status: ")

        # Report 0x0e: config setup
        cmd = [0x0e, 0x06, 0x01, 0x01, 0x00, 0xff]
        result = try_send_feature(dev, cmd)
        print(f"\n    Sent 0x0e config: result={result}")

        # Try wireless command 0x90 (Kone Pro Air style)
        print("\n  Trying wireless command 0x90...")
        # Battery status query
        cmd90 = [0x00, 0x90, 0x0a] + [0x00] * 62
        result = try_write(dev, cmd90)
        print(f"    Sent 0x90/0x0a (battery): result={result}")
        time.sleep(0.05)
        resp = read_input(dev, 200)
        if resp:
            hex_dump(resp, "      Response: ")

        # Transceiver status
        cmd90 = [0x00, 0x90, 0x70] + [0x00] * 62
        result = try_write(dev, cmd90)
        print(f"    Sent 0x90/0x70 (transceiver): result={result}")
        time.sleep(0.05)
        resp = read_input(dev, 200)
        if resp:
            hex_dump(resp, "      Response: ")

        dev.close()

    # Try dongle IF0 (mouse HID, 0x0001:0x0002)
    print("\n\n--- Probing Dongle IF0 (mouse, UP=0x0001) ---")
    info = find_device(DONGLE_PID, usage_page=0x0001, interface=0)
    if info:
        dev = open_device(info)
        found = {}
        for rid in range(256):
            data = try_read_feature(dev, rid)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                found[rid] = data
        print(f"  Found {len(found)} reports:")
        for rid, data in sorted(found.items()):
            print(f"    Report 0x{rid:02x}: {len(data)} bytes")
            hex_dump(data, "      ")
        dev.close()

    # Try dock IF0 (vendor, 0xff01)
    print("\n\n--- Probing Dock IF0 (UP=0xff01) ---")
    info = find_device(DOCK_PID, usage_page=0xff01)
    if info:
        dev = open_device(info)
        found = {}
        for rid in range(256):
            data = try_read_feature(dev, rid)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                found[rid] = data
        print(f"  Found {len(found)} reports:")
        for rid, data in sorted(found.items()):
            print(f"    Report 0x{rid:02x}: {len(data)} bytes")
            hex_dump(data, "      ")
            if rid == 0x06:
                print("      Possible DPI decode (offset 7-16, value*50):")
                for i in range(7, min(17, len(data)), 2):
                    if i+1 < len(data):
                        dpi = decode_dpi(data[i], data[i+1])
                        if 50 <= dpi <= 50000:
                            print(f"        byte[{i}:{i+1}] = {dpi} DPI")
        dev.close()

    print("\n=== Probe Complete ===")

if __name__ == '__main__':
    main()
