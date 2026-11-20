# ROCCAT Manager

Set up the **ROCCAT Kone XP Air**'s buttons, DPI and its five onboard profiles from a simple Windows app,
without Turtle Beach Swarm II.

## Download

**[Download the latest version](https://github.com/audiovideo1979-sys/roccat-manager/releases/latest)**:
on that page, under **Assets**, click **ROCCAT.Manager.exe**.

It's a single program file with no installer. Save it anywhere you like (Documents, for example) and
double-click it.

- **Windows says "Windows protected your PC"?** The program isn't code-signed, so Windows asks the first
  time. Click **More info**, then **Run anyway**.
- Right-click its taskbar icon → **Pin to taskbar** to find it again.

## What you need

- Windows 10 or 11 (64-bit). The app window uses Microsoft Edge WebView2, which Windows 11 already has.
- A **ROCCAT Kone XP Air** connected through its **2.4 GHz USB receiver**. The app only talks to that
  receiver; other mice are not supported and are left alone.
- Swarm II is **not** needed. If it is installed, that's fine too.

## How to use it

1. **Stored Profiles** (left) is your library. The app starts with a few example profiles: click one to
   change its DPI and what each button does, or make a new one. Changes save by themselves.
2. **Onboard Profiles** are the mouse's five memory slots. Drag a stored profile onto a slot.
3. Click **Push to Mouse** for the selected slot, or **Push all 5 slots**. Writing takes about 15 seconds;
   leave the mouse alone until "Writing to the mouse..." disappears.
4. **Gaming / Work** at the top keeps two different sets of five slots, so you can switch between them.

If a keyboard key ever seems stuck after a push (for example Ctrl or Alt), click **Release stuck keys**.

Your profiles are saved on your PC in `%APPDATA%\ROCCAT Manager\profiles`. The line at the bottom left of the
app says where.

## Good to know

- Not made by or affiliated with ROCCAT or Turtle Beach. It writes the mouse's onboard memory the same way
  Swarm II does; use it at your own risk.
- Lighting (RGB) and macros are not supported.
- Running two Windows installs on one PC and want the same profiles on both? See
  [SYNC_SETUP.md](SYNC_SETUP.md) (shares them through Google Drive).

## For developers

Python 3.12 (64-bit) on Windows: `build.bat` builds `dist\ROCCAT Manager.exe`; `python -m pytest -q tests`
runs the tests (no mouse needed). How the mouse protocol works is in [HANDOFF.md](HANDOFF.md) and
[CLAUDE.md](CLAUDE.md). To publish a new version: **Actions → Build Windows app → Run workflow**, type the
version (e.g. `v1.0.1`) in "Release to publish", run it. GitHub runs the tests, builds the program on Windows
and attaches it to a new release (`.github/workflows/release.yml`; pushing a `v*` tag does the same).
