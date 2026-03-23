"""
Try to write a modified DPI value to the mouse via HID.
This will change DPI stage 1 from 1000 to 300 (very noticeable change).
"""
import hid
import time

VENDOR_ID = 0x10F5

def find_device(pid, usage_page):
    for d in hid.enumerate():
        if d['vendor_id'] == VENDOR_ID and d['product_id'] == pid and d['usage_page'] == usage_page:
            return d
    return None

# Open mouse docking interface (0xff01)
mouse_info = find_device(0x5019, 0xFF01)
if not mouse_info:
    print("Mouse not found!")
    exit(1)

dev = hid.device()
dev.open_path(mouse_info['path'])
dev.set_nonblocking(1)
print(f"Opened: {mouse_info['product_string']}")

# Read current report 0x06 (DPI data)
data = list(dev.get_feature_report(0x06, 512))
print(f"\nCurrent report 0x06:")
print(f"  {' '.join(f'{b:02x}' for b in data[:40])}")

# Decode DPI stages (4 bytes each: DPI/50, R, G, B)
print("\nCurrent DPI stages:")
for i in range(4):
    offset = 1 + i * 4
    dpi_raw = data[offset]
    r, g, b = data[offset+1], data[offset+2], data[offset+3]
    print(f"  Stage {i+1}: {dpi_raw*50} DPI (raw={dpi_raw:#04x}), Color=({r},{g},{b})")

# Modify stage 1 DPI from 1000 (0x14) to 300 (0x06) - very noticeable
old_dpi = data[1]
new_dpi = 0x06  # 300 DPI - very slow, easy to notice
data[1] = new_dpi
print(f"\nChanging stage 1: {old_dpi*50} -> {new_dpi*50} DPI")

# Write back
print("Writing report 0x06...")
try:
    dev.send_feature_report(data[:64])
    print("Write succeeded!")
except Exception as e:
    print(f"Feature report write failed: {e}")
    print("Trying as output report...")
    try:
        dev.write(data[:64])
        print("Output report write succeeded!")
    except Exception as e2:
        print(f"Output report also failed: {e2}")

time.sleep(0.2)

# Read back to verify
readback = list(dev.get_feature_report(0x06, 512))
print(f"\nReadback report 0x06:")
print(f"  {' '.join(f'{b:02x}' for b in readback[:40])}")

if readback[1] == new_dpi:
    print("\nDPI VALUE CHANGED IN REPORT!")
    print("Move your mouse - if it feels extremely slow, the write worked!")
    print("\nTo restore, run: python hid_dpi_write.py --restore")
else:
    print(f"\nValue did not change (still {readback[1]:#04x})")
    print("The mouse might not accept writes on this report via this method.")

import sys
if '--restore' in sys.argv:
    data[1] = 0x14  # restore 1000 DPI
    dev.send_feature_report(data[:64])
    print("Restored to 1000 DPI")

dev.close()
