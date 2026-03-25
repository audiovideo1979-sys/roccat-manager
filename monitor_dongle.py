"""
Monitor the dongle's feature report 0x06 while Swarm II makes changes.
This reads the report every 50ms and logs any changes.
Run this WHILE Swarm II is open, then change a DPI value.
"""
import hid
import time
import sys

VENDOR_ID = 0x10F5

# Find dongle on IF=2 (0xFF03)
dev = hid.device()
found = False
for d in hid.enumerate():
    if (d['vendor_id'] == VENDOR_ID and
        d['product_id'] == 0x5017 and
        d['usage_page'] == 0xFF03):
        try:
            dev.open_path(d['path'])
            found = True
            print(f"Monitoring dongle: {d['product_string']}")
        except:
            print("Can't open dongle - Swarm II might have it exclusively")
            print("Trying other interfaces...")
        break

if not found:
    # Try each dongle interface
    for d in hid.enumerate():
        if d['vendor_id'] == VENDOR_ID and d['product_id'] == 0x5017:
            try:
                dev.open_path(d['path'])
                found = True
                print(f"Monitoring dongle IF={d['interface_number']} UP=0x{d['usage_page']:04x}")
                break
            except:
                continue

if not found:
    print("Cannot open any dongle interface!")
    sys.exit(1)

dev.set_nonblocking(1)

print("\nNow change a DPI value in Swarm II...")
print("Watching for changes (Ctrl+C to stop)\n")

last_data = None
start = time.time()

try:
    while True:
        try:
            data = dev.get_feature_report(0x06, 64)
            hex_str = ' '.join(f'{b:02x}' for b in data[:32])

            if data != last_data:
                elapsed = time.time() - start
                print(f"[{elapsed:7.3f}s] CHANGED: {hex_str}")
                last_data = list(data)

        except Exception as e:
            print(f"Read error: {e}")

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopped.")

dev.close()
