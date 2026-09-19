# ROCCAT Manager — Handoff

## Confirmed on hardware (2026-09-19, PC run)

- **DIRECT WRITES WORK.** A/B test, variant B (our own `DirectHidTransport` handle, backend=dll, Swarm
  II running): writing button 12 = key "M" through our own handle changed the physical button — pressing
  it typed `m`. Swarm II is NOT in the write path. This settles the April question: the "must use Swarm's
  handle" conclusion was the wrong-bytes problem, not the handle. **The app can run Transport = Direct and
  drop the Frida/Swarm dependency for writes.** (Variant A / Frida read "no change" in the same run, most
  likely a mis-press during setup; irrelevant, B is the target path.)
- Reliability note: 4 of 131 feature reports returned rc=-1 (transient) yet the block still landed. Added
  an automatic send retry to `DirectHidTransport` so pushes are solid.
- `pytest` passes on the PC (Python 3.12, frida 17.9.1, hidapi 0.15.0).
- `diag_swarm_handle.py`: Swarm II opens and writes through
  `\\?\HID#VID_10F5&PID_5017&MI_02&Col03#...` — the dongle, interface 2, collection 3,
  **usage page 0xFF03, usage 0xFF00**, product "Kone XP Air Dongle". It opens that same path twice
  (one handle streams 0x4d lighting, one carries the 06 00 00 04/05 receiver pings). The receiver's
  HID collection list has exactly one 0xFF03 collection — that same Col03 path.
- **This is the collection `DirectHidTransport` / `find_dongle_path` open by default** (PID 0x5017,
  usage page 0xFF03). So Swarm's handle is not on a private collection; a fresh handle to the same
  path should behave the same. Strong evidence the April "must use Swarm's handle" conclusion was the
  wrong-bytes problem, not the handle. The direct-vs-Frida button A/B test (variant B) is the empirical
  confirmation — pending.
- Bug fixed live: frida 17 removed `frida.enumerate_processes()` (now on the device object).
- Modifiers on mouse buttons (Ctrl/Alt for AutoCAD) can leave a modifier stuck "held" in Windows when
  a profile switch drops the button's key-up — the keyboard then acts dead. Fix: `kone_xp_air/winput.py`
  `release_modifiers()` (ctypes SendInput, no-op off Windows) is called after every mouse job in
  `run_mouse_job`, and a "Release stuck keys" button (`POST /api/release-modifiers`, no mouse lock)
  clears it on demand. The feature stays; it's just made safe.
  - Packaging: `kone_xp_air.winput` is in `roccat_manager.spec` `hiddenimports`; `server.py` imports it
    at load, so without it the windowed exe closes on launch (ModuleNotFoundError, caught to startup.log).
- Push/switch is a ~15 s onboard-memory write and two must never overlap (an overlapping write can
  corrupt a profile or strand a modifier). The UI now shows a "Writing to the mouse..." overlay
  (`#busy-overlay`, `withMouseLock()` in `index.html`) for the duration and refuses a second mouse
  operation until it finishes. Server-side `MOUSE_LOCK` already serialised the HID handle; this is the
  matching UI lock the user asked for ("lock the mouse for a couple of secs to load it").
- Active-profile memory: the mouse keeps its active onboard slot across power cycles, but the app only
  knew it after a push/switch, so a fresh launch highlighted nothing. The last slot set is now persisted
  (`slots.json` key `active_slot`, written in `run_mouse_job`, read by `GET /api/slots/{boot}` →
  `activeSlot` on load). It is "what this app last set", not a read-back from the mouse — a decoded
  read-back of the mouse's current profile is still open (page reads are undecoded). Self-corrects on
  the next push/switch.
- Windows key on a button — **not possible on this mouse (settled on hardware 2026-09-19).** Bare
  Ctrl/Alt/Shift fire (own scancode 00 e0/e1/e2 00 06), but a bare Windows/GUI key does nothing, tried
  both ways: as its own scancode (00 e3 00 06) and through the modifier byte (00 00 08 06). Swarm II
  never binds a lone Win either — every Win in the captures is Win+<key> (e.g. WWM.dat `00 0b 08 06`),
  so the firmware only honors the GUI key as a combo modifier. The bare "Win" option was removed from
  the button menu and the modifier-byte experiment reverted. For a Start-menu button use **Ctrl+Esc**
  (00 29 01 06); Win+<key> shortcuts (Show Desktop = Win+D, Snipping Tool = Win+Shift+S) work and are
  already offered. Escape is now a first-class dropdown option (00 29 00 06) — handy for AutoCAD.
- **DPI set in the app did nothing — ROOT-CAUSED & FIXED (pending hardware re-verify).** The "Read
  back" diagnostic confirmed the mouse **rejects the 0x46 profile block** (pushed DPI 2700, read-back
  did not contain `8c 0a`). Comparing our block to Swarm's own `.dat` exports (WWM/Main Test/Grounded,
  decoded by datfile.py) showed ours was wrong, NOT a mystery — no capture needed:
  - byte 5: we sent `0x1f`, Swarm sends **`0x02`** (all three .dat agree).
  - bytes 31-32: we sent `06 ff`, Swarm sends **`01 00`**.
  - commit: we sent `06 01 46 06 03 ff <cs16 over 75B>`; Swarm sends `06 01 46 06 03 <colourB>
    <cs16 over 76B = block + colourB>`. Verified: cs16(block[:75]+[colourB]) == the .dat's stored cs
    for WWM (17ef), Main Test (17ad), Grounded (166e).
  The old bytes came from `roccat_write.build_profile`, assumed to change DPI in April but never
  actually verified. `ProfileBlock` / `profile_commit_packet` / `sequences.write_profile_block` now
  reproduce Swarm's real block byte-for-byte, pinned in `tests/test_datfile.py`
  (`test_profile_block_reproduces_swarm_main_blocks`) and `tests/test_protocol.py` against the .dat.
  DPI X is raw LE16 (correct); DPI Y is set = X.
  **Content fix was not enough — the write SEQUENCE was also wrong.** After rebuild+push, nothing
  changed on the mouse (no DPI, no pink). `write_profile_block` selected each page with **flag 0x01**
  (the READ flag — `read_pages` and profile-switch reads use 0x01), unlike the proven button write,
  which selects 0x47 pages with **flag 0x00** (`inject_full.js`). Changed the profile page-select flag
  to **0x00** (WRITE). **Verify on hardware:** set DPI 3000, push → pointer speed should change (the
  real oracle; the Read-back decode is unproven). If it STILL doesn't apply, we have no captured 0x46
  write — capture Swarm changing DPI (Frida logger on hid_send/get_feature_report, 0x4d filter off) and
  match its exact page/commit/activation sequence. Do NOT keep guessing.
- **RGB off — still open, but unblocked.** The LEDs live in the same 0x46 block (7×5 entries at 36-70,
  hardcoded pink `14 ff 00 48 ff`), so once the block is accepted the app can set them. We have no
  Swarm "lighting off" export, and the LED-entry layout has two conflicting readings
  ([bright,R,G,B,alpha] vs [index,R,G,B,bright]), so the exact off bytes still need a capture or a
  careful hardware A/B — do NOT guess. Interim: **Toggle RGB** button action (00 00 0b 08, in the
  working 0x47 block) turns lighting off with a press today. Note: with the DPI fix the accepted block
  now also asserts the pink LEDs, so a push will set the mouse pink until lighting-off lands.

## Where things stand (2026-09-19)

**Working today:** with Swarm II running in the tray, the app writes DPI, button layouts and profile
switches to the Kone XP Air through Swarm's own HID handle (Frida injection). That is the April 2026
result and it still holds.

**New this session** (cloud session, no mouse attached — nothing below was run against hardware):

- The protocol was re-derived from the repo's own captures and from Swarm II's `.dat` exports, and put
  in one hardware-independent package, `kone_xp_air/`, with 88 tests that pin every packet builder to
  the captured traffic. Decoding Swarm's exports and re-encoding them reproduces Swarm's bytes exactly,
  checksums included.
- The app (`ROCCAT_Manager/server.py` + `index.html`) runs on that package. Pushes now target the slot
  you click (the old push wrote the same DPI to all five slots and the button block with no slot at
  all — which slot received it was never recorded), and a transport switch in the sidebar picks Frida
  or a plain HID handle.
- Three Windows tools (`tools/`) exist to settle the one question that matters: does a plain handle work
  for button writes when it sends *exactly* what Swarm sends? See `RUN_ON_PC.md`.

## Why direct button writes "did not work" in April (from the code; not yet confirmed on the mouse)

Commit f90cb9c concluded "opening a new handle doesn't work — must use Swarm's existing handle". The two
experiments it compared differed in far more than the handle:

| | direct path (`roccat_write.py`) | working path (`inject_full.js`, Frida replay that reports itself as the exact capture) |
|---|---|---|
| block header | `07 7d <slot> 00 00` (Swarm's memory/.dat form) | `00 00 00 00 00` |
| after the 5 pages | `06 01 49 06 03 05 cs cs` "commit" — appears in no capture | nothing |
| activation | none | read 4 profile pages, 0x45 select + 0x4e activate to another slot, read again, back |
| Swarm II / Device Service | killed first | alive |
| button data | a different, mis-aligned keybind set | byte-exact capture |

Nobody ever sent the working bytes through a plain handle. `tools/ab_test_buttons.py` does exactly that,
in six variants (A Frida, B plain handle with Swarm alive, C Swarm killed, D + receiver init sequence from
the SignalRGB plugin, E + `.dat`-style header, F + 0x49 commit).

Bugs found on the way (all fixed in `kone_xp_air/`, the old files are left untouched):

- `frida_inject.py` wrote the right-button code at offset 8; the record starts at 7 and the code sits at
  9, so every push corrupted button 2's record.
- `frida_inject.py` push wrote one DPI to all five slots (and, because it patched byte 7 of every page,
  clobbered two profile bytes on pages 1-2), wrote the button block with no slot, then always ended on
  slot 0; the UI's "Push" ignored the slot you clicked.
- `frida_inject.py` silently turned unknown actions (`Hotkey Shift`, `Hotkey Del`, `Delete`, `Page Up`,
  `Ctrl+C` — all used in stored profiles) into Disabled.
- `server.py` imported a function that never existed (`inject_buttons`), so `/api/write-buttons` always
  failed; the page-load "live profiles" read overwrote stored keybinds with the mis-decoded heap copy.
- The stored template in `roccat_write.py` carried a checksum that did not match its own bytes.

## What is established (each line is covered by a test)

Transport: HID feature report ID 0x06, 30 bytes, to the receiver's vendor collection (dongle PID 0x5017,
usage page 0xFF03 — the collection the working DPI writes used). Byte 1: 0x01 = mouse, 0x00 = receiver.

| command | packet | notes |
|---|---|---|
| apply / handshake | `06 01 44 07`, 100 ms, `get_feature_report(0x06)`, 50 ms | after every write; response never decoded |
| select page | `06 01 46/47 06 02 <page> <flag>` | flag 01 for profile pages, 00 for button pages |
| write page | `06 01 46/47 06 19 <25 bytes>` | |
| read page | `06 01 46/47 07` then get_feature_report | answers never decoded — `tools/dump_mouse_pages.py` |
| profile select | `06 01 45 06 02 <slot> 05` | |
| activate | `06 01 4e 06 04 01 01 01 ff` | byte 5 was the slot in `roccat_write.py`, 01 in the capture and in SignalRGB |
| profile commit | `06 01 46 06 03 ff <sum16 of the 75 bytes>` | Swarm sends the profile colour's B there and sums 76 bytes; the mouse accepts the `ff` form |
| 0x49 | `06 01 49 06 03 05 cs cs` | seen after profile writes in the SignalRGB capture; not in the button capture |

Button block (command 0x47, 125 bytes = 5 pages): 3-byte header (`00 00 00` on the wire; `07 7d <flag>` in
`.dat` files and Swarm's memory — the flag is not the slot), 30 four-byte entries at offset 3+4k, 16-bit
little-endian sum of bytes 0..122 at the end. Entries k=0..14 are the 15 inputs in this order: left,
right, middle, wheel up, wheel down, side 10, side 11, top 8 (DPI up), top 9 (DPI down), thumb 12, thumb
13, tilt, tilt, Easy-Shift (14), profile switch (15, underside). k=15..29 are the same inputs on the
Easy-Shift layer. Entry encoding `[00, key, code|modbits, type]`:

| type | meaning | codes seen |
|---|---|---|
| 01 | mouse | 01 left, 02 right, 03 middle, 05 browser fwd, 06 browser back, 07/08 tilt, 09/0a wheel up/down (04 double-click from the INI table, unseen) |
| 02 | DPI | 02 up, 03 down (01/04 cycle from the INI table, unseen) |
| 03 | media | 04 play/pause, 07/08 volume up/down, 02/03 prev/next track |
| 06 | keyboard | key = HID usage, modbits 01 LCtrl 02 LShift 04 LAlt 08 LWin; a lone modifier is its own usage (`e1`) with modbits 0 |
| 08 | system | 01 profile cycle, 0b toggle RGB (Easy-Shift default of button 15) |
| 0a | Easy-Shift | 01 |
| 04 | unknown Swarm function (WWM.dat, Grounded.dat) | kept verbatim as `Raw 00 00 xx 04` |

Profile block (command 0x46, 75 bytes = 3 pages): `06 4e <slot> 06 06 1f <active stage>`, 5 x LE16 DPI,
5 x LE16 second DPI set, 9 config bytes, 7 x 5 LED bytes, `01 64 ff ff`. This is the `roccat_write.py`
form proven to change DPI. Swarm's `.dat` block is the same 75 bytes + colour B + sum16(0..75); the app
keeps the proven form. Byte 2 may be a flag rather than the slot (WWM.dat, in slot 4, has 01 there), which
is why every push now switches to the slot first.

`.dat` exports: `00 00 00 7d` + the 125-byte button block, `00 00 00 4e` + the 78-byte profile block
(`kone_xp_air/datfile.py`; the ones this project exported earlier carry zero checksums).

## Still open — in the order worth doing

1. **Run `RUN_ON_PC.md`** (diag + A/B). Then:
   - B works: set Transport to "Direct" in the sidebar; Swarm II is no longer needed for the app.
   - only C/D work: direct works but Swarm must be closed — add a "kill Swarm first" option to
     `open_mouse()` in `server.py` (`kone_xp_air.transport.kill_swarm`).
   - only A works and the diag shows Swarm on a different collection: put that path in
     `profiles/mouse_config.json` (`"path"`), rerun B.
   - only A works on the same collection: stay on Frida (it works) and record it as a real finding.
2. `tools/dump_mouse_pages.py`: decode the read-back so profiles come from the mouse, not Swarm's heap
   (the old `/api/profiles/live` is gone; nothing reads the mouse today).
3. Ten-second checks after a push: tilt left/right are named after `roccat_write.py`'s table — assign
   something distinctive to "Tilt Left" and confirm the physical direction; the Easy-Shift media names
   follow the factory chart and the owner's Main Test export.
4. Persistence: after a direct push, put the mouse to sleep / re-pair and check the buttons survive.
   If not, variant F (0x49 commit) is the candidate.
5. Unknown wire codes: Mute (not offered any more), Swarm's type-0x04 functions, polling rate (byte 29
   in the SignalRGB capture, bytes 3-4 in Swarm's exports — not exposed in the UI).
6. Housekeeping: `swarm_ini.py` mis-decodes Qt's `\a \b \v` escapes (its 0x61/0x62/0x76 constants are
   artefacts); `SWARM_II_DAT_FORMAT.py` / `dat_export.py` carry a wrong action table and write zero
   checksums. Both are unused by the push path now; fix or delete when convenient.

## Files

- `kone_xp_air/` — `protocol.py` (packets, blocks, checksums), `actions.py` (names <-> codes),
  `sequences.py` (ordered op lists = the captured traffic), `transport.py` (recording / direct / Frida),
  `frida_executor.js` (runs an op list through Swarm's handle, identifies the handle), `session.py`
  (`KoneXPAir`: switch, write DPI, write buttons, push slots), `datfile.py` (.dat reader).
- `tools/` — `diag_swarm_handle.py`, `ab_test_buttons.py`, `dump_mouse_pages.py`.
- `tests/` — `python -m pytest -q tests` (no hardware, no Windows needed).
- `ROCCAT_Manager/server.py`, `templates/index.html`, `profiles/{stored,slots,mouse_config}.json`.
- Root-level experiment scripts from March/April are kept as history; `frida_inject.py` and
  `roccat_write.py` are superseded by the package.

## History

- 2026-03-22/23 (@1, @2): Flask app, `.dat` format, HID probing; nothing changed the mouse.
- 2026-04-10..12 (@3, reconstructed from git — never written up): direct DPI write and profile switch
  through `KONE_XP_AIR.dll`'s hidapi on the dongle (0xFF03); button writes over the same handle did not
  take; byte-exact replay through Swarm's handle via Frida did; heap-scan profile reader; Frida push
  wired into the app.
- 2026-09-19 (@4): this session, see above.

## Environment (unchanged)

Windows 11 dual boot; mouse VID 0x10F5, receiver PID 0x5017, mouse PID 0x5019; Swarm II at
`C:\Program Files\Turtle Beach Swarm II\` (`Data\Devices\KONE_XP_AIR\KONE_XP_AIR.dll` bundles the hidapi
the app calls); onboard container `%APPDATA%\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_Profile_Mgr.dat`.
Python deps: `flask frida hidapi` (+ `pytest`).
