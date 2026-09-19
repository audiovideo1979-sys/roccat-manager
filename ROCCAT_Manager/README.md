# ROCCAT Manager — Kone XP Air

Profile manager for the Kone XP Air that writes to the mouse without opening Swarm II.

## First time
1. Double-click `INSTALL_AND_RUN.bat` (installs `flask frida hidapi`, starts the server, opens the browser).
2. Leave Swarm II running in the tray for now — the default transport goes through it. Once
   `tools/ab_test_buttons.py` shows the direct handle works, pick **Direct** in the sidebar and Swarm II
   is no longer needed.

## Daily use
- `Launch.bat` → http://localhost:5555
- Left column: **Onboard Profiles** 1–5 (what is on the mouse for this boot) and **Stored Profiles**
  (the library). Drag a stored profile onto a slot to assign it.
- Click a slot → that slot's profile is written to the mouse and the mouse switches to it (about 15 s).
- **Push to Mouse** writes the selected stored profile to the slot(s) it is assigned to.
- **Push all 5 slots** writes every assigned slot.
- Edit DPI and buttons in the editor; changes autosave to `profiles/stored.json`. Buttons with no known
  wire code are kept as they were on the mouse and reported in the toast.
- Boot tabs (Gaming / Work) keep separate slot assignments; the mouse only holds one set at a time.

## Importing what Swarm II has
`POST /api/import-dat` with a `.dat` export (or `{"source": "onboard"}` for the live container in
`%APPDATA%\Turtle Beach\Swarm II\Setting`) creates stored profiles from Swarm's own data.

## Troubleshooting
- "Swarm II not running" → start it (tray) or switch Transport to Direct.
- "another mouse operation is still running" → wait; pushes are serialised.
- Frida "access denied" → run the launcher as Administrator.
- See `RUN_ON_PC.md` and `HANDOFF.md` for the diagnostics.
