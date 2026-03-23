import hid

devices = [d for d in hid.enumerate() if d['vendor_id'] == 0x10F5]
vendor_devs = [d for d in devices if d['usage_page'] >= 0xFF00]

for d in vendor_devs:
    path = d['path']
    pid = d['product_id']
    iface = d['interface_number']
    usage = f"{d['usage_page']:#06x}:{d['usage']:#06x}"

    print(f"\n{'='*70}")
    print(f"PID={pid:#06x} IF={iface} Usage={usage} - {d['product_string']}")
    print(f"Path: {path}")

    try:
        dev = hid.device()
        dev.open_path(path)
        print("OPENED OK")

        found = 0
        for rid in range(0x00, 0x100):
            try:
                data = dev.get_feature_report(rid, 512)
                if data and len(data) > 1:
                    nonzero = sum(1 for b in data if b != 0)
                    if nonzero > 1:
                        found += 1
                        hex_str = ' '.join(f'{b:02x}' for b in data[:80])
                        print(f'  Report {rid:#04x} ({len(data)}B, {nonzero} nz): {hex_str}')
            except:
                pass

        if found == 0:
            # Try reading input reports (non-blocking)
            dev.set_nonblocking(1)
            data = dev.read(512)
            if data:
                print(f"  Input read ({len(data)}B): {' '.join(f'{b:02x}' for b in data[:40])}")
            else:
                print("  No feature reports, no pending input data")

        dev.close()
    except Exception as e:
        print(f"FAILED: {e}")

print("\n\nDone.")
