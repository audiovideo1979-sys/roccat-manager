"""The sequences must reproduce the captured Swarm II traffic byte for byte and sleep for sleep."""
from kone_xp_air import protocol as P
from kone_xp_air import sequences as S

CAP = P.CAPTURED_BUTTON_BLOCK


def pk(hexstr):
    return P.packet(bytes.fromhex(hexstr))


def strip_marks(ops):
    return [(op.kind, op.data, op.seconds) for op in ops if op.kind != 'mark']


def HS():
    return [('send', pk('06 01 44 07'), 0.0), ('sleep', b'', 0.1), ('get', b'', 0.0), ('sleep', b'', 0.05)]


def test_write_buttons_equals_inject_full_js_replay():
    """inject_full.js: the exact sequence that made button 12 change on the mouse."""
    sel = ['06 01 47 06 02 %02x 00' % pg for pg in range(5)]
    wr = [('06 01 47 06 19 ' + CAP[i * 25:(i + 1) * 25].hex(' ')) for i in range(5)]
    expected = []
    for pg in range(5):
        expected += [('send', pk(sel[pg]), 0.0), ('sleep', b'', 0.05)] + HS()
        expected += [('send', pk(wr[pg]), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('sleep', b'', 0.5)]
    for pg in range(4):
        expected += [('send', pk('06 01 46 06 02 %02x 01' % pg), 0.0), ('sleep', b'', 0.05),
                     ('send', pk('06 01 46 07'), 0.0), ('sleep', b'', 0.1), ('get', b'', 0.0)]
    expected += [('sleep', b'', 0.2)]
    expected += [('send', pk('06 01 45 06 02 01 05'), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('send', pk('06 01 4e 06 04 01 01 01 ff'), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('sleep', b'', 1.0)]
    for pg in range(4):
        expected += [('send', pk('06 01 46 06 02 %02x 00' % pg), 0.0), ('sleep', b'', 0.05),
                     ('send', pk('06 01 46 07'), 0.0), ('sleep', b'', 0.1), ('get', b'', 0.0)]
    expected += [('sleep', b'', 0.2)]
    expected += [('send', pk('06 01 45 06 02 00 05'), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('send', pk('06 01 4e 06 04 01 01 01 ff'), 0.0), ('sleep', b'', 0.05)] + HS()

    ops = S.write_buttons(CAP, slot=0, scratch=1, pre_switch=False)
    assert strip_marks(ops) == expected


def test_write_profile_block_commits_the_swarm_way():
    """Profile write: 3 page writes then a commit with colour-B in byte 5 and the checksum over the 76
    bytes (block + colour-B) — the form Swarm's .dat exports use. The old 0xff/75-byte commit is what
    the mouse was rejecting (DPI-set-in-app did nothing)."""
    block = P.ProfileBlock.from_dpi(2, 950).to_bytes()
    commit_b = 0xFF                                     # default colour-B
    pages = [block[i * 25:(i + 1) * 25] for i in range(3)]
    cs = (sum(block) + commit_b) & 0xFFFF               # checksum over 76 bytes
    expected = []
    for pg in range(3):
        expected += [('send', pk('06 01 46 06 02 %02x 01' % pg), 0.0), ('sleep', b'', 0.05)] + HS()
        expected += [('send', pk('06 01 46 06 19 ' + pages[pg].hex(' ')), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('send', pk('06 01 46 06 02 03 01'), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('send', pk('06 01 46 06 03 %02x %02x %02x' % (commit_b, cs & 0xFF, cs >> 8)), 0.0), ('sleep', b'', 0.05)] + HS()
    assert strip_marks(S.write_profile_block(block, commit_b)) == expected


def test_switch_profile_equals_frida_inject_switch():
    expected = []
    for pg in range(4):
        expected += [('send', pk('06 01 46 06 02 %02x 01' % pg), 0.0), ('sleep', b'', 0.05),
                     ('send', pk('06 01 46 07'), 0.0), ('sleep', b'', 0.1), ('get', b'', 0.0)]
    expected += [('sleep', b'', 0.1)]
    expected += [('send', pk('06 01 45 06 02 03 05'), 0.0), ('sleep', b'', 0.05)] + HS()
    expected += [('send', pk('06 01 4e 06 04 01 01 01 ff'), 0.0), ('sleep', b'', 0.05)] + HS()
    assert strip_marks(S.switch_profile(3)) == expected
    # roccat_write.switch_profile variant: slot number in byte 5 of the activate packet
    ops = S.switch_profile(3, activate_b5=3)
    assert S.only_sends(ops)[-2][:9].hex(' ') == '06 01 4e 06 04 03 01 01 ff'


def test_pre_switch_prefixes_a_full_switch():
    ops = S.write_buttons(CAP, slot=2, pre_switch=True)
    sends = S.only_sends(ops)
    assert sends[8][:7].hex(' ') == '06 01 45 06 02 02 05'    # after 4x(select,read) comes select slot 2
    assert sends[-4][:7].hex(' ') == '06 01 45 06 02 02 05'   # ends back on slot 2 (select, apply, activate, apply)
    assert any(s[:7].hex(' ') == '06 01 45 06 02 03 05' for s in sends)  # scratch slot 3


def test_op_json_and_totals():
    ops = S.write_buttons(CAP)
    js = S.to_json(ops)
    assert js[1] == {'k': 'send', 'd': list(pk('06 01 47 06 02 00 00')), 'l': 'mouse buttons select page 0 flag 00'}
    assert abs(S.total_sleep(ops) - 5.9) < 1e-9
    assert len(S.only_sends(ops)) == 44
