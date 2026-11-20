"""
server.py  —  ROCCAT Manager backend
Run: python server.py
Opens at http://localhost:5555
"""

import hashlib
import json
import os
import sys
import re
import io
import shutil
import threading
import time
import zipfile
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file

FROZEN = getattr(sys, "frozen", False)   # running as a PyInstaller-built .exe
if not FROZEN and str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
import drivefolders  # noqa: E402  (finds Google Drive's "My Drive" on any drive letter)


def _bundle_base():
    # PyInstaller onefile extracts bundled data to sys._MEIPASS; in dev it's the source tree
    if FROZEN and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


# ── Where profiles live ───────────────────────────────────────────────────────
# Both dual-boot sides share one profile folder through Google Drive (SYNC_SETUP.md). The app finds it on its
# own, so neither side needs ROCCAT_MANAGER_DATA set: next to the program when the .exe runs from the Drive
# folder, or at My Drive\Claude Folder\Projects\Personal\ROCCAT Manager Data on whatever drive letter Google
# Drive for desktop uses on that side (drivefolders.py).
SHARED_DATA_NAME = "ROCCAT Manager Data"
MOVED_NOTE = "MOVED TO GOOGLE DRIVE.txt"   # left in this PC's own profiles folder once they were copied over
FROM_DEFAULTS = "from_defaults"            # in a shared stored.json first saved from the built-in defaults


def _local_data_dir():
    root = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~")
    return Path(root) / "ROCCAT Manager"


def shared_data_candidates(exe_path=None):
    """Folders that, if they already exist, are the Google Drive profile folder both sides share."""
    if exe_path:   # ...\ROCCAT_Manager_Full\ROCCAT Manager.exe -> ...\ROCCAT Manager Data
        yield Path(os.path.abspath(exe_path)).parent.parent / SHARED_DATA_NAME
    for d in drivefolders.personal_dirs():
        yield d / SHARED_DATA_NAME


def _is_dir(p):
    try:
        return p.is_dir()
    except OSError:
        return False


def resolve_data_dir(env=None, exe_path=None, candidates=None, local=None):
    """Pick the folder profiles live in. Returns (folder, how), how = "env", "shared" or "local":
    1. ROCCAT_MANAGER_DATA if set (created if missing); 2. the shared Google Drive folder, only if it already
    exists (never created here, so a typo can't start an empty profile set); 3. "ROCCAT Manager" in %APPDATA%."""
    env = os.environ if env is None else env
    override = env.get("ROCCAT_MANAGER_DATA")
    if override:
        try:
            d = Path(override)
            d.mkdir(parents=True, exist_ok=True)
            return d, "env"
        except OSError:
            pass
    for d in (shared_data_candidates(exe_path) if candidates is None else candidates):
        if _is_dir(d):
            return d, "shared"
    d = _local_data_dir() if local is None else local
    d.mkdir(parents=True, exist_ok=True)
    return d, "local"


def _same_folder(a, b):
    # not Path.resolve(): on Google Drive's virtual drive letter it can fail or return a volume path
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _read_json_file(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _without_active_slot(slots):
    return {k: v for k, v in slots.items() if k != "active_slot"} if isinstance(slots, dict) else slots


def has_real_profiles(folder, seed_dir):
    """True when the folder holds the user's own profiles: stored.json exists and it, or the slot assignments,
    differ from the shipped defaults (unchanged since March 2026, so equal means never edited; the remembered
    active slot doesn't count). A shared stored.json first saved from the built-in defaults, on a side that
    had no profiles of its own, is marked from_defaults and doesn't count either: it must not shut out the
    other side's real set. An unreadable stored.json counts as real: it is the user's, never disposable."""
    f = folder / "stored.json"
    if not f.is_file():
        return False
    data = _read_json_file(f)
    if data is None:
        return True
    if isinstance(data, dict) and data.get(FROM_DEFAULTS):
        return False
    if data != _read_json_file(seed_dir / "stored.json"):
        return True
    slots = _read_json_file(folder / "slots.json")
    seed_slots = _read_json_file(seed_dir / "slots.json")
    return slots is not None and _without_active_slot(slots) != _without_active_slot(seed_slots)


def _newer(a, b):
    """a was modified after b (2 s slack for coarse file times)."""
    try:
        return a.stat().st_mtime > b.stat().st_mtime + 2
    except OSError:
        return False


def _fingerprint(folder):
    """What this PC's profiles were when the note was written: stored.json + slot assignments (the
    remembered active slot left out: a profile switch is not an edit)."""
    stored = _read_json_file(folder / "stored.json")
    slots = _without_active_slot(_read_json_file(folder / "slots.json"))
    return hashlib.sha1(json.dumps([stored, slots], sort_keys=True).encode("utf-8")).hexdigest()


def _note_state(note):
    try:
        for line in note.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("state: "):
                return line[len("state: "):].strip()
    except OSError:
        pass
    return None


def _same_profiles(a, b):
    return (_read_json_file(a / "stored.json") == _read_json_file(b / "stored.json")
            and _without_active_slot(_read_json_file(a / "slots.json"))
            == _without_active_slot(_read_json_file(b / "slots.json")))


def _write_moved_note(local_profiles, shared_profiles):
    try:
        local_profiles.mkdir(parents=True, exist_ok=True)
        (local_profiles / MOVED_NOTE).write_text(
            "ROCCAT Manager keeps profiles in the Google Drive folder\n  %s\nso both boots share them. "
            "Anything in this folder is this PC's own old copy, kept as a backup.\n\nstate: %s\n"
            % (shared_profiles, _fingerprint(local_profiles)), encoding="utf-8")
    except OSError:
        pass


def migrate_local_profiles(shared_profiles, local_profiles, seed_dir, stamp=None):
    """First run against the shared folder: bring this PC's own profiles along, once. Returns
    "copied"      this PC's profiles were copied in (they stay here too, as a backup);
    "not-merged"  the shared folder already has other real profiles, which win; this PC's are left alone;
    None          nothing to do (no profiles of its own here, only the defaults, or already brought over).
    Only real profiles count on either side (see has_real_profiles), so a side that only ever had the
    defaults can't block or overwrite the other side's. Anything in the shared folder is backed up first.
    The note left here marks this PC as connected (even when there was nothing to bring), so this happens
    once: profiles changed here after that (an old copy of the app, or a session while Google Drive was
    off) are reported, never copied over the shared ones."""
    if _same_folder(shared_profiles, local_profiles):
        return None
    local_stored = local_profiles / "stored.json"
    note = local_profiles / MOVED_NOTE
    if not has_real_profiles(local_profiles, seed_dir):
        if not note.exists():
            _write_moved_note(local_profiles, shared_profiles)
        return None
    if note.exists():
        recorded = _note_state(note)
        changed = _fingerprint(local_profiles) != recorded if recorded else _newer(local_stored, note)
        if changed:                    # edited here after connecting: report it, never copy it over
            if _same_profiles(local_profiles, shared_profiles):
                _write_moved_note(local_profiles, shared_profiles)
                return None
            return "not-merged"
        if recorded is None:
            _write_moved_note(local_profiles, shared_profiles)       # add the fingerprint to an older note
        shared_data = _read_json_file(shared_profiles / "stored.json")
        if not (isinstance(shared_data, dict) and shared_data.get(FROM_DEFAULTS)):
            return None                # connected before, nothing changed here since
        # this PC's own profiles were brought over before, but Google Drive now holds the other side's copy
        # started from the examples instead (an edit there before the upload arrived): bring them in again.
        # Not when the shared file is merely missing: Drive may just not have caught up yet.
    if _read_json_file(local_stored) is None:
        return "not-merged"            # damaged: don't spread it to the other side; the user is told instead
    if has_real_profiles(shared_profiles, seed_dir):
        if _read_json_file(shared_profiles / "stored.json") == _read_json_file(local_stored):
            _write_moved_note(local_profiles, shared_profiles)    # already the same profiles (copied by hand)
            return None
        return "not-merged"
    shared_profiles.mkdir(parents=True, exist_ok=True)
    existing = sorted(shared_profiles.glob("*.json"))   # e.g. slots.json from a profile switch on the other side
    if existing:
        backup = shared_profiles / ("replaced-" + (stamp or time.strftime("%Y%m%d-%H%M%S")))
        backup.mkdir(parents=True, exist_ok=True)
        for f in existing:
            shutil.copy2(str(f), str(backup / f.name))
    # stored.json last: it is what marks the shared folder as holding real profiles, so a copy cut short is
    # simply redone on the next launch
    for f in sorted(local_profiles.glob("*.json"), key=lambda f: f.name == "stored.json"):
        shutil.copy2(str(f), str(shared_profiles / f.name))
    _write_moved_note(local_profiles, shared_profiles)
    return "copied"


# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
REPO_ROOT     = BASE_DIR.parent
BUNDLE_DIR    = _bundle_base()                 # where templates/static/seed data live
STATIC_DIR    = BUNDLE_DIR / "static"
TEMPLATES_DIR = BUNDLE_DIR / "templates"
# Profiles are user data: inside the exe the bundle is read-only, so they live in the shared Google Drive
# folder (or %APPDATA% when there is none). In dev they stay in the source tree.
if FROZEN:
    DATA_DIR, DATA_HOW = resolve_data_dir(exe_path=sys.executable)
else:
    DATA_DIR, DATA_HOW = BASE_DIR, "dev"
PROFILES_DIR  = DATA_DIR / "profiles"
SEED_DIR      = BUNDLE_DIR / "profiles"        # defaults shipped in the bundle, copied on first run
MIGRATION     = None                           # what the first run against the shared folder did (see above)

STORED_FILE = PROFILES_DIR / "stored.json"
SLOTS_FILE  = PROFILES_DIR / "slots.json"
MOUSE_CONFIG_FILE = PROFILES_DIR / "mouse_config.json"


def seed_profiles():
    """On first run of the packaged app with a this-PC-only folder, copy the shipped default profiles in.
    A shared folder is never seeded: the defaults are read from the bundle until the first save (see
    _profile_file), so they can't sync over, or be mistaken for, the other side's profiles."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("stored.json", "slots.json"):
        dst, src = PROFILES_DIR / name, SEED_DIR / name
        if not dst.exists() and src.exists():
            try:
                shutil.copy(src, dst)
            except OSError:
                pass


def prepare_profiles(local_profiles=None):
    """Startup of the packaged app: shared folder -> bring this PC's profiles in once; otherwise seed."""
    if DATA_HOW in ("shared", "env"):
        local_profiles = _local_data_dir() / "profiles" if local_profiles is None else local_profiles
        try:
            return migrate_local_profiles(PROFILES_DIR, local_profiles, SEED_DIR)
        except (OSError, ValueError):
            return "copy-failed"       # shown in the sidebar; the next launch tries again (never block startup)
    seed_profiles()
    return None


# kone_xp_air (protocol + transports) lives at the repo root in dev; it is bundled in the exe
if not FROZEN and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from kone_xp_air import protocol as kxp_protocol, actions as kxp_actions, datfile as kxp_datfile  # noqa: E402
from kone_xp_air.session import KoneXPAir  # noqa: E402
from kone_xp_air.transport import make_transport, TransportError, is_swarm_running, format_results, kill_swarm  # noqa: E402
from kone_xp_air.winput import release_modifiers  # noqa: E402

if FROZEN:
    MIGRATION = prepare_profiles()

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

def _profile_file(path):
    # shared folder, nothing saved there yet: read the shipped defaults straight from the bundle
    if DATA_HOW in ("shared", "env") and not path.exists() and (SEED_DIR / path.name).exists():
        return SEED_DIR / path.name
    return path

def profiles_source():
    """What a page loading profiles now would get: "none" (shared folder with nothing saved yet: the bundled
    examples), "examples" (a shared set started from the examples), or "saved". The page sends back what it
    loaded with every write; a write from a page whose profiles are out of date is refused."""
    if DATA_HOW in ("shared", "env"):
        if not STORED_FILE.exists():
            return "none"
        data = _read_json_file(STORED_FILE)
        if isinstance(data, dict) and data.get(FROM_DEFAULTS):
            return "examples"
    return "saved"

def load_stored():
    data = load_json(_profile_file(STORED_FILE))
    return data.get("profiles", [])

def save_stored(profiles):
    data = {"profiles": profiles}
    if DATA_HOW in ("shared", "env") and (not STORED_FILE.exists()
                                          or (_read_json_file(STORED_FILE) or {}).get(FROM_DEFAULTS)):
        # this side started from the built-in defaults (it had no profiles of its own): say so, so the other
        # side's real profiles still come in on its first run (has_real_profiles)
        data[FROM_DEFAULTS] = True
    save_json(STORED_FILE, data)

def load_slots():
    data = load_json(_profile_file(SLOTS_FILE))
    if not data:
        data = {"boot1": [None]*5, "boot2": [None]*5}
    return data

def save_slots(data):
    save_json(SLOTS_FILE, data)

def load_active_slot():
    """Onboard slot (0-4) the mouse was last set to by this app, or None if never set.
    The mouse keeps its active profile across power cycles and this app is how profiles get
    switched, so this is what the UI shows as 'currently on' at startup. It self-corrects on
    the next push/switch. Stored alongside the slot maps in slots.json."""
    v = load_json(SLOTS_FILE).get("active_slot")
    return v if isinstance(v, int) and 0 <= v <= 4 else None

def save_active_slot(slot):
    """Remember the active onboard slot so the next launch can show what the mouse is on."""
    if not (isinstance(slot, int) and 0 <= slot <= 4):
        return
    if DATA_HOW in ("shared", "env") and not STORED_FILE.exists():
        return      # shared folder with no profiles yet: don't start one (it would race the other side's in Drive)
    data = load_slots()
    data["active_slot"] = slot
    save_slots(data)

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
    return jsonify({"profiles": load_stored(), "source": profiles_source()})


# Writes that are harmless whatever profiles the page holds (keyboard fix, settings, diagnostics, a plain switch)
_ANY_PAGE_MAY_WRITE = ("/api/release-modifiers", "/api/mouse/config", "/api/mouse/read-pages", "/api/switch-profile/")

def _is_profile_write():
    return (request.method in ("POST", "PUT", "DELETE") and request.path.startswith("/api/")
            and not request.path.startswith(_ANY_PAGE_MAY_WRITE))

@app.before_request
def _refuse_writes_from_a_page_with_out_of_date_profiles():
    # e.g. the page opened before Google Drive delivered this side's profiles and still shows the built-in
    # examples, which share ids with the real set: a save now would write example data over a real profile.
    # A request without the header (tests, scripts) is not checked.
    sent = request.headers.get("X-Profiles-Source")
    if _is_profile_write() and sent is not None and sent != profiles_source():
        return jsonify({"success": False, "reload": True,
                        "error": "Your profiles just arrived from Google Drive, so nothing was changed. "
                                 "Reloading them now - then make that change again."}), 409
    return None

@app.after_request
def _tell_the_page_what_its_write_left(response):
    # the page's own first save in an empty shared folder turns "none" into "examples"; it follows along
    if _is_profile_write() and response.status_code < 400:
        response.headers["X-Profiles-Source"] = profiles_source()
    return response

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
    for boot, ids in slots.items():
        if isinstance(ids, list):          # slots.json also holds "active_slot", a plain number
            slots[boot] = [None if s == profile_id else s for s in ids]
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
    return jsonify({"boot": boot_id, "slots": resolved, "active_slot": load_active_slot()})

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
    "transport": "direct",     # "direct" = our own handle (confirmed on hardware); "frida" = via Swarm II
    "backend": "auto",         # direct only: "auto" (bundled hidapi, else Swarm's DLL), or force "hid"/"dll"
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
            # A profile switch can drop the "key up" of a button bound to a modifier, leaving it
            # stuck "held" in Windows. Clear any stuck modifier after every mouse op, best-effort.
            try:
                release_modifiers()
            except Exception:
                pass
        out.setdefault("success", True)
        # Remember which onboard slot the mouse is now on, so the next launch can show it.
        if out.get("success") and isinstance(out.get("active_slot"), int):
            try:
                save_active_slot(out["active_slot"])
            except Exception:
                pass
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


@app.route("/api/data-location", methods=["GET"])
def data_location():
    """Where profiles are saved, so each side can show it is using the shared Google Drive folder."""
    return jsonify({"success": True, "path": str(PROFILES_DIR), "how": DATA_HOW,
                    "shared": DATA_HOW in ("shared", "env"), "migration": MIGRATION,
                    "has_profiles": STORED_FILE.exists(), "source": profiles_source(),
                    "readable": not STORED_FILE.exists() or _read_json_file(STORED_FILE) is not None,
                    "local_path": str(_local_data_dir() / "profiles"),
                    # this PC has used the shared folder before (so "not found" now is worth a warning)
                    "was_shared": (_local_data_dir() / "profiles" / MOVED_NOTE).exists()})


@app.route("/api/release-modifiers", methods=["POST"])
def release_stuck_modifiers():
    """Send a key-up for every keyboard modifier, clearing any stuck 'held' Ctrl/Alt/Shift/Win.
    Deliberately does NOT take MOUSE_LOCK — it's an OS keyboard action, so it works even mid-push."""
    r = release_modifiers()
    return jsonify({"success": bool(r.get("ok")), "released": r.get("released", 0),
                    "note": r.get("skipped") or r.get("error") or ""})


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
