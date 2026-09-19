"""capture_swarm_dpi.py — record the HID feature reports Swarm II sends when you change the DPI.

Windows only, Swarm II running. This is how we reproduce Swarm's real DPI write (our own 0x46 write is
rejected by the mouse; the .dat gives the block content but not the wire write sequence).

    python tools/capture_swarm_dpi.py
    python tools/capture_swarm_dpi.py --process "Turtle Beach Device Service.exe"   # if the UI exe shows nothing

Steps:
  1. Open Swarm II (so it owns the mouse).
  2. Run this. It attaches and prints "hooked ...".
  3. In Swarm II change the DPI to a distinctive value (e.g. 800 -> 3000) and click apply/save.
  4. Watch the SEND lines scroll. Press ENTER here to stop.
  5. Copy ALL the SEND/GET lines from step 3 and send them back.

If nothing prints when you change the DPI, the write is happening in the other process — re-run with
--process "Turtle Beach Device Service.exe". Run the terminal as Administrator if attach fails.
"""
import argparse
import os
import sys

import _common  # noqa: F401  (adds repo root to sys.path)
import frida

JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capture_swarm_dpi.js')
DEFAULT_PROCESS = 'Turtle Beach Swarm II.exe'


def find_pid(name):
    try:
        for p in frida.get_local_device().enumerate_processes():
            if p.name.lower() == name.lower():
                return p.pid
    except Exception as e:
        _common.say('process enumerate failed: %s' % e)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--process', default=DEFAULT_PROCESS, help='process that loads KONE_XP_AIR.dll')
    args = ap.parse_args()

    pid = find_pid(args.process)
    if pid is None:
        _common.say('%s is not running. Open Swarm II first (or try --process "Turtle Beach Device Service.exe").'
                    % args.process)
        return 1
    _common.say('Attaching to %s (pid %d)...' % (args.process, pid))
    try:
        session = frida.get_local_device().attach(pid)
    except Exception as e:
        _common.say('could not attach: %s\nRun this terminal as Administrator and try again.' % e)
        return 1

    count = {'n': 0}

    def on_message(msg, data):
        if msg.get('type') == 'send':
            p = msg.get('payload') or {}
            if 'line' in p:
                _common.say('[%s]' % p['line'])
            else:
                count['n'] += 1
                _common.say('%s  %s' % (p.get('dir', '??'), p.get('data', '')))
        elif msg.get('type') == 'error':
            _common.say('SCRIPT ERROR: %s' % (msg.get('description') or msg))

    with open(JS, encoding='utf-8') as f:
        script = session.create_script(f.read())
    script.on('message', on_message)
    script.load()

    _common.say('\n=== Now change the DPI in Swarm II (e.g. 800 -> 3000) and click apply. ===')
    try:
        input('Press ENTER here when done...\n')
    except (EOFError, KeyboardInterrupt):
        pass
    _common.say('Captured %d frames. Send back the SEND/GET lines from the DPI change.' % count['n'])
    try:
        session.detach()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
