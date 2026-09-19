import pytest

from kone_xp_air import actions as A


@pytest.mark.parametrize('name,wire', [
    ('Left Click', '00 00 01 01'),
    ('Right Click', '00 00 02 01'),
    ('Middle Click', '00 00 03 01'),
    ('Scroll Up', '00 00 09 01'),
    ('Scroll Down', '00 00 0a 01'),
    ('Browser Forward', '00 00 05 01'),
    ('Browser Back', '00 00 06 01'),
    ('Tilt Left', '00 00 07 01'),
    ('Tilt Right', '00 00 08 01'),
    ('DPI Up', '00 00 02 02'),
    ('DPI Down', '00 00 03 02'),
    ('Play/Pause', '00 00 04 03'),
    ('Volume Up', '00 00 07 03'),
    ('Volume Down', '00 00 08 03'),
    ('Prev Track', '00 00 02 03'),
    ('Next Track', '00 00 03 03'),
    ('Easy Shift', '00 00 01 0a'),
    ('Profile Cycle', '00 00 01 08'),
    ('Disabled', '00 00 00 00'),
    ('Hotkey Delete', '00 4c 00 06'),
    ('Hotkey E', '00 08 00 06'),
    ('Hotkey PageUp', '00 4b 00 06'),
    ('Hotkey LCtrl+V', '00 19 01 06'),
    ('Hotkey LCtrl+C', '00 06 01 06'),
    ('Hotkey Insert', '00 49 00 06'),
])
def test_encode_matches_capture(name, wire):
    assert A.encode_action(name).hex(' ') == wire
    assert A.decode_entry(bytes.fromhex(wire)) == name


@pytest.mark.parametrize('loose,canon', [
    ('Ctrl+C', 'Hotkey LCtrl+C'), ('Delete', 'Hotkey Delete'), ('Insert', 'Hotkey Insert'),
    ('Page Up', 'Hotkey PageUp'), ('Page Down', 'Hotkey PageDown'), ('Hotkey Del', 'Hotkey Delete'),
    ('Hotkey Alt+2', 'Hotkey LAlt+2'), ('Hotkey Alt+C', 'Hotkey LAlt+C'), ('Hotkey q', 'Hotkey Q'),
    ('Hotkey LShift', 'Hotkey LShift'), ('Hotkey Shift', 'Hotkey LShift'), ('Hotkey Left Shift', 'Hotkey LShift'),
    ('Browser Backward', 'Browser Back'), ('Click', 'Left Click'), ('Menu', 'Right Click'),
    ('Universal Scroll', 'Middle Click'), ('', 'Disabled'), (None, 'Disabled'), ('IE Forward', 'Browser Forward'),
])
def test_loose_spellings(loose, canon):
    assert A.normalize(loose) == canon
    assert A.is_known(loose)


def test_modifier_only_hotkey_encoding():
    # Ctrl/Shift/Alt lone = own scancode + modbits 0, exactly as Swarm II writes it in Main Test.dat /
    # Grounded.dat (confirmed on hardware). These must NOT change.
    assert A.encode_action('Hotkey LCtrl').hex(' ') == '00 e0 00 06'
    assert A.encode_action('Hotkey LShift').hex(' ') == '00 e1 00 06'
    assert A.encode_action('Hotkey LAlt').hex(' ') == '00 e2 00 06'
    assert A.decode_entry(bytes.fromhex('00 e1 00 06')) == 'Hotkey LShift'
    assert A.encode_action('Hotkey LWin+H').hex(' ') == '00 0b 08 06'      # WWM.dat
    assert A.encode_action('Toggle RGB').hex(' ') == '00 00 0b 08'


def test_lone_windows_key_uses_the_modifier_byte():
    # The firmware ignores the Windows key as a standalone scancode (00 e3 00 06 does nothing), so a
    # lone Win is sent with no base key and the GUI bit in the modifier byte instead. Round-trips.
    assert A.encode_action('Win').hex(' ') == '00 00 08 06'
    assert A.encode_action('Hotkey LWin').hex(' ') == '00 00 08 06'
    assert A.decode_entry(bytes.fromhex('00 00 08 06')) == 'Hotkey LWin'
    assert A.encode_action('Hotkey RWin').hex(' ') == '00 00 80 06'
    assert A.decode_entry(bytes.fromhex('00 00 80 06')) == 'Hotkey RWin'
    # the canonical name is unchanged; only the wire bytes differ
    assert A.normalize('Win') == 'Hotkey LWin'


def test_unknown_actions():
    for bad in ('Mute', 'Macro 1', 'Hotkey', 'Hotkey Fluffy', 'Dance', 'Raw 00'):
        assert not A.is_known(bad)
        with pytest.raises(A.UnknownAction):
            A.encode_action(bad)


def test_unknown_entries_round_trip_as_raw():
    for h in ('00 00 08 04', '00 00 05 04', 'ff 00 06 00'):
        name = A.decode_entry(bytes.fromhex(h))
        assert name == 'Raw ' + h
        assert A.is_known(name) and A.encode_action(name).hex(' ') == h
    assert not A.is_known('Raw 00 00')


def test_every_stored_profile_action_is_encodable():
    import json
    import os
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ROCCAT_Manager', 'profiles')
    seen = set()
    for fn in ('stored.json', 'boot1.json', 'boot2.json'):
        with open(os.path.join(base, fn)) as f:
            for p in json.load(f).get('profiles', []):
                for layer in ('keybinds', 'easy_shift'):
                    for action in (p.get(layer) or {}).values():
                        seen.add(action)
    unknown = sorted(a for a in seen if not A.is_known(a))
    assert unknown == [], 'stored profiles use actions the encoder cannot express: %r' % unknown
