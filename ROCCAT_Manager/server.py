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

@app.route("/api/import-to-mouse/<boot_id>", methods=["POST"])
def import_to_mouse(boot_id):
    """Write all 5 active slot profiles directly to SWARM II's onboard profile file and restart SWARM."""
    slots = load_slots()
    boot_slots = slots.get(boot_id, [None]*5)
    stored = load_stored()
    prof_map = {p["id"]: p for p in stored}

    if not ONBOARD_FILE.exists():
        return jsonify({"success": False, "error": "SWARM II profile file not found. Is SWARM II installed?"}), 404

    sys.path.insert(0, str(BASE_DIR))
    from profile_mgr_format import (
        parse_profile_mgr, write_profile_mgr_to_file, create_minimal_profile,
        fix_trailing_bytes, _make_data_content, _encode_utf16be,
        _make_simple_content, _make_profile_color_content, make_default_main_data
    )
    from dat_export import profile_to_dat_args, action_to_entry, KEYBIND_TO_SLOT

    def build_custom_buttons_data(profile):
        """Build 129-byte KoneXPAirButtons from our JSON profile."""
        args = profile_to_dat_args(profile)
        button_assignments = args['button_assignments']
        data = b'\x00\x00\x00'  # Padding
        data += b'\x7D\x07\x7D'  # Identifier
        data += b'\x01'  # Modified flag
        for entry in button_assignments:
            data += bytes(entry)
        data += b'\x00\x00'  # Checksum (SWARM recalculates)
        return data

    def build_custom_main_data(profile):
        """Build 82-byte KoneXPAirMain from our JSON profile."""
        dpi = profile.get('dpi', 800)
        color_hex = profile.get('color', '#888780').lstrip('#')
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)
        return make_default_main_data(
            dpi_stages=[dpi, dpi, dpi, dpi, dpi],
            color_rgb=(r, g, b)
        )

    def build_profile_for_mgr(profile):
        """Build a profile dict compatible with profile_mgr_format."""
        color_hex = profile.get('color', '#888780').lstrip('#')
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b_val = int(color_hex[4:6], 16)
        blocks = [
            {'name': 'DesktopProfile', 'raw_content': _make_simple_content(0)},
            {'name': 'KoneXPAirButtons', 'raw_content': _make_data_content(0x0C, build_custom_buttons_data(profile))},
            {'name': 'KoneXPAirMain', 'raw_content': _make_data_content(0x0C, build_custom_main_data(profile))},
            {'name': 'ProfileColor', 'raw_content': _make_profile_color_content(r, g, b_val)},
            {'name': 'ProfileImage', 'raw_content': _make_data_content(0x0A,
                _encode_utf16be(":/icons/resource/graphic/icons/Basics/profile_icons/profile_default_icon.png"))},
            {'name': 'ProfileName', 'raw_content': _make_data_content(0x0A, _encode_utf16be(profile.get('name', 'Profile')))},
        ]
        return {'block_count': len(blocks), 'blocks': blocks}

    try:
        # Parse existing onboard file
        mgr = parse_profile_mgr(str(ONBOARD_FILE))

        # Build new profiles list
        new_profiles = []
        for i, pid in enumerate(boot_slots):
            if pid and pid in prof_map:
                new_profiles.append(build_profile_for_mgr(prof_map[pid]))
            elif i < len(mgr.get('profiles', [])):
                # Keep existing profile if no replacement
                new_profiles.append(mgr['profiles'][i])
            else:
                # Create empty default
                new_profiles.append(create_minimal_profile(name=f"Profile {i+1}"))

        # Replace profiles in manager
        mgr['profiles'] = new_profiles
        mgr['profile_count'] = len(new_profiles)
        fix_trailing_bytes(mgr)

        # Backup original
        import shutil
        backup = str(ONBOARD_FILE) + '.bak'
        shutil.copy2(str(ONBOARD_FILE), backup)

        # Write new file
        write_profile_mgr_to_file(mgr, str(ONBOARD_FILE))

        # Restart SWARM II
        restart_msg = restart_swarm()

        return jsonify({
            "success": True,
            "message": f"Wrote {len(new_profiles)} profiles to mouse. {restart_msg}",
            "backup": backup
        })

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
