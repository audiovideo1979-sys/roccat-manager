"""
ab_test_buttons.py — Settle in one sitting why direct button writes "did not work".

Windows only. Usage:
    python tools/ab_test_buttons.py            interactive; runs the variants below and asks you what happened
    python tools/ab_test_buttons.py --only A   run one variant

It writes the SAME byte-exact button block (the captured factory layout with one thumb button
toggled between Delete and Insert) through different transports, then asks you to press button 12
(the thumb button that was Delete in the capture) in Notepad and report what it typed.

Variants, in the order of information gained:
    A  Frida (Swarm II's own handle)                       — the known-good path; confirms the rig works today
    B  Direct handle, Swarm II left RUNNING                 — same bytes, our handle, Swarm's session still alive
    C  Direct handle, Swarm II KILLED first                 — how roccat_write.py did it
    D  C + SignalRGB init preamble (06 00 00 04 / 05 ...)   — in case the receiver needs a session start
    E  Direct, Swarm killed, block header 07 7d 00 (.dat form)  — does the mouse care about the header bytes?
    F  Direct, Swarm killed, add the 0x49 commit afterwards  — does 0x49 make it persist across power cycle?

If B works, the April "must use Swarm's handle" conclusion was wrong and the app can drop Frida.
If only A works, run diag_swarm_handle.py: Swarm's handle is on a different collection than ours.
"""
import argparse
import sys
import time

import _common
from kone_xp_air import protocol as P
from kone_xp_air import sequences as S
from kone_xp_air.session import KoneXPAir
from kone_xp_air.transport import (DirectHidTransport, FridaTransport, TransportError,
                                   kill_swarm, is_swarm_running, format_results)

BUTTON = 'thumb_button_1'
BASE = P.DEFAULT_BLOCK
SLOT = 0


def signalrgb_preamble():
    return S.receiver_init()


def block_with(action, header=P.ZERO_HEADER):
    return P.ButtonBlock.from_bindings({BUTTON: action}, {}, base=BASE, header=header)


def run_variant(name, transport, action, header=P.ZERO_HEADER, preamble=False, commit49=False,
                pre_switch=False, log=_common.say):
    blk = block_with(action, header)
    ops = []
    if preamble:
        ops += signalrgb_preamble()
    ops += S.write_buttons(blk.to_bytes(), slot=SLOT, scratch=1, pre_switch=pre_switch)
    if commit49:
        ops += [S.send(P.commit49_packet(P.checksum16(blk.to_bytes()[:123]))), S.sleep(0.05)] + S.handshake()
    log('\n==== Variant %s: %s -> %s (header %s, %d sends, ~%.1fs) ====' % (
        name, BUTTON, action, blk.to_bytes()[:3].hex(' '), len(S.only_sends(ops)), S.total_sleep(ops)))
    t0 = time.time()
    try:
        res = transport.run(ops)
    except TransportError as e:
        log('transport error: %s' % e)
        return None
    finally:
        transport.close()
    log(format_results(res))
    bad = [r for r in res if r.op.kind in ('send', 'get') and not r.ok]
    log('done in %.1fs, %d ops, %d failed' % (time.time() - t0, len(res), len(bad)))
    return res


def check(expected_key):
    _common.say('\nNow: click into Notepad, press button 12 (thumb button that used to be Delete).')
    _common.say('Expected if the write reached the mouse: it acts as %s.' % expected_key)
    return _common.ask('What did it do? (ins/del/other) ')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='run a single variant letter')
    ap.add_argument('--path', help='HID path for direct variants (from diag_swarm_handle.py)')
    ap.add_argument('--backend', choices=['dll', 'hid'], default='dll')
    args = ap.parse_args()
    path = args.path.encode() if args.path else None

    def direct():
        return DirectHidTransport(path=path, backend=args.backend, log=_common.say)

    def frida():
        return FridaTransport(log=_common.say)

    outcomes = {}
    variants = [
        ('A', 'Frida, Swarm running', lambda: frida(), dict()),
        ('B', 'Direct, Swarm running', lambda: direct(), dict()),
        ('C', 'Direct, Swarm killed', lambda: (kill_swarm(), direct())[1], dict()),
        ('D', 'Direct, Swarm killed, SignalRGB preamble', lambda: (kill_swarm(), direct())[1], dict(preamble=True)),
        ('E', 'Direct, Swarm killed, 07 7d 00 header', lambda: (kill_swarm(), direct())[1], dict(header=P.dat_header(0x00))),
        ('F', 'Direct, Swarm killed, + 0x49 commit', lambda: (kill_swarm(), direct())[1], dict(commit49=True)),
    ]
    toggle = ['Hotkey Insert', 'Hotkey Delete']
    n = 0
    for letter, title, make, extra in variants:
        if args.only and letter != args.only.upper():
            continue
        if letter == 'A' and not is_swarm_running():
            _common.say('Variant A needs Swarm II running. Start it, wait for the mouse to show, then press Enter.')
            input()
        if letter == 'B' and not is_swarm_running():
            _common.say('Variant B needs Swarm II running. Start it, then press Enter.')
            input()
        action = toggle[n % 2]
        n += 1
        expected = 'INSERT (toggles overwrite mode; type a letter over text to see)' if action == 'Hotkey Insert' else 'DELETE'
        res = run_variant(letter, make(), action, **extra)
        if res is None:
            outcomes[letter] = 'transport error'
            continue
        outcomes[letter] = check(expected)
        _common.say('recorded: %s -> %s' % (letter, outcomes[letter]))
    _common.say('\n==== Summary ====')
    for k, v in outcomes.items():
        _common.say('  %s: %s' % (k, v))
    _common.say('\nPaste this summary plus the per-op logs above into the HANDOFF. Remember to push your real '
                'profile back afterwards (Push to Mouse in the app).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
