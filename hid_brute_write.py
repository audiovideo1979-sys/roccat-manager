"""
Brute-force HID write test — try every possible write method on every interface.

The spy showed us read-only state. SWARM II must use output reports or
a different interface to send commands. This script tries everything.
"""
import hid
import time
import sys

VENDOR = 0x10F5
DONGLE_PID = 0x5017
MOUSE_PID = 0x5019

TARGET_DPI = 450
TARGET_BYTE = TARGET_DPI // 50  # 0x09

def hex_line(data, count=32):
    if not data:
        return "(none)"
    return " ".join("%02X" % b for b in data[:count])

def try_feature_write(handle, label, report_id, data):
    """Try send_feature_report."""
    buf = bytearray(256)
    buf[0] = report_id
    for i, b in enumerate(data):
        buf[i + 1] = b
    try:
        result = handle.send_feature_report(bytes(buf))
        print("  [feature 0x%02X] sent %d bytes, returned %s" % (report_id, len(data) + 1, result))
        return True
    except Exception as e:
        print("  [feature 0x%02X] ERROR: %s" % (report_id, e))
        return False

def try_output_write(handle, label, report_id, data):
    """Try hid.write() which sends output reports."""
    buf = bytearray([report_id] + list(data))
    # Pad to at least 64 bytes (common HID report size)
    while len(buf) < 64:
        buf.append(0)
    try:
        result = handle.write(bytes(buf))
        print("  [output  0x%02X] sent %d bytes, returned %s" % (report_id, len(buf), result))
        return True
    except Exception as e:
        print("  [output  0x%02X] ERROR: %s" % (report_id, e))
        return False

def read_mouse_dpi():
    """Read current DPI from any mouse 0xFF01 interface."""
    for d in hid.enumerate(VENDOR, MOUSE_PID):
        if d["usage_page"] == 0xFF01:
            try:
                h = hid.device()
                h.open_path(d["path"])
                data = h.get_feature_report(0x06, 256)
                h.close()
                if data and len(data) > 17:
                    stages = []
                    for i in range(5):
                        off = 1 + i * 4
                        stages.append(data[off] * 50)
                    return stages
            except:
                pass
    return None

def main():
    print("=" * 60)
    print("ROCCAT Brute-Force Write Test")
    print("Target: %d DPI (0x%02X)" % (TARGET_DPI, TARGET_BYTE))
    print("=" * 60)
    print()

    # Read baseline DPI
    baseline = read_mouse_dpi()
    print("Baseline DPI stages: %s" % baseline)
    print()

    # Enumerate ALL vendor interfaces
    all_devs = []
    for d in hid.enumerate(VENDOR):
        up = d["usage_page"]
        pid = d["product_id"]
        iface = d["interface_number"]
        name = "DONGLE" if pid == DONGLE_PID else "MOUSE"
        label = "%s PID=%04X IF=%d UP=%04X" % (name, pid, iface, up)
        # Include vendor pages AND standard HID pages on vendor devices
        all_devs.append({"path": d["path"], "label": label, "up": up, "pid": pid, "iface": iface})

    # Deduplicate by path
    seen = set()
    unique_devs = []
    for d in all_devs:
        key = d["path"]
        if key not in seen:
            seen.add(key)
            unique_devs.append(d)

    print("All ROCCAT interfaces (%d unique):" % len(unique_devs))
    for d in unique_devs:
        print("  %s" % d["label"])
    print()

    # =====================================================
    # PHASE 1: Try OUTPUT reports on each vendor interface
    # =====================================================
    print("=" * 60)
    print("PHASE 1: Output reports (hid.write)")
    print("=" * 60)
    print()

    # DPI command patterns to try
    # Pattern A: SWARM-style dongle command
    cmd_a = [0x01, 0x44, 0x08, 0x11, 0x01, 0x01, 0x5A,
             0xFF, 0xFF, 0xFF, 0xFF,
             TARGET_BYTE, TARGET_BYTE, TARGET_BYTE,
             TARGET_BYTE, TARGET_BYTE, TARGET_BYTE]

    # Pattern B: Simple DPI value
    cmd_b = [TARGET_BYTE]

    # Pattern C: Kone Pro style (report 0x04 = profile select, 0x06 = settings)
    cmd_c_04 = [0x01]  # select profile 1
    cmd_c_06 = [0x00, TARGET_BYTE, 0x00, 0x00]  # DPI setting

    for d in unique_devs:
        if d["up"] not in (0xFF00, 0xFF01, 0xFF02, 0xFF03):
            continue  # skip standard HID interfaces

        print("--- %s ---" % d["label"])
        try:
            h = hid.device()
            h.open_path(d["path"])

            # Try output report 0x06 with SWARM command
            try_output_write(h, d["label"], 0x06, cmd_a)

            # Try output report 0x08
            try_output_write(h, d["label"], 0x08, cmd_a)

            # Try output report 0x04 (profile select)
            try_output_write(h, d["label"], 0x04, cmd_c_04)

            # Try output report 0x90 (Kone Pro init)
            try_output_write(h, d["label"], 0x90, [0x01])

            # Try output report 0x00
            try_output_write(h, d["label"], 0x00, cmd_a)

            h.close()
        except Exception as e:
            print("  Cannot open: %s" % e)
        print()

    # Check if DPI changed
    after1 = read_mouse_dpi()
    print("DPI after Phase 1: %s" % after1)
    if after1 != baseline:
        print("*** DPI CHANGED IN PHASE 1! ***")
        return
    print()

    # =====================================================
    # PHASE 2: Try feature reports with different formats
    # on the dongle
    # =====================================================
    print("=" * 60)
    print("PHASE 2: Feature reports with alternate formats")
    print("=" * 60)
    print()

    for d in unique_devs:
        if d["up"] not in (0xFF00, 0xFF01, 0xFF02, 0xFF03):
            continue

        print("--- %s ---" % d["label"])
        try:
            h = hid.device()
            h.open_path(d["path"])

            # Try writing feature reports 0x00 through 0x0F
            for rid in range(0x10):
                # Build a DPI command for this report
                data = bytearray(256)
                data[0] = rid
                # Try putting DPI value at various offsets
                data[1] = TARGET_BYTE
                data[2] = 0x00
                data[3] = 0x00
                data[4] = TARGET_BYTE
                try:
                    result = h.send_feature_report(bytes(data))
                    if result > 0:
                        # Read it back
                        try:
                            readback = h.get_feature_report(rid, 256)
                            if readback and readback[1] == TARGET_BYTE:
                                print("  [feature 0x%02X] ACCEPTED! Readback byte[1]=0x%02X" % (rid, readback[1]))
                        except:
                            pass
                except:
                    pass

            h.close()
        except Exception as e:
            print("  Cannot open: %s" % e)
        print()

    after2 = read_mouse_dpi()
    print("DPI after Phase 2: %s" % after2)
    if after2 != baseline:
        print("*** DPI CHANGED IN PHASE 2! ***")
        return
    print()

    # =====================================================
    # PHASE 3: Try the mouse's 0xFF00 and 0xFF02 interfaces
    # These had no readable reports — might be write-only
    # =====================================================
    print("=" * 60)
    print("PHASE 3: Mouse write-only interfaces (0xFF00, 0xFF02)")
    print("=" * 60)
    print()

    for d in unique_devs:
        if d["pid"] != MOUSE_PID:
            continue
        if d["up"] not in (0xFF00, 0xFF02):
            continue

        print("--- %s ---" % d["label"])
        try:
            h = hid.device()
            h.open_path(d["path"])

            # Try writing various DPI command formats
            for rid in [0x04, 0x06, 0x08, 0x0A, 0x0E, 0x0F]:
                # Format 1: Simple DPI at byte 1
                buf = bytearray(64)
                buf[0] = rid
                buf[1] = TARGET_BYTE
                try_output_write(h, d["label"], rid, [TARGET_BYTE])

                # Format 2: With command prefix
                try_output_write(h, d["label"], rid,
                    [0x11, 0x01, TARGET_BYTE, 0x00, TARGET_BYTE, 0x00])

            # Try feature reports too
            for rid in [0x04, 0x06, 0x08]:
                data = bytearray(256)
                data[0] = rid
                data[1] = TARGET_BYTE
                data[2] = 0xFF
                data[3] = 0x00
                data[4] = 0x00
                data[5] = TARGET_BYTE
                try:
                    h.send_feature_report(bytes(data))
                    print("  [feature 0x%02X] sent" % rid)
                except Exception as e:
                    print("  [feature 0x%02X] error: %s" % (rid, str(e)[:40]))

            h.close()
        except Exception as e:
            print("  Cannot open: %s" % e)
        print()

    after3 = read_mouse_dpi()
    print("DPI after Phase 3: %s" % after3)
    if after3 != baseline:
        print("*** DPI CHANGED IN PHASE 3! ***")
        return

    print()
    print("=" * 60)
    print("RESULT: No method changed the actual DPI.")
    print()
    print("This means SWARM II likely uses:")
    print("  a) Raw USB control transfers (not HID layer)")
    print("  b) A proprietary driver/filter driver")
    print("  c) Direct USB pipe writes bypassing HID")
    print()
    print("Next step: Use API Monitor to hook SWARM II's")
    print("  HidD_SetFeature / HidD_SetOutputReport /")
    print("  DeviceIoControl / WriteFile calls")
    print("=" * 60)

if __name__ == "__main__":
    main()
