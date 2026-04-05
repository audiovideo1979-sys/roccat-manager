"""
swarm_ini.py — Read/write Turtle Beach Swarm II INI profiles

Decodes and encodes the Qt ByteArray fields in KONE_XP_AIR_TB.ini,
particularly m_btn_setting (button mappings) and MainSetting (DPI/profile data).
"""

import re
import struct
import shutil
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
SWARM_SETTING_DIR = Path(r"C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Setting")
INI_FILE = SWARM_SETTING_DIR / "KONE_XP_AIR_TB.ini"

# ── Standard function codes (type 0x01) ──────────────────────────────────────
# Sequential, matching Swarm II's STANDARD function list
STANDARD_FUNCTIONS = {
    0x00: "Disabled",
    0x01: "Click",
    0x02: "Menu",
    0x03: "Universal Scroll",
    0x04: "Double-Click",
    0x05: "Browser Forward",
    0x06: "Browser Backward",
    0x07: "Tilt Left",
    0x08: "Tilt Right",
    0x09: "Scroll Up",
    0x0a: "Scroll Down",
    0x0b: "Insert",
    0x0c: "Delete",
    0x0d: "Home",
    0x0e: "End",
    0x0f: "Page Up",
    0x10: "Page Down",
    0x11: "Ctrl",
    0x12: "Shift",
    0x13: "Alt",
    0x14: "Win",
    0x15: "CapsLock",
}

# Reverse lookup
STANDARD_BY_NAME = {v: k for k, v in STANDARD_FUNCTIONS.items()}

# ── DPI function codes (type 0x02) ───────────────────────────────────────────
DPI_FUNCTIONS = {
    0x01: "DPI Cycle Up",
    0x02: "DPI Up",
    0x03: "DPI Down",
    0x04: "DPI Cycle Down",
}

# ── Easy Shift codes (type 0x03) ─────────────────────────────────────────────
EASYSHIFT_FUNCTIONS = {
    0x04: "ES Unknown 04",
}

# ── Scroll codes (type 0x04) ─────────────────────────────────────────────────
SCROLL_FUNCTIONS = {
    0x76: "Scroll Up (wheel)",
}

# ── Special codes (type 0x0a) ────────────────────────────────────────────────
SPECIAL_FUNCTIONS = {
    0x01: "Easy Shift",
}

# ── Profile/macro codes (type 0x62) ──────────────────────────────────────────
PROFILE_FUNCTIONS = {
    0x01: "Profile Macro 1",
}

# ── Multimedia codes (type 0x04) ─────────────────────────────────────────────
MULTIMEDIA_FUNCTIONS = {
    0x61: "Volume Up",
    0x62: "Volume Down",
}

# ── USB HID Scancodes (for keyboard hotkey type 0x06) ────────────────────────
HID_SCANCODES = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F',
    0x0A: 'G', 0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L',
    0x10: 'M', 0x11: 'N', 0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R',
    0x16: 'S', 0x17: 'T', 0x18: 'U', 0x19: 'V', 0x1A: 'W', 0x1B: 'X',
    0x1C: 'Y', 0x1D: 'Z',
    0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4', 0x22: '5',
    0x23: '6', 0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'Enter', 0x29: 'Escape', 0x2A: 'Backspace', 0x2B: 'Tab',
    0x2C: 'Space', 0x2D: 'Minus', 0x2E: 'Equals', 0x2F: 'LBracket',
    0x30: 'RBracket', 0x31: 'Backslash', 0x33: 'Semicolon', 0x34: 'Quote',
    0x35: 'Grave', 0x36: 'Comma', 0x37: 'Period', 0x38: 'Slash',
    0x39: 'CapsLock',
    0x3A: 'F1', 0x3B: 'F2', 0x3C: 'F3', 0x3D: 'F4', 0x3E: 'F5', 0x3F: 'F6',
    0x40: 'F7', 0x41: 'F8', 0x42: 'F9', 0x43: 'F10', 0x44: 'F11', 0x45: 'F12',
    0x46: 'PrintScreen', 0x47: 'ScrollLock', 0x48: 'Pause',
    0x49: 'Insert', 0x4A: 'Home', 0x4B: 'PageUp', 0x4C: 'Delete',
    0x4D: 'End', 0x4E: 'PageDown', 0x4F: 'Right', 0x50: 'Left',
    0x51: 'Down', 0x52: 'Up',
    0x53: 'NumLock', 0x54: 'NumDivide', 0x55: 'NumMultiply',
    0x56: 'NumMinus', 0x57: 'NumPlus', 0x58: 'NumEnter',
    0x59: 'Num1', 0x5A: 'Num2', 0x5B: 'Num3', 0x5C: 'Num4',
    0x5D: 'Num5', 0x5E: 'Num6', 0x5F: 'Num7', 0x60: 'Num8',
    0x61: 'Num9', 0x62: 'Num0',
    0xE0: 'LCtrl', 0xE1: 'LShift', 0xE2: 'LAlt', 0xE3: 'LWin',
    0xE4: 'RCtrl', 0xE5: 'RShift', 0xE6: 'RAlt', 0xE7: 'RWin',
}

HID_BY_NAME = {v: k for k, v in HID_SCANCODES.items()}

# ── HID Modifier masks ──────────────────────────────────────────────────────
HID_MODIFIERS = {
    0x01: 'LCtrl',
    0x02: 'LShift',
    0x04: 'LAlt',
    0x08: 'LWin',
    0x10: 'RCtrl',
    0x20: 'RShift',
    0x40: 'RAlt',
    0x80: 'RWin',
}


# ── Qt ByteArray decoder ────────────────────────────────────────────────────
def decode_qt_bytearray(data):
    """Decode Qt @ByteArray(...) escape sequences to raw bytes."""
    result = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x5c and i + 1 < len(data):  # backslash
            c = data[i + 1]
            if c == ord('x'):
                i += 2
                hex_str = ''
                while i < len(data) and len(hex_str) < 2:
                    ch = chr(data[i])
                    if ch in '0123456789abcdefABCDEF':
                        hex_str += ch
                        i += 1
                    else:
                        break
                if hex_str:
                    result.append(int(hex_str, 16))
            elif c == ord('0'):
                result.append(0)
                i += 2
            elif c == ord('n'):
                result.append(0x0a)
                i += 2
            elif c == ord('r'):
                result.append(0x0d)
                i += 2
            elif c == ord('t'):
                result.append(0x09)
                i += 2
            elif c == ord('f'):
                result.append(0x0c)
                i += 2
            elif c == 0x5c:
                result.append(0x5c)
                i += 2
            else:
                result.append(data[i + 1])
                i += 2
        else:
            result.append(b)
            i += 1
    return bytes(result)


def encode_qt_bytearray(data):
    """Encode raw bytes to Qt @ByteArray(...) escape sequence format."""
    result = bytearray()
    for b in data:
        if b == 0x00:
            result.extend(b'\\0')
        elif b == 0x0a:
            result.extend(b'\\n')
        elif b == 0x0d:
            result.extend(b'\\r')
        elif b == 0x09:
            result.extend(b'\\t')
        elif b == 0x0c:
            result.extend(b'\\f')
        elif b == 0x5c:
            result.extend(b'\\\\')
        elif 32 <= b < 127 and b not in (0x28, 0x29, 0x22):
            # printable ASCII except parens and quotes
            result.append(b)
        else:
            result.extend(('\\x%x' % b).encode())
    return bytes(result)


# ── INI field extraction ────────────────────────────────────────────────────
def read_ini():
    """Read the raw INI file."""
    with open(INI_FILE, 'rb') as f:
        return f.read()


def extract_field(raw, field_name):
    """Extract and decode a @ByteArray field from raw INI data."""
    pattern = field_name.encode() + rb'="?@ByteArray\(([^)]*)\)"?'
    m = re.search(pattern, raw)
    if m:
        return decode_qt_bytearray(m.group(1)), m.start(1), m.end(1)
    return None, None, None


def replace_field(raw, field_name, new_data):
    """Replace a @ByteArray field's content in raw INI data."""
    pattern = field_name.encode() + rb'="?@ByteArray\(([^)]*)\)"?'
    m = re.search(pattern, raw)
    if not m:
        return raw
    encoded = encode_qt_bytearray(new_data)
    return raw[:m.start(1)] + encoded + raw[m.end(1):]


# ── Button action parsing ───────────────────────────────────────────────────
def decode_button_action(data, offset):
    """
    Decode a button action starting at offset.
    Returns (action_dict, bytes_consumed).

    Entry formats:
    - [code] [type] where type in (0x01, 0x02, 0x03, 0x04, 0x0a, 0x62)
    - [scancode] [modifier] [0x06] [0x00] for keyboard hotkeys
    - [0x00] for disabled/padding
    """
    if offset >= len(data):
        return None, 0

    code = data[offset]

    # Check for 4-byte keyboard hotkey format: [scancode] [modifier] [0x06] [0x00]
    # Modifier must be a valid bitmask (0x00-0x0F for common combos, up to 0xFF)
    # But certain values like 0x62 are actually type bytes for other entry formats
    if offset + 3 < len(data) and data[offset + 2] == 0x06 and data[offset + 3] == 0x00:
        scancode = data[offset]
        modifier = data[offset + 1]

        # Validate: modifier should be 0x00 or a valid HID modifier bitmask
        # Valid modifier bits: LCtrl=01, LShift=02, LAlt=04, LWin=08, RCtrl=10, RShift=20, RAlt=40, RWin=80
        # Values like 0x62, 0x04, etc. that are also type bytes need context checking
        # A real keyboard entry has scancode in the HID range (0x04-0xE7)
        is_valid_keyboard = (
            scancode in HID_SCANCODES and
            modifier <= 0x0F  # common modifier combos (Ctrl+Shift+Alt+Win)
        )
        # Also accept higher modifiers if scancode is clearly a key
        if not is_valid_keyboard and scancode in HID_SCANCODES and modifier in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x40, 0x80):
            is_valid_keyboard = True

        if is_valid_keyboard:
            key_name = HID_SCANCODES.get(scancode, f'Unknown(0x{scancode:02x})')

            mod_parts = []
            for mask, name in sorted(HID_MODIFIERS.items()):
                if modifier & mask:
                    mod_parts.append(name)

            if mod_parts:
                action_name = '+'.join(mod_parts) + '+' + key_name
            else:
                action_name = key_name

            return {
                'type': 'keyboard',
                'name': action_name,
                'scancode': scancode,
                'modifier': modifier,
            }, 4

    # 2-byte action: [code] [type]
    if offset + 1 < len(data):
        action_type = data[offset + 1]

        if action_type == 0x01:
            name = STANDARD_FUNCTIONS.get(code, f'Standard(0x{code:02x})')
            return {'type': 'standard', 'name': name, 'code': code}, 2

        elif action_type == 0x02:
            name = DPI_FUNCTIONS.get(code, f'DPI(0x{code:02x})')
            return {'type': 'dpi', 'name': name, 'code': code}, 2

        elif action_type == 0x03:
            return {'type': 'easyshift_func', 'name': f'ES(0x{code:02x})', 'code': code}, 2

        elif action_type == 0x04:
            name = SCROLL_FUNCTIONS.get(code, f'Scroll(0x{code:02x})')
            return {'type': 'scroll', 'name': name, 'code': code}, 2

        elif action_type == 0x0a:
            name = SPECIAL_FUNCTIONS.get(code, f'Special(0x{code:02x})')
            return {'type': 'special', 'name': name, 'code': code}, 2

        elif action_type == 0x62:
            return {'type': 'profile', 'name': f'Profile(0x{code:02x})', 'code': code}, 2

    # Single byte — padding or unknown
    return {'type': 'raw', 'name': f'Raw(0x{code:02x})', 'code': code}, 1


def encode_button_action(action):
    """Encode a button action dict back to bytes."""
    if action['type'] == 'keyboard':
        return bytes([action['scancode'], action.get('modifier', 0), 0x06, 0x00])
    elif action['type'] == 'standard':
        return bytes([action['code'], 0x01])
    elif action['type'] == 'dpi':
        return bytes([action['code'], 0x02])
    elif action['type'] == 'easyshift_func':
        return bytes([action['code'], 0x03])
    elif action['type'] == 'scroll':
        return bytes([action['code'], 0x04])
    elif action['type'] == 'special':
        return bytes([action['code'], 0x0a])
    elif action['type'] == 'profile':
        return bytes([action['code'], 0x62])
    elif action['type'] == 'disabled':
        return bytes([0x00])
    else:
        return bytes([action.get('code', 0x00)])


# ── Profile parsing ─────────────────────────────────────────────────────────
# Kone XP Air has 14 buttons, each with primary + Easy Shift = 28 entries per profile
BUTTON_NAMES = [
    'left_click', 'right_click', 'middle_click',
    'scroll_up', 'scroll_down',
    'thumb_1', 'thumb_2',
    'unknown_8', 'unknown_9',
    'unknown_10',
    'side_fwd', 'side_back',
    'tilt_left', 'tilt_right',
]


def parse_btn_setting(data):
    """
    Parse the m_btn_setting ByteArray into profile button assignments.
    Returns list of profile dicts.
    """
    if len(data) < 4:
        return []

    num_profiles = struct.unpack('>I', data[0:4])[0]
    profiles = []
    offset = 4

    for p_idx in range(num_profiles):
        # Skip to profile header: 7d 61 7d [idx] 00
        while offset < len(data) - 4:
            if data[offset:offset + 3] == b'\x7d\x61\x7d':
                break
            offset += 1

        if offset >= len(data) - 4:
            break

        profile_idx = data[offset + 3]
        offset += 5  # skip header

        # Parse button entries until next profile header or end
        entries = []
        while offset < len(data):
            # Check for next profile header or end marker
            if offset + 3 <= len(data) and data[offset:offset + 3] == b'\x7d\x61\x7d':
                break
            # Check for end-of-profile marker: 76 62 [checksum_lo] [checksum_hi]
            if offset + 2 <= len(data) and data[offset:offset + 2] == b'\x76\x62':
                offset += 4  # skip marker + 2-byte checksum
                break

            # Skip padding zeros between entries
            if data[offset] == 0x00:
                offset += 1
                continue

            action, consumed = decode_button_action(data, offset)
            if action and consumed > 0:
                entries.append(action)
                offset += consumed
            else:
                offset += 1

        profiles.append({
            'index': profile_idx,
            'entries': entries,
        })

    return profiles


def parse_main_setting(data):
    """Parse MainSetting ByteArray for DPI and profile data."""
    if len(data) < 8:
        return []

    num_profiles = struct.unpack('>I', data[0:4])[0]
    profiles = []
    offset = 4

    for _ in range(num_profiles):
        if offset + 4 > len(data):
            break
        prof_len = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4

        if offset + prof_len > len(data):
            break

        prof_data = data[offset:offset + prof_len]
        offset += prof_len

        if len(prof_data) < 27:
            profiles.append({'raw': prof_data.hex()})
            continue

        # Parse profile structure
        active_dpi_stage = prof_data[6]
        dpi_x = []
        dpi_y = []
        for i in range(5):
            dpi_x.append(struct.unpack_from('<H', prof_data, 7 + i * 2)[0])
            dpi_y.append(struct.unpack_from('<H', prof_data, 17 + i * 2)[0])

        profiles.append({
            'active_dpi_stage': active_dpi_stage,
            'dpi_x': dpi_x,
            'dpi_y': dpi_y,
            'polling_rate': prof_data[5],
            'raw': prof_data.hex(),
        })

    return profiles


# ── High-level API ──────────────────────────────────────────────────────────
def read_profiles_from_ini():
    """Read all profile data from Swarm II INI file."""
    raw = read_ini()

    btn_data, _, _ = extract_field(raw, 'm_btn_setting')
    main_data, _, _ = extract_field(raw, 'MainSetting')

    btn_profiles = parse_btn_setting(btn_data) if btn_data else []
    main_profiles = parse_main_setting(main_data) if main_data else []

    result = []
    for i in range(max(len(btn_profiles), len(main_profiles))):
        profile = {'index': i}
        if i < len(main_profiles):
            profile['dpi'] = main_profiles[i]
        if i < len(btn_profiles):
            profile['buttons'] = btn_profiles[i]
        result.append(profile)

    return result


def write_dpi_to_ini(profile_idx, dpi_values):
    """
    Write DPI values for a specific profile to the INI file.
    dpi_values: list of 5 DPI values (int)
    """
    raw = read_ini()
    main_data, start, end = extract_field(raw, 'MainSetting')
    if main_data is None:
        raise ValueError("MainSetting field not found in INI")

    # Parse and modify
    num_profiles = struct.unpack('>I', main_data[0:4])[0]
    offset = 4

    for p in range(num_profiles):
        if offset + 4 > len(main_data):
            break
        prof_len = struct.unpack('>I', main_data[offset:offset + 4])[0]

        if p == profile_idx:
            prof_start = offset + 4
            new_data = bytearray(main_data)

            # Write DPI X and Y values
            for i in range(min(5, len(dpi_values))):
                struct.pack_into('<H', new_data, prof_start + 7 + i * 2, dpi_values[i])
                struct.pack_into('<H', new_data, prof_start + 17 + i * 2, dpi_values[i])

            # Backup and write
            backup_ini()
            new_raw = replace_field(raw, 'MainSetting', bytes(new_data))
            with open(INI_FILE, 'wb') as f:
                f.write(new_raw)
            return True

        offset += 4 + prof_len

    return False


def backup_ini():
    """Create a backup of the INI file."""
    if INI_FILE.exists():
        backup = str(INI_FILE) + '.bak'
        shutil.copy2(str(INI_FILE), backup)


# ── CLI test ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    profiles = read_profiles_from_ini()
    for p in profiles:
        print(f"\n=== Profile {p['index']} ===")
        if 'dpi' in p:
            d = p['dpi']
            if 'dpi_x' in d:
                print(f"  DPI: {d['dpi_x']} (active stage {d.get('active_dpi_stage', '?')})")
        if 'buttons' in p:
            print(f"  Buttons ({len(p['buttons']['entries'])} entries):")
            for i, entry in enumerate(p['buttons']['entries']):
                print(f"    [{i:2d}] {entry['type']:12s} = {entry['name']}")
