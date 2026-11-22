"""
ROCCAT Manager — native desktop app.

Renders the existing Flask UI inside a WebView window (pywebview): no browser, no localhost URL —
double-click the exe and a window opens, like Swarm. Build a single .exe with build.bat.

A windowed (no-console) exe has no stdout/stderr; anything that writes to them would crash the app on
launch. So before importing anything that might log, redirect output to a log file, and wrap startup so
any failure is written there and shown in a message box instead of silently closing.
"""
import os
import sys
import traceback

FROZEN = getattr(sys, "frozen", False)


def _data_dir():
    root = os.environ.get("APPDATA") or os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~")
    d = os.path.join(root, "ROCCAT Manager")
    os.makedirs(d, exist_ok=True)
    return d


def _log_path():
    return os.path.join(_data_dir(), "startup.log")


class _NullStream:
    def write(self, *a):
        return 0

    def flush(self):
        pass


# In a windowed exe sys.stdout/sys.stderr are None. Give them a real destination so stray prints and
# library logging can never take the app down, and so errors are captured.
if FROZEN or sys.stdout is None or sys.stderr is None:
    try:
        _fh = open(_log_path(), "a", buffering=1, encoding="utf-8")
        sys.stdout = _fh
        sys.stderr = _fh
    except Exception:
        sys.stdout = sys.stderr = _NullStream()

_HERE = os.path.dirname(os.path.abspath(__file__))
if not FROZEN:
    for p in (_HERE, os.path.join(_HERE, "ROCCAT_Manager")):
        if p not in sys.path:
            sys.path.insert(0, p)


def _fatal(exc):
    """Record a startup failure and tell the user where to look, instead of vanishing."""
    try:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write("\n=== startup failure ===\n")
            traceback.print_exc(file=f)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "ROCCAT Manager could not start.\n\nDetails were written to:\n%s\n\n%s"
            % (_log_path(), exc),
            "ROCCAT Manager",
            0x10,  # MB_ICONERROR
        )
    except Exception:
        pass


_INSTANCE_MUTEX = None   # held for the life of the process


def _only_instance():
    """True if no other ROCCAT Manager is running (Windows named mutex). Two copies must never write to the
    mouse at once, and the copy started at login may still be loading the main profile."""
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    handle = k32.CreateMutexW(None, False, "Local\\ROCCATManager.SingleInstance")
    err = ctypes.get_last_error()
    if not handle:              # e.g. ERROR_ACCESS_DENIED: a copy started "as administrator" holds it
        return False
    if err == 183:              # ERROR_ALREADY_EXISTS
        k32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _INSTANCE_MUTEX = handle
    return True


def _message(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, "ROCCAT Manager", 0x40)   # MB_ICONINFORMATION
    except Exception:
        pass


def _log(text):
    import time as _time
    print("%s %s" % (_time.strftime("%Y-%m-%d %H:%M:%S"), text))


def run_at_login():
    """Started by Windows at login (--startup): load this PC's main profile onto the mouse, then exit.
    No window, no error boxes (everything goes to startup.log), and never longer than 10 minutes."""
    import threading
    watchdog = threading.Timer(600, os._exit, (3,))
    watchdog.daemon = True
    watchdog.start()
    try:
        import winstartup
        import drivefolders
        os.environ["ROCCAT_MANAGER_AT_LOGIN"] = "1"     # server.py: read only, no first-run copying

        def load(choice):
            import server   # only now: the profiles folder is chosen when server is imported
            return server.load_startup_profile(choice["boot_id"], choice["slot"], shared=choice.get("shared", False))
        winstartup.run_at_login(load, drivefolders.find, log=_log)
    except Exception:
        _log("startup: failed:\n" + traceback.format_exc())


def main():
    import winstartup
    at_login = winstartup.STARTUP_ARG in sys.argv[1:]
    if not _only_instance():
        if not at_login:
            _message("ROCCAT Manager is already open, or it is loading your main profile onto the mouse "
                     "(after Windows starts that can take a minute or two while Google Drive starts up)."
                     "\n\nTry again in a moment.")
        return
    if at_login:
        run_at_login()
        return
    if FROZEN:   # opened from Google Drive (maybe a newer version): update the copy Windows starts at login
        import threading
        threading.Thread(target=winstartup.refresh_installed_copy, args=(sys.executable,), daemon=True).start()

    import webview
    from server import app  # the Flask application (ROCCAT_Manager/server.py)

    # Passing the Flask (WSGI) app makes pywebview serve it internally — no visible localhost port.
    webview.create_window(
        "ROCCAT Manager",
        app,
        width=1180,
        height=820,
        min_size=(920, 640),
    )
    webview.start()  # blocks until the window is closed


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never close silently
        _fatal(exc)
        raise
