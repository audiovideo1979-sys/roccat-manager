"""
winstartup.py  —  "load my main profile when Windows starts", per Windows install.

The choice lives on THIS PC, not in the shared Google Drive folder: each dual-boot side has its own main
profile and its own registry. Turning it on:
  - copies the app to %LOCALAPPDATA%\\ROCCAT Manager\\app\\ROCCAT Manager.exe. At login Google Drive may not
    have mounted its drive letter yet, so a login entry pointing into Drive could silently fail to start;
  - adds HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run  "ROCCAT Manager" = "<that copy>" --startup.
At login that copy waits for the Google Drive profiles folder (when this PC shares through it), writes the
chosen slot's profile to the mouse and switches to it, then exits without opening a window (desktop.py).

Nothing here imports server.py: desktop.py uses this before the profiles folder is chosen.
"""
import json
import os
import shutil
import time
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ROCCAT Manager"
STARTUP_ARG = "--startup"
SETTINGS_NAME = "this_pc.json"
SHARED_DATA_NAME = "ROCCAT Manager Data"    # same as server.SHARED_DATA_NAME
MOVED_NOTE = "MOVED TO GOOGLE DRIVE.txt"    # same as server.MOVED_NOTE


def local_root(env=None):
    """%APPDATA%\\ROCCAT Manager: this PC's own folder (per Windows install)."""
    env = os.environ if env is None else env
    root = env.get("APPDATA") or env.get("XDG_DATA_HOME") or os.path.expanduser("~")
    return Path(root) / "ROCCAT Manager"


def installed_exe(env=None):
    """Where the copy that Windows starts at login lives (a local disk, always there at login)."""
    env = os.environ if env is None else env
    root = env.get("LOCALAPPDATA") or env.get("APPDATA") or os.path.expanduser("~")
    return Path(root) / "ROCCAT Manager" / "app" / "ROCCAT Manager.exe"


# ── the choice (this PC only) ─────────────────────────────────────────────────
def settings_file(env=None):
    return local_root(env) / SETTINGS_NAME


def load_settings(path=None):
    try:
        with open(path or settings_file()) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data, path=None):
    path = Path(path or settings_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def valid_choice(choice):
    return (isinstance(choice, dict) and choice.get("boot_id") in ("boot1", "boot2")
            and isinstance(choice.get("slot"), int) and 1 <= choice["slot"] <= 5)


# ── the Windows login entry ───────────────────────────────────────────────────
def _winreg():
    import winreg
    return winreg


def run_entry(reg=None):
    """The command Windows runs at login for this app, or None."""
    reg = reg or _winreg()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            value, _ = reg.QueryValueEx(key, RUN_VALUE)
            return value
    except OSError:
        return None


def set_run_entry(exe, reg=None):
    reg = reg or _winreg()
    with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        reg.SetValueEx(key, RUN_VALUE, 0, reg.REG_SZ, '"%s" %s' % (exe, STARTUP_ARG))


def remove_run_entry(reg=None):
    reg = reg or _winreg()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, RUN_VALUE)
    except OSError:
        pass        # not there: nothing to remove


# ── the local copy of the app ─────────────────────────────────────────────────
def _same_path(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def install_copy(src, dest):
    """Copy the app to dest unless dest already has this version or a newer one. Returns True if copied.
    Raises OSError if it can't (e.g. the local copy is running right now)."""
    src, dest = Path(src), Path(dest)
    if _same_path(src, dest):
        return False
    s = src.stat()
    try:
        d = dest.stat()
        if d.st_size == s.st_size and int(d.st_mtime) == int(s.st_mtime):
            return False                    # same version
        if int(d.st_mtime) > int(s.st_mtime):
            return False                    # never replace a newer copy with an older one
    except FileNotFoundError:
        pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".new")
    shutil.copy2(str(src), str(tmp))
    os.replace(str(tmp), str(dest))
    return True


def enable(choice, exe, reg=None, settings_path=None, dest=None):
    """Load choice = {boot_id, slot} at every Windows login on this PC."""
    if not valid_choice(choice):
        raise ValueError("choose a slot 1-5 of boot1 or boot2")
    dest = Path(dest or installed_exe())
    install_copy(exe, dest)
    set_run_entry(dest, reg)
    settings = load_settings(settings_path)
    settings["startup"] = {"boot_id": choice["boot_id"], "slot": choice["slot"]}
    save_settings(settings, settings_path)


def disable(reg=None, settings_path=None):
    remove_run_entry(reg)
    settings = load_settings(settings_path)
    settings.pop("startup", None)
    save_settings(settings, settings_path)


def refresh_installed_copy(current_exe, reg=None, dest=None):
    """The app was opened from somewhere else (e.g. a newer copy in Google Drive) while the login entry is
    on: bring the local copy up to date so the next login runs this version. Best effort."""
    dest = Path(dest or installed_exe())
    entry = run_entry(reg)
    if not entry or os.path.normcase(str(dest)) not in os.path.normcase(entry):
        return False
    try:
        return install_copy(current_exe, dest)
    except OSError:
        return False


# ── at login ──────────────────────────────────────────────────────────────────
def this_pc_shares(env=None):
    """This PC keeps its profiles in the shared Google Drive folder (it has connected to it before)."""
    env = os.environ if env is None else env
    return bool(env.get("ROCCAT_MANAGER_DATA")) or (local_root(env) / "profiles" / MOVED_NOTE).exists()


def shared_profiles_ready(find, env=None):
    """Google Drive is up and the shared profiles are there (find = drivefolders.find)."""
    env = os.environ if env is None else env
    folder = Path(env["ROCCAT_MANAGER_DATA"]) if env.get("ROCCAT_MANAGER_DATA") else find(SHARED_DATA_NAME)
    try:
        return folder is not None and (Path(folder) / "profiles" / "stored.json").is_file()
    except OSError:
        return False


def wait_for(ready, timeout=180, interval=3, sleep=time.sleep, clock=time.monotonic):
    end = clock() + timeout
    while True:
        if ready():
            return True
        if clock() >= end:
            return False
        sleep(interval)


def run_at_login(load, find, log=print, settings_path=None, env=None, wait=wait_for):
    """What the copy started at login does. load(boot_id, slot) writes that slot to the mouse
    (server.load_startup_profile). Returns a short outcome for the log."""
    choice = load_settings(settings_path).get("startup")
    if not valid_choice(choice):
        log("startup: no main profile chosen on this PC; nothing to do")
        return "nothing-chosen"
    if this_pc_shares(env) and not wait(lambda: shared_profiles_ready(find, env)):
        log("startup: the Google Drive profiles folder did not appear; nothing was loaded")
        return "no-drive"
    result = load(choice["boot_id"], choice["slot"])
    log("startup: %s" % (result,))
    return "loaded" if result.get("success") else "failed"
