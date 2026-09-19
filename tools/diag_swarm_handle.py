"""
diag_swarm_handle.py — Which HID collection does Swarm II actually write through?

Windows only. Swarm II must be running with the mouse connected.

    python tools/diag_swarm_handle.py

Attaches Frida to Swarm II, waits for its hid_send_feature_report calls, and reports for the handle
that carries report 0x06: VID/PID, usage page/usage, report lengths and the kernel object name. It
then lists every HID collection of our vendor as the `hid` package sees them, so the matching path can
be used by DirectHidTransport. Also prints which command bytes Swarm sends on each handle.
"""
import json
import sys

import _common  # noqa: F401
from kone_xp_air.transport import FridaTransport, TransportError, enumerate_candidates
from kone_xp_air import sequences as S


def main():
    _common.say('Attaching to Swarm II and watching its HID traffic for up to 10 s ...')
    t = FridaTransport(wait_handle_s=10, prefer_non_lighting=True, diag=True, log=_common.say)
    try:
        t.run([S.mark('diag only')])
    except TransportError as e:
        _common.say('FAILED: %s' % e)
        if t.last_message:
            _common.say(json.dumps(t.last_message, indent=2))
        return 1
    msg = t.last_message or {}
    _common.say('\n== Handles Swarm II used for report 0x06 ==')
    for h in msg.get('handles', []):
        _common.say('  %s  sends=%d  cmds=%s' % (h['handle'], h['sends'], h['cmds']))
        _common.say('      first: %s' % h.get('first'))
        _common.say('      last : %s' % h.get('last'))
    _common.say('\n== Chosen handle: %s ==' % msg.get('handle'))
    _common.say(json.dumps(msg.get('diag') or {}, indent=2))
    _common.say('\n== Our vendor\'s HID collections (python hid.enumerate) ==')
    try:
        for c in enumerate_candidates():
            _common.say('  pid=%s usage_page=%s usage=%s iface=%s product=%r' % (
                c['pid'], c['usage_page'], c['usage'], c['interface'], c['product']))
            _common.say('      %s' % c['path'])
    except Exception as e:
        _common.say('  hid.enumerate failed: %s (pip install hidapi)' % e)
    _common.say('\nMatch the chosen handle\'s pid/usage_page/usage to a path above. If it is NOT pid=0x5017 '
                'usage_page=0xff03, pass that path to DirectHidTransport(path=...) / ab_test_buttons.py --path.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
