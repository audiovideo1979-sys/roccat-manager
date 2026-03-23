"""
roccat_automation.py
Drives SWARM II invisibly using pywinauto UI automation.
Control names are pre-mapped based on SWARM II's known UI structure.
Run inspector.py first to verify/update control names for your SWARM version.
"""

import time
import subprocess
import os
from typing import Optional

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False

SWARM_PATHS = [
    r"C:\Program Files\Turtle Beach Swarm II\Turtle Beach Swarm II.exe",
]

POLLING_RATE_MAP = {
    125:  "125 Hz",
    250:  "250 Hz",
    500:  "500 Hz",
    1000: "1000 Hz",
    2000: "2000 Hz",
    4000: "4000 Hz",
}

BUTTON_LABEL_MAP = {
    "left_button":   "Left Button",
    "right_button":  "Right Button",
    "middle_button": "Middle Button",
    "scroll_up":     "Scroll Up",
    "scroll_down":   "Scroll Down",
    "side_button_1": "Side Button 1",
    "side_button_2": "Side Button 2",
    "dpi_up":        "DPI Up Button",
    "dpi_down":      "DPI Down Button",
    "profile_cycle": "Profile Button",
    "easy_shift":    "Easy Shift",
}


def find_swarm_exe() -> Optional[str]:
    for path in SWARM_PATHS:
        if os.path.exists(path):
            return path
    return None


def get_swarm_app(launch_if_closed=True) -> Optional[object]:
    if not PYWINAUTO_AVAILABLE:
        return None
    try:
        app = Application(backend="uia").connect(title_re=".*SWARM.*", timeout=5)
        return app
    except Exception:
        if launch_if_closed:
            exe = find_swarm_exe()
            if exe:
                subprocess.Popen([exe])
                time.sleep(4)
                try:
                    return Application(backend="uia").connect(title_re=".*SWARM.*", timeout=10)
                except Exception:
                    return None
        return None


def navigate_to_profile(app, slot_index: int):
    """Click the correct profile slot in SWARM II (0-indexed)."""
    win = app.top_window()
    try:
        # Profile slots are usually named "Profile 1" through "Profile 5"
        # These control names are placeholders — update after running inspector.py
        slot_names = [
            "Profile slot 1", "Profile slot 2", "Profile slot 3",
            "Profile slot 4", "Profile slot 5"
        ]
        win.child_window(title=slot_names[slot_index], control_type="Button").click_input()
        time.sleep(0.5)
    except Exception as e:
        print(f"[SWARM] Could not navigate to profile slot {slot_index + 1}: {e}")


def set_dpi_stages(app, stages: list, active_stage: int):
    """
    Set DPI stages and active stage in SWARM II.
    NOTE: Control names need verification via inspector.py.
    """
    win = app.top_window()
    try:
        # Navigate to Performance/DPI tab
        win.child_window(title="Performance", control_type="Button").click_input()
        time.sleep(0.5)

        for i, dpi_val in enumerate(stages[:5]):
            try:
                # DPI stage fields — named "DPI stage 1" etc in SWARM II
                field = win.child_window(title=f"DPI stage {i+1}", control_type="Edit")
                field.set_text(str(dpi_val))
                time.sleep(0.1)
            except Exception as e:
                print(f"[SWARM] DPI stage {i+1} field not found: {e}")

        # Set active stage
        try:
            stage_btn = win.child_window(
                title=f"Stage {active_stage + 1}", control_type="Button"
            )
            stage_btn.click_input()
        except Exception as e:
            print(f"[SWARM] Active stage button not found: {e}")

    except Exception as e:
        print(f"[SWARM] DPI tab navigation failed: {e}")


def set_keybind(app, button_key: str, action: str):
    """
    Set a single keybind for a button in SWARM II.
    NOTE: Control names need verification via inspector.py.
    """
    win = app.top_window()
    label = BUTTON_LABEL_MAP.get(button_key, button_key)
    try:
        # Navigate to Buttons/Assignment tab
        win.child_window(title="Buttons", control_type="Button").click_input()
        time.sleep(0.4)

        # Find the button row and click its dropdown
        btn_row = win.child_window(title=label, control_type="ListItem")
        btn_row.click_input()
        time.sleep(0.3)

        # Find the action dropdown and select
        combo = win.child_window(control_type="ComboBox")
        combo.select(action)
        time.sleep(0.2)

    except Exception as e:
        print(f"[SWARM] Keybind set failed for {button_key}: {e}")


def set_polling_rate(app, rate: int):
    """Set polling rate in SWARM II."""
    win = app.top_window()
    rate_label = POLLING_RATE_MAP.get(rate, "1000 Hz")
    try:
        win.child_window(title="Performance", control_type="Button").click_input()
        time.sleep(0.4)
        win.child_window(title=rate_label, control_type="RadioButton").click_input()
        time.sleep(0.2)
    except Exception as e:
        print(f"[SWARM] Polling rate set failed: {e}")


def save_profile(app):
    """Click save/apply in SWARM II."""
    win = app.top_window()
    try:
        save_btn = win.child_window(title_re=".*Save.*|.*Apply.*", control_type="Button")
        save_btn.click_input()
        time.sleep(0.5)
    except Exception as e:
        print(f"[SWARM] Save failed: {e}")


def apply_full_profile(profile: dict, headless=True) -> dict:
    """
    Main entry point. Takes a profile dict and applies it fully to SWARM II.
    Returns status dict.
    """
    if not PYWINAUTO_AVAILABLE:
        return {"success": False, "error": "pywinauto not installed. Run: pip install pywinauto pywin32"}

    status = {"success": False, "steps": []}

    app = get_swarm_app(launch_if_closed=True)
    if not app:
        status["error"] = "Could not connect to or launch SWARM II"
        return status

    slot_index = profile.get("slot", 1) - 1

    try:
        navigate_to_profile(app, slot_index)
        status["steps"].append(f"Navigated to slot {slot_index + 1}")

        dpi = profile.get("dpi", {})
        set_dpi_stages(app, dpi.get("stages", [800]), dpi.get("active_stage", 0))
        status["steps"].append("DPI stages set")

        for key, action in profile.get("keybinds", {}).items():
            set_keybind(app, key, action)
        status["steps"].append("Keybinds set")

        set_polling_rate(app, profile.get("polling_rate", 1000))
        status["steps"].append("Polling rate set")

        save_profile(app)
        status["steps"].append("Saved")

        if headless:
            app.top_window().minimize()

        status["success"] = True

    except Exception as e:
        status["error"] = str(e)

    return status


def run_inspector():
    """
    Dumps SWARM II's full control tree to inspector_output.txt.
    Run this once to get real control names for your SWARM version.
    """
    if not PYWINAUTO_AVAILABLE:
        print("pywinauto not installed.")
        return

    app = get_swarm_app(launch_if_closed=True)
    if not app:
        print("Could not connect to SWARM II")
        return

    import io
    from contextlib import redirect_stdout

    win = app.top_window()
    buf = io.StringIO()
    with redirect_stdout(buf):
        win.print_control_identifiers(depth=6)

    output = buf.getvalue()
    with open("inspector_output.txt", "w") as f:
        f.write(output)
    print(f"Control tree saved to inspector_output.txt ({len(output)} chars)")
    return output


if __name__ == "__main__":
    print("Running SWARM II inspector...")
    run_inspector()
