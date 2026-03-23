"""
HID Spy — Monitor all ROCCAT feature reports in real-time.
Detects changes when SWARM II pushes settings to the mouse.

Run this, then change DPI in SWARM II and save.
The spy will show which reports changed and the exact bytes that differ.
"""
import hid
import time
import sys
from collections import defaultdict

VENDOR = 0x10F5
DONGLE_PID = 0x5017
MOUSE_PID = 0x5019

# Vendor-specific usage pages (where config data lives)
VENDOR_PAGES = {0xFF00, 0xFF01, 0xFF02, 0xFF03}

def hex_dump(data, prefix=""):
    """Compact hex dump."""
    return prefix + " ".join("%02X" % b for b in data)

def diff_reports(old, new):
    """Show byte-level differences."""
    diffs = []
    for i in range(min(len(old), len(new))):
        if old[i] != new[i]:
            diffs.append((i, old[i], new[i]))
    if len(old) != len(new):
        diffs.append(("len", len(old), len(new)))
    return diffs

def main():
    print("=" * 70)
    print("ROCCAT HID Spy — Monitoring all vendor interfaces")
    print("=" * 70)
    print()

    # Enumerate all vendor-specific interfaces
    devices = []
    for d in hid.enumerate(VENDOR):
        if d["usage_page"] in VENDOR_PAGES:
            pid = d["product_id"]
            iface = d["interface_number"]
            usage = d["usage_page"]
            name = "DONGLE" if pid == DONGLE_PID else "MOUSE"
            label = "%s PID=%04X IF=%d UP=%04X" % (name, pid, iface, usage)
            devices.append({
                "path": d["path"],
                "label": label,
                "pid": pid,
                "iface": iface,
                "usage_page": usage,
            })

    print("Found %d vendor interfaces:" % len(devices))
    for d in devices:
        print("  %s" % d["label"])
    print()

    # Open all devices and read initial feature reports
    handles = []
    snapshots = {}  # (label, report_id) -> bytes

    for d in devices:
        try:
            h = hid.device()
            h.open_path(d["path"])
            h.set_nonblocking(1)
            handles.append((h, d))
            print("Opened: %s" % d["label"])

            # Read all possible feature reports (0x00 - 0x20)
            for rid in range(0x00, 0x21):
                try:
                    data = h.get_feature_report(rid, 256)
                    if data and len(data) > 1 and any(b != 0 for b in data[1:]):
                        key = (d["label"], rid)
                        snapshots[key] = bytes(data)
                        print("  Report 0x%02X: %d bytes [%s...]" % (
                            rid, len(data),
                            " ".join("%02X" % b for b in data[:16])
                        ))
                except:
                    pass
        except Exception as e:
            print("FAILED to open %s: %s" % (d["label"], e))

    print()
    print("-" * 70)
    print("BASELINE captured. Now change DPI in SWARM II and save!")
    print("Monitoring for changes... (Ctrl+C to stop)")
    print("-" * 70)
    print()

    # Also try to read input reports
    change_count = 0
    poll_count = 0
    start = time.time()

    try:
        while True:
            poll_count += 1
            elapsed = time.time() - start

            # Check input reports (non-blocking)
            for h, d in handles:
                try:
                    data = h.read(256)
                    if data:
                        print("[%.1fs] INPUT %s: %s" % (
                            elapsed, d["label"],
                            " ".join("%02X" % b for b in data[:32])
                        ))
                except:
                    pass

            # Poll feature reports every 0.5 seconds
            if poll_count % 5 == 0:
                for h, d in handles:
                    for rid in range(0x00, 0x21):
                        try:
                            data = h.get_feature_report(rid, 256)
                            if not data:
                                continue
                            key = (d["label"], rid)
                            current = bytes(data)

                            if key in snapshots:
                                if current != snapshots[key]:
                                    change_count += 1
                                    diffs = diff_reports(snapshots[key], current)
                                    print()
                                    print("[%.1fs] *** CHANGE #%d *** %s Report 0x%02X" % (
                                        elapsed, change_count, d["label"], rid
                                    ))
                                    for offset, old_val, new_val in diffs:
                                        if offset == "len":
                                            print("  Length: %d -> %d" % (old_val, new_val))
                                        else:
                                            print("  Byte[%d]: 0x%02X -> 0x%02X" % (offset, old_val, new_val))

                                    # Show full before/after for this report
                                    print("  BEFORE: %s" % " ".join("%02X" % b for b in snapshots[key][:32]))
                                    print("  AFTER:  %s" % " ".join("%02X" % b for b in current[:32]))
                                    print()

                                    snapshots[key] = current
                            else:
                                # New report appeared
                                if any(b != 0 for b in data[1:]):
                                    snapshots[key] = current
                                    print("[%.1fs] NEW report: %s 0x%02X (%d bytes)" % (
                                        elapsed, d["label"], rid, len(data)
                                    ))
                        except:
                            pass

            time.sleep(0.1)

    except KeyboardInterrupt:
        print()
        print("Stopped after %.1f seconds, %d changes detected." % (
            time.time() - start, change_count
        ))

    # Close all
    for h, d in handles:
        h.close()

if __name__ == "__main__":
    main()
