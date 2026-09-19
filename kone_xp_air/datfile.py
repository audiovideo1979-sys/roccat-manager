"""
Read the device blocks out of Swarm II profile exports (.dat) and the onboard container
(%APPDATA%/Turtle Beach/Swarm II/Setting/KONE_XP_AIR_Profile_Mgr.dat).

Swarm stores each block behind a big-endian 32-bit length: 00 00 00 7d + 125-byte button block
(07 7d flag ...), 00 00 00 4e + 78-byte main block (06 4e flag ...). Both checksums are sum16 over
all but the last two bytes; files exported by this project's older code carry 00 00 there.
"""
import re

from . import protocol as P

_BUTTONS = re.compile(rb'\x00\x00\x00\x7d\x07\x7d')
_MAIN = re.compile(rb'\x00\x00\x00\x4e\x06\x4e')


def find_button_blocks(raw):
    return [raw[m.start() + 4:m.start() + 4 + P.BUTTON_BLOCK_LEN] for m in _BUTTONS.finditer(raw)
            if m.start() + 4 + P.BUTTON_BLOCK_LEN <= len(raw)]


def find_main_blocks(raw):
    return [raw[m.start() + 4:m.start() + 4 + P.PROFILE_DAT_LEN] for m in _MAIN.finditer(raw)
            if m.start() + 4 + P.PROFILE_DAT_LEN <= len(raw)]


def main_block_checksum_ok(block78):
    stored = block78[76] | (block78[77] << 8)
    return stored == P.checksum16(block78[:76]), stored


def read_profiles(raw):
    """Every (buttons, main) pair in the file, decoded. Checksums are verified when non-zero."""
    out = []
    buttons = find_button_blocks(raw)
    mains = find_main_blocks(raw)
    for i, b in enumerate(buttons):
        stored = b[123] | (b[124] << 8)
        blk = P.ButtonBlock.parse(b, verify_checksum=stored != 0)
        entry = {'buttons': blk, 'button_checksum_ok': stored == P.checksum16(b[:123]) if stored else None}
        if i < len(mains):
            m = mains[i]
            prof = P.ProfileBlock.parse(m[:P.PROFILE_BLOCK_LEN])
            ok, st = main_block_checksum_ok(m)
            entry.update(main=prof, color=(m[73], m[74], m[75]), main_checksum_ok=ok if st else None,
                         dpi=prof.dpi_x, active_stage=prof.active_stage)
        out.append(entry)
    return out


def read_profiles_from_file(path):
    with open(path, 'rb') as f:
        return read_profiles(f.read())


def to_stored_profile(entry, name, color=None):
    """Shape used by ROCCAT_Manager/profiles/stored.json."""
    blk = entry['buttons']
    ui_keybinds = {k: v for k, v in blk.primary.items() if k != 'profile_switch'}
    ui_es = {k: v for k, v in blk.easy_shift.items() if k not in ('profile_switch', 'easy_shift')}
    dpi = entry.get('dpi') or [800] * 5
    return {
        'name': name,
        'color': color or ('#%02x%02x%02x' % entry['color'] if 'color' in entry else '#888780'),
        'dpi': dpi[entry.get('active_stage', 0)] if 0 <= entry.get('active_stage', 0) < 5 else dpi[0],
        'dpi_stages': list(dpi),
        'keybinds': ui_keybinds,
        'easy_shift': ui_es,
    }
