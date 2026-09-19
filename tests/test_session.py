from kone_xp_air import protocol as P
from kone_xp_air.session import KoneXPAir
from kone_xp_air.transport import RecordingTransport, format_results, make_transport, OpResult
from kone_xp_air import sequences as S

MAIN_TEST = {
    'name': 'Main Test', 'dpi': 950,
    'keybinds': {
        'left_button': 'Left Click', 'right_button': 'Right Click', 'middle_button': 'Middle Click',
        'scroll_up': 'Scroll Up', 'scroll_down': 'Scroll Down', 'tilt_left': 'Tilt Left', 'tilt_right': 'Tilt Right',
        'dpi_up': 'Hotkey G', 'dpi_down': 'Hotkey Alt+C', 'side_button_1': 'Browser Backward',
        'side_button_2': 'Browser Forward', 'thumb_button_1': 'Hotkey Left Shift', 'thumb_button_2': 'Hotkey Q',
        'easy_shift': 'Easy Shift',
    },
    'easy_shift': {
        'scroll_up': 'Volume Up', 'scroll_down': 'Volume Down', 'tilt_left': 'Prev Track', 'tilt_right': 'Next Track',
        'dpi_up': 'Hotkey F2', 'dpi_down': 'Hotkey F1', 'side_button_1': 'Page Up', 'side_button_2': 'Page Down',
        'thumb_button_1': 'Hotkey Del', 'thumb_button_2': 'Insert',
    },
}


def page_writes(sends, cmd):
    return [s[5:30] for s in sends if s[2] == cmd and s[4] == P.SUB_WRITE_PAGE]


def test_push_profile_writes_dpi_then_buttons_for_the_slot():
    t = RecordingTransport()
    mouse = KoneXPAir(t)
    summary = mouse.push_profile(2, MAIN_TEST)
    sends = t.sends()
    dpi_block = b''.join(page_writes(sends, P.CMD_PROFILE))
    assert P.ProfileBlock.parse(dpi_block).slot == 2
    assert P.ProfileBlock.parse(dpi_block).dpi_x == [950] * 5
    btn_block = b''.join(page_writes(sends, P.CMD_BUTTONS))
    blk = P.ButtonBlock.parse(btn_block)
    assert blk.header == P.ZERO_HEADER
    assert blk.primary['thumb_button_1'] == 'Hotkey LShift'
    assert btn_block[39:43].hex(' ') == '00 e1 00 06'                # lone modifier: modbits 0, as Swarm writes it
    assert blk.primary['side_button_1'] == 'Browser Back'
    assert blk.primary['profile_switch'] == 'Profile Cycle'      # untouched template entry
    assert blk.easy_shift['side_button_1'] == 'Hotkey PageUp'
    assert blk.easy_shift['left_button'] == 'Left Click'           # untouched template entry
    assert summary == {'slot': 2, 'name': 'Main Test', 'dpi': [950] * 5, 'buttons': True, 'unsupported': []}
    # profile-select packets: switch to 2 first, then (after DPI + buttons) scratch 3, back to 2
    selects = [s[5] for s in sends if s[2] == P.CMD_PROFILE_SELECT]
    assert selects == [2, 3, 2]
    # order on the wire: switch, DPI pages, button pages
    kinds = [s[2] for s in sends if s[2] in (P.CMD_PROFILE_SELECT, P.CMD_BUTTONS) or (s[2] == P.CMD_PROFILE and s[4] == P.SUB_WRITE_PAGE)]
    assert kinds[0] == P.CMD_PROFILE_SELECT and P.CMD_PROFILE in kinds and kinds.index(P.CMD_PROFILE) < kinds.index(P.CMD_BUTTONS)


def test_push_slots_restores_active_slot_and_reports_unsupported():
    t = RecordingTransport()
    mouse = KoneXPAir(t)
    bad = dict(MAIN_TEST, name='Bad', keybinds=dict(MAIN_TEST['keybinds'], left_button='Mute'))
    out = mouse.push_slots([(0, MAIN_TEST), (4, bad)], restore_slot=1)
    assert [o['slot'] for o in out] == [0, 4]
    assert out[1]['unsupported'] == ["primary/left_button: 'Mute'"]
    selects = [s[5] for s in t.sends() if s[2] == P.CMD_PROFILE_SELECT]
    assert selects == [0, 1, 0, 4, 0, 4, 1]


def test_header_mode_dat_and_activate_slot_options():
    t = RecordingTransport()
    mouse = KoneXPAir(t, header_mode='dat', activate_b5='slot', pre_switch=False)
    mouse.write_buttons(3, MAIN_TEST['keybinds'], MAIN_TEST['easy_shift'])
    sends = t.sends()
    blk = b''.join(page_writes(sends, P.CMD_BUTTONS))
    assert blk[:3].hex(' ') == '07 7d 00'
    activates = [s[5] for s in sends if s[2] == P.CMD_ACTIVATE]
    assert activates == [4, 3]           # scratch 4 then back to 3, slot in byte 5
    assert [s[5] for s in sends if s[2] == P.CMD_PROFILE_SELECT] == [4, 3]


def test_dpi_dict_form_and_stage_list():
    t = RecordingTransport()
    mouse = KoneXPAir(t, pre_switch=False)
    mouse.push_profile(1, {'dpi': {'stages': [400, 800, 1600, 3200, 6400], 'active_stage': 2}})
    blk = P.ProfileBlock.parse(b''.join(page_writes(t.sends(), P.CMD_PROFILE)))
    assert blk.dpi_x == [400, 800, 1600, 3200, 6400] and blk.active_stage == 2 and blk.slot == 1


def test_failed_op_raises_with_context():
    class Failing(RecordingTransport):
        def run(self, ops):
            res = super().run(ops)
            i = next(i for i, r in enumerate(res) if r.op.kind == 'send')
            res[i] = OpResult(res[i].op, rc=-1, error='boom')
            return res
    mouse = KoneXPAir(Failing())
    try:
        mouse.switch_profile(0)
        assert False, 'expected failure'
    except RuntimeError as e:
        assert 'boom' in str(e) and 'HID operations failed' in str(e)


def test_read_raw_pages_returns_get_buffers():
    resp = [bytes([0x06] + [i] * 29) for i in range(4)]
    t = RecordingTransport(responses=resp)
    mouse = KoneXPAir(t)
    got = mouse.read_raw_pages(P.CMD_BUTTONS, 0x00)
    assert got == resp


def test_format_results_and_factory():
    t = make_transport('recording')
    res = t.run(S.handshake())
    text = format_results(res)
    assert '> mouse apply' in text and '< get rc=30' in text


def test_preamble_is_sent_once_per_session():
    t = RecordingTransport()
    mouse = KoneXPAir(t, preamble=True, pre_switch=False)
    mouse.switch_profile(1)
    mouse.switch_profile(2)
    sends = t.sends()
    inits = [s for s in sends if s[:5] == bytes([0x06, 0x01, 0x13, 0x07, 0x02])]
    assert len(inits) == 1 and sends[0] == inits[0]
    assert [s[:4].hex(' ') for s in sends[1:3]] == ['06 00 00 04', '06 00 00 05']
