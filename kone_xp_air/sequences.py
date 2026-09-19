"""
Command sequences as ordered op lists.

The whole point of this layer: the direct-HID transport and the Frida-injected transport execute the
SAME op list, so an A/B test isolates the handle as the only variable. Sequences reproduce the
captured Swarm II traffic byte for byte (inject_full.js for buttons, roccat_write.write_profile for
DPI, roccat_write.switch_profile / frida_inject for profile switching).

Op kinds:
    send   data = 30-byte feature report to hid_send_feature_report
    get    read one 30-byte feature report (report ID 0x06) with hid_get_feature_report
    sleep  seconds
    mark   a label, for logs only
"""
from dataclasses import dataclass

from . import protocol as P


@dataclass(frozen=True)
class Op:
    kind: str
    data: bytes = b''
    seconds: float = 0.0
    label: str = ''

    def to_json(self):
        d = {'k': self.kind}
        if self.kind == 'send':
            d['d'] = list(self.data)
            d['l'] = self.label or P.describe(self.data)
        elif self.kind == 'sleep':
            d['s'] = self.seconds
        elif self.kind == 'mark':
            d['l'] = self.label
        return d


def send(pkt, label=''):
    return Op('send', bytes(pkt), label=label or P.describe(pkt))


def get():
    return Op('get')


def sleep(seconds):
    return Op('sleep', seconds=seconds)


def mark(label):
    return Op('mark', label=label)


def handshake():
    """Swarm's post-write pattern: apply, 100 ms, read status, 50 ms (HS() in every capture replay)."""
    return [send(P.apply_packet()), sleep(0.1), get(), sleep(0.05)]


# ── Profile (DPI) block, command 0x46 — as roccat_write.write_profile (proven over a direct handle) ──

def write_profile_block(block_bytes, commit_b=0xFF):
    # Page-select flag 0x00 = WRITE, matching the proven button write (inject_full.js selects each 0x47
    # page with flag 0x00). The old code used 0x01 here — the READ flag (read_pages / profile-switch
    # read use 0x01) — so the profile pages were selected in read mode and the DPI writes never stuck
    # (confirmed on hardware 2026-09-19: block content correct but push changed nothing).
    pages = P.split_pages(block_bytes, P.PROFILE_PAGES)
    ops = [mark('write profile block slot %d' % block_bytes[2])]
    for pg, page in enumerate(pages):
        ops += [send(P.select_page_packet(P.CMD_PROFILE, pg, 0x00)), sleep(0.05)] + handshake()
        ops += [send(P.write_page_packet(P.CMD_PROFILE, page)), sleep(0.05)] + handshake()
    ops += [send(P.select_page_packet(P.CMD_PROFILE, 0x03, 0x00)), sleep(0.05)] + handshake()
    # Commit as Swarm does: colour-B in byte 5, checksum over the 76 bytes (block + that B).
    cs = P.checksum16(bytes(block_bytes) + bytes([commit_b & 0xFF]))
    ops += [send(P.profile_commit_packet(commit_b, cs)), sleep(0.05)] + handshake()
    return ops


# ── Reads (response buffers are returned by the transport; decoding them is still open) ──

def read_pages(cmd, flag, count=4):
    """Page-read loop exactly as the captures do it: select page, 50 ms, read, 100 ms, get."""
    ops = [mark('read %s pages flag %02x' % ('buttons' if cmd == P.CMD_BUTTONS else 'profile', flag))]
    for pg in range(count):
        ops += [send(P.select_page_packet(cmd, pg, flag)), sleep(0.05),
                send(P.read_packet(cmd)), sleep(0.1), get()]
    return ops


# ── Profile switching, commands 0x45 + 0x4e ──

def select_and_activate(slot, activate_b5=0x01, count=P.PROFILE_COUNT):
    return ([send(P.profile_select_packet(slot, count)), sleep(0.05)] + handshake() +
            [send(P.activate_packet(activate_b5)), sleep(0.05)] + handshake())


def switch_profile(slot, activate_b5=0x01):
    """Full switch as frida_inject.switch_profile / roccat_write.switch_profile: read 4 profile pages
    (flag 01) first, as Swarm does, then select + activate."""
    return [mark('switch to slot %d' % slot)] + read_pages(P.CMD_PROFILE, 0x01) + [sleep(0.1)] + \
        select_and_activate(slot, activate_b5)


# ── Button block, command 0x47 — byte-for-byte the working replay (inject_full.js) ──

def write_button_pages(block_bytes):
    pages = P.split_pages(block_bytes, P.BUTTON_PAGES)
    ops = [mark('write button block (header %s)' % block_bytes[:4].hex(' '))]
    for pg, page in enumerate(pages):
        ops += [send(P.select_page_packet(P.CMD_BUTTONS, pg, 0x00)), sleep(0.05)] + handshake()
        ops += [send(P.write_page_packet(P.CMD_BUTTONS, page)), sleep(0.05)] + handshake()
    return ops


def _b5(activate_b5, slot):
    """activate_b5 is an int used verbatim, or 'slot' to put the slot number in byte 5."""
    return slot if activate_b5 == 'slot' else activate_b5


def activate_buttons(slot, scratch, activate_b5=0x01):
    """The tail of the working replay after the pages: read profile pages (flag 01), switch to a scratch
    slot, read pages (flag 00), switch back. The replay used slot 0 with scratch 1."""
    ops = [sleep(0.5)] + read_pages(P.CMD_PROFILE, 0x01) + [sleep(0.2)]
    ops += select_and_activate(scratch, _b5(activate_b5, scratch)) + [sleep(1.0)]
    ops += read_pages(P.CMD_PROFILE, 0x00) + [sleep(0.2)]
    ops += select_and_activate(slot, _b5(activate_b5, slot))
    return ops


def write_buttons(block_bytes, slot=0, scratch=None, pre_switch=False, activate_b5=0x01):
    """Write a button block for `slot`. With pre_switch=False and slot=0/scratch=1 this is exactly the
    working replay. pre_switch=True first switches the mouse to `slot`, on the hypothesis that a block
    with a zero header lands in the active profile."""
    if scratch is None:
        scratch = (slot + 1) % P.PROFILE_COUNT
    ops = []
    if pre_switch:
        ops += switch_profile(slot, _b5(activate_b5, slot)) + [sleep(0.3)]
    ops += write_button_pages(block_bytes)
    ops += activate_buttons(slot, scratch, activate_b5)
    return ops


# ── Receiver init preamble ──

SIGNALRGB_INIT = [
    [0x06, 0x01, 0x13, 0x07, 0x02], [0x06, 0x00, 0x00, 0x04], [0x06, 0x00, 0x00, 0x05],
    [0x06, 0x01, 0x35, 0x07], [0x06, 0x01, 0x00, 0x04], [0x06, 0x01, 0x00, 0x05],
    [0x06, 0x01, 0x4E, 0x06, 0x04, 0x01, 0x01, 0x01, 0xFF], [0x06, 0x01, 0x44, 0x07],
    [0x06, 0x01, 0x49, 0x06, 0x01, 0x04], [0x06, 0x01, 0x44, 0x07],
]


def receiver_init():
    """The sequence the SignalRGB Kone XP Air plugin sends after opening the receiver (Initialize()),
    30 ms apart. Not part of any Swarm capture in the repo; A/B variant D tests whether a fresh handle
    needs it before the mouse accepts button writes."""
    ops = [mark('receiver init (SignalRGB preamble)')]
    for pkt in SIGNALRGB_INIT:
        ops += [send(P.packet(pkt), 'init ' + bytes(pkt).hex(' ')), sleep(0.03)]
    return ops


# ── Utilities ──

def only_sends(ops):
    return [op.data for op in ops if op.kind == 'send']


def total_sleep(ops):
    return sum(op.seconds for op in ops if op.kind == 'sleep')


def to_json(ops):
    return [op.to_json() for op in ops]
