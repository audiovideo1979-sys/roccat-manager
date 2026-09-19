"""
High-level operations on the mouse, transport-agnostic.

    mouse = KoneXPAir(FridaTransport())        # or DirectHidTransport(), RecordingTransport()
    mouse.switch_profile(2)
    mouse.write_dpi(2, 1600)
    mouse.write_buttons(2, keybinds, easy_shift)
    mouse.push_slots([(0, profile_a), (1, profile_b)], restore_slot=0)
"""
from . import protocol as P
from . import sequences as S
from .transport import OpResult, format_results


class KoneXPAir:
    def __init__(self, transport, activate_b5=0x01, header_mode='zero', pre_switch=True, preamble=False, log=None):
        """
        activate_b5   byte 5 of the 0x4e activate packet: 0x01 (working replay, SignalRGB) or 'slot'
        header_mode   'zero' = the 3 zero header bytes of the working capture; 'dat' = experimental
                      07 7d 00 header (Swarm's .dat / in-memory form), for the A/B tool
        pre_switch    switch the mouse to the target slot before writing (the block carries no slot,
                      so it lands in the active profile; the DPI block's byte 2 may or may not be one)
        preamble      send the SignalRGB receiver-init sequence once at the start of every job
        """
        self.transport = transport
        self.activate_b5 = activate_b5
        self.header_mode = header_mode
        self.pre_switch = pre_switch
        self.preamble = preamble
        self.log = log or (lambda m: None)
        self.last_results = []
        self._preamble_sent = False

    # ---- primitives ----
    def _run(self, ops):
        if self.preamble and not self._preamble_sent:
            ops = S.receiver_init() + list(ops)
            self._preamble_sent = True
        self.last_results = self.transport.run(ops)
        self.log(format_results(self.last_results))
        failed = [r for r in self.last_results if r.op.kind in ('send', 'get') and not r.ok]
        if failed:
            first = failed[0]
            raise RuntimeError('%d of %d HID operations failed; first: %s (rc=%s %s)' % (
                len(failed), len(self.last_results), first.op.label or first.op.kind, first.rc, first.error))
        return self.last_results

    def _b5(self, slot):
        return slot if self.activate_b5 == 'slot' else self.activate_b5

    def switch_profile(self, slot):
        return self._run(S.switch_profile(slot, self._b5(slot)))

    def write_dpi(self, slot, dpi, active_stage=0):
        block = P.ProfileBlock.from_dpi(slot, dpi, active_stage)
        self._run(S.write_profile_block(block.to_bytes()))
        return block

    def build_button_block(self, slot, keybinds, easy_shift, base=None):
        header = P.dat_header(0x00) if self.header_mode == 'dat' else P.ZERO_HEADER
        return P.ButtonBlock.from_bindings(keybinds, easy_shift, base=base, header=header)

    def write_buttons(self, slot, keybinds, easy_shift, base=None, scratch=None):
        block = self.build_button_block(slot, keybinds, easy_shift, base)
        ops = S.write_buttons(block.to_bytes(), slot=slot, scratch=scratch, pre_switch=self.pre_switch,
                              activate_b5=self.activate_b5)
        self._run(ops)
        return block

    def read_raw_pages(self, cmd=P.CMD_PROFILE, flag=0x01, count=4):
        """Raw get_feature_report buffers after each page read; decoding them is still open work."""
        results = self._run(S.read_pages(cmd, flag, count))
        return [r.response for r in results if r.op.kind == 'get']

    # ---- profile dicts as stored by server.py ----
    def push_profile(self, slot, profile, base=None):
        """Switch the mouse to `slot`, write the profile's DPI block and button block there, then run
        the activate tail of the working replay (scratch slot and back). Leaves the mouse on `slot`."""
        summary = {'slot': slot, 'name': profile.get('name', ''), 'dpi': None, 'buttons': False, 'unsupported': []}
        ops = []
        if self.pre_switch:
            ops += S.switch_profile(slot, self._b5(slot)) + [S.sleep(0.3)]
        dpi = profile.get('dpi')
        if dpi:
            stages = dpi.get('stages', 800) if isinstance(dpi, dict) else dpi
            active = dpi.get('active_stage', 0) if isinstance(dpi, dict) else 0
            dblock = P.ProfileBlock.from_dpi(slot, stages, active)
            ops += S.write_profile_block(dblock.to_bytes()) + [S.sleep(0.1)]
            summary['dpi'] = dblock.dpi_x
        keybinds = profile.get('keybinds') or {}
        easy_shift = profile.get('easy_shift') or {}
        if keybinds or easy_shift:
            bblock = self.build_button_block(slot, keybinds, easy_shift, base)
            ops += S.write_buttons(bblock.to_bytes(), slot=slot, pre_switch=False, activate_b5=self.activate_b5)
            summary['buttons'] = True
            summary['unsupported'] = ['%s/%s: %r' % u for u in bblock.unsupported]
        if ops:
            self._run(ops)
        return summary

    def push_slots(self, assignments, restore_slot=None):
        """assignments: [(slot, profile_dict), ...]. Ends on restore_slot if given."""
        out = []
        for slot, profile in assignments:
            out.append(self.push_profile(slot, profile))
        if restore_slot is not None:
            self.switch_profile(restore_slot)
        return out
