"""
Wire-level protocol for the ROCCAT Kone XP Air (Turtle Beach VID 0x10F5) through its USB receiver.

Everything is a HID *feature* report: report ID 0x06, 30 bytes, sent to the receiver's vendor
collection (this project opens the dongle, PID 0x5017, usage page 0xFF03). Byte 1 addresses the
target: 0x00 = the receiver itself, 0x01 = the paired mouse (confirmed by the SignalRGB plugins:
the wired-mode plugin sends the same commands with 0x00, the wireless one with 0x01).

Command byte (offset 2) when talking to the mouse:
    0x44  apply / handshake          06 01 44 07          Swarm follows every write with this + a get_feature_report
    0x45  profile select             06 01 45 06 02 <slot> <count>
    0x46  profile (DPI/LED) block    pages of 25 bytes, 75-byte block, commit 06 01 46 06 03 ff <cs16>
    0x47  button block               pages of 25 bytes, 125-byte block, no commit in the working capture
    0x49  commit / profile table     06 01 49 06 03 05 <cs16>   (seen after profile writes in the SignalRGB capture)
    0x4D  live lighting frame        06 01 4d 06 15 ...   Swarm streams these continuously
    0x4E  activate                   06 01 4e 06 04 01 01 01 ff
Sub-command byte (offset 4) for 0x46/0x47:
    0x02  select page   06 01 <cmd> 06 02 <page> <flag>
    0x03  commit        06 01 <cmd> 06 03 ...
    0x07  read          06 01 <cmd> 07            then get_feature_report(0x06)
    0x19  write page    06 01 <cmd> 06 19 <25 bytes>

This module is pure Python and hardware-free: it only builds and parses bytes.
"""
from dataclasses import dataclass, field
import struct

from . import actions

REPORT_ID = 0x06
REPORT_LEN = 30
PAGE_LEN = 25
TARGET_RECEIVER = 0x00
TARGET_MOUSE = 0x01

CMD_APPLY = 0x44
CMD_PROFILE_SELECT = 0x45
CMD_PROFILE = 0x46
CMD_BUTTONS = 0x47
CMD_COMMIT = 0x49
CMD_LIGHTING = 0x4D
CMD_ACTIVATE = 0x4E

SUB_SELECT_PAGE = 0x02
SUB_COMMIT = 0x03
SUB_READ = 0x07
SUB_WRITE_PAGE = 0x19

PROFILE_COUNT = 5


# ── Packets ──────────────────────────────────────────────────────────────────

def packet(payload):
    """Pad a payload to the 30-byte feature report."""
    payload = bytes(payload)
    if len(payload) > REPORT_LEN:
        raise ValueError('payload longer than %d bytes' % REPORT_LEN)
    return payload + b'\x00' * (REPORT_LEN - len(payload))


def apply_packet(target=TARGET_MOUSE):
    return packet([REPORT_ID, target, CMD_APPLY, 0x07])


def select_page_packet(cmd, page, flag):
    return packet([REPORT_ID, TARGET_MOUSE, cmd, 0x06, SUB_SELECT_PAGE, page, flag])


def write_page_packet(cmd, page_bytes):
    page_bytes = bytes(page_bytes)
    if len(page_bytes) != PAGE_LEN:
        raise ValueError('page must be %d bytes' % PAGE_LEN)
    return packet([REPORT_ID, TARGET_MOUSE, cmd, 0x06, SUB_WRITE_PAGE] + list(page_bytes))


def read_packet(cmd):
    return packet([REPORT_ID, TARGET_MOUSE, cmd, SUB_READ])


def profile_select_packet(slot, count=PROFILE_COUNT):
    _check_slot(slot)
    return packet([REPORT_ID, TARGET_MOUSE, CMD_PROFILE_SELECT, 0x06, 0x02, slot, count])


def activate_packet(b5=0x01):
    """06 01 4e 06 04 <b5> 01 01 ff. The working button replay and SignalRGB always send b5=0x01;
    roccat_write.switch_profile sent the slot number there. Both are reported to work."""
    return packet([REPORT_ID, TARGET_MOUSE, CMD_ACTIVATE, 0x06, 0x04, b5, 0x01, 0x01, 0xFF])


def profile_commit_packet(commit_b, checksum):
    """06 01 46 06 03 <commit_b> <cs_lo> <cs_hi>. Swarm puts the profile colour's B channel in byte 5
    and the checksum over the 76 bytes (block + that B). The old code sent 0xff here with a 75-byte
    checksum, which the mouse rejects."""
    return packet([REPORT_ID, TARGET_MOUSE, CMD_PROFILE, 0x06, SUB_COMMIT, commit_b & 0xFF,
                   checksum & 0xFF, (checksum >> 8) & 0xFF])


def commit49_packet(checksum, count=PROFILE_COUNT):
    return packet([REPORT_ID, TARGET_MOUSE, CMD_COMMIT, 0x06, SUB_COMMIT, count,
                   checksum & 0xFF, (checksum >> 8) & 0xFF])


def receiver_packet(a, b):
    """06 00 <a> <b> — commands addressed to the receiver (e.g. 06 00 00 04 / 06 00 00 05)."""
    return packet([REPORT_ID, TARGET_RECEIVER, a, b])


def get_feature_request():
    """Buffer handed to hid_get_feature_report: report ID in byte 0."""
    return packet([REPORT_ID])


def split_pages(block, count):
    block = bytes(block)
    if len(block) != count * PAGE_LEN:
        raise ValueError('block must be %d bytes' % (count * PAGE_LEN))
    return [block[i * PAGE_LEN:(i + 1) * PAGE_LEN] for i in range(count)]


def checksum16(data):
    return sum(bytes(data)) & 0xFFFF


def _check_slot(slot):
    if not 0 <= slot < PROFILE_COUNT:
        raise ValueError('slot must be 0-4, got %r' % (slot,))


_CMD_NAMES = {CMD_APPLY: 'apply', CMD_PROFILE_SELECT: 'profile-select', CMD_PROFILE: 'profile',
              CMD_BUTTONS: 'buttons', CMD_COMMIT: 'commit49', CMD_LIGHTING: 'lighting',
              CMD_ACTIVATE: 'activate'}


def describe(pkt):
    """Human label for a packet, for logs and the A/B tool."""
    p = bytes(pkt)
    if len(p) < 4 or p[0] != REPORT_ID:
        return 'raw ' + p[:8].hex(' ')
    tgt = 'mouse' if p[1] == TARGET_MOUSE else 'receiver'
    name = _CMD_NAMES.get(p[2], '0x%02x' % p[2])
    if p[2] in (CMD_PROFILE, CMD_BUTTONS):
        if p[3] == SUB_READ:
            return '%s %s read' % (tgt, name)
        sub = p[4]
        if sub == SUB_SELECT_PAGE:
            return '%s %s select page %d flag %02x' % (tgt, name, p[5], p[6])
        if sub == SUB_WRITE_PAGE:
            return '%s %s write page [%s]' % (tgt, name, p[5:30].hex(' '))
        if sub == SUB_COMMIT:
            return '%s %s commit %02x cs=%04x' % (tgt, name, p[5], p[6] | (p[7] << 8))
    if p[2] == CMD_PROFILE_SELECT:
        return '%s profile-select slot %d of %d' % (tgt, p[5], p[6])
    if p[2] == CMD_COMMIT:
        return '%s commit49 %s' % (tgt, p[3:8].hex(' '))
    if p[2] == CMD_ACTIVATE:
        return '%s activate %s' % (tgt, p[5:9].hex(' '))
    if p[2] == CMD_APPLY:
        return '%s apply' % tgt
    return '%s %s %s' % (tgt, name, p[3:8].hex(' '))


# ── Button block (command 0x47) ───────────────────────────────────────────────
#
# 125 bytes = 3-byte header + 30 x 4-byte entries + 16-bit little-endian sum checksum.
# Entries k=0..14 are the 15 physical inputs, k=15..29 the same 15 inputs on the Easy-Shift layer
# (the Easy-Shift key's own Easy-Shift entry is normally disabled; button 15's is the RGB toggle).
# Header: 00 00 00 on the wire (the byte-exact Swarm II write captured via Frida, inject_buttons2.js);
# 07 7d <flag> in Swarm's .dat exports and in its process memory (07 = command 0x47 & 0x0f, 7d = 125 =
# block length, flag = 00/01 with unknown meaning - NOT the onboard slot: WWM.dat sits in slot 4 and
# carries 01). Every Swarm-written .dat in ROCCAT_Manager/profiles verifies with this layout and checksum.

BUTTON_BLOCK_LEN = 125
BUTTON_PAGES = 5
BUTTON_HEADER_LEN = 3
BUTTON_ENTRY_LEN = 4
BUTTON_ENTRY_COUNT = 30
BUTTON_CHECKSUM_OFFSET = 123

PRIMARY_BUTTONS = [
    'left_button', 'right_button', 'middle_button', 'scroll_up', 'scroll_down',
    'side_button_1', 'side_button_2', 'dpi_up', 'dpi_down',
    'thumb_button_1', 'thumb_button_2', 'tilt_left', 'tilt_right',
    'easy_shift', 'profile_switch',
]
EASYSHIFT_BUTTONS = list(PRIMARY_BUTTONS)
assert len(PRIMARY_BUTTONS) + len(EASYSHIFT_BUTTONS) == BUTTON_ENTRY_COUNT

ZERO_HEADER = b'\x00\x00\x00'


def dat_header(flag=0x00):
    """Header as found in Swarm's .dat exports and process memory: 07 7d <flag>. Never observed on
    the wire; the A/B tool sends it to see whether the mouse ignores the header bytes."""
    if not 0 <= flag <= 0xFF:
        raise ValueError('flag must be a byte')
    return bytes([0x07, 0x7D, flag])


def entry_offset(k):
    return BUTTON_HEADER_LEN + BUTTON_ENTRY_LEN * k


@dataclass
class ButtonBlock:
    primary: dict = field(default_factory=dict)      # button name -> action name (15)
    easy_shift: dict = field(default_factory=dict)   # button name -> action name (15)
    header: bytes = ZERO_HEADER
    unsupported: list = field(default_factory=list)  # (layer, button, action) that could not be encoded

    # ---- building ----
    @classmethod
    def from_bindings(cls, keybinds=None, easy_shift=None, base=None, header=None):
        """Build a block from UI dicts. Buttons missing from the dicts, or with an action the encoder
        does not know, keep the value from `base` (a ButtonBlock; defaults to DEFAULT_BLOCK)."""
        base = base or DEFAULT_BLOCK
        blk = cls(primary=dict(base.primary), easy_shift=dict(base.easy_shift),
                  header=header if header is not None else base.header)
        for layer, src, names in (('primary', keybinds or {}, PRIMARY_BUTTONS),
                                  ('easy_shift', easy_shift or {}, EASYSHIFT_BUTTONS)):
            dst = getattr(blk, layer)
            for name in names:
                if name not in src:
                    continue
                action = src[name]
                if actions.is_known(action):
                    dst[name] = actions.normalize(action)
                else:
                    blk.unsupported.append((layer, name, action))
        return blk

    def entries(self):
        out = []
        for name in PRIMARY_BUTTONS:
            out.append(actions.encode_action(self.primary.get(name, 'Disabled')))
        for name in EASYSHIFT_BUTTONS:
            out.append(actions.encode_action(self.easy_shift.get(name, 'Disabled')))
        return out

    def to_bytes(self):
        if len(self.header) != BUTTON_HEADER_LEN:
            raise ValueError('header must be %d bytes' % BUTTON_HEADER_LEN)
        body = bytearray(self.header)
        for e in self.entries():
            body += e
        if len(body) != BUTTON_CHECKSUM_OFFSET:
            raise AssertionError('button block body is %d bytes' % len(body))
        cs = checksum16(body)
        body += bytes([cs & 0xFF, (cs >> 8) & 0xFF])
        return bytes(body)

    def pages(self):
        return split_pages(self.to_bytes(), BUTTON_PAGES)

    def with_header(self, header):
        return ButtonBlock(primary=dict(self.primary), easy_shift=dict(self.easy_shift), header=bytes(header))

    # ---- parsing ----
    @classmethod
    def parse(cls, data, verify_checksum=True):
        data = bytes(data)
        if len(data) != BUTTON_BLOCK_LEN:
            raise ValueError('button block must be %d bytes, got %d' % (BUTTON_BLOCK_LEN, len(data)))
        stored = data[BUTTON_CHECKSUM_OFFSET] | (data[BUTTON_CHECKSUM_OFFSET + 1] << 8)
        calc = checksum16(data[:BUTTON_CHECKSUM_OFFSET])
        if verify_checksum and stored != calc:
            raise ValueError('button block checksum mismatch: stored %04x, computed %04x' % (stored, calc))
        entries = [data[entry_offset(k):entry_offset(k) + BUTTON_ENTRY_LEN] for k in range(BUTTON_ENTRY_COUNT)]
        primary = {name: actions.decode_entry(entries[i]) for i, name in enumerate(PRIMARY_BUTTONS)}
        es = {name: actions.decode_entry(entries[len(PRIMARY_BUTTONS) + i]) for i, name in enumerate(EASYSHIFT_BUTTONS)}
        return cls(primary=primary, easy_shift=es, header=data[:BUTTON_HEADER_LEN])


# The byte-exact block Swarm II wrote in the capture that worked (owner's profile: Delete on thumb 1,
# E on thumb 2, everything else the Swarm defaults). Used as the template for buttons the UI does not set.
CAPTURED_BUTTON_BLOCK = bytes([
    0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x03, 0x01, 0x00, 0x00, 0x09, 0x01, 0x00, 0x00, 0x0a, 0x01, 0x00, 0x00,
    0x05, 0x01, 0x00, 0x00, 0x06, 0x01, 0x00, 0x00, 0x02, 0x02, 0x00, 0x00, 0x03, 0x02, 0x00, 0x4c, 0x00, 0x06, 0x00, 0x08, 0x00, 0x06, 0x00, 0x00, 0x07,
    0x01, 0x00, 0x00, 0x08, 0x01, 0x00, 0x00, 0x01, 0x0a, 0x00, 0x00, 0x01, 0x08, 0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x02, 0x01, 0x00, 0x00, 0x04, 0x03,
    0x00, 0x00, 0x07, 0x03, 0x00, 0x00, 0x08, 0x03, 0x00, 0x4b, 0x00, 0x06, 0x00, 0x4e, 0x00, 0x06, 0x00, 0x19, 0x01, 0x06, 0x00, 0x06, 0x01, 0x06, 0x00,
    0x4c, 0x00, 0x06, 0x00, 0x49, 0x00, 0x06, 0x00, 0x00, 0x02, 0x03, 0x00, 0x00, 0x03, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0b, 0x08, 0x6b, 0x02,
])
assert len(CAPTURED_BUTTON_BLOCK) == BUTTON_BLOCK_LEN

DEFAULT_BLOCK = ButtonBlock.parse(CAPTURED_BUTTON_BLOCK)


# ── Profile block (command 0x46): DPI stages, polling, LED colours ────────────
#
# 75 bytes = 3 pages. Layout as written by roccat_write.build_profile, which is the form proven to
# change DPI on the owner's mouse over a direct handle. Byte meanings marked (?) are unverified.
#   0   0x06                      (?) block type
#   1   0x4E                      (?) constant
#   2   slot 0-4                  profile this block belongs to (verified: writes to all 5 slots work)
#   3-4 0x06 0x06                 (?) SignalRGB's capture of the Roccat-VID model has 00 00 here
#   5   0x1f                      (?) repo called this polling rate; SignalRGB shows the same constant
#   6   active DPI stage 0-4
#   7-16  five DPI X values, LE16
#   17-26 five DPI Y values, LE16
#   27-35 00 00 03 0a 06 ff 05 00 00   (?) byte 29 is the polling-rate code in SignalRGB's capture (0x03)
#   36-70 seven 5-byte LED entries      repo writes 14 ff 00 48 ff; SignalRGB shows <index> r g b <brightness>
#   71-72 01 64
#   73-74 ff ff                          profile colour R,G in Swarm's .dat exports (c5 0b = the purple default)
# Commit: 06 01 46 06 03 ff <sum16 of all 75 bytes>.
# Swarm's .dat "KoneXPAirMain" block is 78 bytes: these 75, then colour B, then sum16(block[0:76]); on the
# wire Swarm sends B in byte 5 of the commit packet (SignalRGB capture: 06 01 46 06 03 dc ...). The repo's
# proven form sends ff there and a checksum over the 75 bytes only, so the mouse evidently does not
# validate this checksum. ProfileBlock keeps the proven form; `color` is carried for round-tripping .dat.

PROFILE_BLOCK_LEN = 75
PROFILE_DAT_LEN = 78
PROFILE_PAGES = 3
DPI_MIN, DPI_MAX = 50, 19000
DPI_STAGES = 5

# Bytes 31-32 = 01 00 (the real DPI-write bug: roccat_write used 06 ff here, which the mouse rejected —
# DPI-set-in-app did nothing). This is matched to a live Frida capture of Swarm II writing DPI on the
# wire (capture_swarm_dpi.py, 2026-09-20), which also confirmed byte 5 = 0x1f and the commit checksum
# is over 76 bytes (block + the 0xff commit byte). NOTE: Swarm's exported .dat files store this block
# differently (byte 5 = 0x02, and a real colour-B instead of 0xff), so the .dat is NOT the wire form —
# parse() reads whatever the source has; the defaults below are the WIRE form we send.
_PROFILE_MID = bytes([0x00, 0x00, 0x03, 0x0a, 0x01, 0x00, 0x05, 0x00, 0x00])
_PROFILE_LED_ENTRY = bytes([0x14, 0xFF, 0x00, 0x48, 0xFF])
_PROFILE_TAIL = bytes([0x01, 0x64, 0xFF, 0xFF])


@dataclass
class ProfileBlock:
    slot: int = 0
    dpi_x: list = field(default_factory=lambda: [800] * DPI_STAGES)
    dpi_y: list = None
    active_stage: int = 0
    byte5: int = 0x1F
    mid: bytes = _PROFILE_MID
    leds: bytes = _PROFILE_LED_ENTRY * 7
    tail: bytes = _PROFILE_TAIL
    bytes3_4: bytes = b'\x06\x06'
    color: tuple = (0xFF, 0xFF, 0xFF)   # profile colour R,G,B; R,G sit at bytes 73-74, B rides the commit

    @classmethod
    def from_dpi(cls, slot, dpi, active_stage=0):
        """dpi: a single int (all five stages equal) or a list of up to five ints."""
        if isinstance(dpi, int):
            stages = [dpi] * DPI_STAGES
        else:
            stages = list(dpi)
            if not stages:
                raise ValueError('dpi list is empty')
            stages = (stages + [stages[-1]] * DPI_STAGES)[:DPI_STAGES]
        for v in stages:
            if not DPI_MIN <= int(v) <= DPI_MAX:
                raise ValueError('DPI %r out of range %d-%d' % (v, DPI_MIN, DPI_MAX))
        if not 0 <= active_stage < DPI_STAGES:
            raise ValueError('active_stage must be 0-4')
        _check_slot(slot)
        return cls(slot=slot, dpi_x=[int(v) for v in stages], active_stage=active_stage)

    def to_bytes(self):
        _check_slot(self.slot)
        p = bytearray(PROFILE_BLOCK_LEN)
        p[0] = 0x06
        p[1] = 0x4E
        p[2] = self.slot
        p[3:5] = self.bytes3_4
        p[5] = self.byte5
        p[6] = self.active_stage
        ys = self.dpi_y if self.dpi_y is not None else self.dpi_x
        for i in range(DPI_STAGES):
            struct.pack_into('<H', p, 7 + i * 2, self.dpi_x[i])
            struct.pack_into('<H', p, 17 + i * 2, ys[i])
        p[27:36] = self.mid
        p[36:71] = self.leds
        p[71:73] = bytes(self.tail[:2])
        p[73] = self.color[0] & 0xFF
        p[74] = self.color[1] & 0xFF
        return bytes(p)

    def pages(self):
        return split_pages(self.to_bytes(), PROFILE_PAGES)

    def commit_color_b(self):
        """Byte 5 of the commit packet — the profile colour's B channel, as Swarm sends it."""
        return self.color[2] & 0xFF

    def commit_checksum(self):
        """sum16 over the 75-byte block PLUS the colour-B byte (76 bytes), exactly as Swarm's .dat
        exports store it and its wire commit computes it. The old form summed 75 bytes with 0xff in the
        packet, which the mouse rejects."""
        return checksum16(self.to_bytes() + bytes([self.commit_color_b()]))

    @classmethod
    def parse(cls, data):
        data = bytes(data)
        if len(data) != PROFILE_BLOCK_LEN:
            raise ValueError('profile block must be %d bytes, got %d' % (PROFILE_BLOCK_LEN, len(data)))
        xs = [struct.unpack_from('<H', data, 7 + i * 2)[0] for i in range(DPI_STAGES)]
        ys = [struct.unpack_from('<H', data, 17 + i * 2)[0] for i in range(DPI_STAGES)]
        return cls(slot=data[2], dpi_x=xs, dpi_y=ys, active_stage=data[6], byte5=data[5],
                   mid=data[27:36], leds=data[36:71], tail=data[71:75], bytes3_4=data[3:5],
                   color=(data[73], data[74], 0x00))  # B is not in the 75-byte block; set it explicitly
