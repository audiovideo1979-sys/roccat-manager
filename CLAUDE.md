# ROCCAT Manager Full — Claude Code Instructions

## On Session Start
1. Read `HANDOFF.md` for current state and pending tasks
2. Check `CHANGELOG.txt` for the latest @N version number — continue from there

## Project Basics
- **What it is:** Custom web UI to manage ROCCAT Kone XP Air mouse profiles without opening SWARM II
- **Web app:** `ROCCAT_Manager/server.py` (Flask, port 5555) + SPA frontend in `ROCCAT_Manager/templates/`
- **Run server:** `ROCCAT_Manager/Launch.bat` or `python ROCCAT_Manager/server.py`
- **Working directory:** `C:\Projects Folder\ROCCAT_Manager_Full\`
- **Git:** Currently inside the Consumables monorepo (`C:\Projects Folder\` remote). Needs its own GitHub repo.
- **Push:** `cd "C:\Projects Folder" && git add -A && git commit -m "..." && git push`

## Rules
- **Always update CHANGELOG.txt** after every change with the next @N version number
- **Always update HANDOFF.md** at the end of each session
- **No .env file** — no secrets/credentials in this project

## Architecture
- `ROCCAT_Manager/server.py` — Flask backend, all REST API routes, profile CRUD, .dat export/import
- `ROCCAT_Manager/templates/index.html` — Single-file SPA (dark theme, no framework)
- `ROCCAT_Manager/profiles/` — JSON data files (boot1.json, boot2.json, slots.json, stored.json) + .dat exports
- `ROCCAT_Manager/automation/roccat_automation.py` — pywinauto driver for SWARM II (⚠️ stubs need calibration)
- `ROCCAT_Manager/SWARM_II_DAT_FORMAT.py` — Reverse-engineered single-profile .dat parser/writer
- `ROCCAT_Manager/profile_mgr_format.py` — Multi-profile container .dat format
- `ROCCAT_Manager/dat_export.py` — JSON → .dat converter + keybind action mapper
- Root `hid_*.py` files — HID protocol experiments (not integrated into main app)

## Data Model
- `boot1.json` / `boot2.json` — 5 profiles per boot, each with: name, color, polling_rate, dpi (5 stages + active), keybinds (11 buttons), easy_shift (11 buttons)
- `slots.json` — maps profile IDs to onboard slot numbers per boot
- `stored.json` — library of all available profiles for slot assignment
- `job_config` equivalent = `profiles/*.json` (no job_config.json in this project)

## REST API (port 5555)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve UI |
| `GET` | `/api/stored` | List stored profiles |
| `POST` | `/api/stored` | Create profile |
| `PUT` | `/api/stored/{id}` | Update profile |
| `DELETE` | `/api/stored/{id}` | Delete profile |
| `POST` | `/api/stored/{id}/duplicate` | Duplicate profile |
| `GET` | `/api/slots/{boot_id}` | Get slot assignments |
| `PUT` | `/api/slots/{boot_id}/{slot}` | Assign profile to slot |
| `GET` | `/api/export/{id}` | Download single profile as .dat |
| `GET` | `/api/export-all/{boot_id}` | Download all profiles as .zip |
| `POST` | `/api/import-to-mouse/{boot_id}` | Write profiles to SWARM II onboard file |

## ⚠️ Automation Calibration — Top Priority
`roccat_automation.py` has placeholder control names that need to be mapped to actual SWARM II UI controls:
1. Install deps: `pip install pywinauto pywin32`
2. Open SWARM II, navigate to Kone XP Air main screen
3. Run: `python ROCCAT_Manager/automation/roccat_automation.py`
4. This writes `inspector_output.txt` — send to Claude for control name mapping
5. Update the stub names in `roccat_automation.py` with real control names

## Binary .dat Format
- Single profile: 651 bytes, UTF-16LE, blocks: `DesktopProfile`, `KoneXPAirButtons`, `KoneXPAirMain`, `ProfileColor`, `ProfileImage`, `ProfileName`
- Multi-profile container: `KONE_XP_AIR_Profile_Mgr.dat` in `%APPDATA%\Turtle Beach\Swarm II\Setting\`
- Full reverse-engineering done in `SWARM_II_DAT_FORMAT.py` and `profile_mgr_format.py`

## Environment
- **OS:** Windows 11, dual-boot on separate drives
- **Mouse:** ROCCAT Kone XP Air (USB wireless, VID: 0x10F5, PID: 0x5019)
- **SWARM II path:** `C:\Program Files\Turtle Beach Swarm II\Turtle Beach Swarm II.exe`
- **SWARM II config:** `%APPDATA%\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_Profile_Mgr.dat`
- **AppData/ROCCAT folder:** Empty — SWARM II stores nothing locally (confirmed)

## Out of Scope (per Steve)
- RGB lighting — explicitly excluded
- Macro recording (future)
- Easy Shift secondary layer UI (future — currently JSON-only)
