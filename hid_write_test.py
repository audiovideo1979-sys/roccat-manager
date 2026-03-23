"""
Test writing to PID_5019 interfaces that had no readable feature reports.
Also try writing to the dongle with various commands.
"""
import hid
import time
import struct

VENDOR_ID = 0x10F5

def find_devices():
    result = {}
    for d in hid.enumerate():
        if d['vendor_id'] != VENDOR_ID:
            continue
        key = f"PID={d['product_id']:#06x}_IF={d['interface_number']}_UP={d['usage_page']:#06x}"
        if key not in result:
            result[key] = d
    return result

devs = find_devices()

# Try the PID_5019 IF=1 (0xff00) interface - output/write test
print("=== Testing PID_5019 IF=1 (Usage 0xff00) ===")
for key, d in devs.items():
    if d['product_id'] == 0x5019 and d['interface_number'] == 1:
        print(f"  Path: {d['path']}")
        try:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)
            print("  Opened OK")

            # Try writing various report IDs
            for rid in [0x04, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0D, 0x0E]:
                try:
                    # Send as feature report: select profile 0
                    cmd = [rid, 0x00] + [0x00] * 62
                    dev.send_feature_report(cmd)
                    time.sleep(0.05)
                    print(f"  Wrote report {rid:#04x} OK")

                    # Try reading back
                    resp = dev.get_feature_report(rid, 512)
                    if resp and sum(1 for b in resp if b != 0) > 1:
                        print(f"    Response: {' '.join(f'{b:02x}' for b in resp[:40])}")
                except Exception as e:
                    pass

            # Try writing as output report
            for rid in [0x00, 0x04, 0x06, 0x08]:
                try:
                    cmd = [rid, 0x00] + [0x00] * 62
                    dev.write(cmd)
                    time.sleep(0.05)
                    print(f"  Output report {rid:#04x} written OK")

                    # Check for input response
                    resp = dev.read(512)
                    if resp:
                        print(f"    Input response: {' '.join(f'{b:02x}' for b in resp[:40])}")
                except Exception as e:
                    pass

            dev.close()
        except Exception as e:
            print(f"  Failed: {e}")
        break

# Try the PID_5019 IF=2 (0xff02) interface
print("\n=== Testing PID_5019 IF=2 (Usage 0xff02) ===")
for key, d in devs.items():
    if d['product_id'] == 0x5019 and d['interface_number'] == 2:
        print(f"  Path: {d['path']}")
        try:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)
            print("  Opened OK")

            # Try writing various report IDs
            for rid in [0x04, 0x06, 0x07, 0x08, 0x09, 0x0D, 0x0E]:
                try:
                    cmd = [rid, 0x00] + [0x00] * 62
                    dev.send_feature_report(cmd)
                    time.sleep(0.05)
                    print(f"  Wrote feature report {rid:#04x} OK")

                    resp = dev.get_feature_report(rid, 512)
                    if resp and sum(1 for b in resp if b != 0) > 1:
                        print(f"    Response: {' '.join(f'{b:02x}' for b in resp[:40])}")
                except:
                    pass

            # Try output reports
            for rid in [0x00, 0x04, 0x06, 0x08]:
                try:
                    cmd = [rid, 0x00] + [0x00] * 62
                    dev.write(cmd)
                    time.sleep(0.05)
                    print(f"  Output report {rid:#04x} written OK")

                    resp = dev.read(512)
                    if resp:
                        print(f"    Input response: {' '.join(f'{b:02x}' for b in resp[:40])}")
                except:
                    pass

            dev.close()
        except Exception as e:
            print(f"  Failed: {e}")
        break

# Now try the dongle's vendor interface with write commands
print("\n=== Testing Dongle PID_5017 IF=2 (Usage 0xff03) writes ===")
for key, d in devs.items():
    if d['product_id'] == 0x5017 and d['usage_page'] == 0xFF03:
        try:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)
            print("  Opened dongle OK")

            # Try writing various report IDs as feature reports
            for rid in range(0x01, 0x10):
                try:
                    cmd = [rid, 0x00] + [0x00] * 62
                    dev.send_feature_report(cmd)
                    time.sleep(0.05)
                    print(f"  Feature report {rid:#04x} accepted")

                    # Check for response
                    resp = dev.get_feature_report(rid, 512)
                    if resp and sum(1 for b in resp if b != 0) > 1:
                        print(f"    Response: {' '.join(f'{b:02x}' for b in resp[:40])}")

                    # Check for input
                    inp = dev.read(64)
                    if inp:
                        print(f"    Input: {' '.join(f'{b:02x}' for b in inp[:40])}")
                except Exception as e:
                    pass

            # Try output reports
            for rid in [0x00, 0x08]:
                try:
                    cmd = [rid] + [0x00] * 63
                    dev.write(cmd)
                    time.sleep(0.05)
                    print(f"  Output report {rid:#04x} written OK")

                    inp = dev.read(64)
                    if inp:
                        print(f"    Input response: {' '.join(f'{b:02x}' for b in inp[:40])}")
                except:
                    pass

            dev.close()
        except Exception as e:
            print(f"  Failed: {e}")
        break

print("\nDone.")
