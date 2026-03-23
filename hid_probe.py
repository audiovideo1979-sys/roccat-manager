import hid

# Enumerate to get exact paths
devices = [d for d in hid.enumerate() if d['vendor_id'] == 0x10F5]
vendor_devs = [d for d in devices if d['usage_page'] >= 0xFF00]

# Use the first 0xff01 interface (the one that had data)
target = None
for d in vendor_devs:
    if d['usage_page'] == 0xFF01 and d['product_id'] == 0x5019:
        target = d
        break

if not target:
    print("Device not found!")
    exit(1)

print(f"Opening: {target['product_string']} IF={target['interface_number']} Usage={target['usage_page']:#06x}")

dev = hid.device()
dev.open_path(target['path'])
print("Opened OK\n")

# Probe ALL report IDs 0x00-0xFF
for rid in range(0x00, 0x100):
    try:
        data = dev.get_feature_report(rid, 512)
        if data and len(data) > 1:
            nonzero = sum(1 for b in data if b != 0)
            if nonzero > 1:
                hex_str = ' '.join(f'{b:02x}' for b in data[:64])
                print(f'Report {rid:#04x} ({len(data)} bytes, {nonzero} non-zero): {hex_str}')
    except:
        pass

dev.close()
