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


def main():
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
