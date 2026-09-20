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


def test_profile_write_matches_the_swarm_dpi_capture():
    """Byte-for-byte against a live Frida capture of Swarm II writing DPI 3000 to slot 1
    (tools/capture_swarm_dpi.py, 2026-09-20). This is the write the mouse ACCEPTS; the earlier forms
    (roccat_write's bytes 31-32 = 06 ff, and the .dat's byte 5 = 0x02) did not change DPI on hardware."""
    wire = bytes.fromhex((
        '06 4e 01 06 06 1f 00 b8 0b 20 03 20 03 20 03 20 03 20 03 20 03 20 03 20 03'   # page 0
        '20 03 00 00 03 0a 01 00 05 00 00 14 ff 00 48 ff 14 ff 00 48 ff 14 ff 00 48'   # page 1
        'ff 14 ff 00 48 ff 14 ff 00 48 ff 14 ff 00 48 ff 14 ff 00 48 ff 01 64 ff ff'   # page 2
    ).replace(' ', ''))
    blk = P.ProfileBlock(slot=1, dpi_x=[3000, 800, 800, 800, 800], dpi_y=[800, 800, 800, 800, 800])
    assert blk.to_bytes() == wire                                   # exact block
    sends = S.only_sends(S.write_profile_block(blk.to_bytes(), blk.commit_color_b()))
    assert b''.join(s[5:30] for s in sends if s[4] == 0x19) == wire  # 3 page writes reconstruct it
    assert all(s[6] == 0x01 for s in sends if s[4] == 0x02)         # every page select uses flag 0x01
    commit = next(s for s in sends if s[4] == 0x03)
    assert commit[:8].hex(' ') == '06 01 46 06 03 ff 69 16'         # captured commit (cs16 over block+0xff)


def test_write_profile_block_commits_the_swarm_way():
    """Profile write: 3 page writes then a commit with byte 5 = 0xff and the checksum over the 76 bytes
    (block + that 0xff) — matching the Swarm DPI capture. The old 0xff/75-byte commit and the 06 ff mid
    bytes are what the mouse was rejecting (DPI-set-in-app did nothing)."""
    block = P.ProfileBlock.from_dpi(2, 950).to_bytes()
    commit_b = 0xFF                                     # 0xff on the wire (the block's colour-B default)
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
