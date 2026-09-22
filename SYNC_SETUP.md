# Running ROCCAT Manager on both Windows boots, synced via Google Drive

Goal: the same app **and** the same profiles on the Gaming boot and the Work boot, kept in sync.
Only one boot runs at a time (dual boot), so there are never simultaneous edits to worry about.

Two things get shared through Google Drive:
1. **The program** — put the whole folder in Drive; both boots see the same files.
2. **The profiles** — the built .exe normally saves them per-boot under `%APPDATA%`. Set the
   `ROCCAT_MANAGER_DATA` environment variable to a Drive folder and every install reads/writes the
   **same** profiles there.

Program folder (in Drive): `G:\My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full`
Shared data folder (in Drive): `G:\My Drive\Claude Folder\Projects\Personal\ROCCAT Manager Data`

---

## One-time setup — Gaming boot (the one that already works)

1. **Put the program in Drive.** Clone the repo into the Drive path:
   ```
   git clone https://github.com/audiovideo1979-sys/roccat-manager "G:\My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full"
   cd "G:\My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full"
   git checkout claude/roccat-swarm-integration
   ```

2. **Point profiles at the shared Drive folder** (run once, then reopen the terminal):
   ```
   setx ROCCAT_MANAGER_DATA "G:\My Drive\Claude Folder\Projects\Personal\ROCCAT Manager Data"
   ```

3. **Copy your existing profiles over** so nothing is lost:
   ```
   xcopy "%APPDATA%\ROCCAT Manager\profiles" "G:\My Drive\Claude Folder\Projects\Personal\ROCCAT Manager Data\profiles" /E /I /Y
   ```

4. **Build once** and run:
   ```
   build.bat
   dist\"ROCCAT Manager.exe"
   ```
   Confirm your profiles are all there.

5. In Google Drive, right-click the program folder and the data folder → **Available offline**, so the
   .exe and profiles are always on disk (not online-only).

---

## One-time setup — Work boot

1. Install **Google Drive for Desktop** and sign in with the **same** account
   (`audiovideo1979@gmail.com`) so `G:\My Drive\...` shows the same files. Make both folders
   **Available offline**.

2. Set the same variable (reopen the terminal after):
   ```
   setx ROCCAT_MANAGER_DATA "G:\My Drive\Claude Folder\Projects\Personal\ROCCAT Manager Data"
   ```

3. **Just run the same .exe from Drive** — no need to install Python or build here:
   ```
   G:\My Drive\Claude Folder\Projects\Personal\ROCCAT_Manager_Full\dist\"ROCCAT Manager.exe"
   ```
   It's the same built app and it reads the same synced profiles.

---

## How it stays in sync
- Edit a profile on one boot → Google Drive syncs the `ROCCAT Manager Data` folder → the other boot
  sees it the next time it runs.
- The program itself is in Drive, so an update built on one boot appears on the other after it syncs.

## Updating the app later
- On the Gaming boot: `git pull` then `build.bat` in the Drive program folder. Wait for Google Drive to
  finish syncing (the .exe is ~50 MB) before running it on the Work boot.

## Gotchas
- Building (`build.bat`) **inside** a Google Drive folder can occasionally be slow or fail while Drive
  is syncing. If a build acts up: pause Google Drive syncing, build, then resume — or keep a local clone
  just for building and copy the finished `dist\ROCCAT Manager.exe` into the Drive folder. The profiles
  sync the same way regardless, because they live in the `ROCCAT Manager Data` folder, not next to the
  .exe.
- If the shared Drive folder isn't mounted when the app starts, it falls back to the per-boot
  `%APPDATA%` location (so it won't crash) — just start it again once Drive is up.
