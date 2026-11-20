# Running ROCCAT Manager on both Windows boots, synced via Google Drive

Goal: the same app **and** the same profiles on the Personal (gaming) boot and the Work boot.
Only one boot runs at a time (dual boot), so there are never simultaneous edits.

Both live in Google Drive, side by side:

| What | Drive folder |
|---|---|
| The program, `ROCCAT Manager.exe` | `My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full` |
| The profiles (`profiles\stored.json`, `slots.json`, `mouse_config.json`) | `My Drive\Claude Folder\Projects\Personal\ROCCAT Manager Data` |

**No setup per boot (since @7).** The app looks for `ROCCAT Manager Data` itself: next to the folder the
.exe runs from, then under `My Drive` on any drive letter Google Drive uses on that boot (G: first), or in
your user folder when Drive is in "mirror files" mode. No `setx`, no environment variable. The sidebar
shows which folder it is using:

- **"Profiles: shared through Google Drive"** (green) — synced, all good.
- **"Profiles: this PC only (...)"** (amber) — Google Drive wasn't running or the folder wasn't found.
  Start Google Drive, then reopen the app. Hover the line to see the exact folder.

The old `ROCCAT_MANAGER_DATA` variable still works and still wins if it is set.

---

## Personal boot — once (this is where the app is built)

1. Make sure **Google Drive for desktop** is running and File Explorer shows
   `My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full`.
2. Get the latest code and build it (Command Prompt):
   ```
   cd /d "%USERPROFILE%\Downloads"
   git clone --branch claude/roccat-swarm-integration-e5coz3 --depth 1 https://github.com/audiovideo1979-sys/EOS-consumables-builder roccat-src
   cd roccat-src\roccat-manager
   build.bat
   ```
   (Already have that repo cloned? `git pull` on that branch and run `roccat-manager\build.bat` instead.)
   At the end `build.bat` prints **"Copied to Google Drive: ...ROCCAT Manager.exe"**.
3. Close any older ROCCAT Manager that is open, then run `ROCCAT Manager.exe` **from the Drive folder**.
   On this first run it copies your existing profiles from `%APPDATA%\ROCCAT Manager\profiles` into
   `ROCCAT Manager Data\profiles` and says so. The `%APPDATA%` copy stays where it is as a backup.
4. Wait for the Google Drive tray icon to say it is up to date (the .exe is about 50 MB) before switching
   to the Work boot.

## Work boot — once

1. Install **Google Drive for desktop** and sign in with the **same Google account**.
2. Open `My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full` and double-click
   `ROCCAT Manager.exe`. If Windows says "Windows protected your PC", click **More info → Run anyway**.
   Right-click its taskbar icon → **Pin to taskbar** for next time.
3. Check the sidebar says "Profiles: shared through Google Drive". Python, git and Swarm II are not needed
   on this boot.

Optional, both boots: right-click both Drive folders → **Available offline**, so the app and profiles are
always on the disk even before Drive has finished starting.

---

## How it stays in sync
- Edit a profile on one boot → Drive uploads `ROCCAT Manager Data` → the other boot sees it the next time
  the app starts there. Let Drive finish uploading before you reboot.
- Copying profiles in (step 3 above) only happens when the shared folder has no profiles yet, or only the
  defaults the app put there on its very first run (marked with a `.seeded-defaults` file; those defaults
  are kept in a `defaults-backup-<date>` folder). Profiles that were really edited are never overwritten.
  So if the Work boot runs first, that's fine — the Personal boot's profiles still come in afterwards, as
  long as nothing was edited on the Work boot in between.

## Updating the app later
- On the Personal boot: `git pull`, then `build.bat`. It replaces the .exe in Drive (close the app first,
  or the copy fails and `build.bat` says so). Wait for Drive to sync before using it on the Work boot.

## Gotchas
- Building **inside** a Google Drive folder can be slow or fail while Drive syncs — build from a normal
  folder (as above); `build.bat` copies the finished .exe into Drive for you.
- If `build.bat` says "Google Drive folder not found", start Google Drive for desktop and run it again,
  or copy `dist\ROCCAT Manager.exe` into the Drive folder by hand.
- `startup.log` (only written when the app fails to start) stays per boot in `%APPDATA%\ROCCAT Manager`.
