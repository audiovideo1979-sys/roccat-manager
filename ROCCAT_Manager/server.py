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
import threading
import zipfile
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
REPO_ROOT     = BASE_DIR.parent
PROFILES_DIR  = BASE_DIR / "profiles"
STATIC_DIR    = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

STORED_FILE = PROFILES_DIR / "stored.json"
SLOTS_FILE  = PROFILES_DIR / "slots.json"
MOUSE_CONFIG_FILE = PROFILES_DIR / "mouse_config.json"

# kone_xp_air (protocol + transports) lives at the repo root, next to this folder
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from kone_xp_air import protocol as kxp_protocol, actions as kxp_actions, datfile as kxp_datfile  # noqa: E402
from kone_xp_air.session import KoneXPAir  # noqa: E402
from kone_xp_air.transport import make_transport, TransportError, is_swarm_running, format_results, kill_swarm  # noqa: E402

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

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

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

# ── Mouse access (kone_xp_air) ───────────────────────────────────────────────
DEFAULT_MOUSE_CONFIG = {
    "transport": "frida",      # "frida" = through Swarm II's own handle (known good); "direct" = our own handle
    "backend": "dll",          # direct only: "dll" (Swarm's bundled hidapi, proven for DPI) or "hid"
    "path": None,              # direct only: HID path; None = dongle PID 0x5017, usage page 0xff03
    "activate_b5": 1,          # byte 5 of the 0x4e activate packet: 1 (working replay) or "slot"
    "header_mode": "zero",     # button block header: "zero" (working capture) or "dat" (07 7d 00)
    "wait_handle_s": 8,        # frida only: how long to wait for Swarm's handle
    "kill_swarm": False,       # direct only: stop Swarm II + Device Service before opening the receiver
    "preamble": False,         # direct only: send the SignalRGB receiver-init sequence first (A/B variant D)
}

MOUSE_LOCK = threading.Lock()   # HID sequences must never interleave
LAST_MOUSE_LOG = []


def load_mouse_config():
    cfg = dict(DEFAULT_MOUSE_CONFIG)
    cfg.update(load_json(MOUSE_CONFIG_FILE) or {})
    return cfg


def save_mouse_config(cfg):
    save_json(MOUSE_CONFIG_FILE, cfg)


def _log(msg):
    LAST_MOUSE_LOG.append(msg)
    del LAST_MOUSE_LOG[:-400]


def open_mouse(cfg=None):
    """A KoneXPAir session on the configured transport. Caller holds MOUSE_LOCK and closes it."""
    cfg = cfg or load_mouse_config()
    kind = cfg.get("transport", "frida")
    if kind == "direct":
        path = cfg.get("path")
        if cfg.get("kill_swarm"):
            kill_swarm()
        t = make_transport("direct", path=path.encode() if isinstance(path, str) else path,
                           backend=cfg.get("backend", "dll"), log=_log)
    elif kind == "recording":
        t = make_transport("recording")
    else:
        t = make_transport("frida", wait_handle_s=float(cfg.get("wait_handle_s", 8)), log=_log)
    b5 = cfg.get("activate_b5", 1)
    return KoneXPAir(t, activate_b5=b5 if b5 == "slot" else int(b5),
                     header_mode=cfg.get("header_mode", "zero"),
                     preamble=bool(cfg.get("preamble")) and kind == "direct", log=_log)


def run_mouse_job(fn):
    """Run fn(mouse) under the lock, translating errors into a JSON-able result."""
    if not MOUSE_LOCK.acquire(timeout=0.5):
        return {"success": False, "error": "another mouse operation is still running"}
    try:
        del LAST_MOUSE_LOG[:]
        mouse = open_mouse()
        try:
            out = fn(mouse)
        finally:
            mouse.transport.close()
        out.setdefault("success", True)
        return out
    except TransportError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:  # keep the UI informative
        return {"success": False, "error": "%s: %s" % (type(e).__name__, e)}
    finally:
        MOUSE_LOCK.release()


def profile_for_push(profile):
    """Only the fields the mouse needs; DPI as stored (single int, or dpi_stages if present)."""
    dpi = profile.get("dpi_stages") or profile.get("dpi", 800)
    return {"name": profile.get("name", ""), "dpi": dpi,
            "keybinds": profile.get("keybinds") or {}, "easy_shift": profile.get("easy_shift") or {}}


def slot_assignments(boot_id):
    """[(slot_index, profile_dict), ...] for every assigned slot of a boot."""
    slots = load_slots().get(boot_id, [None] * 5)
    prof_map = {p["id"]: p for p in load_stored()}
    return [(i, prof_map[pid]) for i, pid in enumerate(slots) if pid and pid in prof_map]


@app.route("/api/mouse/status", methods=["GET"])
def mouse_status():
    cfg = load_mouse_config()
    info = {"success": True, "config": cfg, "swarm_running": None, "receiver_found": None, "log": LAST_MOUSE_LOG[-60:]}
    try:
        info["swarm_running"] = is_swarm_running()
    except Exception:
        pass
    try:
        from kone_xp_air.transport import find_dongle_path
        info["receiver_found"] = find_dongle_path() is not None
    except Exception as e:
        info["receiver_error"] = str(e)
    return jsonify(info)


@app.route("/api/mouse/config", methods=["GET", "PUT"])
def mouse_config():
    if request.method == "GET":
        return jsonify({"success": True, "config": load_mouse_config()})
    body = request.get_json() or {}
    cfg = load_mouse_config()
    for key in DEFAULT_MOUSE_CONFIG:
        if key in body:
            cfg[key] = body[key]
    if cfg.get("transport") not in ("frida", "direct", "recording"):
        return jsonify({"success": False, "error": "transport must be frida or direct"}), 400
    save_mouse_config(cfg)
    return jsonify({"success": True, "config": cfg})


@app.route("/api/mouse/log", methods=["GET"])
def mouse_log():
    return jsonify({"success": True, "log": LAST_MOUSE_LOG})


@app.route("/api/actions", methods=["GET"])
def list_actions():
    """Action names the encoder can put on the wire (hotkeys are 'Hotkey <mods>+<Key>')."""
    return jsonify({"success": True, "actions": kxp_actions.all_action_names(),
                    "keys": sorted(kxp_actions.HID_KEYS.keys()), "modifiers": list(kxp_actions.MODIFIER_BITS.keys())})


@app.route("/api/push-slot", methods=["POST"])
def push_slot():
    """Push the profile assigned to one onboard slot and leave the mouse on that slot.
    body: {boot_id, slot (1-5)}"""
    body = request.get_json() or {}
    boot_id = body.get("boot_id", "boot1")
    slot = int(body.get("slot", 0))
    if not 1 <= slot <= 5:
        return jsonify({"success": False, "error": "slot must be 1-5"}), 400
    assigned = dict(slot_assignments(boot_id))
    if slot - 1 not in assigned:
        return jsonify({"success": False, "error": "slot %d has no profile assigned" % slot}), 400
    profile = assigned[slot - 1]

    def job(mouse):
        summary = mouse.push_profile(slot - 1, profile_for_push(profile))
        return {"message": "Pushed %s to slot %d" % (profile["name"], slot), "pushed": [summary],
                "active_slot": slot - 1, "unsupported": summary["unsupported"]}
    return jsonify(run_mouse_job(job))


@app.route("/api/import-to-mouse", methods=["POST"])
def import_to_mouse():
    """Push profiles to the mouse.
    body: {boot_id, profile_id}  -> push that profile to every slot it is assigned to in boot_id
          {boot_id}              -> push every assigned slot, then return to the first assigned slot
          {boot_id, restore_slot}-> ... and return to that slot (1-5) instead"""
    body = request.get_json() or {}
    boot_id = body.get("boot_id", "boot1")
    profile_id = body.get("profile_id")
    assignments = slot_assignments(boot_id)
    if profile_id:
        assignments = [(i, p) for i, p in assignments if p["id"] == profile_id]
        if not assignments:
            return jsonify({"success": False, "error": "Assign this profile to an onboard slot (drag it onto 1-5) before pushing"}), 400
    if not assignments:
        return jsonify({"success": False, "error": "No profiles assigned to slots for %s" % boot_id}), 400
    restore = body.get("restore_slot")
    restore_slot = int(restore) - 1 if restore else (assignments[0][0] if len(assignments) > 1 else None)

    def job(mouse):
        pushed = mouse.push_slots([(i, profile_for_push(p)) for i, p in assignments], restore_slot=restore_slot)
        names = ", ".join("%s->%d" % (s["name"], s["slot"] + 1) for s in pushed)
        unsupported = [u for s in pushed for u in s["unsupported"]]
        return {"message": "Pushed " + names, "pushed": pushed,
                "active_slot": restore_slot if restore_slot is not None else pushed[-1]["slot"],
                "unsupported": unsupported}
    return jsonify(run_mouse_job(job))


@app.route("/api/switch-profile/<int:slot>", methods=["POST"])
def switch_profile(slot):
    """Switch the mouse to onboard slot 0-4 (no writes)."""
    if slot < 0 or slot > 4:
        return jsonify({"success": False, "error": "Slot must be 0-4"}), 400

    def job(mouse):
        mouse.switch_profile(slot)
        return {"message": "Switched to profile %d" % (slot + 1), "active_slot": slot}
    return jsonify(run_mouse_job(job))


@app.route("/api/mouse/read-pages", methods=["POST"])
def read_pages():
    """Raw page read-back for diagnostics. body: {cmd: 'buttons'|'profile', flag: 0|1}"""
    body = request.get_json() or {}
    cmd = kxp_protocol.CMD_BUTTONS if body.get("cmd") == "buttons" else kxp_protocol.CMD_PROFILE
    flag = int(body.get("flag", 1))

    def job(mouse):
        pages = mouse.read_raw_pages(cmd, flag, int(body.get("count", 5)))
        return {"pages": [p.hex(" ") for p in pages], "log": format_results(mouse.last_results)}
    return jsonify(run_mouse_job(job))


# ── Routes — Import Swarm II exports (.dat) ─────────────────────────────────
SWARM_SETTING_DIR = Path(os.environ.get("APPDATA", "")) / "Turtle Beach" / "Swarm II" / "Setting"
ONBOARD_FILE = SWARM_SETTING_DIR / "KONE_XP_AIR_Profile_Mgr.dat"


@app.route("/api/import-dat", methods=["POST"])
def import_dat():
    """Create/refresh stored profiles from a Swarm II .dat export (multipart 'file') or from the
    onboard container in %APPDATA% (body {source: 'onboard'}). Names come from the .dat when it has
    them, else from 'name' / 'names'."""
    raw = None
    names = []
    if "file" in request.files:
        raw = request.files["file"].read()
        names = [request.form.get("name") or Path(request.files["file"].filename).stem]
    else:
        body = request.get_json() or {}
        if body.get("source") == "onboard":
            if not ONBOARD_FILE.exists():
                return jsonify({"success": False, "error": "%s not found" % ONBOARD_FILE}), 404
            raw = ONBOARD_FILE.read_bytes()
            names = body.get("names") or []
    if raw is None:
        return jsonify({"success": False, "error": "send a .dat file or {source:'onboard'}"}), 400
    entries = kxp_datfile.read_profiles(raw)
    if not entries:
        return jsonify({"success": False, "error": "no Kone XP Air profile blocks found in that file"}), 400
    profiles = load_stored()
    created, updated = [], []
    for i, e in enumerate(entries):
        name = names[i] if i < len(names) and names[i] else "Imported %d" % (i + 1)
        sp = kxp_datfile.to_stored_profile(e, name)
        existing = next((p for p in profiles if p.get("name") == name), None)
        if existing:
            existing.update({k: sp[k] for k in ("dpi", "dpi_stages", "keybinds", "easy_shift")})
            updated.append(name)
        else:
            sp["id"] = make_id(name)
            profiles.append(sp)
            created.append(name)
    save_stored(profiles)
    return jsonify({"success": True, "created": created, "updated": updated,
                    "checksums_ok": [e.get("button_checksum_ok") for e in entries]})


# ── Routes — Live Swarm II INI Profiles (legacy, kept for the Sync button) ───
@app.route("/api/swarm/profiles", methods=["GET"])
def get_swarm_profiles():
    """Read live profile data from Swarm II's INI file."""
    try:
        from swarm_ini import read_profiles_from_ini
        profiles = read_profiles_from_ini()
        return jsonify({"success": True, "profiles": profiles})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import webbrowser
    print("\n  ROCCAT Manager running at http://localhost:5555\n")
    webbrowser.open("http://localhost:5555")
    app.run(host="127.0.0.1", port=5555, debug=False)
