# ROCCAT Manager — Kone XP Air

Custom profile manager UI that replaces SWARM II for daily use.
Drives SWARM II invisibly in the background via pywinauto automation.

## First time setup
1. Double-click `INSTALL_AND_RUN.bat`
2. That's it — opens in your browser at http://localhost:5000

## Daily use
- Double-click `Launch.bat`
- Edit DPI, keybinds, polling rate in the UI
- Click **Apply to mouse →** to push one profile
- Click **Push all to SWARM II** to push all 5 at once
- Changes auto-save to JSON every 800ms

## File structure
```
roccat_manager/
├── server.py                  Flask backend
├── templates/index.html       Custom UI
├── profiles/
│   ├── boot1.json             Boot 1 profile data
│   └── boot2.json             Boot 2 profile data
├── automation/
│   └── roccat_automation.py   pywinauto SWARM II driver
├── INSTALL_AND_RUN.bat        First time setup
└── Launch.bat                 Daily launcher
```

## Tuning pywinauto after install
Once Python is installed, run the inspector once to verify SWARM II's
control names match what roccat_automation.py expects:

```
python automation/roccat_automation.py
```

This writes `inspector_output.txt`. Open it and check that the control
names match these in roccat_automation.py:
- Profile slot buttons
- DPI stage edit fields
- Polling rate radio buttons
- Button assignment list items

## Boot setup
- Boot 1: `$BOOT_NAME = "Boot1"` is pre-set
- Boot 2: switch to Boot 2 tab in the UI — data saves to `profiles/boot2.json`
  on that drive's copy of the app
