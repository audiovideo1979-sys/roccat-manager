"""
Direct HID write to Kone XP Air via dongle.
Protocol decoded from USB capture of Swarm II.

Target: Dongle PID=0x5017, IF=2 (usage_page=0xFF03), Report ID=0x06
All commands are 30-byte SET_FEATURE reports.

CLOSE SWARM II BEFORE RUNNING THIS.
"""
import hid
import time
import struct
import sys

VENDOR_ID = 0x10F5
DONGLE_PID = 0x5017
USAGE_PAGE = 0xFF03
REPORT_LEN = 30

def pad(data, length=REPORT_LEN):
    """Pad command to report length."""
    return list(data) + [0x00] * (length - len(data))

def find_dongle():
    for d in hid.enumerate():
        if (d['vendor_id'] == VENDOR_ID and
            d['product_id'] == DONGLE_PID and
            d['usage_page'] == USAGE_PAGE):
            return d
    return None

def send_cmd(dev, data, label=""):
    """Send a feature report and read back response."""
    cmd = pad(data)
    dev.send_feature_report(cmd)
    time.sleep(0.05)
    # Read response
    try:
        resp = dev.get_feature_report(0x06, REPORT_LEN + 1)
        if label:
            hex_resp = ' '.join(f'{b:02x}' for b in resp[:16])
            print(f"  {label}: sent OK, resp={hex_resp}")
        return resp
    except Exception as e:
        if label:
            print(f"  {label}: sent OK, no resp ({e})")
        return None

def build_profile_data(dpi_values, active_stage=0, dpi_y_values=None):
    """
    Build 75-byte profile data from DPI settings.

    dpi_values: list of 5 DPI values (e.g. [400, 1050, 1200, 1600, 3200])
    active_stage: 0-4, which DPI stage is active
    dpi_y_values: optional separate Y-axis DPI values (defaults to same as dpi_values)
    """
    if dpi_y_values is None:
        dpi_y_values = list(dpi_values)

    # Page 0: Header + DPI values
    page0 = [
        0x06,  # byte 0: report/config ID
        0x4e,  # byte 1: data length marker (78?)
        0x00,  # byte 2
        0x06,  # byte 3: num DPI stages? or config version
        0x06,  # byte 4: same
        0x0a,  # byte 5: polling rate (0x0a=1000Hz)
        active_stage & 0xFF,  # byte 6: active DPI stage (0-indexed)
    ]

    # DPI X values (5 x 16-bit LE)
    for dpi in dpi_values[:5]:
        page0.extend([dpi & 0xFF, (dpi >> 8) & 0xFF])

    # DPI Y values (4 fit in page 0, 1 overflows to page 1)
    for dpi in dpi_y_values[:4]:
        page0.extend([dpi & 0xFF, (dpi >> 8) & 0xFF])

    assert len(page0) == 25, f"Page 0 should be 25 bytes, got {len(page0)}"

    # Page 1: Last Y DPI + config + LED colors
    page1 = []
    # 5th Y DPI value
    page1.extend([dpi_y_values[4] & 0xFF, (dpi_y_values[4] >> 8) & 0xFF])
    # Config bytes (from capture)
    page1.extend([0x01, 0x00, 0x03, 0x0a, 0x01, 0x00, 0x05, 0x00, 0x00])
    # LED data for DPI stages (brightness, R, G, B, alpha) - 5 bytes each
    # From capture: 14 ff 00 48 ff (pinkish-red, brightness 20)
    led_entry = [0x14, 0xff, 0x00, 0x48, 0xff]
    # 2 full LEDs fit + partial 3rd
    page1.extend(led_entry)  # LED 1
    page1.extend(led_entry)  # LED 2
    page1.extend(led_entry[:4])  # LED 3 partial (ff continues on page 2)

    assert len(page1) == 25, f"Page 1 should be 25 bytes, got {len(page1)}"

    # Page 2: Continue LEDs + footer
    page2 = [0xff]  # LED 3 alpha
    page2.extend(led_entry)  # LED 4
    page2.extend(led_entry)  # LED 5
    page2.extend(led_entry)  # LED 6?
    page2.extend(led_entry)  # LED 7?
    # Footer from capture
    page2.extend([0x01, 0xff, 0x51, 0xff])

    assert len(page2) == 25, f"Page 2 should be 25 bytes, got {len(page2)}"

    return page0, page1, page2

def checksum(page0, page1, page2):
    """Calculate 16-bit LE checksum (sum of all 75 data bytes)."""
    total = sum(page0) + sum(page1) + sum(page2)
    return total & 0xFFFF

def write_profile(dev, dpi_values, active_stage=0, dpi_y_values=None):
    """Write a full profile to the mouse via the dongle."""
    page0, page1, page2 = build_profile_data(dpi_values, active_stage, dpi_y_values)
    pages = [page0, page1, page2]

    csum = checksum(page0, page1, page2)
    print(f"\nProfile data checksum: 0x{csum:04x}")

    # Step 1: Init
    print("\n1. Init sequence...")
    send_cmd(dev, [0x06, 0x00, 0x00, 0x04], "Init 04")
    time.sleep(0.05)
    send_cmd(dev, [0x06, 0x00, 0x00, 0x05], "Init 05")
    time.sleep(0.1)
    send_cmd(dev, [0x06, 0x01, 0x44, 0x07], "Handshake")
    time.sleep(0.1)

    # Step 2: Write pages
    for page_num in range(3):
        print(f"\n2.{page_num}. Writing page {page_num}...")
        # Select page
        send_cmd(dev, [0x06, 0x01, 0x46, 0x06, 0x02, page_num], f"Select page {page_num}")
        time.sleep(0.1)
        send_cmd(dev, [0x06, 0x01, 0x44, 0x07], "Handshake")
        time.sleep(0.1)

        # Write data (0x19 = 25 bytes of data)
        data_cmd = [0x06, 0x01, 0x46, 0x06, 0x19] + pages[page_num]
        hex_str = ' '.join(f'{b:02x}' for b in data_cmd[:30])
        print(f"    Data: {hex_str}")
        send_cmd(dev, data_cmd, f"Write page {page_num}")
        time.sleep(0.1)
        send_cmd(dev, [0x06, 0x01, 0x44, 0x07], "Handshake")
        time.sleep(0.1)

    # Step 3: End pages marker
    print("\n3. End pages + commit...")
    send_cmd(dev, [0x06, 0x01, 0x46, 0x06, 0x02, 0x03], "End pages")
    time.sleep(0.1)
    send_cmd(dev, [0x06, 0x01, 0x44, 0x07], "Handshake")
    time.sleep(0.1)

    # Step 4: Commit with checksum
    csum_lo = csum & 0xFF
    csum_hi = (csum >> 8) & 0xFF
    send_cmd(dev, [0x06, 0x01, 0x46, 0x06, 0x03, 0x00, csum_lo, csum_hi], "Commit")
    time.sleep(0.1)
    send_cmd(dev, [0x06, 0x01, 0x44, 0x07], "Final handshake")

    print("\nDone! Profile written.")


def read_current(dev):
    """Read current profile by doing a read cycle."""
    print("\nReading current profile...")
    # Try just reading report 0x06
    try:
        data = dev.get_feature_report(0x06, REPORT_LEN + 1)
        hex_str = ' '.join(f'{b:02x}' for b in data[:30])
        print(f"  Current report 0x06: {hex_str}")
        return data
    except Exception as e:
        print(f"  Read failed: {e}")
        return None


if __name__ == '__main__':
    # Parse DPI from command line
    target_dpi = 10000
    if len(sys.argv) > 1:
        target_dpi = int(sys.argv[1])

    print(f"=== Direct DPI Write to Kone XP Air ===")
    print(f"Target DPI: {target_dpi}")
    print(f"Make sure Swarm II is CLOSED!\n")

    info = find_dongle()
    if not info:
        print("ERROR: Dongle not found!")
        print("Available ROCCAT devices:")
        for d in hid.enumerate():
            if d['vendor_id'] == VENDOR_ID:
                print(f"  PID=0x{d['product_id']:04x} UP=0x{d['usage_page']:04x} "
                      f"Usage=0x{d['usage']:04x} {d['product_string']}")
        sys.exit(1)

    print(f"Found dongle: {info['product_string']}")
    print(f"  PID=0x{info['product_id']:04x} UP=0x{info['usage_page']:04x}")

    dev = hid.device()
    dev.open_path(info['path'])
    dev.set_nonblocking(1)

    # Read current state
    read_current(dev)

    # Write new profile with target DPI on all stages
    # Keep original structure but change DPI values
    dpi_values = [target_dpi, target_dpi, target_dpi, target_dpi, target_dpi]

    print(f"\nWriting DPI = {target_dpi} on all 5 stages...")
    write_profile(dev, dpi_values, active_stage=0)

    # Read back
    time.sleep(0.5)
    read_current(dev)

    dev.close()
    print("\nMove your mouse - did the DPI change?")
