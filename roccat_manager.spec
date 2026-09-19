# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ROCCAT Manager (native desktop app).
# Build:  python -m PyInstaller --noconfirm --clean roccat_manager.spec   (see build.bat)
# Windowed by default; set RM_DEBUG=1 to get a console build that prints startup errors.
import os
from PyInstaller.utils.hooks import collect_all

DEBUG = bool(os.environ.get("RM_DEBUG"))

# Data bundled inside the exe (found at runtime via sys._MEIPASS; see server.py _bundle_base()).
datas = [
    ("ROCCAT_Manager/templates", "templates"),
    ("ROCCAT_Manager/static", "static"),
    ("ROCCAT_Manager/profiles/stored.json", "profiles"),
    ("ROCCAT_Manager/profiles/slots.json", "profiles"),
    ("kone_xp_air/frida_executor.js", "kone_xp_air"),
]
binaries = []
hiddenimports = [
    "clr",            # pywebview's Windows backend (WebView2 via pythonnet)
    "_frida",         # frida's native extension (lazy-imported by transport.py)
    "server",
    "kone_xp_air", "kone_xp_air.transport", "kone_xp_air.session", "kone_xp_air.protocol",
    "kone_xp_air.actions", "kone_xp_air.sequences", "kone_xp_air.datfile",
    # legacy .dat export helpers, imported lazily by some routes
    "SWARM_II_DAT_FORMAT", "dat_export",
]

# Pull in everything these packages need (native libs, data, submodules).
for pkg in ("webview", "flask", "jinja2", "werkzeug", "frida", "hid", "clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # a package that is not installed / not collectable is skipped
        print("collect_all(%s) skipped: %s" % (pkg, exc))

a = Analysis(
    ["desktop.py"],
    pathex=[".", "ROCCAT_Manager"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", "matplotlib", "numpy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# One EXE containing everything (a.binaries + a.datas, no COLLECT) => a single-file .exe.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ROCCAT Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=DEBUG,
    disable_windowed_traceback=False,
    icon=None,
)
