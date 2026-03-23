import hid
import time

# Find the dongle's vendor control interface (0xff03)
devices = [d for d in hid.enumerate() if d['vendor_id'] == 0x10F5]

dongle_ctrl = None
for d in devices:
    if d['product_id'] == 0x5017 and d['usage_page'] == 0xFF03:
        dongle_ctrl = d
        break

if not dongle_ctrl:
    print("Dongle control interface not found!")
    exit(1)

print(f"Opening: {dongle_ctrl['product_string']}")
dev = hid.device()
dev.open_path(dongle_ctrl['path'])
print("Opened OK\n")

# Read initial report 0x06
print("=== Initial Report 0x06 ===")
data = dev.get_feature_report(0x06, 512)
print(f"  {len(data)} bytes: {' '.join(f'{b:02x}' for b in data[:80])}")
print()

# Try Kone Pro style: send report 0x04 to select profile 0
# Format: [report_id, profile, 0x80, 0x00]
print("=== Trying profile select (report 0x04) ===")
for profile in range(5):
    try:
        cmd = [0x04, profile, 0x80, 0x00]
        dev.send_feature_report(cmd)
        time.sleep(0.05)

        # Read report 0x06 after selecting profile
        data = dev.get_feature_report(0x06, 512)
        nonzero = sum(1 for b in data if b != 0)
        print(f"  Profile {profile}: {' '.join(f'{b:02x}' for b in data[:80])}")
    except Exception as e:
        print(f"  Profile {profile} select failed: {e}")

print()

# Try reading other report IDs that might appear after profile select
print("=== Re-scanning all reports after profile select ===")
for rid in range(0x00, 0x20):
    try:
        data = dev.get_feature_report(rid, 512)
        if data and len(data) > 1:
            nonzero = sum(1 for b in data if b != 0)
            if nonzero > 1:
                print(f"  Report {rid:#04x} ({len(data)}B): {' '.join(f'{b:02x}' for b in data[:80])}")
    except:
        pass

print()

# Try Kone XP style from eruption: report 0x04 with [0x04, i, j, 0x00]
print("=== Eruption-style init (report 0x04) ===")
for i in range(5):
    for j in [0x80, 0x90]:
        try:
            cmd = [0x04, i, j, 0x00]
            dev.send_feature_report(cmd)
            time.sleep(0.02)
            data = dev.get_feature_report(0x06, 512)
            first_different = data[:2] != [0x06, 0x01]
            print(f"  [{i},{j:#04x}] -> 0x06: {' '.join(f'{b:02x}' for b in data[:40])}")
        except Exception as e:
            print(f"  [{i},{j:#04x}] failed: {e}")

print()

# Try sending report 0x90 (Kone Pro Air style)
print("=== Kone Pro Air style report 0x90 ===")
try:
    cmd = [0x00, 0x90, 0x0a] + [0x00] * 62
    dev.send_feature_report(cmd)
    time.sleep(0.05)
    data = dev.get_feature_report(0x90, 65)
    print(f"  Report 0x90: {' '.join(f'{b:02x}' for b in data[:40])}")
except Exception as e:
    print(f"  Failed: {e}")

dev.close()
print("\nDone.")
