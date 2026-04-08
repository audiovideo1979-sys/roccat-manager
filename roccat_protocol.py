"""
ROCCAT HID Protocol implementation for Kone XP Air.
Based on reverse-engineered protocol from libratbag, roccat-tools, and roccat-konepro-linux.

Key discovery: The mouse uses VID 0x10F5 (Turtle Beach) but the protocol
is ROCCAT's standard HID Feature Report protocol with control register handshake.
"""
import hid
import time
import struct

# ── Device constants ────────────────────────────────────────────────────────
VID_TB = 0x10F5   # Turtle Beach VID
VID_ROCCAT = 0x1E7D  # ROCCAT VID (may also be used)
PID_DONGLE = 0x5017  # Kone XP Air wireless dongle
PID_DOCK = 0x5019    # Kone XP Air dock/wired

# ── Report IDs ──────────────────────────────────────────────────────────────
REPORT_CONTROL = 0x04    # Control register - profile select and ready check
REPORT_ACTIVE  = 0x05    # Active profile select
REPORT_SETTINGS = 0x06   # Profile settings (DPI, polling, LEDs)
REPORT_BUTTONS = 0x07    # Button mappings
REPORT_MACRO = 0x08      # Macro data
REPORT_INFO = 0x09       # Device info / factory reset
REPORT_DEBOUNCE = 0x11   # Debounce time

# ── Control register states ─────────────────────────────────────────────────
STATUS_READY = 0x01
STATUS_ERROR = 0x02
STATUS_BUSY  = 0x03


def find_config_interface(vid=None, pid=None):
    """Find the vendor-specific configuration interface for the mouse."""
    vids = [vid] if vid else [VID_TB, VID_ROCCAT]
    pids = [pid] if pid else [PID_DONGLE, PID_DOCK]

    candidates = []
    for v in vids:
        for p in pids:
            for dev in hid.enumerate(v, p):
                info = {
                    'vid': v, 'pid': p,
                    'interface': dev['interface_number'],
                    'usage_page': dev['usage_page'],
                    'path': dev['path'],
                    'product': dev.get('product_string', ''),
                }
                candidates.append(info)

    if not candidates:
        print("No ROCCAT/Turtle Beach devices found!")
        return None

    print(f"Found {len(candidates)} interfaces:")
    for c in candidates:
        print(f"  VID=0x{c['vid']:04X} PID=0x{c['pid']:04X} IF={c['interface']} "
              f"UsagePage=0x{c['usage_page']:04X} - {c['product']}")

    # Prefer interface 3 (Kone Pro pattern)
    for c in candidates:
        if c['interface'] == 3:
            print(f"\nSelected: IF=3 (Kone Pro pattern)")
            return c['path']

    # Fallback: vendor-defined usage pages
    for c in candidates:
        if c['usage_page'] in (0xFF00, 0xFF01, 0xFF02, 0xFF03):
            print(f"\nSelected: UsagePage=0x{c['usage_page']:04X}")
            return c['path']

    # Last resort: first candidate
    print(f"\nSelected: first candidate")
    return candidates[0]['path']


def open_device(path=None):
    """Open the mouse HID device."""
    if path is None:
        path = find_config_interface()
    if path is None:
        raise RuntimeError("No device found")

    dev = hid.device()
    dev.open_path(path)
    dev.set_nonblocking(0)  # blocking mode
    return dev


def wait_ready(dev, max_retries=10):
    """Poll control register until device is ready."""
    time.sleep(0.01)
    for i in range(max_retries):
        try:
            response = dev.get_feature_report(REPORT_CONTROL, 4)
            status = response[1] if len(response) > 1 else 0
            if status == STATUS_READY:
                return True
            elif status == STATUS_ERROR:
                print(f"  Device rejected data (error status)")
                return False
            elif status == STATUS_BUSY:
                time.sleep(0.1)
            else:
                time.sleep(0.05)
        except Exception as e:
            print(f"  wait_ready error: {e}")
            time.sleep(0.05)
    print(f"  Device not ready after {max_retries} retries")
    return False


def compute_checksum(data):
    """Compute ROCCAT additive checksum, store in last 2 bytes."""
    data = bytearray(data)
    crc = sum(data[:-2]) & 0xFFFF
    data[-2] = crc & 0xFF
    data[-1] = (crc >> 8) & 0xFF
    return bytes(data)


def read_profile_settings(dev, profile_index):
    """Read settings for a profile."""
    # Select profile for settings read
    dev.send_feature_report(bytes([REPORT_CONTROL, profile_index, 0x80, 0x00]))
    if not wait_ready(dev):
        return None

    # Read settings
    data = dev.get_feature_report(REPORT_SETTINGS, 128)
    return data


def write_profile_settings(dev, profile_index, settings_bytes):
    """Write settings to a profile slot."""
    # Step 1: Select profile for settings write
    dev.send_feature_report(bytes([REPORT_CONTROL, profile_index, 0x80, 0x00]))
    if not wait_ready(dev):
        return False

    # Step 2: Apply checksum
    settings = compute_checksum(settings_bytes)

    # Step 3: Write settings
    dev.send_feature_report(settings)
    if not wait_ready(dev):
        return False

    return True


def read_button_mapping(dev, profile_index):
    """Read button mappings for a profile."""
    dev.send_feature_report(bytes([REPORT_CONTROL, profile_index, 0x90, 0x00]))
    if not wait_ready(dev):
        return None

    data = dev.get_feature_report(REPORT_BUTTONS, 128)
    return data


def write_button_mapping(dev, profile_index, button_bytes):
    """Write button mappings to a profile slot."""
    dev.send_feature_report(bytes([REPORT_CONTROL, profile_index, 0x90, 0x00]))
    if not wait_ready(dev):
        return False

    buttons = compute_checksum(button_bytes)
    dev.send_feature_report(buttons)
    if not wait_ready(dev):
        return False

    return True


def set_active_profile(dev, profile_index):
    """Switch the mouse to a specific profile."""
    dev.send_feature_report(bytes([REPORT_ACTIVE, 0x03, profile_index]))
    return wait_ready(dev)


def read_device_info(dev):
    """Read device information."""
    try:
        data = dev.get_feature_report(REPORT_INFO, 16)
        return data
    except:
        return None


# ── Main test ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys

    print("=== ROCCAT Protocol Test for Kone XP Air ===\n")

    # Try all interfaces to find the right one
    all_devs = []
    for vid in [VID_TB, VID_ROCCAT]:
        for d in hid.enumerate(vid):
            all_devs.append(d)

    print(f"All HID devices with VID 0x10F5 or 0x1E7D:")
    for d in all_devs:
        print(f"  PID=0x{d['product_id']:04X} IF={d['interface_number']} "
              f"UsagePage=0x{d['usage_page']:04X} Usage=0x{d['usage']:04X} "
              f"- {d.get('product_string', '')}")

    print("\n--- Testing each interface ---\n")

    tested = set()
    for d in all_devs:
        key = (d['product_id'], d['interface_number'], d['usage_page'])
        if key in tested:
            continue
        tested.add(key)

        print(f"PID=0x{d['product_id']:04X} IF={d['interface_number']} "
              f"UsagePage=0x{d['usage_page']:04X}:")

        try:
            dev = hid.device()
            dev.open_path(d['path'])
            dev.set_nonblocking(1)

            # Try reading control register
            try:
                ctrl = dev.get_feature_report(REPORT_CONTROL, 4)
                print(f"  Report 0x04 (control): {' '.join(f'{b:02x}' for b in ctrl[:8])}")
            except Exception as e:
                print(f"  Report 0x04: {e}")

            # Try reading active profile
            try:
                active = dev.get_feature_report(REPORT_ACTIVE, 4)
                print(f"  Report 0x05 (active):  {' '.join(f'{b:02x}' for b in active[:8])}")
            except Exception as e:
                print(f"  Report 0x05: {e}")

            # Try reading settings
            try:
                settings = dev.get_feature_report(REPORT_SETTINGS, 128)
                print(f"  Report 0x06 (settings): {' '.join(f'{b:02x}' for b in settings[:20])}...")
                if len(settings) > 10:
                    # Try to decode DPI
                    for encoding in ['direct', 'x50']:
                        if encoding == 'direct':
                            dpi = struct.unpack_from('<H', bytes(settings), 7)[0] if len(settings) > 8 else 0
                        else:
                            dpi = struct.unpack_from('<H', bytes(settings), 7)[0] * 50 if len(settings) > 8 else 0
                        if 50 <= dpi <= 30000:
                            print(f"    DPI (offset 7, {encoding}): {dpi}")
            except Exception as e:
                print(f"  Report 0x06: {e}")

            # Try reading buttons
            try:
                buttons = dev.get_feature_report(REPORT_BUTTONS, 128)
                print(f"  Report 0x07 (buttons): {' '.join(f'{b:02x}' for b in buttons[:20])}...")
            except Exception as e:
                print(f"  Report 0x07: {e}")

            # Try reading device info
            try:
                info = dev.get_feature_report(REPORT_INFO, 16)
                print(f"  Report 0x09 (info):    {' '.join(f'{b:02x}' for b in info[:16])}")
            except Exception as e:
                print(f"  Report 0x09: {e}")

            dev.close()
        except Exception as e:
            print(f"  Could not open: {e}")

        print()
