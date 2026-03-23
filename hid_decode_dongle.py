"""
Read and decode the dongle's report 0x06 in detail.
Compare with and without Swarm II running.
"""
import hid
import time

VENDOR_ID = 0x10F5

# Find dongle vendor interface
devices = [d for d in hid.enumerate() if d['vendor_id'] == VENDOR_ID]
dongle = None
for d in devices:
    if d['product_id'] == 0x5017 and d['usage_page'] == 0xFF03:
        dongle = d
        break

if not dongle:
    print("Dongle not found!")
    exit(1)

dev = hid.device()
dev.open_path(dongle['path'])
dev.set_nonblocking(1)
print(f"Opened: {dongle['product_string']}\n")

# Read report 0x06 with full hex dump
data = dev.get_feature_report(0x06, 512)
print(f"Report 0x06 ({len(data)} bytes):")
for i in range(0, min(len(data), 128), 16):
    hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
    print(f"  {i:04x}: {hex_part:<48s}  {ascii_part}")

print("\n=== Attempting decode ===")
print(f"Byte 0: {data[0]:#04x} (report ID)")
print(f"Byte 1: {data[1]:#04x}")
print(f"Byte 2: {data[2]:#04x} ({data[2]})")
print(f"Byte 3: {data[3]:#04x} ({data[3]})")

# Try DPI decode at various offsets
print("\n--- Possible DPI values (byte * 50) ---")
for i in range(4, min(30, len(data))):
    if data[i] > 0 and data[i] < 0xFF:
        dpi = data[i] * 50
        print(f"  Byte {i}: {data[i]:#04x} ({data[i]}) → {dpi} DPI")

# Try LE16 DPI decode
print("\n--- Possible LE16 DPI values ---")
for i in range(4, min(30, len(data)), 2):
    val = data[i] | (data[i+1] << 8)
    if 50 <= val <= 36000:
        print(f"  Bytes {i}-{i+1}: {data[i]:02x} {data[i+1]:02x} → {val} (raw)")
        print(f"    As DPI/50 index: {val*50}")

# Read any pending input reports
print("\n=== Pending input reports ===")
for _ in range(10):
    inp = dev.read(64)
    if inp:
        print(f"  Input ({len(inp)}B): {' '.join(f'{b:02x}' for b in inp)}")
    else:
        break
    time.sleep(0.01)

# Also try reading ALL report IDs more carefully
print("\n=== All available reports (0x00-0xFF) ===")
for rid in range(0x100):
    try:
        data = dev.get_feature_report(rid, 512)
        if data and len(data) > 1:
            nonzero = sum(1 for b in data if b != 0)
            if nonzero > 1:
                print(f"  Report {rid:#04x} ({len(data)}B, {nonzero}nz): {' '.join(f'{b:02x}' for b in data[:48])}")
    except:
        pass

dev.close()
