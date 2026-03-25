"""
Monitor all HID traffic on Kone XP Air dongle and docking interfaces
while Swarm II makes changes. Run this BEFORE making changes in Swarm II.

This polls all feature reports on all interfaces to detect what Swarm II writes.
"""
import hid
import time
import sys
import json
from datetime import datetime

VID = 0x10F5
DONGLE_PID = 0x5017
DOCK_PID = 0x5019

def enum_devices():
    """List all Kone XP Air HID interfaces"""
    devices = []
    for d in hid.enumerate():
        if d['vendor_id'] == VID and d['product_id'] in (DONGLE_PID, DOCK_PID):
            devices.append(d)
            print(f"  PID={d['product_id']:04x} IF={d['interface_number']} "
                  f"usage={d['usage_page']:04x}:{d['usage']:04x} "
                  f"product={d['product_string']}")
    return devices

def read_all_reports(dev, label, report_ids=range(0, 16)):
    """Read all feature reports and return as dict"""
    results = {}
    for rid in report_ids:
        try:
            data = dev.get_feature_report(rid, 256)
            if data and len(data) > 1 and not all(b == 0 for b in data[1:]):
                results[rid] = list(data)
        except Exception:
            pass
    return results

def snapshot_all_devices(devices):
    """Take a snapshot of all feature reports on all devices"""
    snap = {}
    for info in devices:
        key = f"PID_{info['product_id']:04x}_IF{info['interface_number']}_UP{info['usage_page']:04x}"
        try:
            dev = hid.device()
            dev.open_path(info['path'])
            dev.set_nonblocking(1)
            reports = read_all_reports(dev, key)
            snap[key] = reports
            dev.close()
        except Exception as e:
            snap[key] = {'error': str(e)}
    return snap

def compare_snapshots(before, after):
    """Find differences between two snapshots"""
    changes = []
    all_keys = set(list(before.keys()) + list(after.keys()))
    for key in sorted(all_keys):
        b = before.get(key, {})
        a = after.get(key, {})
        if isinstance(b, dict) and 'error' in b:
            continue
        if isinstance(a, dict) and 'error' in a:
            continue
        all_rids = set(list(b.keys()) + list(a.keys()))
        for rid in sorted(all_rids):
            bd = b.get(rid)
            ad = a.get(rid)
            if bd != ad:
                changes.append({
                    'device': key,
                    'report_id': rid,
                    'before': bd,
                    'after': ad
                })
    return changes

def monitor_input_reports(devices, duration=10):
    """Monitor INPUT reports (interrupt transfers) from all devices"""
    opened = []
    for info in devices:
        key = f"PID_{info['product_id']:04x}_IF{info['interface_number']}_UP{info['usage_page']:04x}"
        try:
            dev = hid.device()
            dev.open_path(info['path'])
            dev.set_nonblocking(1)
            opened.append((dev, key, info))
        except Exception as e:
            print(f"  Could not open {key}: {e}")

    print(f"\nMonitoring INPUT reports for {duration}s...")
    print("Make your change in Swarm II NOW!\n")

    start = time.time()
    input_reports = []
    while time.time() - start < duration:
        for dev, key, info in opened:
            try:
                data = dev.read(256)
                if data:
                    ts = time.time() - start
                    hex_data = ' '.join(f'{b:02x}' for b in data)
                    entry = {'time': round(ts, 3), 'device': key, 'data': list(data)}
                    input_reports.append(entry)
                    print(f"  [{ts:6.3f}s] {key}: {hex_data}")
            except Exception:
                pass
        time.sleep(0.001)

    for dev, _, _ in opened:
        dev.close()

    return input_reports

def main():
    print("=== Kone XP Air HID Sniffer ===\n")
    print("Enumerating devices...")
    devices = enum_devices()

    if not devices:
        print("No Kone XP Air devices found!")
        return

    # Take baseline snapshot
    print(f"\nTaking baseline snapshot of {len(devices)} interfaces...")
    before = snapshot_all_devices(devices)
    for key, reports in before.items():
        if isinstance(reports, dict) and 'error' not in reports:
            print(f"  {key}: {len(reports)} reports with data")

    # Monitor input reports
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    input_reports = monitor_input_reports(devices, duration)

    # Take after snapshot
    print(f"\nTaking post-change snapshot...")
    after = snapshot_all_devices(devices)

    # Compare
    changes = compare_snapshots(before, after)

    print(f"\n=== RESULTS ===")
    print(f"Input reports received: {len(input_reports)}")
    print(f"Feature report changes: {len(changes)}")

    for c in changes:
        print(f"\n  Device: {c['device']}, Report ID: {c['report_id']}")
        if c['before']:
            print(f"    Before: {' '.join(f'{b:02x}' for b in c['before'])}")
        else:
            print(f"    Before: (none)")
        if c['after']:
            print(f"    After:  {' '.join(f'{b:02x}' for b in c['after'])}")
        else:
            print(f"    After:  (none)")
        # Highlight changed bytes
        if c['before'] and c['after']:
            diffs = []
            for i, (a, b) in enumerate(zip(c['before'], c['after'])):
                if a != b:
                    diffs.append(f"byte[{i}]: {a:02x}->{b:02x}")
            if diffs:
                print(f"    Changed: {', '.join(diffs)}")

    # Save full results
    results = {
        'timestamp': datetime.now().isoformat(),
        'input_reports': input_reports,
        'feature_changes': changes,
        'before_snapshot': {k: {str(rid): v for rid, v in reps.items()} if isinstance(reps, dict) else reps for k, reps in before.items()},
        'after_snapshot': {k: {str(rid): v for rid, v in reps.items()} if isinstance(reps, dict) else reps for k, reps in after.items()},
    }
    with open('hid_sniff_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\nFull results saved to hid_sniff_results.json")

if __name__ == '__main__':
    main()
