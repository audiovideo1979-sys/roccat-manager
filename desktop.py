"""
ROCCAT Manager — native desktop app.

Renders the existing Flask UI inside a WebView window (pywebview) so there is no browser and no
localhost URL to type: double-click the exe and a window opens, like Swarm. Build a single .exe with
build.bat (which runs PyInstaller on Windows); run this file directly for a dev window.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "frozen", False):
    # dev: make server.py (under ROCCAT_Manager/) and the kone_xp_air package importable
    for p in (_HERE, os.path.join(_HERE, "ROCCAT_Manager")):
        if p not in sys.path:
            sys.path.insert(0, p)

import webview           # noqa: E402
from server import app  # the Flask application (ROCCAT_Manager/server.py)


def main():
    # Passing the Flask (WSGI) app makes pywebview serve it internally — no visible localhost port.
    webview.create_window(
        "ROCCAT Manager",
        app,
        width=1180,
        height=820,
        min_size=(920, 640),
    )
    webview.start()      # blocks until the window is closed


if __name__ == "__main__":
    main()
