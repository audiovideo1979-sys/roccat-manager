"""
Monitor HID traffic on all ROCCAT vendor interfaces.
Reads input reports in non-blocking mode while also polling feature reports
for changes. Run this, then make a change in Swarm II.
"""
import hid
import time
import sys

VENDOR_ID = 0x10F5

def open_all_vendor_devices():
    devices = []
    for d in hid.enumerate():
        if d['vendor_id'] != VENDOR_ID:
            continue
        if d['usage_page'] < 0xFF00:
            continue

        try:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)

            # Read initial feature reports
            initial = {}
            for rid in range(0x00, 0x20):
                try:
                    data = dev.get_feature_report(rid, 512)
                    if data and len(data) > 1 and sum(1 for b in data if b != 0) > 1:
                        initial[rid] = bytes(data)
                except:
                    pass

            label = f"PID={d['product_id']:#06x} IF={d['interface_number']} Usage={d['usage_page']:#06x}"
            devices.append({
                'dev': dev,
                'label': label,
                'initial': initial,
                'path': d['path'],
            })
            print(f"Opened: {label} ({len(initial)} feature reports)")
        except Exception as e:
            pass

    return devices

def monitor(devices, duration=60):
    print(f"\nMonitoring for {duration}s... Make a change in Swarm II now!\n")
    start = time.time()
    changes_found = 0

    while time.time() - start < duration:
        for d in devices:
            dev = d['dev']

            # Check for input reports
            try:
                data = dev.read(512)
                if data:
                    hex_str = ' '.join(f'{b:02x}' for b in data[:64])
                    elapsed = time.time() - start
                    print(f"[{elapsed:6.2f}s] {d['label']} INPUT ({len(data)}B): {hex_str}")
                    changes_found += 1
            except:
                pass

            # Poll feature reports for changes (every ~0.5s)
        time.sleep(0.01)

        # Every 0.5 seconds, check feature reports
        elapsed = time.time() - start
        if int(elapsed * 2) % 1 == 0 and int(elapsed * 10) % 5 == 0:
            for d in devices:
                dev = d['dev']
                for rid in d['initial']:
                    try:
                        data = bytes(dev.get_feature_report(rid, 512))
                        if data != d['initial'][rid]:
                            hex_old = ' '.join(f'{b:02x}' for b in d['initial'][rid][:40])
                            hex_new = ' '.join(f'{b:02x}' for b in data[:40])
                            print(f"[{elapsed:6.2f}s] {d['label']} REPORT {rid:#04x} CHANGED!")
                            print(f"    OLD: {hex_old}")
                            print(f"    NEW: {hex_new}")
                            d['initial'][rid] = data
                            changes_found += 1
                    except:
                        pass

    return changes_found

if __name__ == '__main__':
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    devices = open_all_vendor_devices()
    print(f"\nOpened {len(devices)} vendor interfaces")

    if not devices:
        print("No devices found!")
        sys.exit(1)

    changes = monitor(devices, duration)

    for d in devices:
        d['dev'].close()

    print(f"\nDone. {changes} changes detected.")
