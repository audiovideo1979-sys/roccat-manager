# ROCCAT Manager — Claude Code Instructions

## On session start
1. Read `HANDOFF.md` (state, open questions, the protocol reference).
2. `CHANGELOG.txt` has the latest @N — continue from there.
3. Run `python -m pytest -q tests` — 88 tests, no hardware needed. Keep it green.

## What it is
Web UI (Flask, port 5555) that manages the five onboard profiles of a ROCCAT Kone XP Air (DPI, button
layout, Easy-Shift layer) without opening Turtle Beach Swarm II. Windows 11, dual boot; the mouse is on
its USB receiver (VID 0x10F5, receiver PID 0x5017).

## Layout
- `kone_xp_air/` — the protocol. `protocol.py` packets + blocks + checksums, `actions.py` names <-> wire
  codes, `sequences.py` op lists that reproduce the captured Swarm traffic, `transport.py`
  (RecordingTransport for tests, DirectHidTransport, FridaTransport + `frida_executor.js`),
  `session.py` (`KoneXPAir`), `datfile.py` (.dat exports).
- `ROCCAT_Manager/server.py` — Flask API; `templates/index.html` — single-file SPA;
  `profiles/stored.json` (profile library), `profiles/slots.json` (boot1/boot2 -> 5 profile ids),
  `profiles/mouse_config.json` (transport + protocol options).
- `tools/` — Windows-only diagnostics (see `RUN_ON_PC.md`). `tests/` — pytest.
- Root `*.py` / `*.js` from March–April 2026 are experiment history (superseded, kept for reference).
  `ROCCAT_Manager/SWARM_II_DAT_FORMAT.py`, `profile_mgr_format.py`, `dat_export.py`, `swarm_ini.py`,
  `automation/` are legacy and not on the push path.

## Run
- `ROCCAT_Manager/Launch.bat` or `python ROCCAT_Manager/server.py` (opens http://localhost:5555).
- Transport "Frida" (default) needs Swarm II running (tray is fine). "Direct" needs nothing but the
  receiver — switch to it once `tools/ab_test_buttons.py` shows it works.
- Deps: `pip install flask frida hidapi pytest`. 64-bit Python (matches `KONE_XP_AIR.dll`).

## REST API (port 5555)
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/stored`, PUT/DELETE `/api/stored/{id}`, POST `/api/stored/{id}/duplicate` | profile library |
| GET | `/api/slots/{boot}`, PUT `/api/slots/{boot}/{n}` | slot assignments |
| POST | `/api/push-slot` `{boot_id, slot 1-5}` | write that slot's profile, leave the mouse on it |
| POST | `/api/import-to-mouse` `{boot_id[, profile_id][, restore_slot]}` | push one profile to its slot(s), or every assigned slot |
| POST | `/api/switch-profile/{0-4}` | switch only |
| GET/PUT | `/api/mouse/config`, GET `/api/mouse/status`, GET `/api/mouse/log` | transport + options, presence, last HID log |
| POST | `/api/mouse/read-pages` `{cmd, flag}` | raw page read-back (diagnostics) |
| POST | `/api/import-dat` (file or `{source:'onboard'}`) | stored profiles from Swarm exports |
| GET | `/api/export/{id}`, `/api/export-all/{boot}` | legacy .dat export (zero checksums) |
| GET | `/api/actions` | names the encoder supports |

## Rules
- Every packet or block change gets a test that pins it to a capture (`tests/test_sequences.py`,
  `tests/test_datfile.py`). Never "fix" bytes by reasoning alone — the April session lost days that way.
- Direct and Frida transports must execute the same op list; add behaviour in `sequences.py`, not in a
  transport.
- Update `CHANGELOG.txt` (next @N) and `HANDOFF.md` at the end of every session. No secrets, no .env.
- Hardware findings go into HANDOFF.md "What is established" only after they were seen on the mouse.

## Protocol in one paragraph
Feature report 0x06, 30 bytes, byte 1 = 0x01 (mouse via receiver). 0x46 = profile block (75 B, 3 pages,
DPI), 0x47 = button block (125 B, 5 pages: 3-byte header, 30 entries `[00, key, code|mods, type]`,
sum16), 0x45 select + 0x4e activate = profile switch, `06 01 44 07` + get_feature after every write.
Full tables in HANDOFF.md and `kone_xp_air/protocol.py`.

## Out of scope (per Steve)
RGB lighting (0x4d frames), macros, Swarm II UI automation.
