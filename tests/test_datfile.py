"""Swarm II's own .dat exports are the strongest ground truth for the codec: real Swarm-written blocks
with real checksums, and one of them is the profile the owner transcribed in Main Test Keybinds.txt."""
import os

from kone_xp_air import datfile, protocol as P

PROFILES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ROCCAT_Manager', 'profiles')


def load(name):
    return datfile.read_profiles_from_file(os.path.join(PROFILES, name))


def test_swarm_written_exports_verify_both_checksums():
    for name in ('Main Test.dat', 'Grounded.dat', 'WWM.dat'):
        entries = load(name)
        assert len(entries) >= 1, name
        e = entries[0]
        assert e['button_checksum_ok'] is True, name
        assert e['main_checksum_ok'] is True, name


def test_project_generated_exports_have_zero_checksums_but_still_parse():
    for name in ('KONE_XP_AIR.dat', 'Main Test Copy.dat', 'Main Test IMPORT.dat'):
        e = load(name)[0]
        assert e['button_checksum_ok'] is None and e['main_checksum_ok'] is None, name


def test_main_test_export_matches_the_owners_notes():
    """Main Test Keybinds.txt: 8=G, 9=Alt+C, 10=Browser Back, 11=Browser Forward, 12=Left Shift, 13=Q,
    ES: 4/5 Volume Up/Down, 6/7 Prev/Next Track, 8/9 F2/F1, 10/11 Page Up/Down, 12 Del, 13 Insert; DPI 950."""
    e = load('Main Test.dat')[0]
    b = e['buttons']
    assert b.header.hex(' ') == '07 7d 00'
    assert b.primary == {
        'left_button': 'Left Click', 'right_button': 'Right Click', 'middle_button': 'Middle Click',
        'scroll_up': 'Scroll Up', 'scroll_down': 'Scroll Down',
        'side_button_1': 'Browser Back', 'side_button_2': 'Browser Forward',
        'dpi_up': 'Hotkey G', 'dpi_down': 'Hotkey LAlt+C',
        'thumb_button_1': 'Hotkey LShift', 'thumb_button_2': 'Hotkey Q',
        'tilt_left': 'Tilt Left', 'tilt_right': 'Tilt Right',
        'easy_shift': 'Easy Shift', 'profile_switch': 'Profile Cycle',
    }
    assert b.easy_shift == {
        'left_button': 'Left Click', 'right_button': 'Right Click', 'middle_button': 'Play/Pause',
        'scroll_up': 'Volume Up', 'scroll_down': 'Volume Down',
        'side_button_1': 'Hotkey PageUp', 'side_button_2': 'Hotkey PageDown',
        'dpi_up': 'Hotkey F2', 'dpi_down': 'Hotkey F1',
        'thumb_button_1': 'Hotkey Delete', 'thumb_button_2': 'Hotkey Insert',
        'tilt_left': 'Prev Track', 'tilt_right': 'Next Track',
        'easy_shift': 'Disabled', 'profile_switch': 'Toggle RGB',
    }
    assert e['dpi'] == [400, 950, 1200, 1600, 2600] and e['active_stage'] == 1
    assert e['color'] == (0xC5, 0x0B, 0xDC)
    # re-encoding the decoded names reproduces Swarm's bytes, checksum included
    raw = datfile.find_button_blocks(open(os.path.join(PROFILES, 'Main Test.dat'), 'rb').read())[0]
    assert P.ButtonBlock.from_bindings(b.primary, b.easy_shift, header=b.header).to_bytes() == raw


def test_modifier_only_and_win_hotkeys_round_trip_from_swarm_exports():
    g = load('Grounded.dat')[0]['buttons']
    assert g.primary['side_button_1'] == 'Hotkey LAlt' and g.primary['side_button_2'] == 'Hotkey LShift'
    assert g.primary['thumb_button_1'] == 'Disabled'
    w = load('WWM.dat')[0]['buttons']
    assert w.header.hex(' ') == '07 7d 01'
    assert w.primary['dpi_up'] == 'Hotkey LWin+H'
    assert w.primary['side_button_1'] == 'Hotkey F3' and w.primary['side_button_2'] == 'Hotkey F8'
    assert w.primary['thumb_button_1'].startswith('Raw ')          # type 0x04 code 08: unknown Swarm function
    assert w.easy_shift['easy_shift'] == 'Easy Shift'
    for name in ('Grounded.dat', 'WWM.dat'):
        raw = datfile.find_button_blocks(open(os.path.join(PROFILES, name), 'rb').read())[0]
        blk = P.ButtonBlock.parse(raw)
        # unknown Swarm functions come back as 'Raw ..' names and re-encode verbatim, so the whole
        # Swarm-written block round-trips byte for byte, checksum included
        assert P.ButtonBlock.from_bindings(blk.primary, blk.easy_shift, header=blk.header).to_bytes() == raw, name


def test_any_swarm_main_block_round_trips_through_parse():
    """parse -> to_bytes reproduces every Swarm main block exactly (incl. Grounded's per-zone colours),
    so ProfileBlock can represent any real .dat block and its 76-byte commit checksum. NOTE: the .dat
    stores byte 5 = 0x02, which differs from the WIRE write (byte 5 = 0x1f); parse reads what's there,
    while from_dpi defaults to the wire form (see test_sequences for the wire pin)."""
    for name in ('Main Test.dat', 'WWM.dat', 'Grounded.dat'):
        m = datfile.find_main_blocks(open(os.path.join(PROFILES, name), 'rb').read())[0]
        blk = P.ProfileBlock.parse(m[:75])
        blk.color = (m[73], m[74], m[75])
        assert blk.to_bytes() == m[:75], name
        assert blk.commit_checksum() == (m[76] | (m[77] << 8)), name


def test_to_stored_profile_shape():
    e = load('Main Test.dat')[0]
    sp = datfile.to_stored_profile(e, 'Main Test')
    assert sp['dpi'] == 950 and sp['dpi_stages'] == [400, 950, 1200, 1600, 2600]
    assert sp['color'] == '#c50bdc'
    assert 'profile_switch' not in sp['keybinds'] and 'easy_shift' not in sp['easy_shift']
    assert sp['keybinds']['thumb_button_1'] == 'Hotkey LShift'
