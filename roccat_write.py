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


def write_buttons(dev, button_data):
    """
    Write button mappings to the mouse using command 0x47.
    button_data: 125 bytes (5 pages of 25 bytes)
    Protocol captured from Swarm II via Frida.
    """
    pages = [button_data[i * 25:(i + 1) * 25] for i in range(5)]
    checksum = sum(button_data) & 0xFFFF

    print(f'Writing buttons ({len(button_data)} bytes, checksum=0x{checksum:04x})')

    for pg in range(5):
        # SELECT PAGE: 06 01 47 06 02 [page] 00
        send(dev, [0x06, 0x01, 0x47, 0x06, 0x02, pg, 0x00], f'Btn select page {pg}')
        time.sleep(0.05)
        handshake(dev)

        # WRITE PAGE: 06 01 47 06 19 [25 bytes]
        page_cmd = [0x06, 0x01, 0x47, 0x06, 0x19] + list(pages[pg])
        send(dev, page_cmd, f'Btn write page {pg}')
        time.sleep(0.05)
        handshake(dev)

    # COMMIT: 06 01 49 06 03 [num_profiles] [checksum_lo] [checksum_hi]
    cs_lo = checksum & 0xFF
    cs_hi = (checksum >> 8) & 0xFF
    send(dev, [0x06, 0x01, 0x49, 0x06, 0x03, 0x05, cs_lo, cs_hi], 'Btn commit')
    time.sleep(0.05)
    handshake(dev)

    print('Buttons written!')


def build_button_data(keybinds, easy_shift, profile_slot=0):
    """
    Build 125-byte button data from keybind assignments.
    keybinds: dict of button_name -> action_string
    easy_shift: dict of button_name -> action_string
    """
    # HID scancodes for keyboard keys
    HID_KEYS = {
        'A': 0x04, 'B': 0x05, 'C': 0x06, 'D': 0x07, 'E': 0x08, 'F': 0x09,
        'G': 0x0A, 'H': 0x0B, 'I': 0x0C, 'J': 0x0D, 'K': 0x0E, 'L': 0x0F,
        'M': 0x10, 'N': 0x11, 'O': 0x12, 'P': 0x13, 'Q': 0x14, 'R': 0x15,
        'S': 0x16, 'T': 0x17, 'U': 0x18, 'V': 0x19, 'W': 0x1A, 'X': 0x1B,
        'Y': 0x1C, 'Z': 0x1D,
        '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
        '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
        'Enter': 0x28, 'Escape': 0x29, 'Backspace': 0x2A, 'Tab': 0x2B,
        'Space': 0x2C, 'CapsLock': 0x39,
        'F1': 0x3A, 'F2': 0x3B, 'F3': 0x3C, 'F4': 0x3D, 'F5': 0x3E, 'F6': 0x3F,
        'F7': 0x40, 'F8': 0x41, 'F9': 0x42, 'F10': 0x43, 'F11': 0x44, 'F12': 0x45,
        'Insert': 0x49, 'Home': 0x4A, 'PageUp': 0x4B, 'Delete': 0x4C,
        'End': 0x4D, 'PageDown': 0x4E,
        'Right': 0x4F, 'Left': 0x50, 'Down': 0x51, 'Up': 0x52,
        'LCtrl': 0xE0, 'LShift': 0xE1, 'LAlt': 0xE2, 'LWin': 0xE3,
        'RCtrl': 0xE4, 'RShift': 0xE5, 'RAlt': 0xE6, 'RWin': 0xE7,
    }

    MOD_MAP = {
        'LCtrl': 0x01, 'Ctrl': 0x01, 'LShift': 0x02, 'Shift': 0x02,
        'LAlt': 0x04, 'Alt': 0x04, 'LWin': 0x08, 'Win': 0x08,
        'RCtrl': 0x10, 'RShift': 0x20, 'RAlt': 0x40, 'RWin': 0x80,
    }

    # Standard function codes
    STD_CODES = {
        'Left Click': 0x01, 'Click': 0x01,
        'Right Click': 0x02, 'Menu': 0x02,
        'Middle Click': 0x03, 'Universal Scroll': 0x03,
        'Double-Click': 0x04,
        'Browser Forward': 0x05, 'Browser Back': 0x06, 'Browser Backward': 0x06,
        'Tilt Left': 0x07, 'Tilt Right': 0x08,
        'Scroll Up': 0x09, 'Scroll Down': 0x0a,
    }

    def encode_action(action_str):
        """Encode an action string to bytes."""
        if not action_str or action_str == 'Disabled':
            return b''

        # Standard functions
        if action_str in STD_CODES:
            return bytes([STD_CODES[action_str], 0x01])

        # DPI functions
        if action_str == 'DPI Up':
            return bytes([0x02, 0x02])
        if action_str == 'DPI Down':
            return bytes([0x03, 0x02])

        # Easy Shift
        if action_str == 'Easy Shift':
            return bytes([0x01, 0x0a])

        # Keyboard hotkey
        if action_str.startswith('Hotkey '):
            key_str = action_str[7:]
            parts = key_str.split('+')
            modifier = 0
            scancode = 0
            for part in parts:
                part = part.strip()
                if part in MOD_MAP:
                    modifier |= MOD_MAP[part]
                elif part in HID_KEYS:
                    scancode = HID_KEYS[part]
                elif part.upper() in HID_KEYS:
                    scancode = HID_KEYS[part.upper()]
            if scancode:
                return bytes([scancode, modifier, 0x06, 0x00])

        # Volume/multimedia
        if action_str == 'Volume Up':
            return bytes([0x07, 0x03])
        if action_str == 'Volume Down':
            return bytes([0x08, 0x03])
        if action_str == 'Prev Track':
            return bytes([0x07, 0x03])
        if action_str == 'Next Track':
            return bytes([0x08, 0x03])

        return b''

    # Button slot order (primary layer)
    primary_order = [
        'left_button', 'right_button', 'middle_button',
        'scroll_up', 'scroll_down',
        'side_button_1', 'side_button_2',
        'dpi_up', 'dpi_down',
        'thumb_button_1', 'thumb_button_2',
        'tilt_left', 'tilt_right',
        'easy_shift',
    ]

    # Easy Shift layer order
    es_order = [
        'left_button', 'right_button',
        'middle_button',
        'scroll_up', 'scroll_down',
        'side_button_1', 'side_button_2',
        'dpi_up', 'dpi_down',
        'thumb_button_1', 'thumb_button_2',
        'tilt_left', 'tilt_right',
    ]

    # Raw button data captured from Swarm II via Frida (second pass = original state)
    # This is the EXACT data Swarm II writes, concatenated from 5 pages of 25 bytes
    BUTTON_TEMPLATE = bytearray([
        0x07, 0x7d, 0x00, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x03, 0x01, 0x00, 0x00, 0x09, 0x01, 0x00, 0x00, 0x0a, 0x01, 0x00, 0x13,
        0x00, 0x06, 0x00, 0x41, 0x00, 0x06, 0x00, 0x00, 0x03, 0x01, 0x00, 0x06, 0x00, 0x06, 0x00, 0x25, 0x00, 0x06, 0x00, 0x00, 0x05, 0x01, 0x00, 0x00, 0x07,
        0x01, 0x00, 0x00, 0x08, 0x01, 0x00, 0x00, 0x01, 0x0a, 0x00, 0x00, 0x01, 0x08, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x04, 0x03,
        0x00, 0x00, 0x07, 0x03, 0x00, 0x00, 0x08, 0x03, 0x00, 0x4b, 0x00, 0x06, 0x00, 0x4e, 0x00, 0x06, 0x00, 0x19, 0x01, 0x06, 0x00, 0x06, 0x01, 0x06, 0x00,
        0x4c, 0x00, 0x06, 0x00, 0x49, 0x00, 0x06, 0x00, 0x00, 0x02, 0x03, 0x00, 0x00, 0x03, 0x03, 0x00, 0x00, 0x01, 0x0a, 0x00, 0x00, 0x0b, 0x08, 0x24, 0x03,
    ])

    data = bytearray(BUTTON_TEMPLATE)
    data[2] = profile_slot

    # Entry offset map: (offset, entry_size)
    # Offsets verified against raw Frida capture
    ENTRY_OFFSETS = {
        'left_button':    (5, 2),     # [01 01]
        'right_button':   (9, 2),     # [02 01]
        'middle_button':  (13, 2),    # [03 01]
        'scroll_up':      (17, 2),    # [09 01]
        'scroll_down':    (21, 2),    # [0a 01]
        'side_button_1':  (24, 4),    # [13 00 06 00] keyboard P
        'side_button_2':  (28, 4),    # [41 00 06 00] keyboard F8
        'dpi_up':         (33, 2),    # [03 01] Middle Click
        'dpi_down':       (36, 4),    # [06 00 06 00] keyboard C
        'thumb_button_1': (40, 4),    # [25 00 06 00] keyboard 8
        'thumb_button_2': (45, 2),    # [05 01] Browser Forward
        'tilt_left':      (49, 2),    # [07 01] Tilt Left
        'tilt_right':     (53, 2),    # [08 01] Tilt Right
        'easy_shift':     (57, 2),    # [01 0a] Easy Shift
    }

    # Easy Shift layer offsets (verified from capture)
    ES_ENTRY_OFFSETS = {
        'left_button':    (65, 2),    # [01 01]
        'right_button':   (69, 2),    # [02 01]
        'side_button_1':  (84, 4),    # [4b 00 06 00] PageUp
        'side_button_2':  (88, 4),    # [4e 00 06 00] PageDown
        'dpi_up':         (92, 4),    # [19 01 06 00] LCtrl+V
        'dpi_down':       (96, 4),    # [06 01 06 00] LCtrl+C
        'thumb_button_1': (100, 4),   # [4c 00 06 00] Delete
        'thumb_button_2': (104, 4),   # [49 00 06 00] Insert
    }

    # Override entries with user's keybinds
    # NOTE: We only replace entries that match the template's size at that slot.
    # If a 2-byte action replaces a 4-byte keyboard slot, we write the 2 bytes
    # and zero out the remaining 2. Vice versa is not supported (would shift data).
    for btn_name, (offset, slot_size) in ENTRY_OFFSETS.items():
        action = keybinds.get(btn_name, '')
        if not action:
            continue
        encoded = encode_action(action)
        if not encoded:
            continue
        # Write the encoded bytes
        for j in range(min(len(encoded), slot_size)):
            if offset + j < len(data) - 2:
                data[offset + j] = encoded[j]
        # Zero remaining bytes if encoded is shorter than slot
        for j in range(len(encoded), slot_size):
            if offset + j < len(data) - 2:
                data[offset + j] = 0x00

    for btn_name, (offset, slot_size) in ES_ENTRY_OFFSETS.items():
        action = easy_shift.get(btn_name, '')
        if not action:
            continue
        encoded = encode_action(action)
        if not encoded:
            continue
        for j in range(min(len(encoded), slot_size)):
            if offset + j < len(data) - 2:
                data[offset + j] = encoded[j]
        for j in range(len(encoded), slot_size):
            if offset + j < len(data) - 2:
                data[offset + j] = 0x00

    # Recompute checksum
    cs = sum(data[:-2]) & 0xFFFF
    data[-2] = cs & 0xFF
    data[-1] = (cs >> 8) & 0xFF

    return bytes(data)


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

    # Check for --buttons flag with JSON data
    button_json = None
    if '--buttons' in sys.argv:
        idx = sys.argv.index('--buttons')
        if idx + 1 < len(sys.argv):
            import json
            button_json = json.loads(sys.argv[idx + 1])

    print(f'=== ROCCAT Direct Write — Setting DPI to {target_dpi} ===\n')

    kill_swarm()
    dev = open_dongle()
    if not dev:
        return

    # Write DPI to ALL 5 profile slots
    dpi_values = [target_dpi] * 5
    for slot in range(5):
        profile = build_profile(dpi_values, profile_slot=slot)
        write_profile(dev, profile)
        time.sleep(0.1)
        print(f'  DPI slot {slot} written')

    # Write button mappings if provided
    if button_json:
        keybinds = button_json.get('keybinds', {})
        easy_shift = button_json.get('easy_shift', {})
        print(f'\nWriting button mappings...')
        for slot in range(5):
            btn_data = build_button_data(keybinds, easy_shift, profile_slot=slot)
            write_buttons(dev, btn_data)
            time.sleep(0.1)
            print(f'  Button slot {slot} written')

    dll.hid_close(dev)
    try:
        dll.hid_exit()
    except:
        pass

    print(f'\nDone! Mouse should now be at {target_dpi} DPI.')
    if button_json:
        print('Button mappings also updated.')


if __name__ == '__main__':
    main()
