"""
winput.py — clear stuck keyboard modifiers on Windows.

A mouse button bound to a keyboard modifier (Ctrl/Alt/Shift/Win) sends "modifier down" on press and
"up" on release. When the app switches the mouse's onboard profile, that release can be dropped across
the layout change, leaving the modifier held in Windows — the keyboard then acts dead (every key is
Ctrl+key / Alt+key). Because this app runs in the user's own desktop session, it can send synthetic
key-UP events to release those modifiers.

Uses only stdlib ctypes (already used for HID I/O) — no extra dependency. No-op off Windows so the
test suite and Linux dev are unaffected.
"""
import sys

# Virtual-key codes for every keyboard modifier (left/right + generic).
_MODIFIER_VKS = [
    0x11,  # VK_CONTROL
    0xA2,  # VK_LCONTROL
    0xA3,  # VK_RCONTROL
    0x10,  # VK_SHIFT
    0xA0,  # VK_LSHIFT
    0xA1,  # VK_RSHIFT
    0x12,  # VK_MENU (Alt)
    0xA4,  # VK_LMENU
    0xA5,  # VK_RMENU
    0x5B,  # VK_LWIN
    0x5C,  # VK_RWIN
]

IS_WINDOWS = sys.platform.startswith("win")


def _release_windows(vks):
    import ctypes
    from ctypes import wintypes

    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _INPUTunion(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

    events = (INPUT * len(vks))()
    for i, vk in enumerate(vks):
        events[i].type = INPUT_KEYBOARD
        events[i].u.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    sent = ctypes.windll.user32.SendInput(len(events), ctypes.byref(events), ctypes.sizeof(INPUT))
    return int(sent)


def release_modifiers():
    """Send a key-UP for every keyboard modifier, clearing any that got stuck 'held'.

    Returns a dict: {'ok': bool, 'released': <count of key-ups sent>, 'skipped'|'error': ...}.
    Never raises — callers use it as a best-effort safety net.
    """
    if not IS_WINDOWS:
        return {"ok": True, "released": 0, "skipped": "not Windows"}
    try:
        sent = _release_windows(_MODIFIER_VKS)
        return {"ok": True, "released": sent}
    except Exception as e:  # never let a safety net take down a push
        return {"ok": False, "released": 0, "error": "%s: %s" % (type(e).__name__, e)}


if __name__ == "__main__":
    print(release_modifiers())
