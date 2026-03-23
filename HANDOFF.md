# ROCCAT Manager Full — Handoff

## Session: 2026-03-23 — Initial project registration

### What was done this session
- Project was built in a prior session (with Sasha on claude.ai) — core app is complete
- Registered into the standard Projects Folder workflow this session
- Created CLAUDE.md, HANDOFF.md, CHANGELOG.txt

### Current State
**~90% complete.** Core app fully functional:
- Web UI (dark theme SPA) — complete
- Flask REST API — complete
- Profile data model (boot1/boot2 JSON) — complete, Boot 1 has 5 real profiles
- Binary .dat format reverse-engineered and implemented — complete
- .dat export/import to SWARM II onboard file — complete
- Launcher scripts (INSTALL_AND_RUN.bat, Launch.bat) — complete

**Boot 1 Profiles (configured):**
1. Main Test — #7F77DD, 950 DPI
2. Grounded — configured
3. WWM — configured
4. Default 03 — configured
5. Default 05 — configured

**Boot 2 Profiles:** All empty/template — not yet configured

### Files Modified This Session
- `CLAUDE.md` — created (new)
- `HANDOFF.md` — created (new)
- `CHANGELOG.txt` — created (new)

### Last Deploy Ref
@1 — Initial project registration (no code changes yet)

### Pending / Next Tasks
1. **⚠️ BLOCKING: pywinauto calibration** — run inspector to get real SWARM II control names
   - `pip install pywinauto pywin32`
   - Open SWARM II, navigate to Kone XP Air screen
   - Run: `python ROCCAT_Manager/automation/roccat_automation.py`
   - Read `inspector_output.txt` → update control names in `roccat_automation.py`
   - Test "Apply to mouse" on one profile
   - Test "Push all to SWARM II"
2. **Configure Boot 2 profiles** — set real names/DPI/keybinds for second Windows install
3. **Set up own GitHub repo** — currently sitting inside Consumables monorepo (EOS-consumables-builder)
4. **Test full workflow end-to-end** on Boot 1

### Known Bugs / Issues
- Port inconsistency: README says 5000, server.py uses 5555 — verify which is live
- HID direct communication (root hid_*.py files) is experimental, not integrated
- pywinauto control names are stubs — automation won't work until calibrated

### Key Decisions Made
- pywinauto approach chosen over direct HID protocol (more reliable; HID experiments moved to root as separate files)
- RGB lighting explicitly excluded from scope
- Easy Shift secondary layer editing deferred (JSON-only for now)
- Binary .dat format fully reverse-engineered as backup plan for direct write
- Boot 1 is source of truth; Boot 2 intentionally empty until second drive is set up
