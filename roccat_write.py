"""
Direct mouse profile write using KONE_XP_AIR.dll's HIDAPI.
Protocol captured via Frida from Swarm II's actual DPI write sequence.
"""
import ctypes
import os
import sys
import time
import struct
import subprocess

# ── Load KONE_XP_AIR.dll ────────────────────────────────────────────────────
SWARM_DIR = r'C:\Program Files\Turtle Beach Swarm II'
os.add_dll_directory(SWARM_DIR)
os.environ['PATH'] = SWARM_DIR + ';' + os.environ.get('PATH', '')

DLL_PATH = os.path.join(SWARM_DIR, 'Data', 'Devices', 'KONE_XP_AIR', 'KONE_XP_AIR.dll')
dll = ctypes.CDLL(DLL_PATH)

# ── Define HIDAPI function signatures ────────────────────────────────────────
dll.hid_init.restype = ctypes.c_int
dll.hid_open_path.restype = ctypes.c_void_p
dll.hid_open_path.argtypes = [ctypes.c_char_p]
dll.hid_send_feature_report.restype = ctypes.c_int
dll.hid_send_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
dll.hid_get_feature_report.restype = ctypes.c_int
dll.hid_get_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
dll.hid_close.argtypes = [ctypes.c_void_p]

REPORT_LEN = 30


def pad(data):
    """Pad data to 30 bytes."""
    return bytes(data) + b'\x00' * (REPORT_LEN - len(data))


def send(dev, data, label=''):
    """Send a feature report and return bytes written."""
    padded = pad(data)
    n = dll.hid_send_feature_report(dev, padded, REPORT_LEN)
    if label:
        print(f'  {label}: sent {n} bytes')
    return n


def get_response(dev):
    """Read feature report response (1 byte, report ID 0x06)."""
    buf = ctypes.create_string_buffer(REPORT_LEN)
    buf[0] = 0x06
    n = dll.hid_get_feature_report(dev, buf, REPORT_LEN)
    return n


def handshake(dev):
    """Send handshake and wait for response."""
    send(dev, [0x06, 0x01, 0x44, 0x07])
    time.sleep(0.1)
    get_response(dev)
    time.sleep(0.05)


def write_profile(dev, profile_data):
    """
    Write a full profile to the mouse using the exact Swarm II protocol.
    profile_data: 75 bytes of profile data (DPI, polling, LEDs, etc.)
    """
    # Split into 3 pages of 25 bytes
    pages = []
    for i in range(3):
        pages.append(profile_data[i * 25:(i + 1) * 25])

    # Compute checksum over all profile data
    checksum = sum(profile_data) & 0xFFFF

    print(f'Writing profile ({len(profile_data)} bytes, checksum=0x{checksum:04x})')

    # Page write sequence (captured from Swarm II via Frida)
    for pg in range(3):
        # SELECT PAGE: 06 01 46 06 02 [page] 01 00
        # Note the 01 at position 6 — critical!
        send(dev, [0x06, 0x01, 0x46, 0x06, 0x02, pg, 0x01], f'Select page {pg}')
        time.sleep(0.05)

        # HANDSHAKE + GET RESPONSE
        handshake(dev)

        # WRITE PAGE DATA: 06 01 46 06 19 [25 bytes]
        page_cmd = [0x06, 0x01, 0x46, 0x06, 0x19] + list(pages[pg])
        send(dev, page_cmd, f'Write page {pg}')
        time.sleep(0.05)

        # HANDSHAKE + GET RESPONSE
        handshake(dev)

    # SELECT END PAGE: 06 01 46 06 02 03 01 00
    send(dev, [0x06, 0x01, 0x46, 0x06, 0x02, 0x03, 0x01], 'Select end page')
    time.sleep(0.05)
    handshake(dev)

    # COMMIT: 06 01 46 06 03 ff [checksum_lo] [checksum_hi]
    cs_lo = checksum & 0xFF
    cs_hi = (checksum >> 8) & 0xFF
    send(dev, [0x06, 0x01, 0x46, 0x06, 0x03, 0xFF, cs_lo, cs_hi], 'Commit')
    time.sleep(0.05)
    handshake(dev)

    print('Profile written!')


def switch_profile(dev, slot, num_profiles=5):
    """
    Switch the active profile on the mouse.
    Captured from Swarm II via Frida:
      06 01 45 06 02 [slot] [num_profiles]  — Profile SELECT
      06 01 44 07                            — Handshake
      06 01 4e 06 04 [slot] 01 01 ff        — Profile ACTIVATE
      06 01 44 07                            — Handshake
    """
    print(f'Switching to profile slot {slot}...')

    # Read pages first (Swarm II does this before switching)
    for pg in range(4):
        send(dev, [0x06, 0x01, 0x46, 0x06, 0x02, pg, 0x01], f'Read page {pg}')
        time.sleep(0.05)
        send(dev, [0x06, 0x01, 0x46, 0x07], 'Page handshake')
        time.sleep(0.1)
        get_response(dev)
        time.sleep(0.05)

    # SELECT profile
    send(dev, [0x06, 0x01, 0x45, 0x06, 0x02, slot, num_profiles], f'Select slot {slot}')
    time.sleep(0.05)
    handshake(dev)

    # ACTIVATE profile
    send(dev, [0x06, 0x01, 0x4e, 0x06, 0x04, slot, 0x01, 0x01, 0xff], f'Activate slot {slot}')
    time.sleep(0.05)
    handshake(dev)

    print(f'Switched to profile slot {slot}!')


def build_profile(dpi_values, profile_slot=0, polling_rate=0x1f):
    """
    Build a 75-byte profile data block.
    dpi_values: list of 5 DPI values (int, actual DPI like 400, 800, etc.)
    profile_slot: onboard profile slot (0-4)
    polling_rate: 0x1f=default, 0x0a=1000Hz
    """
    p = bytearray(75)

    # Header
    p[0] = 0x06       # Report ID
    p[1] = 0x4E       # Profile data length marker
    p[2] = profile_slot  # Profile slot (0-4)
    p[3] = 0x06       # Unknown
    p[4] = 0x06       # Unknown
    p[5] = polling_rate

    # Active DPI stage (0-indexed)
    p[6] = 0x00

    # DPI X values (5 stages, 16-bit LE)
    for i in range(5):
        dpi = dpi_values[i] if i < len(dpi_values) else dpi_values[-1]
        struct.pack_into('<H', p, 7 + i * 2, dpi)

    # DPI Y values (same as X)
    for i in range(5):
        dpi = dpi_values[i] if i < len(dpi_values) else dpi_values[-1]
        struct.pack_into('<H', p, 17 + i * 2, dpi)

    # Config bytes
    p[27] = 0x00
    p[28] = 0x00
    p[29] = 0x03
    p[30] = 0x0a
    p[31] = 0x06
    p[32] = 0xff
    p[33] = 0x05
    p[34] = 0x00
    p[35] = 0x00

    # LED color data (default green for all 5 stages + 2 extra)
    for i in range(7):
        offset = 36 + i * 5
        if offset + 4 < len(p):
            p[offset] = 0x14       # brightness
            p[offset + 1] = 0xFF   # R
            p[offset + 2] = 0x00   # G
            p[offset + 3] = 0x48   # B
            p[offset + 4] = 0xFF   # alpha

    # Footer
    p[71] = 0x01
    p[72] = 0x64
    p[73] = 0xFF
    p[74] = 0xFF

    return bytes(p)


def find_dongle_path():
    """Find the dongle's config interface path."""
    import hid
    for d in hid.enumerate(0x10F5, 0x5017):
        if d['usage_page'] == 0xFF03:
            return d['path']
    return None


def kill_swarm():
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Swarm II.exe'], capture_output=True)
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Device Service.exe'], capture_output=True)
    subprocess.run(['taskkill', '/f', '/im', 'ROCCAT_Swarm_Monitor.exe'], capture_output=True)
    time.sleep(2)


def open_dongle():
    path = find_dongle_path()
    if not path:
        print('Dongle not found!')
        return None
    print(f'Dongle path: {path}')
    dll.hid_init()
    dev = dll.hid_open_path(path)
    if not dev:
        print('Could not open device!')
        return None
    print(f'Device opened: {dev}')
    return dev


def main():
    if len(sys.argv) < 2:
        print('Usage:')
        print('  python roccat_write.py <dpi>          Set DPI on all profiles')
        print('  python roccat_write.py switch <slot>  Switch to profile slot (0-4)')
        return

    # Check if this is a profile switch or DPI write
    if sys.argv[1] == 'switch':
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        print(f'=== Switching to profile slot {slot} ===\n')

        kill_swarm()
        dev = open_dongle()
        if not dev:
            return

        switch_profile(dev, slot)
        dll.hid_close(dev)
        try:
            dll.hid_exit()
        except:
            pass
        print('\nDone!')
        return

    target_dpi = int(sys.argv[1])

    print(f'=== ROCCAT Direct Write — Setting DPI to {target_dpi} ===\n')

    kill_swarm()
    dev = open_dongle()
    if not dev:
        return

    print(f'Dongle path: {path}')

    # Initialize DLL's HIDAPI and open device
    dll.hid_init()
    dev = dll.hid_open_path(path)
    if not dev:
        print('Could not open device!')
        return

    print(f'Device opened: {dev}\n')

    # Write to ALL 5 profile slots
    dpi_values = [target_dpi] * 5
    for slot in range(5):
        profile = build_profile(dpi_values, profile_slot=slot)
        write_profile(dev, profile)
        time.sleep(0.1)
        print(f'  Slot {slot} written')

    dll.hid_close(dev)

    # Don't restart Swarm II — it would overwrite our values

    print(f'\nDone! Mouse should now be at {target_dpi} DPI.')
    print('Check if the mouse speed changed!')


if __name__ == '__main__':
    main()
