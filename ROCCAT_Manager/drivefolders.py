"""
drivefolders.py  —  find the Google Drive "Personal" projects folder on this PC.

Google Drive for desktop puts "My Drive" on its own drive letter (G: by default, but the letter can differ
between the two dual-boot sides) or, in "mirror files" mode, under the user's home folder. Both the app
(server.py, for the shared profile folder) and build.bat (to copy the new .exe into Drive) use this, so neither
side needs a hard-coded drive letter.

Run as a script to print the path of a folder inside it, or nothing if it isn't there:
    python drivefolders.py ROCCAT_Manager_Full
"""
import os
import sys
from pathlib import Path

PERSONAL = Path("My Drive") / "Claude Folder" / "Projects" / "Personal"

DRIVE_FIXED, DRIVE_REMOTE, DRIVE_RAMDISK = 3, 4, 6


def drive_roots():
    """Drive roots worth looking at, G: first. Removable and optical drives are skipped: asking an empty
    card reader or DVD drive for a folder can pop up a "There is no disk in the drive" box."""
    if os.name != "nt":
        return []
    import ctypes
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    letters = sorted((chr(65 + i) for i in range(26) if mask & (1 << i)), key=lambda c: (c != "G", c))
    roots = []
    for c in letters:
        root = c + ":\\"
        if k32.GetDriveTypeW(ctypes.c_wchar_p(root)) in (DRIVE_FIXED, DRIVE_REMOTE, DRIVE_RAMDISK):
            roots.append(Path(root))
    return roots


def personal_dirs():
    """Every place the Personal projects folder could be, most likely first."""
    yield Path.home() / PERSONAL
    for root in drive_roots():
        yield root / PERSONAL


def find(name):
    """The first existing folder called `name` inside the Personal projects folder, or None."""
    for d in personal_dirs():
        p = d / name
        try:
            if p.is_dir():
                return p
        except OSError:
            pass
    return None


if __name__ == "__main__":
    found = find(sys.argv[1]) if len(sys.argv) > 1 else None
    if found:
        print(found)
