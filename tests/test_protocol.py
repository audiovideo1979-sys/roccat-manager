import struct

import pytest

from kone_xp_air import protocol as P

CAP = P.CAPTURED_BUTTON_BLOCK

FACTORY_PRIMARY = {
    'left_button': 'Left Click', 'right_button': 'Right Click', 'middle_button': 'Middle Click',
    'scroll_up': 'Scroll Up', 'scroll_down': 'Scroll Down',
    'side_button_1': 'Browser Forward', 'side_button_2': 'Browser Back',
    'dpi_up': 'DPI Up', 'dpi_down': 'DPI Down',
    'thumb_button_1': 'Hotkey Delete',   # owner's change; factory is Q
    'thumb_button_2': 'Hotkey E',
    'tilt_left': 'Tilt Left', 'tilt_right': 'Tilt Right',
    'easy_shift': 'Easy Shift', 'profile_switch': 'Profile Cycle',
}
FACTORY_EASYSHIFT = {
    'left_button': 'Left Click', 'right_button': 'Right Click', 'middle_button': 'Play/Pause',
    'scroll_up': 'Volume Up', 'scroll_down': 'Volume Down',
    'side_button_1': 'Hotkey PageUp', 'side_button_2': 'Hotkey PageDown',
    'dpi_up': 'Hotkey LCtrl+V', 'dpi_down': 'Hotkey LCtrl+C',
    'thumb_button_1': 'Hotkey Delete', 'thumb_button_2': 'Hotkey Insert',
    'tilt_left': 'Prev Track', 'tilt_right': 'Next Track',
    'easy_shift': 'Disabled', 'profile_switch': 'Toggle RGB',
}


def test_capture_checksum_is_sum16():
    assert P.checksum16(CAP[:123]) == 0x026B
    assert CAP[123] | (CAP[124] << 8) == 0x026B


def test_capture_decodes_to_factory_layout():
    blk = P.ButtonBlock.parse(CAP)
    assert blk.primary == FACTORY_PRIMARY
    assert blk.easy_shift == FACTORY_EASYSHIFT
    assert blk.header == b'\x00\x00\x00'


def test_capture_round_trips_byte_exact():
    blk = P.ButtonBlock.from_bindings(FACTORY_PRIMARY, FACTORY_EASYSHIFT)
    assert blk.unsupported == []
    assert blk.to_bytes() == CAP
    assert P.ButtonBlock.parse(CAP).to_bytes() == CAP


def test_entry_offsets():
    assert [P.entry_offset(k) for k in (0, 1, 9, 14, 15, 29)] == [3, 7, 39, 59, 63, 119]
    assert P.entry_offset(29) + 4 == P.BUTTON_CHECKSUM_OFFSET


def test_changing_one_binding_touches_only_its_entry_and_checksum():
    blk = P.ButtonBlock.from_bindings({'thumb_button_1': 'Hotkey Insert'}, {})
    out = blk.to_bytes()
    diff = [i for i in range(125) if out[i] != CAP[i]]
    assert 40 in diff and set(diff) <= {40, 123, 124}   # entry k=9 byte 0 (4c -> 49) and the checksum
    assert out[39:43].hex(' ') == '00 49 00 06'
    assert P.checksum16(out[:123]) == out[123] | (out[124] << 8)


def test_right_button_lands_at_offset_9_not_8():
    # the bug in frida_inject.BUTTON_MAP wrote the right-button code at offset 8
    blk = P.ButtonBlock.from_bindings({'right_button': 'Middle Click'}, {})
    out = blk.to_bytes()
    assert out[7:11].hex(' ') == '00 00 03 01'
    assert out[3:7].hex(' ') == '00 00 01 01'   # left button untouched
    assert out[9:11].hex(' ') == '03 01'        # [code, type] sit at 9-10, never 8-9


def test_unknown_actions_keep_template_and_are_reported():
    blk = P.ButtonBlock.from_bindings({'left_button': 'Mute', 'right_button': 'Right Click'}, {'middle_button': 'Macro 1'})
    assert blk.primary['left_button'] == 'Left Click'
    assert blk.easy_shift['middle_button'] == 'Play/Pause'
    assert blk.unsupported == [('primary', 'left_button', 'Mute'), ('easy_shift', 'middle_button', 'Macro 1')]


def test_dat_header_variant():
    blk = P.ButtonBlock.from_bindings({}, {}, header=P.dat_header(0x00))
    out = blk.to_bytes()
    assert out[:3].hex(' ') == '07 7d 00'
    assert out[3:123] == CAP[3:123]
    assert P.checksum16(out[:123]) == out[123] | (out[124] << 8)
    with pytest.raises(ValueError):
        P.dat_header(256)
    with pytest.raises(ValueError):
        P.ButtonBlock(header=b'\x00\x00').to_bytes()


def test_parse_rejects_bad_checksum_and_length():
    bad = bytearray(CAP)
    bad[50] ^= 0x01
    with pytest.raises(ValueError):
        P.ButtonBlock.parse(bytes(bad))
    with pytest.raises(ValueError):
        P.ButtonBlock.parse(CAP[:-1])
    P.ButtonBlock.parse(bytes(bad), verify_checksum=False)


def test_button_pages_are_the_captured_pages():
    pages = P.ButtonBlock.parse(CAP).pages()
    assert len(pages) == 5 and all(len(p) == 25 for p in pages)
    assert b''.join(pages) == CAP


# ── packets ──

def test_packets_match_captured_bytes():
    assert P.apply_packet()[:4].hex(' ') == '06 01 44 07' and len(P.apply_packet()) == 30
    assert P.select_page_packet(P.CMD_BUTTONS, 3, 0x00)[:7].hex(' ') == '06 01 47 06 02 03 00'
    assert P.select_page_packet(P.CMD_PROFILE, 1, 0x01)[:7].hex(' ') == '06 01 46 06 02 01 01'
    assert P.read_packet(P.CMD_PROFILE)[:4].hex(' ') == '06 01 46 07'
    assert P.profile_select_packet(1)[:7].hex(' ') == '06 01 45 06 02 01 05'
    assert P.activate_packet()[:9].hex(' ') == '06 01 4e 06 04 01 01 01 ff'
    assert P.activate_packet(3)[:9].hex(' ') == '06 01 4e 06 04 03 01 01 ff'
    assert P.profile_commit_packet(0xdc, 0x1234)[:8].hex(' ') == '06 01 46 06 03 dc 34 12'
    assert P.commit49_packet(0x456F)[:8].hex(' ') == '06 01 49 06 03 05 6f 45'
    assert P.receiver_packet(0x00, 0x04)[:4].hex(' ') == '06 00 00 04'
    page = P.write_page_packet(P.CMD_BUTTONS, CAP[:25])
    assert page[:5].hex(' ') == '06 01 47 06 19' and page[5:] == CAP[:25]
    with pytest.raises(ValueError):
        P.write_page_packet(P.CMD_BUTTONS, CAP[:24])
    with pytest.raises(ValueError):
        P.profile_select_packet(5)


def test_describe():
    assert P.describe(P.apply_packet()) == 'mouse apply'
    assert P.describe(P.select_page_packet(P.CMD_BUTTONS, 2, 0)) == 'mouse buttons select page 2 flag 00'
    assert P.describe(P.profile_select_packet(4)) == 'mouse profile-select slot 4 of 5'
    assert 'write page' in P.describe(P.write_page_packet(P.CMD_PROFILE, CAP[:25]))


# ── profile (DPI) block: must equal Swarm II's real .dat form ──
# The old test pinned roccat_write.build_profile ("proven on hardware"), but that block is REJECTED by
# the mouse (confirmed 2026-09-19: DPI-set-in-app does nothing, read-back doesn't contain it). The real
# form comes from Swarm's own .dat exports (WWM/Main Test/Grounded): byte 5 = 0x02, bytes 31-32 = 01 00,
# and the commit checksum is over the 76 bytes (block + colour-B). See test_datfile for the .dat pin.

def reference_swarm_profile(dpi_values, profile_slot=0, active_stage=0, color=(0xFF, 0xFF, 0xFF)):
    """The real Swarm II profile block layout (its .dat exports reproduce byte-for-byte)."""
    p = bytearray(75)
    p[0] = 0x06; p[1] = 0x4E; p[2] = profile_slot; p[3] = 0x06; p[4] = 0x06; p[5] = 0x02; p[6] = active_stage
    for i in range(5):
        dpi = dpi_values[i] if i < len(dpi_values) else dpi_values[-1]
        struct.pack_into('<H', p, 7 + i * 2, dpi)
        struct.pack_into('<H', p, 17 + i * 2, dpi)
    p[27:36] = bytes([0x00, 0x00, 0x03, 0x0a, 0x01, 0x00, 0x05, 0x00, 0x00])
    for i in range(7):
        offset = 36 + i * 5
        p[offset:offset + 5] = bytes([0x14, 0xFF, 0x00, 0x48, 0xFF])
    p[71] = 0x01; p[72] = 0x64; p[73] = color[0]; p[74] = color[1]
    return bytes(p)


@pytest.mark.parametrize('slot,dpi', [(0, 800), (3, 950), (4, [400, 800, 1600, 3200, 6400]), (1, [1200])])
def test_profile_block_matches_swarm_form(slot, dpi):
    blk = P.ProfileBlock.from_dpi(slot, dpi)
    ref_values = [dpi] * 5 if isinstance(dpi, int) else dpi
    ref = reference_swarm_profile(ref_values, profile_slot=slot)
    assert blk.to_bytes() == ref
    # commit checksum is over the 76 bytes: the block plus the colour-B byte (default 0xff)
    assert blk.commit_color_b() == 0xFF
    assert blk.commit_checksum() == (sum(ref) + 0xFF) & 0xFFFF
    back = P.ProfileBlock.parse(blk.to_bytes())
    assert back.slot == slot and back.dpi_x == blk.dpi_x and back.dpi_y == blk.dpi_x


def test_profile_block_validation():
    with pytest.raises(ValueError):
        P.ProfileBlock.from_dpi(0, 20)
    with pytest.raises(ValueError):
        P.ProfileBlock.from_dpi(5, 800)
    with pytest.raises(ValueError):
        P.ProfileBlock.from_dpi(0, 800, active_stage=5)
    with pytest.raises(ValueError):
        P.ProfileBlock.from_dpi(0, [])
