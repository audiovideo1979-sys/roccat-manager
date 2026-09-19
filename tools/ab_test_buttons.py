"""
ab_test_buttons.py — Settle whether direct button writes work, and under which conditions.

Windows only. Swarm II must be installed; the Kone XP Air on its receiver.

    python tools\\ab_test_buttons.py              run the variants in order, ask what happened
    python tools\\ab_test_buttons.py --only A     run one variant (A..F)
    python tools\\ab_test_buttons.py --only AB    run a subset

Each variant rewrites onboard slot 0's button block and maps thumb button 12 to a DISTINCT, visible
letter. You press button 12 in Notepad and report the letter you see. Because every variant uses a
different letter, a write that silently did nothing is obvious: button 12 still types the PREVIOUS
letter (or its original binding), not this variant's.

Variants, most informative first:
    A  Frida (Swarm II's own handle), Swarm running     the known-good path; proves the rig works now
    B  Direct handle, Swarm II RUNNING                  same collection, our own handle  <-- the key test
    C  Direct handle, Swarm II KILLED first             in case a live Swarm session interferes
    D  Direct, Swarm killed, + receiver-init preamble   in case a fresh handle must start a session
    E  Direct, Swarm killed, 07 7d 00 (.dat) header     does the mouse care about the 3 header bytes?
    F  Direct, Swarm killed, + 0x49 commit              does 0x49 make it persist across a power cycle?

diag_swarm_handle.py already showed Swarm writes through the same collection our direct handle opens
(PID 0x5017, usage page 0xff03), so B is the one that matters: if B changes button 12, direct writes
work and the app can drop Frida. Run A first (baseline), then B.

WARNING: this overwrites slot 0's button layout with a test layout. When you finish, push your real
profile back from the app (Push to Mouse) or from Swarm II. Your DPI is not touched.
"""
import argparse
import os
import sys
import time
import traceback

import _common
from kone_xp_air import protocol as P
from kone_xp_air import sequences as S
from kone_xp_air.transport import (DirectHidTransport, FridaTransport, TransportError,
                                   kill_swarm, is_swarm_running, format_results)

BUTTON = 'thumb_button_1'   # physical thumb button 12
BASE = P.DEFAULT_BLOCK
SLOT = 0

# One distinct, always-visible letter per variant. Pressing button 12 types this letter in Notepad.
LETTERS = {'A': 'N', 'B': 'M', 'C': 'B', 'D': 'V', 'E': 'G', 'F': 'T'}


class Tee:
    """Write every line to the console and to a transcript file the user can send back."""
    def __init__(self, path):
        self.path = path
        self.fh = open(path, 'w', encoding='utf-8')

    def say(self, msg=''):
        print(msg, flush=True)
        self.fh.write(str(msg) + '\n')
        self.fh.flush()

    def ask(self, prompt):
        ans = _common.ask(prompt)
        self.fh.write(prompt + ' ' + ans + '\n')
        self.fh.flush()
        return ans

    def close(self):
        try:
            self.fh.close()
        except Exception:
            pass


def block_with(letter, header=P.ZERO_HEADER):
    return P.ButtonBlock.from_bindings({BUTTON: 'Hotkey ' + letter}, {}, base=BASE, header=header)


def build_ops(letter, header=P.ZERO_HEADER, preamble=False, commit49=False, pre_switch=False):
    blk = block_with(letter, header)
    ops = []
    if preamble:
        ops += S.receiver_init()
    ops += S.write_buttons(blk.to_bytes(), slot=SLOT, scratch=1, pre_switch=pre_switch)
    if commit49:
        ops += [S.send(P.commit49_packet(P.checksum16(blk.to_bytes()[:123]))), S.sleep(0.05)] + S.handshake()
    return ops, blk


def run_variant(letter, title, make_transport, tee, **extra):
    result_letter = LETTERS[letter]
    ops, blk = build_ops(result_letter, **extra)
    tee.say('\n==== Variant %s: %s ====' % (letter, title))
    tee.say('    writes button 12 = key "%s"  (header %s, %d sends, ~%.1fs)'
            % (result_letter, blk.to_bytes()[:3].hex(' '), len(S.only_sends(ops)), S.total_sleep(ops)))
    transport = None
    t0 = time.time()
    try:
        transport = make_transport()
        res = transport.run(ops)
    except TransportError as e:
        tee.say('    TRANSPORT ERROR: %s' % e)
        return {'variant': letter, 'status': 'transport_error', 'error': str(e)}
    except Exception as e:                       # never let one variant abort the whole run
        tee.say('    ERROR: %s' % e)
        tee.say(traceback.format_exc())
        return {'variant': letter, 'status': 'error', 'error': repr(e)}
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
    tee.say(format_results(res))
    failed = [r for r in res if r.op.kind in ('send', 'get') and not r.ok]
    tee.say('    sent %d ops in %.1fs, %d failed at the API level' % (len(res), time.time() - t0, len(failed)))
    if failed:
        tee.say('    (API-level failures mean the write did not even leave the PC cleanly)')
    return {'variant': letter, 'status': 'sent', 'expect_letter': result_letter, 'api_failed': len(failed)}


def observe(letter, tee):
    result_letter = LETTERS[letter]
    tee.say('')
    tee.say('  >> Click into Notepad and press thumb button 12 once.')
    tee.say('  >> If this write reached the mouse, it types the letter "%s".' % result_letter)
    ans = tee.ask('  >> What letter (or action) did button 12 produce? ')
    took = ans.strip().lower() == result_letter.lower()
    tee.say('     recorded: %r  (write %s)' % (ans, 'TOOK' if took else 'did NOT take / different'))
    return {'answer': ans, 'took': took}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='', help='variant letters to run, e.g. A or AB (default: all)')
    ap.add_argument('--path', help='HID path for direct variants (from diag_swarm_handle.py); default auto')
    ap.add_argument('--backend', choices=['dll', 'hid'], default='dll')
    args = ap.parse_args()
    path = args.path.encode() if args.path else None
    only = args.only.upper().replace(',', '').replace(' ', '')

    stamp = time.strftime('%Y%m%d_%H%M%S')
    log_path = os.path.abspath('ab_result_%s.txt' % stamp)
    tee = Tee(log_path)

    def direct():
        return DirectHidTransport(path=path, backend=args.backend, log=tee.say)

    def frida():
        return FridaTransport(log=tee.say)

    variants = [
        ('A', 'Frida, Swarm running', frida, {}),
        ('B', 'Direct, Swarm running', direct, {}),
        ('C', 'Direct, Swarm killed', lambda: (kill_swarm(), direct())[1], {}),
        ('D', 'Direct, Swarm killed, receiver-init preamble', lambda: (kill_swarm(), direct())[1], {'preamble': True}),
        ('E', 'Direct, Swarm killed, 07 7d 00 header', lambda: (kill_swarm(), direct())[1], {'header': P.dat_header(0x00)}),
        ('F', 'Direct, Swarm killed, + 0x49 commit', lambda: (kill_swarm(), direct())[1], {'commit49': True}),
    ]

    outcomes = []
    try:
        tee.say('ROCCAT Kone XP Air — direct-vs-Frida button write A/B test')
        tee.say('transcript: %s' % log_path)
        tee.say('Open Notepad and click into it now. Keep your hand OFF the mouse buttons while a')
        tee.say('variant is writing (each takes 6-15 s); press button 12 only when asked.')
        tee.say('')
        tee.say('Baseline: press thumb button 12 once in Notepad.')
        base_ans = tee.ask('  >> What does button 12 do right now (before any test)? ')
        tee.say('  baseline recorded: %r' % base_ans)

        for letter, title, make, extra in variants:
            if only and letter not in only:
                continue
            if letter in ('A', 'B') and not is_swarm_running():
                tee.say('\nVariant %s needs Swarm II running. Start it, let the mouse appear, then press Enter.' % letter)
                input()
            sent = run_variant(letter, title, make, tee, **extra)
            if sent['status'] != 'sent':
                outcomes.append(dict(sent, took=None, answer=None))
                continue
            obs = observe(letter, tee)
            outcomes.append(dict(sent, **obs))
            tee.say('    (mouse is back on slot 0)')

        tee.say('\n================ SUMMARY ================')
        for o in outcomes:
            if o['status'] != 'sent':
                tee.say('  %s: %s (%s)' % (o['variant'], o['status'], o.get('error', '')))
            else:
                verdict = 'WORKED' if o.get('took') else 'no change'
                tee.say('  %s: %s  (expected "%s", saw %r)' % (o['variant'], verdict, o['expect_letter'], o.get('answer')))
        worked = [o['variant'] for o in outcomes if o.get('took')]
        tee.say('')
        tee.say('  Direct write works: %s' % (', '.join(v for v in worked if v != 'A') or 'none of B-F'))
        if 'B' in worked:
            tee.say('  -> B worked: set Transport to Direct in the app; Swarm II is no longer needed.')
        elif worked and 'A' in worked:
            tee.say('  -> Only Frida/one direct condition worked; send this transcript to Claude to decide.')
    except KeyboardInterrupt:
        tee.say('\ninterrupted.')
    finally:
        tee.say('')
        tee.say('*** RESTORE: slot 0 now holds a TEST layout. Push your real profile back from the app')
        tee.say('    (Push to Mouse) or from Swarm II. Your DPI was not changed. ***')
        tee.say('transcript saved: %s  — send this file to Claude.' % log_path)
        tee.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
