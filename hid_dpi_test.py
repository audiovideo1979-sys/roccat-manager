"""
Attempt to read and modify DPI via the dongle's HID interface.
Based on Kone Pro protocol: report 0x04 selects profile, report 0x06 is profile data.
"""
import hid
import time
import sys

VENDOR_ID = 0x10F5

def find_device(pid, usage_page):
    for d in hid.enumerate():
        if d['vendor_id'] == VENDOR_ID and d['product_id'] == pid and d['usage_page'] == usage_page:
            return d
    return None

# Open dongle vendor interface
dongle_info = find_device(0x5017, 0xFF03)
if not dongle_info:
    print("Dongle not found!")
    sys.exit(1)

dev = hid.device()
dev.open_path(dongle_info['path'])
dev.set_nonblocking(1)
print(f"Opened: {dongle_info['product_string']}")

# Read current state
data06 = dev.get_feature_report(0x06, 512)
print(f"\nCurrent report 0x06 ({len(data06)} bytes):")
for i in range(0, min(64, len(data06)), 16):
    hex_part = ' '.join(f'{b:02x}' for b in data06[i:i+16])
    print(f"  {i:3d}: {hex_part}")

# Now open mouse docking interface (0xff01) to read DPI/LED data
mouse_info = find_device(0x5019, 0xFF01)
if mouse_info:
    mouse_dev = hid.device()
    mouse_dev.open_path(mouse_info['path'])
    mouse_dev.set_nonblocking(1)
    print(f"\nOpened mouse: {mouse_info['product_string']}")

    for rid in [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08]:
        try:
            data = mouse_dev.get_feature_report(rid, 512)
            if data:
                print(f"\nMouse report {rid:#04x} ({len(data)} bytes):")
                for i in range(0, min(64, len(data)), 16):
                    hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
                    print(f"  {i:3d}: {hex_part}")
        except:
            pass

    # Decode report 0x06 as DPI data
    data = mouse_dev.get_feature_report(0x06, 512)
    if data:
        print("\n=== Decoding mouse report 0x06 as DPI stages ===")
        # Pattern: [dpi_byte, brightness, R, G, B, ...] repeating
        # or: [dpi_byte, color1, color2, color3, ...]
        offset = 1  # skip report ID
        stage = 1
        while offset < 35 and offset < len(data):
            dpi_raw = data[offset]
            if dpi_raw == 0:
                break
            dpi = dpi_raw * 50
            # Next bytes might be color
            colors = data[offset+1:offset+4]
            print(f"  Stage {stage}: raw={dpi_raw:#04x} → {dpi} DPI, "
                  f"next bytes: {' '.join(f'{b:02x}' for b in data[offset+1:offset+5])}")
            stage += 1
            offset += 5  # guess stride

        # Alternative: decode as pairs
        print("\n=== Alternative: paired bytes as LE16 DPI ===")
        for i in range(1, 21, 2):
            val = data[i] | (data[i+1] << 8)
            if val > 0:
                print(f"  Bytes {i}-{i+1}: {data[i]:02x} {data[i+1]:02x} → {val} (÷50={val//50})")

    # Try to WRITE a modified DPI report
    if '--write' in sys.argv:
        print("\n=== WRITING MODIFIED DPI ===")
        # Read current report 0x06
        data = list(mouse_dev.get_feature_report(0x06, 512))
        print(f"Before: {' '.join(f'{b:02x}' for b in data[:40])}")

        # Modify byte 1 (first DPI value)
        # If current is 0x14 (1000 DPI), change to 0x0A (500 DPI) for a noticeable change
        old_val = data[1]
        new_val = 0x0A  # 500 DPI if encoding is *50
        data[1] = new_val
        print(f"Setting byte 1 from {old_val:#04x} to {new_val:#04x}")

        try:
            mouse_dev.send_feature_report(data[:64])
            print("Write OK!")
            time.sleep(0.1)

            # Read back
            readback = mouse_dev.get_feature_report(0x06, 512)
            print(f"After:  {' '.join(f'{b:02x}' for b in readback[:40])}")
            if readback[1] == new_val:
                print("VALUE CHANGED! Move your mouse to test if DPI is different.")
            else:
                print("Value did not stick.")
        except Exception as e:
            print(f"Write failed: {e}")

    mouse_dev.close()

dev.close()
print("\nDone.")
