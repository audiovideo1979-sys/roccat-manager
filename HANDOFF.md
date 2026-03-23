# ROCCAT Manager Full — Handoff

## Session: 2026-03-23 (Boot 1 — Work drive)

### What was done this session
- Extensive HID protocol reverse-engineering attempt to bypass SWARM II
- Built `hid_spy.py` — real-time HID report monitor that captured SWARM II's profile cycling
- Discovered SWARM II communicates through the **dongle** (PID 0x5017), not directly to mouse
- Dongle report 0x06 state machine: 0x4D (idle) → 0x46 (transitioning) → 0x44 (data loaded)
- Mouse IF=1 (UP=0xFF00) accepts output writes — confirmed as the write channel
- Tried every write method: hidapi feature/output reports, raw USB control transfers (pyusb), direct Windows HID API (ctypes), frida hooking — none changed actual mouse DPI
- Installed Wireshark 4.6.4 (USBPcap driver present but non-functional on this boot)
- Installed frida for API hooking (hooks attach but can't capture data — JS engine issues)
- Conclusion: need proper USB packet capture (USBPcap/Wireshark) from Boot 2 to decode the actual write protocol

### Current State
**~90% complete.** Core app fully functional. Direct HID bypass is the remaining challenge.

Two approaches to push profiles to mouse:
1. **Working:** .dat file write + SWARM II restart (already in server.py)
2. **Not working yet:** Direct HID protocol (needs USB capture from Boot 2)

### Files Modified/Created This Session
- `hid_spy.py` — Real-time HID report monitor (MOST USEFUL — keep this)
- `hid_dongle_write.py` — Dongle write test
- `hid_brute_write.py` — Brute-force write test on all interfaces
- `ctypes_hid_write.py` — Direct Windows HID API test
- `usb_control_test.py` — Raw USB control transfer test
- `frida_hid_hook.py`, `frida_hook2.py`, `frida_ntdll.py` — Frida API hooking attempts
- `frida_find_dlls.py` — DLL enumeration for SWARM II processes
- `capture_swarm.py`, `capture_elevated.ps1`, `etw_usb_capture.ps1` — USB capture scripts
- `find_usb_iface.py`, `find_usb_iface2.py` — USBPcap interface detection

### Last Deploy Ref
@2 — HID protocol research + capture tools

### Pending / Next Tasks
1. **On Boot 2:** Run USBPcap/Wireshark capture while changing DPI in SWARM II — decode the exact USB write protocol
2. **pywinauto calibration** — run inspector to get real SWARM II control names (alternative to HID bypass)
3. **Configure Boot 2 profiles** with real data
4. **Test .dat file import workflow** end-to-end

### Known Bugs / Issues
- USBPcap filter driver not functional on Boot 1 (installed but "Couldn't open device")
- Frida can't hook hid.dll exports in SWARM II (TypeError: not a function)
- Port inconsistency: README says 5000, server.py uses 5555

### Key Decisions Made
- Direct HID protocol bypass deferred to Boot 2 (needs USB capture)
- .dat file write + SWARM restart is the working approach for now
- Dongle (PID 0x5017) is the command gateway, not the mouse directly
- Mouse IF=1 (0xFF00) is the write channel, but correct command format unknown

### HID Protocol Research Summary
**Devices:**
- Dongle: VID 0x10F5, PID 0x5017, 3 interfaces (all have IN+OUT endpoints)
- Mouse: VID 0x10F5, PID 0x5019, 3 interfaces (IF=1 has OUT endpoint)

**Interfaces (mouse):**
- IF=0 UP=0xFF01 — Main config (readable reports 0x01-0x08, DPI/LED/button data)
- IF=1 UP=0xFF00 — Write channel (accepts output reports, no readable feature reports)
- IF=2 UP=0xFF02 — Unknown (no readable reports, rejects output writes)

**Report layout (mouse 0xFF01):**
- Report 0x01: Active profile DPI + LED color per stage
- Report 0x02: Button/keybind config
- Report 0x03: LED zone colors (4 zones × RGB)
- Report 0x04/0x05: More LED data
- Report 0x06: DPI stage config (5 stages, stable)
- Report 0x08: Similar to 0x06

**Kone Pro protocol (same generation, documented):**
- Uses USB control transfers: SET_REPORT (0x21/0x09) with wValue=0x0300|report_id
- Report 0x04: profile select [0x04, idx, 0x80, 0x00]
- Report 0x06: 69-byte settings blob (DPI as LE16×50, checksum in last 2 bytes)
- Polling status via report 0x04: 1=ready, 3=busy
