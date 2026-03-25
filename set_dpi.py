"""
Set DPI on Kone XP Air by modifying the Swarm II INI file
and triggering a reload via init+handshake.
"""
import sys
import os
import shutil
import time
import re
import hid

INI_PATH = r"C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_TB.ini"
VENDOR_ID = 0x10F5
DONGLE_PID = 0x5017


def decode_qt_bytearray(raw_bytes):
    """Decode Qt's @ByteArray(...) escaping."""
    data = []
    i = 0
    while i < len(raw_bytes):
        if raw_bytes[i] == ord('\\') and i + 1 < len(raw_bytes):
            nc = raw_bytes[i + 1]
            if nc == ord('x'):
                hex_s = ""
                j = i + 2
                while j < len(raw_bytes) and j < i + 4:
                    c = chr(raw_bytes[j])
                    if c in '0123456789abcdefABCDEF':
                        hex_s += c
                        j += 1
                    else:
                        break
                if hex_s:
                    data.append(int(hex_s, 16))
                    i = j
                    continue
            elif nc == ord('0'):
                data.append(0); i += 2; continue
            elif nc == ord('n'):
                data.append(0x0a); i += 2; continue
            elif nc == ord('r'):
                data.append(0x0d); i += 2; continue
            elif nc == ord('t'):
                data.append(0x09); i += 2; continue
            elif nc == ord('f'):
                data.append(0x0c); i += 2; continue
            elif nc == ord('\\'):
                data.append(ord('\\')); i += 2; continue
        data.append(raw_bytes[i])
        i += 1
    return data


def encode_qt_bytearray(data):
    """Encode bytes back to Qt @ByteArray(...) format."""
    parts = []
    for b in data:
        if b == 0:
            parts.append(b'\\0')
        elif b == 0x0a:
            parts.append(b'\\n')
        elif b == 0x0d:
            parts.append(b'\\r')
        elif b == 0x09:
            parts.append(b'\\t')
        elif b == 0x0c:
            parts.append(b'\\f')
        elif b == ord('\\'):
            parts.append(b'\\\\')
        elif 32 <= b < 127 and b != ord(')') and b != ord('('):
            parts.append(bytes([b]))
        else:
            parts.append(f'\\x{b:x}'.encode())
    return b''.join(parts)


def read_profiles(ini_path):
    """Read and decode profiles from INI file."""
    with open(ini_path, 'rb') as f:
        raw = f.read()

    marker = b'MainSetting=@ByteArray('
    idx = raw.find(marker)
    if idx < 0:
        return None, None, None

    start = idx + len(marker)
    # Find closing paren
    i = start
    while i < len(raw):
        if raw[i] == ord(')'):
            break
        i += 1
    end = i

    chunk = raw[start:end]
    data = decode_qt_bytearray(chunk)

    return raw, (start, end), data


def parse_profiles(data):
    """Parse profile data into individual profiles."""
    if len(data) < 4:
        return []

    num = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
    profiles = []
    offset = 4

    for p in range(num):
        if offset + 4 > len(data):
            break
        plen = (data[offset] << 24) | (data[offset+1] << 16) | (data[offset+2] << 8) | data[offset+3]
        offset += 4

        if plen > 200 or offset + plen > len(data):
            # Bad length, try to recover
            break

        pdata = data[offset:offset + plen]
        profiles.append(pdata)
        offset += plen

    return profiles


def show_profile(pdata, index):
    """Display a profile's DPI settings."""
    if len(pdata) < 17:
        print(f"  Profile {index+1}: too short ({len(pdata)} bytes)")
        return

    active = pdata[6]
    print(f"  Profile {index+1} (slot {pdata[2]}): active_stage={active}")

    dpis = []
    for i in range(5):
        off = 7 + i * 2
        if off + 1 < len(pdata):
            dpi = pdata[off] | (pdata[off+1] << 8)
            dpis.append(dpi)
            marker = " <-- active" if i == active else ""
            print(f"    Stage {i+1}: {dpi} DPI{marker}")
    return dpis


def set_dpi_in_profile(pdata, stage, new_dpi):
    """Set a DPI value in a profile. Stage is 0-indexed."""
    off = 7 + stage * 2
    pdata[off] = new_dpi & 0xFF
    pdata[off + 1] = (new_dpi >> 8) & 0xFF
    # Also set Y-axis DPI
    off_y = 17 + stage * 2
    if off_y + 1 < len(pdata):
        pdata[off_y] = new_dpi & 0xFF
        pdata[off_y + 1] = (new_dpi >> 8) & 0xFF
    return pdata


def rebuild_data(profiles):
    """Rebuild the full data block from profiles."""
    num = len(profiles)
    data = [(num >> 24) & 0xFF, (num >> 16) & 0xFF, (num >> 8) & 0xFF, num & 0xFF]
    for pdata in profiles:
        plen = len(pdata)
        data.extend([(plen >> 24) & 0xFF, (plen >> 16) & 0xFF, (plen >> 8) & 0xFF, plen & 0xFF])
        data.extend(pdata)
    return data


def trigger_reload():
    """Send init+handshake to trigger the Device Service to reload."""
    for d in hid.enumerate():
        if d['vendor_id'] == VENDOR_ID and d['product_id'] == DONGLE_PID and d['usage_page'] == 0xFF03:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)

            pad = [0x00] * 30

            # Init sequence
            cmd = [0x06, 0x00, 0x00, 0x04] + [0x00] * 26
            dev.send_feature_report(cmd)
            time.sleep(0.05)

            cmd = [0x06, 0x00, 0x00, 0x05] + [0x00] * 26
            dev.send_feature_report(cmd)
            time.sleep(0.1)

            cmd = [0x06, 0x01, 0x44, 0x07] + [0x00] * 26
            dev.send_feature_report(cmd)
            time.sleep(0.1)

            resp = dev.get_feature_report(0x06, 31)
            dev.close()

            hex_str = ' '.join(f'{b:02x}' for b in resp[:20])
            print(f"  Dongle response: {hex_str}")
            return True

    print("  Dongle not found!")
    return False


if __name__ == '__main__':
    target_dpi = 10000
    profile_idx = 0  # Which profile to modify (0-4)

    if len(sys.argv) > 1:
        target_dpi = int(sys.argv[1])
    if len(sys.argv) > 2:
        profile_idx = int(sys.argv[2])

    print(f"=== Set DPI to {target_dpi} on profile {profile_idx + 1} ===")
    print()

    # Read current profiles
    raw, bounds, data = read_profiles(INI_PATH)
    if data is None:
        print("Could not find MainSetting in INI file!")
        sys.exit(1)

    profiles = parse_profiles(data)
    print(f"Found {len(profiles)} profiles:")
    for i, p in enumerate(profiles):
        show_profile(list(p), i)
    print()

    # Modify the target profile
    if profile_idx >= len(profiles):
        print(f"Profile {profile_idx + 1} not found!")
        sys.exit(1)

    pdata = list(profiles[profile_idx])

    # Set all 5 DPI stages to target
    print(f"Setting all DPI stages to {target_dpi}...")
    for stage in range(5):
        set_dpi_in_profile(pdata, stage, target_dpi)

    profiles[profile_idx] = pdata

    # Rebuild and write
    new_data = rebuild_data(profiles)
    new_encoded = encode_qt_bytearray(new_data)

    # Backup
    bak_path = INI_PATH + '.bak2'
    if not os.path.exists(bak_path):
        shutil.copy2(INI_PATH, bak_path)
        print(f"Backup saved to {bak_path}")

    # Replace in file
    start, end = bounds
    new_raw = raw[:start] + new_encoded + raw[end:]

    with open(INI_PATH, 'wb') as f:
        f.write(new_raw)
    print("INI file updated!")

    # Show new values
    print("\nNew profile:")
    show_profile(pdata, profile_idx)

    # Trigger reload
    print("\nTriggering reload via init+handshake...")
    trigger_reload()

    print(f"\nDone! Check if DPI changed to {target_dpi}.")
    print("If not, try restarting Swarm II.")
