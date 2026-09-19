"""
dump_mouse_pages.py — Read back raw profile/button pages from the mouse and print the responses.

Windows only.
    python tools/dump_mouse_pages.py --transport frida            (Swarm II running)
    python tools/dump_mouse_pages.py --transport direct           (Swarm II running or not)
    python tools/dump_mouse_pages.py --transport direct --kill-swarm

The page-read protocol (select page, read, get_feature_report) is already used by Swarm and the
working replay, but nobody has looked at what comes back. This dumps the 30-byte answers for command
0x46 (profile) and 0x47 (buttons), flags 00 and 01, pages 0-4, so the decoding can be worked out.
If the answers contain the button block pages, reading profiles no longer needs Swarm's heap.
"""
import argparse
import sys

import _common  # noqa: F401
from kone_xp_air import protocol as P
from kone_xp_air import sequences as S
from kone_xp_air.transport import make_transport, kill_swarm, format_results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--transport', choices=['frida', 'direct'], default='frida')
    ap.add_argument('--path', help='HID path for the direct transport (default: dongle usage page 0xff03)')
    ap.add_argument('--backend', choices=['dll', 'hid'], default='dll')
    ap.add_argument('--kill-swarm', action='store_true')
    ap.add_argument('--pages', type=int, default=5)
    args = ap.parse_args()

    if args.kill_swarm:
        kill_swarm()
    kw = {'log': _common.say}
    if args.transport == 'direct':
        kw.update(path=args.path.encode() if args.path else None, backend=args.backend)
    t = make_transport(args.transport, **kw)
    try:
        for cmd, name in ((P.CMD_PROFILE, 'profile 0x46'), (P.CMD_BUTTONS, 'buttons 0x47')):
            for flag in (0x01, 0x00):
                _common.say('\n== %s, flag %02x ==' % (name, flag))
                res = t.run(S.read_pages(cmd, flag, args.pages))
                _common.say(format_results(res))
                gets = [r for r in res if r.op.kind == 'get']
                joined = b''.join(r.response[1:] for r in gets)
                _common.say('   concatenated answers (minus report id): %s' % joined.hex(' '))
    finally:
        t.close()
    _common.say('\nCompare the concatenated bytes with the block you last wrote (tests/test_protocol.py '
                'FACTORY layout, or the page writes printed by ab_test_buttons.py).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
