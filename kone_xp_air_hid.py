"""
Direct HID communication with Kone XP Air via dongle.
Bypasses Swarm II completely.

Protocol decoded from USB capture:
  - Report ID: 0x06, Interface: 2 (usage_page=0xff03)
  - All commands are SET_FEATURE reports, 30 bytes padded with zeros
  - Profile data is 75 bytes split across 3 pages (25 bytes each)
  - Checksum is sum of all 75 bytes, stored as 16-bit LE

Data layout (75 bytes):
  [0]     : 0x06 (config byte)
  [1]     : 0x4e (flags)
  [2]     : 0x00
  [3]     : 0x06
  [4]     : 0x06
  [5]     : 0x0a (debounce/angle?)
  [6]     : active DPI slot (0-indexed)
  [7-16]  : 5 DPI values, 16-bit LE (raw DPI, e.g. 800 = 0x0320)
  [17-26] : 5 DPI values set 2 (Y-axis or alternate?)
  [27-35] : Button/config data
  [36-74] : LED color data per DPI slot
"""
import hid
import struct
import time
import sys

VID = 0x10F5
DONGLE_PID = 0x5017

# Command templates (30 bytes, padded with zeros)
CMD_INIT_1 = bytes([0x06, 0x00, 0x00, 0x04] + [0x00] * 26)
CMD_INIT_2 = bytes([0x06, 0x00, 0x00, 0x05] + [0x00] * 26)
CMD_HANDSHAKE = bytes([0x06, 0x01, 0x44, 0x07] + [0x00] * 26)
CMD_POLL = bytes([0x06, 0x01, 0x4d, 0x06, 0x15] + [0x00] * 25)

def cmd_select_page(page_num):
    """Select data page for writing"""
    return bytes([0x06, 0x01, 0x46, 0x06, 0x02, page_num] + [0x00] * 24)

def cmd_write_page(data_25bytes):
    """Write 25 bytes to selected page"""
    return bytes([0x06, 0x01, 0x46, 0x06, 0x19]) + data_25bytes

def cmd_commit(checksum):
    """Commit with checksum"""
    cs_lo = checksum & 0xFF
    cs_hi = (checksum >> 8) & 0xFF
    return bytes([0x06, 0x01, 0x46, 0x06, 0x03, 0x00, cs_lo, cs_hi] + [0x00] * 22)


def find_dongle():
    """Find the Kone XP Air dongle on interface 2, usage_page 0xff03"""
    for d in hid.enumerate():
        if (d['vendor_id'] == VID and
            d['product_id'] == DONGLE_PID and
            d['usage_page'] == 0xff03):
            return d
    return None


def open_dongle():
    """Open the dongle HID device"""
    info = find_dongle()
    if not info:
        raise RuntimeError("Kone XP Air dongle not found!")
    dev = hid.device()
    dev.open_path(info['path'])
    dev.set_nonblocking(1)
    return dev


def send_cmd(dev, cmd, delay=0.05):
    """Send a feature report command"""
    result = dev.send_feature_report(cmd)
    time.sleep(delay)
    return result


def read_profile(dev):
    """Read current profile data by polling report 0x06"""
    data = dev.get_feature_report(0x06, 256)
    return data


def write_profile(dev, profile_data):
    """Write 75 bytes of profile data to the mouse.

    Args:
        dev: HID device handle
        profile_data: 75 bytes of profile data
    """
    assert len(profile_data) == 75, f"Profile data must be 75 bytes, got {len(profile_data)}"

    # Calculate checksum
    checksum = sum(profile_data) & 0xFFFF

    # Split into 3 pages of 25 bytes
    pages = [profile_data[i*25:(i+1)*25] for i in range(3)]

    print(f"  Writing profile ({len(profile_data)} bytes, checksum=0x{checksum:04x})...")

    # Init sequence
    send_cmd(dev, CMD_INIT_1)
    send_cmd(dev, CMD_INIT_2)
    send_cmd(dev, CMD_HANDSHAKE, delay=0.1)

    # Write each page
    for page_num in range(3):
        print(f"    Page {page_num}: {' '.join(f'{b:02x}' for b in pages[page_num])}")
        send_cmd(dev, cmd_select_page(page_num))
        send_cmd(dev, CMD_HANDSHAKE)
        send_cmd(dev, cmd_write_page(pages[page_num]))
        send_cmd(dev, CMD_HANDSHAKE)

    # Commit
    send_cmd(dev, cmd_select_page(3))
    send_cmd(dev, CMD_HANDSHAKE)
    send_cmd(dev, cmd_commit(checksum))
    send_cmd(dev, CMD_HANDSHAKE)

    print(f"  Profile written successfully!")


def decode_profile(data):
    """Decode profile data into human-readable format"""
    if len(data) < 75:
        print(f"  Warning: profile data only {len(data)} bytes")
        return None

    info = {
        'config_byte': data[0],
        'flags': data[1],
        'active_dpi_slot': data[6],
        'dpi_values': [],
        'dpi_values_2': [],
    }

    # DPI values (offsets 7-16)
    for i in range(5):
        offset = 7 + i * 2
        dpi = struct.unpack_from('<H', bytes(data), offset)[0]
        info['dpi_values'].append(dpi)

    # Second DPI set (offsets 17-26)
    for i in range(5):
        offset = 17 + i * 2
        dpi = struct.unpack_from('<H', bytes(data), offset)[0]
        info['dpi_values_2'].append(dpi)

    return info


def set_dpi_values(profile_data, dpi_list, active_slot=None):
    """Modify DPI values in profile data.

    Args:
        profile_data: 75-byte profile data (bytearray)
        dpi_list: list of up to 5 DPI values (50-19000, step 50)
        active_slot: active DPI slot (0-4), or None to keep current
    Returns:
        modified profile data
    """
    data = bytearray(profile_data)

    if active_slot is not None:
        data[6] = active_slot

    for i, dpi in enumerate(dpi_list[:5]):
        if dpi < 50 or dpi > 19000:
            raise ValueError(f"DPI {dpi} out of range (50-19000)")
        if dpi % 50 != 0:
            raise ValueError(f"DPI {dpi} must be multiple of 50")
        offset = 7 + i * 2
        struct.pack_into('<H', data, offset, dpi)
        # Also update set 2 (keep in sync for now)
        offset2 = 17 + i * 2
        struct.pack_into('<H', data, offset2, dpi)

    return bytes(data)


def main():
    print("=== Kone XP Air Direct HID Control ===\n")

    # Find and open dongle
    info = find_dongle()
    if not info:
        print("ERROR: Kone XP Air dongle not found!")
        return
    print(f"Found dongle: {info['product_string']}")

    dev = open_dongle()

    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python kone_xp_air_hid.py read          - Read current profile")
        print("  python kone_xp_air_hid.py dpi 800 1600 3200 4000 6400  - Set 5 DPI values")
        print("  python kone_xp_air_hid.py slot 2        - Set active DPI slot (0-4)")
        print("  python kone_xp_air_hid.py test           - Test: change DPI 1 to 1000 then back")
        dev.close()
        return

    cmd = sys.argv[1]

    if cmd == 'read':
        print("\nReading current profile...")
        data = read_profile(dev)
        if data:
            print(f"  Raw ({len(data)} bytes): {' '.join(f'{b:02x}' for b in data[:30])}")
            info = decode_profile(data)
            if info:
                print(f"\n  Active DPI slot: {info['active_dpi_slot'] + 1} (0-indexed: {info['active_dpi_slot']})")
                print(f"  DPI set 1: {info['dpi_values']}")
                print(f"  DPI set 2: {info['dpi_values_2']}")

    elif cmd == 'dpi':
        dpi_values = [int(x) for x in sys.argv[2:7]]
        if len(dpi_values) < 1:
            print("Provide 1-5 DPI values")
            dev.close()
            return

        # Read current profile first
        print("\nReading current profile...")
        current = read_profile(dev)
        if not current or len(current) < 75:
            print("ERROR: Could not read profile data")
            dev.close()
            return

        current_info = decode_profile(current)
        print(f"  Current DPI: {current_info['dpi_values']}")

        # Pad DPI values to 5 if needed
        while len(dpi_values) < 5:
            dpi_values.append(dpi_values[-1])

        print(f"  New DPI:     {dpi_values}")

        # Modify and write
        # Use the known good profile data from the capture as base
        profile_data = bytearray(current[:75])
        new_profile = set_dpi_values(profile_data, dpi_values)

        print("\nWriting new profile...")
        write_profile(dev, new_profile)

        # Verify
        time.sleep(0.2)
        verify = read_profile(dev)
        verify_info = decode_profile(verify)
        print(f"\n  Verify DPI: {verify_info['dpi_values']}")

    elif cmd == 'slot':
        slot = int(sys.argv[2])
        if slot < 0 or slot > 4:
            print("Slot must be 0-4")
            dev.close()
            return

        print(f"\nSetting active DPI slot to {slot}...")
        current = read_profile(dev)
        if not current or len(current) < 75:
            print("ERROR: Could not read profile data")
            dev.close()
            return

        profile_data = bytearray(current[:75])
        profile_data[6] = slot
        write_profile(dev, bytes(profile_data))

    elif cmd == 'test':
        print("\n--- TEST: Writing DPI values directly ---")

        # Use the known-good profile data from the capture
        # This is what Swarm II sent:
        known_profile = bytes.fromhex(
            '06 4e 00 06 06 0a 03'   # header + active slot 3
            '90 01'                   # DPI 1: 400
            '1a 04'                   # DPI 2: 1050
            'b0 04'                   # DPI 3: 1200
            '40 06'                   # DPI 4: 1600
            '80 0c'                   # DPI 5: 3200
            '90 01 20 03 b0 04 40 06' # DPI set 2: 400,800,1200,1600
            '80 0c 01 00 03 0a 01 00 05 00 00'  # config
            '14 ff 00 48 ff 14 ff 00 48 ff 14 ff 00 48'  # LED
            'ff 14 ff 00 48 ff 14 ff 00 48 ff 14 ff 00 48'
            'ff 14 ff 00 48 ff 01 ff 51 ff'
            .replace(' ', ''))

        # Modify DPI 1 from 400 to 1000
        modified = set_dpi_values(known_profile, [1000, 1050, 1200, 1600, 3200])

        print(f"  Original DPI 1: 400 -> New: 1000")
        print(f"  Writing...")
        write_profile(dev, modified)

        input("\n  Check your mouse - DPI 1 should now be 1000. Press Enter to revert...")

        # Revert
        print("  Reverting to original...")
        write_profile(dev, known_profile)
        print("  Done!")

    dev.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
