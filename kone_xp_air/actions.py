"""
Action names <-> wire encoding for ROCCAT Kone XP Air button entries.

Every button entry on the wire is 4 bytes: [0x00, key, code_or_modbits, type]

    standard / mouse   [0x00, 0x00, code,    0x01]
    DPI                [0x00, 0x00, code,    0x02]
    multimedia         [0x00, 0x00, code,    0x03]
    keyboard           [0x00, scan, modbits, 0x06]   scan = USB HID usage; modbits LCtrl 01 LShift 02 LAlt 04 LWin 08 RCtrl 10 ...
    profile / system   [0x00, 0x00, code,    0x08]   01 = Profile Cycle, 0b = Toggle RGB
    Easy-Shift         [0x00, 0x00, 0x01,    0x0a]
    disabled           [0x00, 0x00, 0x00,    0x00]
    unknown            kept verbatim as the name 'Raw 00 xx xx xx' (e.g. Swarm's type-0x04 functions)

Sources: the byte-exact Swarm II button write captured via Frida (inject_buttons2.js /
inject_full.js), cross-checked against ROCCAT's official "Kone XP Air - Button Layout and Default
Functions" chart (Screenshot 2026-03-22 170526.png): the capture holds the factory layout except
thumb button 12 (Q -> Delete), and its Easy-Shift layer decodes as the factory Play/Pause, Volume
Up/Down, Next/Previous Track, Ctrl+V/C, Page Up/Down, Del/Ins. Entries marked UNVERIFIED have not
been observed on the wire.
"""

TYPE_DISABLED = 0x00
TYPE_MOUSE = 0x01
TYPE_DPI = 0x02
TYPE_MEDIA = 0x03
TYPE_KEYBOARD = 0x06
TYPE_PROFILE = 0x08
TYPE_EASYSHIFT = 0x0A

# canonical name -> (code, type). Observed on the wire unless noted.
SIMPLE_ACTIONS = {
    'Disabled':        (0x00, TYPE_DISABLED),
    'Left Click':      (0x01, TYPE_MOUSE),
    'Right Click':     (0x02, TYPE_MOUSE),
    'Middle Click':    (0x03, TYPE_MOUSE),
    'Double-Click':    (0x04, TYPE_MOUSE),   # swarm_ini STANDARD_FUNCTIONS; UNVERIFIED on wire
    'Browser Forward': (0x05, TYPE_MOUSE),
    'Browser Back':    (0x06, TYPE_MOUSE),
    'Tilt Left':       (0x07, TYPE_MOUSE),   # naming inherited from roccat_write; direction UNVERIFIED (see HANDOFF)
    'Tilt Right':      (0x08, TYPE_MOUSE),
    'Scroll Up':       (0x09, TYPE_MOUSE),
    'Scroll Down':     (0x0A, TYPE_MOUSE),
    'DPI Cycle Up':    (0x01, TYPE_DPI),     # swarm_ini DPI_FUNCTIONS; UNVERIFIED on wire
    'DPI Up':          (0x02, TYPE_DPI),
    'DPI Down':        (0x03, TYPE_DPI),
    'DPI Cycle Down':  (0x04, TYPE_DPI),     # UNVERIFIED on wire
    'Prev Track':      (0x02, TYPE_MEDIA),   # factory Easy-Shift on the tilt paired with 'Tilt Left'
    'Next Track':      (0x03, TYPE_MEDIA),
    'Play/Pause':      (0x04, TYPE_MEDIA),   # factory Easy-Shift on wheel click
    'Volume Up':       (0x07, TYPE_MEDIA),   # factory Easy-Shift on wheel up
    'Volume Down':     (0x08, TYPE_MEDIA),   # factory Easy-Shift on wheel down
    'Profile Cycle':   (0x01, TYPE_PROFILE), # factory default of button 15 (bottom)
    'Toggle RGB':      (0x0B, TYPE_PROFILE), # factory Easy-Shift default of button 15 (chart: "Toggle RGB on/off")
    'Easy Shift':      (0x01, TYPE_EASYSHIFT),
}

# Spellings accepted on input (Swarm II INI names, older UI names, owner's stored profiles).
ALIASES = {
    'Click': 'Left Click',
    'Menu': 'Right Click',
    'Universal Scroll': 'Middle Click',
    'Browser Backward': 'Browser Back',
    'IE Forward': 'Browser Forward',
    'IE Backward': 'Browser Back',
    'Profile Switch': 'Profile Cycle',
    'Play Pause': 'Play/Pause',
    'Previous Track': 'Prev Track',
    'Easy-Shift': 'Easy Shift',
    'Easy-Shift[+]': 'Easy Shift',
    # old UI option names, expressed as the hotkeys they are
    'Copy': 'Hotkey LCtrl+C', 'Paste': 'Hotkey LCtrl+V', 'Cut': 'Hotkey LCtrl+X',
    'Undo': 'Hotkey LCtrl+Z', 'Redo': 'Hotkey LCtrl+Y',
    'Snipping Tool': 'Hotkey LShift+LWin+S', 'Task Manager': 'Hotkey LCtrl+LShift+Escape',
    'Show Desktop': 'Hotkey LWin+D',
}

HID_KEYS = {
    'A': 0x04, 'B': 0x05, 'C': 0x06, 'D': 0x07, 'E': 0x08, 'F': 0x09,
    'G': 0x0A, 'H': 0x0B, 'I': 0x0C, 'J': 0x0D, 'K': 0x0E, 'L': 0x0F,
    'M': 0x10, 'N': 0x11, 'O': 0x12, 'P': 0x13, 'Q': 0x14, 'R': 0x15,
    'S': 0x16, 'T': 0x17, 'U': 0x18, 'V': 0x19, 'W': 0x1A, 'X': 0x1B,
    'Y': 0x1C, 'Z': 0x1D,
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    'Enter': 0x28, 'Escape': 0x29, 'Backspace': 0x2A, 'Tab': 0x2B,
    'Space': 0x2C, 'Minus': 0x2D, 'Equals': 0x2E, 'LBracket': 0x2F,
    'RBracket': 0x30, 'Backslash': 0x31, 'Semicolon': 0x33, 'Quote': 0x34,
    'Grave': 0x35, 'Comma': 0x36, 'Period': 0x37, 'Slash': 0x38,
    'CapsLock': 0x39,
    'F1': 0x3A, 'F2': 0x3B, 'F3': 0x3C, 'F4': 0x3D, 'F5': 0x3E, 'F6': 0x3F,
    'F7': 0x40, 'F8': 0x41, 'F9': 0x42, 'F10': 0x43, 'F11': 0x44, 'F12': 0x45,
    'PrintScreen': 0x46, 'ScrollLock': 0x47, 'Pause': 0x48,
    'Insert': 0x49, 'Home': 0x4A, 'PageUp': 0x4B, 'Delete': 0x4C,
    'End': 0x4D, 'PageDown': 0x4E,
    'Right': 0x4F, 'Left': 0x50, 'Down': 0x51, 'Up': 0x52,
    'NumLock': 0x53, 'NumDivide': 0x54, 'NumMultiply': 0x55,
    'NumMinus': 0x56, 'NumPlus': 0x57, 'NumEnter': 0x58,
    'Num1': 0x59, 'Num2': 0x5A, 'Num3': 0x5B, 'Num4': 0x5C,
    'Num5': 0x5D, 'Num6': 0x5E, 'Num7': 0x5F, 'Num8': 0x60,
    'Num9': 0x61, 'Num0': 0x62,
    # modifier keys as plain keys (modifier-only hotkeys, e.g. 'Hotkey LShift' = e1 00 06 00 in Swarm's .dat)
    'LCtrl': 0xE0, 'LShift': 0xE1, 'LAlt': 0xE2, 'LWin': 0xE3,
    'RCtrl': 0xE4, 'RShift': 0xE5, 'RAlt': 0xE6, 'RWin': 0xE7,
}
HID_KEY_ALIASES = {
    'Esc': 'Escape', 'Return': 'Enter', 'Del': 'Delete', 'Ins': 'Insert',
    'PgUp': 'PageUp', 'PgDn': 'PageDown', 'Page Up': 'PageUp', 'Page Down': 'PageDown',
    'Left Shift': 'LShift', 'Right Shift': 'RShift', 'Left Ctrl': 'LCtrl', 'Right Ctrl': 'RCtrl',
    'Left Alt': 'LAlt', 'Right Alt': 'RAlt', 'Print Screen': 'PrintScreen', 'Caps Lock': 'CapsLock',
    'Ctrl': 'LCtrl', 'Shift': 'LShift', 'Alt': 'LAlt', 'Win': 'LWin',
}
HID_KEYS_BY_CODE = {v: k for k, v in HID_KEYS.items()}

MODIFIER_BITS = {
    'LCtrl': 0x01, 'LShift': 0x02, 'LAlt': 0x04, 'LWin': 0x08,
    'RCtrl': 0x10, 'RShift': 0x20, 'RAlt': 0x40, 'RWin': 0x80,
}
# The lone Windows/GUI key is the one modifier the Kone XP Air firmware ignores when sent as its own
# scancode: 00 e3 00 06 does nothing on the mouse (confirmed on hardware 2026-09-19). It IS honored
# through the modifier byte, though — that's how it fires inside Win+<key> combos (e.g. Win+H =
# 00 0b 08 06 in WWM.dat). So a lone Windows key is encoded with no base key and the GUI bit set in
# the modifier byte. Ctrl/Shift/Alt keep their own scancode (00 e0/e1/e2 00 06), which is confirmed
# working and matches Swarm II's own .dat exports.
_LONE_GUI_MODBIT = {0xE3: 0x08, 0xE7: 0x80}   # LWin scancode -> LWin bit, RWin -> RWin bit
MODIFIER_NAMES = [(0x01, 'LCtrl'), (0x02, 'LShift'), (0x04, 'LAlt'), (0x08, 'LWin'),
                  (0x10, 'RCtrl'), (0x20, 'RShift'), (0x40, 'RAlt'), (0x80, 'RWin')]

HOTKEY_PREFIX = 'Hotkey '
RAW_PREFIX = 'Raw '


class UnknownAction(ValueError):
    pass


def _resolve_key(part):
    part = part.strip()
    part = HID_KEY_ALIASES.get(part, part)
    if part in HID_KEYS:
        return part
    if part.upper() in HID_KEYS:
        return part.upper()
    if part.capitalize() in HID_KEYS:
        return part.capitalize()
    return None


def parse_hotkey(spec):
    """'LCtrl+V' -> (modbits, scancode, canonical 'Hotkey LCtrl+V'). A lone modifier is sent as its own
    scancode with modbits 0 ('Hotkey LShift' -> e1 00 06 00), which is how Swarm II encodes it in the
    owner's Main Test.dat / Grounded.dat exports. Returns None if the spec is not a hotkey."""
    parts = [p for p in spec.split('+') if p.strip()]
    if not parts:
        return None
    mods, key = 0, None
    for part in parts:
        name = _resolve_key(part)
        if name is None:
            return None
        if name in MODIFIER_BITS and part is not parts[-1]:
            mods |= MODIFIER_BITS[name]
        elif name in MODIFIER_BITS and key is None and len(parts) == 1:
            key = name
        elif name in MODIFIER_BITS and key is None:
            # trailing modifier in a multi-part spec, e.g. 'Ctrl+Shift': treat last as the key
            mods |= MODIFIER_BITS[name]
            key = name
        else:
            key = name
    if key is None:
        return None
    canon = HOTKEY_PREFIX + '+'.join([n for b, n in MODIFIER_NAMES if mods & b and n != key] + [key])
    return mods, HID_KEYS[key], canon


def normalize(name):
    """Canonical action name for any accepted spelling, or None if unknown."""
    if name is None:
        return 'Disabled'
    name = str(name).strip()
    if name == '':
        return 'Disabled'
    name = ALIASES.get(name, name)
    if name in SIMPLE_ACTIONS:
        return name
    if name.startswith(RAW_PREFIX):
        return name if _parse_raw(name) else None
    spec = name[len(HOTKEY_PREFIX):] if name.startswith(HOTKEY_PREFIX) else name
    hk = parse_hotkey(spec)
    return hk[2] if hk else None


def _parse_raw(name):
    try:
        b = bytes.fromhex(name[len(RAW_PREFIX):].replace(' ', ''))
    except ValueError:
        return None
    return b if len(b) == 4 else None


def encode_action(name):
    """Return the 4-byte wire entry for an action name. Raises UnknownAction."""
    canon = normalize(name)
    if canon is None:
        raise UnknownAction(repr(name))
    if canon in SIMPLE_ACTIONS:
        code, typ = SIMPLE_ACTIONS[canon]
        return bytes([0x00, 0x00, code, typ])
    if canon.startswith(RAW_PREFIX):
        return _parse_raw(canon)
    mods, scan, _ = parse_hotkey(canon[len(HOTKEY_PREFIX):])
    if mods == 0 and scan in _LONE_GUI_MODBIT:   # lone Windows key -> modifier byte (see _LONE_GUI_MODBIT)
        return bytes([0x00, 0x00, _LONE_GUI_MODBIT[scan], TYPE_KEYBOARD])
    return bytes([0x00, scan, mods, TYPE_KEYBOARD])


_SIMPLE_BY_WIRE = {(code, typ): name for name, (code, typ) in SIMPLE_ACTIONS.items()}


def decode_entry(entry):
    """4-byte wire entry -> canonical action name. Unknown entries decode to 'Raw 00 xx xx xx', which
    encode_action turns back into the same bytes, so unknown Swarm functions survive a round trip."""
    entry = bytes(entry)
    if len(entry) != 4:
        raise ValueError('entry must be 4 bytes')
    b0, b1, b2, typ = entry
    if b0 == 0 and typ == TYPE_KEYBOARD:
        key = HID_KEYS_BY_CODE.get(b1)
        if key is not None:
            parts = [n for bit, n in MODIFIER_NAMES if b2 & bit and n != key]
            parts.append(key)
            return HOTKEY_PREFIX + '+'.join(parts)
        # lone Windows/GUI key: no base key, GUI bit in the modifier byte (see _LONE_GUI_MODBIT)
        if b1 == 0 and b2 in (0x08, 0x80):
            return HOTKEY_PREFIX + ('LWin' if b2 == 0x08 else 'RWin')
    if b0 == 0 and b1 == 0 and (b2, typ) in _SIMPLE_BY_WIRE:
        return _SIMPLE_BY_WIRE[(b2, typ)]
    if entry == b'\x00\x00\x00\x00':
        return 'Disabled'
    return RAW_PREFIX + entry.hex(' ')


def is_known(name):
    return normalize(name) is not None


def all_action_names():
    """Fixed names the UI can offer; hotkeys are free-form 'Hotkey <mods>+<Key>'."""
    return list(SIMPLE_ACTIONS.keys())
