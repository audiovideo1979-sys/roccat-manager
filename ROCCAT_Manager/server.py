"""
server.py  —  ROCCAT Manager backend
Run: python server.py
Opens at http://localhost:5555
"""

import json
import os
import sys
import re
import io
import zipfile
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
PROFILES_DIR  = BASE_DIR / "profiles"
STATIC_DIR    = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

STORED_FILE = PROFILES_DIR / "stored.json"
SLOTS_FILE  = PROFILES_DIR / "slots.json"

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(STATIC_DIR), template_folder=str(TEMPLATES_DIR))

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path):
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_stored():
    data = load_json(STORED_FILE)
    return data.get("profiles", [])

def save_stored(profiles):
    save_json(STORED_FILE, {"profiles": profiles})

def load_slots():
    data = load_json(SLOTS_FILE)
    if not data:
        data = {"boot1": [None]*5, "boot2": [None]*5}
    return data

def save_slots(data):
    save_json(SLOTS_FILE, data)

def make_id(name):
    """Generate a URL-safe ID from a profile name."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # Ensure unique
    profiles = load_stored()
    existing = {p["id"] for p in profiles}
    if slug not in existing:
        return slug
    i = 2
    while f"{slug}-{i}" in existing:
        i += 1
    return f"{slug}-{i}"

DEFAULT_KEYBINDS = {
    "left_button": "Left Click", "right_button": "Right Click",
    "middle_button": "Middle Click", "scroll_up": "Scroll Up",
    "scroll_down": "Scroll Down", "tilt_left": "Tilt Left",
    "tilt_right": "Tilt Right", "side_button_1": "Browser Back",
    "side_button_2": "Browser Forward", "thumb_button_1": "Disabled",
    "thumb_button_2": "Disabled", "dpi_up": "DPI Up",
    "dpi_down": "DPI Down", "easy_shift": "Easy Shift",
}

DEFAULT_EASYSHIFT = {
    "left_button": "Disabled", "right_button": "Disabled",
    "middle_button": "Disabled", "scroll_up": "Disabled",
    "scroll_down": "Disabled", "tilt_left": "Disabled",
    "tilt_right": "Disabled", "side_button_1": "Disabled",
    "side_button_2": "Disabled", "thumb_button_1": "Disabled",
    "thumb_button_2": "Disabled", "dpi_up": "Disabled",
    "dpi_down": "Disabled",
}

# ── Routes — UI ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(TEMPLATES_DIR), "index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC_DIR), filename)

# ── Routes — Stored Profiles ─────────────────────────────────────────────────
@app.route("/api/stored", methods=["GET"])
def get_stored():
    return jsonify({"profiles": load_stored()})

@app.route("/api/stored", methods=["POST"])
def create_stored():
    body = request.get_json() or {}
    name = body.get("name", "New Profile").strip()
    profiles = load_stored()
    new_profile = {
        "id": make_id(name),
        "name": name,
        "color": body.get("color", "#888780"),
        "dpi": body.get("dpi", 800),
        "keybinds": body.get("keybinds", dict(DEFAULT_KEYBINDS)),
        "easy_shift": body.get("easy_shift", dict(DEFAULT_EASYSHIFT)),
    }
    profiles.append(new_profile)
    save_stored(profiles)
    return jsonify({"success": True, "profile": new_profile})

@app.route("/api/stored/<profile_id>", methods=["PUT"])
def update_stored(profile_id):
    profiles = load_stored()
    idx = next((i for i, p in enumerate(profiles) if p["id"] == profile_id), None)
    if idx is None:
        return jsonify({"error": "Profile not found"}), 404
    updates = request.get_json()
    profiles[idx].update(updates)
    profiles[idx]["id"] = profile_id  # prevent ID overwrite
    save_stored(profiles)
    return jsonify({"success": True, "profile": profiles[idx]})

@app.route("/api/stored/<profile_id>", methods=["DELETE"])
def delete_stored(profile_id):
    profiles = load_stored()
    profiles = [p for p in profiles if p["id"] != profile_id]
    save_stored(profiles)
    # Remove from any slots
    slots = load_slots()
    for boot in slots:
        slots[boot] = [None if s == profile_id else s for s in slots[boot]]
    save_slots(slots)
    return jsonify({"success": True})

@app.route("/api/stored/<profile_id>/duplicate", methods=["POST"])
def duplicate_stored(profile_id):
    profiles = load_stored()
    source = next((p for p in profiles if p["id"] == profile_id), None)
    if not source:
        return jsonify({"error": "Profile not found"}), 404
    new_name = source["name"] + " Copy"
    new_profile = {
        "id": make_id(new_name),
        "name": new_name,
        "color": source["color"],
        "dpi": source["dpi"],
        "keybinds": dict(source["keybinds"]),
        "easy_shift": dict(source.get("easy_shift", {})),
    }
    profiles.append(new_profile)
    save_stored(profiles)
    return jsonify({"success": True, "profile": new_profile})

# ── Routes — Slots ────────────────────────────────────────────────────────────
@app.route("/api/slots/<boot_id>", methods=["GET"])
def get_slots(boot_id):
    slots = load_slots()
    boot_slots = slots.get(boot_id, [None]*5)
    # Resolve profile IDs to full profiles
    profiles = load_stored()
    prof_map = {p["id"]: p for p in profiles}
    resolved = []
    for i, pid in enumerate(boot_slots):
        if pid and pid in prof_map:
            resolved.append({"slot": i+1, "profile": prof_map[pid]})
        else:
            resolved.append({"slot": i+1, "profile": None})
    return jsonify({"boot": boot_id, "slots": resolved})

@app.route("/api/slots/<boot_id>/<int:slot>", methods=["PUT"])
def set_slot(boot_id, slot):
    if slot < 1 or slot > 5:
        return jsonify({"error": "Slot must be 1-5"}), 400
    body = request.get_json()
    profile_id = body.get("profile_id")  # None to clear
    slots = load_slots()
    if boot_id not in slots:
        slots[boot_id] = [None]*5
    slots[boot_id][slot-1] = profile_id
    save_slots(slots)
    return jsonify({"success": True})

# ── Routes — Export .dat ──────────────────────────────────────────────────────
@app.route("/api/export/<profile_id>", methods=["GET"])
def export_dat(profile_id):
    profiles = load_stored()
    profile = next((p for p in profiles if p["id"] == profile_id), None)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    sys.path.insert(0, str(BASE_DIR))
    from SWARM_II_DAT_FORMAT import write_minimal_dat
    from dat_export import profile_to_dat_args

    args = profile_to_dat_args(profile)
    dat_bytes = write_minimal_dat(**args, output_path=None)

    return send_file(
        io.BytesIO(dat_bytes),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"{profile['name']}.dat"
    )

@app.route("/api/export-all/<boot_id>", methods=["GET"])
def export_all_dat(boot_id):
    slots = load_slots()
    boot_slots = slots.get(boot_id, [None]*5)
    profiles = load_stored()
    prof_map = {p["id"]: p for p in profiles}

    sys.path.insert(0, str(BASE_DIR))
    from SWARM_II_DAT_FORMAT import write_minimal_dat
    from dat_export import profile_to_dat_args

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, pid in enumerate(boot_slots):
            if pid and pid in prof_map:
                profile = prof_map[pid]
                args = profile_to_dat_args(profile)
                dat_bytes = write_minimal_dat(**args, output_path=None)
                zf.writestr(f"Slot{i+1}_{profile['name']}.dat", dat_bytes)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{boot_id}_profiles.zip")

# ── Routes — Import to Mouse ──────────────────────────────────────────────────
SWARM_SETTING_DIR = Path(os.environ.get("APPDATA", "")) / "Turtle Beach" / "Swarm II" / "Setting"
ONBOARD_FILE = SWARM_SETTING_DIR / "KONE_XP_AIR_Profile_Mgr.dat"

@app.route("/api/import-to-mouse", methods=["POST"])
def import_to_mouse():
    """
    Write profile DPI directly to mouse hardware via roccat_write.py subprocess.
    """
    try:
        import subprocess as sp

        body = request.get_json() or {}
        profile_id = body.get("profile_id")

        profiles = load_stored()
        profile = next((p for p in profiles if p["id"] == profile_id), None)
        if not profile:
            return jsonify({"success": False, "error": "Profile not found"}), 404

        dpi = profile.get('dpi', 800)
        keybinds = profile.get('keybinds', {})
        easy_shift = profile.get('easy_shift', {})

        # Write DPI and buttons via roccat_write.py subprocess
        # Pass profile data as JSON argument
        import json as jsonmod
        script = str(Path(r"C:\Claude Folder\roccat_write.py"))
        profile_json = jsonmod.dumps({
            'dpi': dpi,
            'keybinds': keybinds,
            'easy_shift': easy_shift,
        })
        result = sp.run(
            ["python", script, str(dpi), "--buttons", profile_json],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            return jsonify({
                "success": True,
                "message": f"DPI set to {dpi} on the mouse!",
            })
        else:
            return jsonify({
                "success": False,
                "error": result.stderr or result.stdout or "Write failed",
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/switch-profile/<int:slot>", methods=["POST"])
def switch_profile(slot):
    """Switch the mouse to a different onboard profile slot (0-4)."""
    try:
        import subprocess as sp
        if slot < 0 or slot > 4:
            return jsonify({"success": False, "error": "Slot must be 0-4"}), 400

        script = str(Path(r"C:\Claude Folder\roccat_write.py"))
        result = sp.run(
            ["python", script, "switch", str(slot)],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            return jsonify({
                "success": True,
                "message": f"Switched to profile slot {slot}!",
            })
        else:
            return jsonify({
                "success": False,
                "error": result.stderr or result.stdout or "Switch failed",
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Routes — Live Swarm II INI Profiles ──────────────────────────────────────
@app.route("/api/swarm/profiles", methods=["GET"])
def get_swarm_profiles():
    """Read live profile data from Swarm II's INI file."""
    try:
        from swarm_ini import read_profiles_from_ini
        profiles = read_profiles_from_ini()
        return jsonify({"success": True, "profiles": profiles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/swarm/dpi/<int:profile_idx>", methods=["PUT"])
def set_swarm_dpi(profile_idx):
    """Write DPI values to Swarm II INI for a specific profile."""
    try:
        from swarm_ini import write_dpi_to_ini
        body = request.get_json()
        dpi_values = body.get("dpi_values", [])
        if len(dpi_values) != 5:
            return jsonify({"error": "Need exactly 5 DPI values"}), 400
        write_dpi_to_ini(profile_idx, dpi_values)
        return jsonify({"success": True, "message": f"DPI updated for profile {profile_idx}. Restart Swarm II without dongle to apply."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/swarm/sync", methods=["POST"])
def sync_from_swarm():
    """Import current Swarm II profiles into ROCCAT Manager's stored profiles."""
    try:
        from swarm_ini import read_profiles_from_ini

        ini_profiles = read_profiles_from_ini()
        profiles = load_stored()

        # Translate Swarm II internal names to our UI names
        NAME_MAP = {
            'Click': 'Left Click',
            'Menu': 'Right Click',
            'Universal Scroll': 'Middle Click',
            'Browser Forward': 'Browser Forward',
            'Browser Backward': 'Browser Back',
            'Scroll Up': 'Scroll Up',
            'Scroll Down': 'Scroll Down',
            'Tilt Left': 'Tilt Left',
            'Tilt Right': 'Tilt Right',
            'Double-Click': 'Double-Click',
            'DPI Up': 'DPI Up',
            'DPI Down': 'DPI Down',
            'DPI Cycle Up': 'DPI Cycle Up',
            'DPI Cycle Down': 'DPI Cycle Down',
            'Easy Shift': 'Easy Shift',
            'Disabled': 'Disabled',
            'Insert': 'Insert',
            'Delete': 'Delete',
            'Home': 'Home',
            'End': 'End',
            'Page Up': 'Page Up',
            'Page Down': 'Page Down',
        }

        def translate_name(entry):
            """Convert an INI button entry to a UI-friendly name."""
            name = entry['name']
            if entry['type'] == 'keyboard':
                return f"Hotkey {name}"
            if entry['type'] == 'disabled' or name == 'Disabled':
                return 'Disabled'
            if entry['type'] in ('easyshift_func', 'profile', 'raw'):
                return 'Disabled'  # entries we can't map yet
            if name == 'Standard(0x61)':
                return 'Tilt Left'
            if name == 'Standard(0x62)':
                return 'Tilt Right'
            if name.startswith('Standard(') or name.startswith('Scroll(') or name.startswith('Profile('):
                return 'Disabled'  # unknown codes
            if name.startswith('ES(0x61)'):
                return 'Prev Track'
            if name.startswith('ES(0x62)'):
                return 'Next Track'
            if name.startswith('ES(0x04)'):
                return 'Disabled'
            if name.startswith('ES('):
                return 'Disabled'
            return NAME_MAP.get(name, name)

        # Swarm II profile names (hardcoded order for now)
        swarm_names = ["WWM", "Main Test", "Grounded", "Default Profile 03", "Default Profile 05"]

        for i, ip in enumerate(ini_profiles):
            if 'dpi' not in ip or 'dpi_x' not in ip.get('dpi', {}):
                continue

            name = swarm_names[i] if i < len(swarm_names) else f"Profile {i+1}"
            dpi = ip['dpi']['dpi_x'][ip['dpi'].get('active_dpi_stage', 0)] if ip['dpi']['dpi_x'] else 800

            keybinds = dict(DEFAULT_KEYBINDS)
            easy_shift = dict(DEFAULT_EASYSHIFT)

            if 'buttons' in ip:
                entries = ip['buttons']['entries']

                # Primary layer button slot mapping (entry index -> button name)
                # Order confirmed by cross-referencing Swarm II button assignments
                btn_map = [
                    'left_button', 'right_button', 'middle_button',  # 0-2: buttons 1-3
                    'scroll_up', 'scroll_down',                       # 3-4: buttons 4-5
                    'side_button_1', 'side_button_2',                 # 5-6: buttons 10-11
                    'dpi_up', 'dpi_down',                             # 7-8: buttons 8-9
                    'thumb_button_1', 'thumb_button_2',               # 9-10: buttons 12-13
                    'tilt_left', 'tilt_right',                        # 11-12: buttons 6-7 (0x61/0x62 = default)
                    'easy_shift', None,                               # 13-14: button 14, profile switch
                ]

                # Easy Shift layer button slot mapping (starting at entry 15)
                es_btn_map = [
                    'left_button', 'right_button',
                    'middle_button',
                    'tilt_left', 'tilt_right',
                    'side_button_1', 'side_button_2',
                    'dpi_up', 'dpi_down',
                    'thumb_button_1', 'thumb_button_2',
                    'scroll_up', 'scroll_down',
                ]

                for j, entry in enumerate(entries):
                    translated = translate_name(entry)
                    if j < len(btn_map) and btn_map[j]:
                        keybinds[btn_map[j]] = translated
                    elif j >= 15 and j - 15 < len(es_btn_map) and es_btn_map[j - 15]:
                        easy_shift[es_btn_map[j - 15]] = translated

            # Find or create profile
            # Only sync button mappings — don't overwrite DPI (user sets that in our UI)
            existing = next((p for p in profiles if p.get('name') == name), None)
            if existing:
                existing['keybinds'] = keybinds
                existing['easy_shift'] = easy_shift
            else:
                profiles.append({
                    'id': make_id(name),
                    'name': name,
                    'color': '#888780',
                    'dpi': dpi,
                    'keybinds': keybinds,
                    'easy_shift': easy_shift,
                })

        save_stored(profiles)
        return jsonify({"success": True, "message": f"Synced {len(ini_profiles)} profiles from Swarm II"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def restart_swarm():
    """Kill and restart SWARM II."""
    import subprocess
    swarm_paths = [
        r"C:\Program Files\Turtle Beach Swarm II\Turtle Beach Swarm II.exe",
    ]
    # Kill SWARM
    try:
        subprocess.run(["taskkill", "/f", "/im", "Turtle Beach Swarm II.exe"], capture_output=True, timeout=5)
    except:
        pass

    import time
    time.sleep(1)

    # Restart
    for path in swarm_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path])
                return f"SWARM II restarted from {path}"
            except:
                pass
    return "Could not restart SWARM II automatically. Please restart it manually."


# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import webbrowser
    print("\n  ROCCAT Manager running at http://localhost:5555\n")
    webbrowser.open("http://localhost:5555")
    app.run(host="127.0.0.1", port=5555, debug=False)
