"""
dat_export.py — Maps ROCCAT Manager JSON profiles to .dat file arguments.
Translates keybind strings like "Hotkey G", "Browser Back" into the
4-byte button entry tuples used by SWARM_II_DAT_FORMAT.
"""
import re

# HID keycodes for keyboard keys
KEY_TO_HID = {
    'A':0x04,'B':0x05,'C':0x06,'D':0x07,'E':0x08,'F':0x09,'G':0x0A,'H':0x0B,
    'I':0x0C,'J':0x0D,'K':0x0E,'L':0x0F,'M':0x10,'N':0x11,'O':0x12,'P':0x13,
    'Q':0x14,'R':0x15,'S':0x16,'T':0x17,'U':0x18,'V':0x19,'W':0x1A,'X':0x1B,
    'Y':0x1C,'Z':0x1D,'1':0x1E,'2':0x1F,'3':0x20,'4':0x21,'5':0x22,'6':0x23,
    '7':0x24,'8':0x25,'9':0x26,'0':0x27,
    'ENTER':0x28,'ESC':0x29,'BACKSPACE':0x2A,'TAB':0x2B,'SPACE':0x2C,
    '-':0x2D,'=':0x2E,'[':0x2F,']':0x30,'\\':0x31,';':0x33,"'":0x34,
    '`':0x35,',':0x36,'.':0x37,'/':0x38,
    'F1':0x3A,'F2':0x3B,'F3':0x3C,'F4':0x3D,'F5':0x3E,'F6':0x3F,
    'F7':0x40,'F8':0x41,'F9':0x42,'F10':0x43,'F11':0x44,'F12':0x45,
    'PRINTSCREEN':0x46,'SCROLLLOCK':0x47,'PAUSE':0x48,
    'INSERT':0x49,'HOME':0x4A,'PAGEUP':0x4B,'DEL':0x4C,'DELETE':0x4C,
    'END':0x4D,'PAGEDOWN':0x4E,
    'RIGHT':0x4F,'LEFT':0x50,'DOWN':0x51,'UP':0x52,
    'LCTRL':0xE0,'LSHIFT':0xE1,'LALT':0xE2,'LGUI':0xE3,
    'RCTRL':0xE4,'RSHIFT':0xE5,'RALT':0xE6,'RGUI':0xE7,
    'SHIFT':0xE1,'CTRL':0xE0,'ALT':0xE2,'WIN':0xE3,
}

# Modifier key names to modifier bitmask
MOD_BITS = {
    'CTRL': 0x01, 'SHIFT': 0x02, 'ALT': 0x04, 'WIN': 0x08,
    'LCTRL': 0x01, 'RCTRL': 0x01, 'LSHIFT': 0x02, 'RSHIFT': 0x02,
    'LALT': 0x04, 'RALT': 0x04, 'LGUI': 0x08, 'RGUI': 0x08,
}

# Standard action string to button entry tuple
ACTION_MAP = {
    'Left Click':       (0x00, 0x00, 0x01, 0x01),
    'Right Click':      (0x00, 0x00, 0x02, 0x01),
    'Middle Click':     (0x00, 0x00, 0x03, 0x01),
    'Scroll Up':        (0x00, 0x00, 0x09, 0x01),
    'Scroll Down':      (0x00, 0x00, 0x0A, 0x01),
    'Browser Back':     (0x00, 0x00, 0x06, 0x01),
    'Browser Forward':  (0x00, 0x00, 0x05, 0x01),
    'DPI Up':           (0x00, 0x00, 0x07, 0x01),
    'DPI Down':         (0x00, 0x00, 0x08, 0x01),
    'Tilt Left':        (0x00, 0x00, 0x02, 0x02),
    'Tilt Right':       (0x00, 0x00, 0x03, 0x02),
    'Volume Up':        (0x00, 0x00, 0x02, 0x03),
    'Volume Down':      (0x00, 0x00, 0x03, 0x03),
    'Easy Shift':       (0x00, 0x00, 0x04, 0x03),
    'DPI Cycle':        (0x00, 0x00, 0x01, 0x08),
    'DPI Cycle Up':     (0x00, 0x00, 0x07, 0x03),
    'DPI Cycle Down':   (0x00, 0x00, 0x08, 0x03),
    'Profile Cycle':    (0x00, 0x00, 0x01, 0x0A),
    'Disabled':         (0x00, 0x00, 0x00, 0x00),
    # Media keys stored as special consumer codes
    'Play/Pause':       (0x00, 0x00, 0x01, 0x03),
    'Next Track':       (0x00, 0x00, 0x05, 0x03),
    'Prev Track':       (0x00, 0x00, 0x06, 0x03),
    'Mute':             (0x00, 0x00, 0x04, 0x03),
    # Keyboard shortcuts stored as key combos
    'Copy':             (0x00, 0x06, 0x01, 0x06),  # Ctrl+C
    'Paste':            (0x00, 0x19, 0x01, 0x06),  # Ctrl+V
    'Cut':              (0x00, 0x1B, 0x01, 0x06),  # Ctrl+X
    'Undo':             (0x00, 0x1D, 0x01, 0x06),  # Ctrl+Z
    'Redo':             (0x00, 0x1C, 0x01, 0x06),  # Ctrl+Y
    # Common actions
    'Page Up':          (0x00, 0x4B, 0x00, 0x06),
    'Page Down':        (0x00, 0x4E, 0x00, 0x06),
    'Delete':           (0x00, 0x4C, 0x00, 0x06),
    'Insert':           (0x00, 0x49, 0x00, 0x06),
    'Home':             (0x00, 0x4A, 0x00, 0x06),
    'End':              (0x00, 0x4D, 0x00, 0x06),
}


def parse_hotkey(hotkey_str):
    """Parse a 'Hotkey X' or 'Hotkey Ctrl+X' string into a button entry tuple."""
    combo = hotkey_str[7:]  # strip 'Hotkey '
    parts = combo.split('+')

    modifiers = 0
    key_name = None

    for part in parts:
        upper = part.upper().strip()
        if upper in MOD_BITS:
            modifiers |= MOD_BITS[upper]
        else:
            key_name = upper

    if key_name is None:
        # Standalone modifier key (e.g. "Hotkey Shift" = LShift key)
        # Check if the last part is a modifier used as a key
        last = parts[-1].upper().strip()
        if last in KEY_TO_HID:
            return (0x00, KEY_TO_HID[last], 0x00, 0x06)
        return (0x00, 0x00, 0x00, 0x00)

    hid = KEY_TO_HID.get(key_name, 0x00)
    return (0x00, hid, modifiers, 0x06)


def action_to_entry(action_str):
    """Convert a keybind action string to a 4-byte button entry tuple."""
    if not action_str or action_str == 'Disabled':
        return (0x00, 0x00, 0x00, 0x00)

    # Check standard actions
    if action_str in ACTION_MAP:
        return ACTION_MAP[action_str]

    # Check hotkey
    if action_str.startswith('Hotkey '):
        return parse_hotkey(action_str)

    # Unknown — disable
    return (0x00, 0x00, 0x00, 0x00)


# Our JSON key order -> .dat slot index mapping
# Our keys:           .dat slot:
# left_button      -> 0
# right_button     -> 1
# middle_button    -> 2
# scroll_up        -> 3
# scroll_down      -> 4
# side_button_1    -> 5  (Forward in .dat)
# side_button_2    -> 6  (Back in .dat)
# tilt_left        -> 7
# tilt_right       -> 8
# thumb_button_1   -> 9  (Top Front in .dat)
# thumb_button_2   -> 10 (Top Rear in .dat)
# dpi_up           -> 11
# dpi_down         -> 12
# (profile)        -> 13 (always disabled)
# easy_shift       -> 14

KEYBIND_TO_SLOT = {
    'left_button':    0,
    'right_button':   1,
    'middle_button':  2,
    'scroll_up':      3,
    'scroll_down':    4,
    'side_button_1':  5,
    'side_button_2':  6,
    'tilt_left':      7,
    'tilt_right':     8,
    'thumb_button_1': 9,
    'thumb_button_2': 10,
    'dpi_up':         11,
    'dpi_down':       12,
    'easy_shift':     14,
}


def profile_to_dat_args(profile):
    """Convert a JSON profile dict to arguments for write_minimal_dat()."""
    keybinds = profile.get('keybinds', {})
    easy_shift = profile.get('easy_shift', {})

    # Build 30 button entries (15 primary + 15 Easy-Shift)
    buttons = [(0x00, 0x00, 0x00, 0x00)] * 30

    # Primary layer (slots 0-14)
    for key, slot in KEYBIND_TO_SLOT.items():
        action = keybinds.get(key, 'Disabled')
        buttons[slot] = action_to_entry(action)

    # Slot 13 = profile button (disabled since removed)
    buttons[13] = (0x00, 0x00, 0x00, 0x00)

    # Easy-Shift layer (slots 15-29)
    for key, slot in KEYBIND_TO_SLOT.items():
        if key == 'easy_shift':
            # ES of easy_shift itself = ES DPI action
            buttons[slot + 15] = (0x00, 0x00, 0x0B, 0x08)
        else:
            action = easy_shift.get(key, 'Disabled')
            buttons[slot + 15] = action_to_entry(action)

    # Slot 28 = ES profile (disabled)
    buttons[28] = (0x00, 0x00, 0x00, 0x00)

    # Parse color
    color_hex = profile.get('color', '#888780').lstrip('#')
    r = int(color_hex[0:2], 16)
    g = int(color_hex[2:4], 16)
    b = int(color_hex[4:6], 16)

    # DPI — fill all 5 stages with the single value
    dpi = profile.get('dpi', 800)

    return {
        'profile_name': profile.get('name', 'Profile'),
        'profile_color_rgb': (r, g, b),
        'dpi_stages': [dpi, dpi, dpi, dpi, dpi],
        'button_assignments': buttons,
    }
