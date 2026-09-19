# Run sheet — settle the direct-write question on the Windows PC

Everything below runs from the `roccat-manager/` folder of the `claude/roccat-swarm-integration-e5coz3`
branch of EOS-consumables-builder. Python must be the 64-bit install you used for `roccat_write.py`.

```bat
cd /d "<your EOS-consumables-builder clone>"
git fetch origin claude/roccat-swarm-integration-e5coz3
git checkout claude/roccat-swarm-integration-e5coz3
cd roccat-manager
pip install frida hidapi flask pytest
python -m pytest -q tests
```
Expected: `89 passed`. That proves the codec reproduces the captured working packets on this machine.

## 1. Which collection does Swarm II really write through?  (Swarm II running, mouse connected)
```bat
python tools/diag_swarm_handle.py
```
Paste the whole output. The interesting lines are the chosen handle's `vid/pid/usage_page/usage/
feature_report_len` and the list of our vendor's collections underneath. If Swarm's handle is NOT
pid 0x5017 / usage page 0xff03, copy that collection's path and use it as `--path` below.

## 2. A/B test: same bytes, different handles  (about 1 minute per variant, interactive)
```bat
python tools/ab_test_buttons.py
```
It writes the factory button layout with thumb button 12 toggled between Insert and Delete, through:
A Frida (Swarm's handle) → B our handle with Swarm running → C our handle with Swarm killed →
D C + the receiver init sequence from the SignalRGB plugin → E C with the `.dat`-style header →
F C + the 0x49 commit. After each write it asks you to press button 12 in Notepad and type what happened.

Notes
- Keep your hands off the mouse buttons while a variant is writing (it takes 6-10 s).
- Variants C-F kill Swarm II; start it again before re-running A or B (`--only A`).
- The test overwrites the ACTIVE onboard slot's buttons. When you are done, push your real profile
  back from the app (or from Swarm II). Your DPI is not touched.
- If Frida says "access denied" when attaching, run the terminal as Administrator.

## 3. Optional: what the mouse answers when asked to read pages back
```bat
python tools/dump_mouse_pages.py --transport frida
python tools/dump_mouse_pages.py --transport direct --kill-swarm
```
Paste the `concatenated answers` lines. If they contain the button block, profiles can be read
straight from the mouse instead of from Swarm's memory.

Send back: the diag output, the A/B summary (letters + what button 12 did), and any error text.

## 4. Capture Swarm's DPI write (to fix DPI-set-in-app doing nothing)
Our own 0x46 profile write is rejected by the mouse, and we have no capture of how Swarm writes DPI.
This records it:
```bat
python tools/capture_swarm_dpi.py
```
1. Open **Swarm II** first (so it owns the mouse).
2. Run the command above — it prints `hooked KONE_XP_AIR.dll ...`.
3. In Swarm II, change the **DPI** to a distinctive value (e.g. 800 → 3000) and click apply/save.
4. Watch the `SEND` / `GET` lines scroll, then press ENTER to stop.
5. Copy ALL the `SEND`/`GET` lines that appeared when you changed the DPI and send them back.

If nothing prints when you change the DPI, re-run with
`python tools/capture_swarm_dpi.py --process "Turtle Beach Device Service.exe"`.
Run the terminal as Administrator if attaching fails.
