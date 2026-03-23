# ROCCAT Manager — Claude Code Briefing

> **Agent:** Brutus (Claude Code)
> **Prepared by:** Sasha (claude.ai)
> **Project:** ROCCAT Manager — Kone XP Air custom profile UI
> **Status:** Core build complete. Automation layer needs calibration.

---

## Project Overview

Steve runs a **dual-boot Windows PC on two separate drives**. He uses a **ROCCAT Kone XP Air** mouse managed by **SWARM II** software. The problem: both Windows installs share the mouse's 5 onboard profile slots, and SWARM II has no CLI — you can't script it. He never wants to open SWARM II again.

The solution is a **custom web UI** (Flask + HTML/JS) that lets Steve edit DPI stages, keybinds, and polling rate for all 5 profiles per boot, then pushes those changes to SWARM II invisibly using **pywinauto UI automation** running in the background.

---

## Repository Structure

```
roccat_manager/
├── server.py                        Flask backend + REST API
├── templates/
│   └── index.html                   Full custom UI (single file, no framework)
├── profiles/
│   ├── boot1.json                   Boot 1 profile data (source of truth)
│   └── boot2.json                   Boot 2 profile data
├── automation/
│   └── roccat_automation.py         pywinauto SWARM II driver
├── INSTALL_AND_RUN.bat              First-time setup (installs deps, launches)
├── Launch.bat                       Daily launcher
└── README.md                        End-user instructions
```

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3, Flask |
| UI | Vanilla HTML/CSS/JS (no framework) |
| Automation | pywinauto, pywin32 |
| Data | JSON files (one per boot) |
| Launcher | Windows batch scripts |

---

## Data Model

### Profile JSON (`profiles/boot1.json`)

```json
{
  "boot": "Boot1",
  "profiles": [
    {
      "slot": 1,
      "name": "Main Test",
      "color": "#7F77DD",
      "polling_rate": 1000,
      "dpi": {
        "stages": [400, 800, 1600, 3200, 6400],
        "active_stage": 2
      },
      "keybinds": {
        "left_button":   "Left Click",
        "right_button":  "Right Click",
        "middle_button": "Middle Click",
        "scroll_up":     "Scroll Up",
        "scroll_down":   "Scroll Down",
        "side_button_1": "Browser Back",
        "side_button_2": "Browser Forward",
        "dpi_up":        "DPI Up",
        "dpi_down":      "DPI Down",
        "profile_cycle": "Profile Cycle",
        "easy_shift":    "Easy Shift"
      }
    }
  ]
}
```

**Field notes:**
- `slot`: 1–5, maps directly to SWARM II onboard slot number
- `dpi.stages`: array of exactly 5 integers, range 100–36000
- `dpi.active_stage`: 0-indexed (0 = stage 1, 4 = stage 5)
- `polling_rate`: one of `[125, 250, 500, 1000, 2000, 4000]`
- `keybinds`: all 11 keys must be present — see full key list below

---

## REST API

All endpoints served by `server.py` at `http://localhost:5000`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve the UI |
| `GET` | `/api/profiles/{boot_id}` | Get all profiles for a boot |
| `GET` | `/api/profiles/{boot_id}/{slot}` | Get single profile |
| `PUT` | `/api/profiles/{boot_id}/{slot}` | Update profile (dpi, keybinds, polling, color) |
| `PUT` | `/api/profiles/{boot_id}/{slot}/name` | Rename profile |
| `POST` | `/api/apply/{boot_id}/{slot}` | Push single profile to SWARM II |
| `POST` | `/api/apply/{boot_id}/all` | Push all 5 profiles to SWARM II |
| `POST` | `/api/inspector` | Dump SWARM II control tree to file |

**`boot_id` values:** `boot1` or `boot2`

**`PUT /api/profiles/{boot_id}/{slot}` body:**
```json
{
  "dpi": { "stages": [400, 800, 1600, 3200, 6400], "active_stage": 2 },
  "polling_rate": 1000,
  "keybinds": { "left_button": "Left Click", ... },
  "color": "#7F77DD"
}
```

**Apply response (success):**
```json
{
  "success": true,
  "steps": ["Navigated to slot 1", "DPI stages set", "Keybinds set", "Polling rate set", "Saved"]
}
```

**Apply response (pywinauto not installed):**
```json
{
  "success": false,
  "error": "pywinauto not installed",
  "install": "Run: pip install pywinauto pywin32"
}
```

---

## Automation Layer — Critical Context

### The Core Problem

SWARM II has **no CLI and no file-based config** (the AppData/Roaming/ROCCAT folder is empty — confirmed). All profile data lives in the mouse's onboard memory. The only way to write to it programmatically is to drive SWARM II's GUI using `pywinauto`.

### How `roccat_automation.py` Works

```
apply_full_profile(profile, headless=True)
  └── get_swarm_app()           # connect or launch SWARM II
  └── navigate_to_profile()    # click correct slot tab
  └── set_dpi_stages()         # navigate to Performance tab, fill fields
  └── set_keybind() x11        # navigate to Buttons tab, set each dropdown
  └── set_polling_rate()       # set polling radio button
  └── save_profile()           # click Save/Apply
  └── app.minimize()           # hide SWARM II if headless=True
```

### ⚠️ Calibration Required — Top Priority

The control names in `roccat_automation.py` are **placeholder stubs** based on typical SWARM II structure. They need to be verified against Steve's actual installed version before `apply_*` endpoints will work.

**To calibrate:**

1. Install pywinauto: `pip install pywinauto pywin32`
2. Open SWARM II, navigate to the Kone XP Air main screen
3. Run: `python automation/roccat_automation.py`
4. This writes `inspector_output.txt` to the project root
5. Send `inspector_output.txt` back to Brutus for mapping

**What to look for in `inspector_output.txt`:**

```
# You need the exact titles/names for:
- Profile slot buttons (slot 1 through 5)
- The "Performance" or "DPI" tab button
- DPI stage input fields (one per stage)
- Active stage selector buttons
- The "Buttons" or "Assignment" tab button
- Button assignment list items (left click, right click, etc.)
- Polling rate radio buttons or dropdown
- Save / Apply button
```

**Current placeholder names in `roccat_automation.py` (likely wrong, fix after inspection):**

```python
# navigate_to_profile()
slot_names = ["Profile slot 1", ..., "Profile slot 5"]

# set_dpi_stages()
win.child_window(title="Performance", control_type="Button")
win.child_window(title=f"DPI stage {i+1}", control_type="Edit")
win.child_window(title=f"Stage {active_stage + 1}", control_type="Button")

# set_keybind()
win.child_window(title="Buttons", control_type="Button")
win.child_window(title=label, control_type="ListItem")

# set_polling_rate()
win.child_window(title=rate_label, control_type="RadioButton")

# save_profile()
win.child_window(title_re=".*Save.*|.*Apply.*", control_type="Button")
```

---

## UI Architecture

The UI (`templates/index.html`) is a single-file vanilla HTML/JS/CSS app. No build step, no framework.

### Layout
```
Shell (flex row)
├── Sidebar (220px fixed)
│   ├── Logo / app name
│   ├── Boot switcher (Boot 1 / Boot 2 tabs)
│   ├── Profile nav (5 items, click to select)
│   └── "Push all to SWARM II" footer button
└── Main (flex column)
    ├── Topbar (profile name input, color swatch, apply button)
    ├── Content (scrollable)
    │   ├── DPI Card (5 stage inputs + active stage + polling rate)
    │   └── Keybinds Card (mouse SVG diagram + assignment table)
    └── Status bar
```

### Key JS functions

| Function | Description |
|---|---|
| `switchBoot(bootId)` | Switches between boot1/boot2, reloads profiles |
| `loadProfiles()` | GET /api/profiles/{boot_id}, populates sidebar |
| `selectProfile(slot)` | Renders topbar, DPI, keybinds, polling for selected slot |
| `autosave()` | Debounced 800ms PUT to save changes to JSON |
| `applyToSwarm()` | POST /api/apply/{boot_id}/{slot} |
| `applyAll()` | POST /api/apply/{boot_id}/all |
| `updateDPIStage(idx, val)` | Updates dpi.stages[idx], clamps 100–36000, triggers autosave |
| `setActiveStage(idx)` | Sets dpi.active_stage, re-renders DPI grid |
| `setPolling(rate)` | Updates polling_rate, triggers autosave |
| `updateKeybind(key, value)` | Updates keybinds[key], triggers autosave |
| `highlightButton(key)` | Highlights SVG button + scrolls to keybind table row |

---

## Keybind Reference

### Button key names (used in JSON and JS)

```
left_button       Right button
right_button      Right button
middle_button     Middle click / scroll wheel press
scroll_up         Scroll wheel up
scroll_down       Scroll wheel down
side_button_1     Lower thumb button
side_button_2     Upper thumb button
dpi_up            DPI cycle up (small button top of mouse)
dpi_down          DPI cycle down (small button top of mouse)
profile_cycle     Profile switch button
easy_shift        Easy Shift modifier button
```

### Available action values (keybind dropdown options)

```
Left Click, Right Click, Middle Click
Scroll Up, Scroll Down
Browser Back, Browser Forward
DPI Up, DPI Down, DPI Cycle
Profile Cycle
Easy Shift
Copy, Paste, Cut, Undo, Redo
Play/Pause, Next Track, Prev Track, Volume Up, Volume Down, Mute
Snipping Tool, Task Manager, Show Desktop
Macro 1, Macro 2, Macro 3
Disabled
```

---

## Known Limitations / Future Work

### Immediate (blocking for automation)
- [ ] **pywinauto control names are stubs** — need inspector run to fix
- [ ] SWARM II version not confirmed — controls may differ between versions

### Near term
- [ ] Add macro recording / macro assignment support
- [ ] RGB lighting section (currently out of scope per Steve's request)
- [ ] Per-profile Easy Shift layer keybinds (secondary layer)
- [ ] Profile color picker UI (currently just a static swatch)

### Nice to have
- [ ] Import directly from `.dat` files (requires full binary format reverse-engineering — partially done, format is UTF-16LE binary, 651 bytes per profile, blocks: `DesktopProfile`, `KoneXPAirButtons`, `KoneXPAirMain`, `ProfileColor`, `ProfileImage`, `ProfileName`)
- [ ] Drag-to-reorder profile slots
- [ ] Profile duplication
- [ ] Export individual profiles as `.dat` for SWARM II manual import fallback

---

## Environment Notes

- **OS:** Windows 11, dual boot on separate drives
- **User profile path:** `C:\Users\audio\`
- **Projects folder:** `C:\Projects Folder\`
- **Python:** Not yet installed on Boot 1 at time of writing
- **SWARM II install path:** `C:\Program Files\Turtle Beach Swarm II\Turtle Beach Swarm II.exe`
- **Profile folder:** `C:\Users\audio\Documents\ROCCAT_Profiles\Boot1\` (Boot 1) and `\Boot2\` (Boot 2)
- **AppData/ROCCAT folder:** Empty — confirmed. SWARM II stores nothing locally.
- **Mouse onboard storage:** 5 slots maximum, hardware limit

---

## First Run Checklist

```
[ ] Copy roccat_manager/ folder to same path on both drives
[ ] Run INSTALL_AND_RUN.bat on Boot 1
[ ] Verify UI opens at http://localhost:5000
[ ] Confirm Boot 1 profiles load correctly (pre-filled from screenshots)
[ ] Update Boot 2 profile names once configured
[ ] Run python automation/roccat_automation.py with SWARM II open
[ ] Send inspector_output.txt to Brutus for control name mapping
[ ] Test Apply to mouse → on one profile
[ ] Test Push all to SWARM II
```

---

## Handoff Notes from Sasha

The `.dat` binary format was partially decoded during this session. One exported profile (651 bytes, UTF-16LE, single profile per file) was inspected and the following blocks identified: `DesktopProfile`, `KoneXPAirButtons`, `KoneXPAirMain`, `ProfileColor`, `ProfileImage`, `ProfileName`. Full format reverse-engineering was deferred in favor of the safer pywinauto approach — but the groundwork is there if direct `.dat` read/write becomes desirable later.

The pywinauto stubs in `roccat_automation.py` are written with real SWARM II navigation logic — the structure is correct, only the control name strings need updating after the inspector run. That should be a quick find-and-replace once the output file is available.

Steve's priority is: DPI stages + keybinds. Polling rate is included. RGB/lighting is explicitly out of scope for now.
