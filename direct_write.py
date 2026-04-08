"""
direct_write.py — Write profiles directly to Kone XP Air via KONE_XP_AIR.dll's HIDAPI.
Protocol decoded via Frida capture of Swarm II's actual write sequence.
"""
import ctypes
import os
import struct
import subprocess
import time

# ── DLL Setup ────────────────────────────────────────────────────────────────
SWARM_DIR = r'C:\Program Files\Turtle Beach Swarm II'
DLL_PATH = os.path.join(SWARM_DIR, 'Data', 'Devices', 'KONE_XP_AIR', 'KONE_XP_AIR.dll')

REPORT_LEN = 30

_dll = None

def _get_dll():
    global _dll
    if _dll is None:
        os.add_dll_directory(SWARM_DIR)
        os.environ['PATH'] = SWARM_DIR + ';' + os.environ.get('PATH', '')
        _dll = ctypes.CDLL(DLL_PATH)
        _dll.hid_init.restype = ctypes.c_int
        _dll.hid_open_path.restype = ctypes.c_void_p
        _dll.hid_open_path.argtypes = [ctypes.c_char_p]
        _dll.hid_send_feature_report.restype = ctypes.c_int
        _dll.hid_send_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        _dll.hid_get_feature_report.restype = ctypes.c_int
        _dll.hid_get_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        _dll.hid_close.argtypes = [ctypes.c_void_p]
        _dll.hid_init()
    return _dll


def _pad(data):
    return bytes(data) + b'\x00' * (REPORT_LEN - len(data))


def _send(dev, data):
    dll = _get_dll()
    return dll.hid_send_feature_report(dev, _pad(data), REPORT_LEN)


def _get(dev):
    dll = _get_dll()
    buf = ctypes.create_string_buffer(REPORT_LEN)
    buf[0] = 0x06
    return dll.hid_get_feature_report(dev, buf, REPORT_LEN)


def _handshake(dev):
    _send(dev, [0x06, 0x01, 0x44, 0x07])
    time.sleep(0.1)
    _get(dev)
    time.sleep(0.05)


def _find_dongle():
    import hid
    for d in hid.enumerate(0x10F5, 0x5017):
        if d['usage_page'] == 0xFF03:
            return d['path']
    return None


def _kill_swarm():
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Swarm II.exe'], capture_output=True)
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Device Service.exe'], capture_output=True)
    subprocess.run(['taskkill', '/f', '/im', 'ROCCAT_Swarm_Monitor.exe'], capture_output=True)
    time.sleep(2)


def _start_swarm():
    svc = os.path.join(SWARM_DIR, 'Turtle Beach Device Service.exe')
    exe = os.path.join(SWARM_DIR, 'Turtle Beach Swarm II.exe')
    if os.path.exists(svc):
        subprocess.Popen([svc])
    time.sleep(2)
    if os.path.exists(exe):
        subprocess.Popen([exe])


def build_profile(dpi_values, profile_slot=0, polling_rate=0x1f):
    """Build 75-byte profile data block."""
    p = bytearray(75)
    p[0] = 0x06
    p[1] = 0x4E
    p[2] = profile_slot
    p[3] = 0x06
    p[4] = 0x06
    p[5] = polling_rate
    p[6] = 0x00  # active DPI stage

    for i in range(5):
        dpi = dpi_values[i] if i < len(dpi_values) else dpi_values[-1]
        struct.pack_into('<H', p, 7 + i * 2, dpi)
        struct.pack_into('<H', p, 17 + i * 2, dpi)

    p[27:36] = bytes([0x00, 0x00, 0x03, 0x0a, 0x06, 0xff, 0x05, 0x00, 0x00])

    for i in range(7):
        off = 36 + i * 5
        if off + 4 < len(p):
            p[off:off+5] = bytes([0x14, 0xFF, 0x00, 0x48, 0xFF])

    p[71:75] = bytes([0x01, 0x64, 0xFF, 0xFF])
    return bytes(p)


def write_profile_to_mouse(dev, profile_data):
    """Write profile using the exact Swarm II protocol."""
    pages = [profile_data[i*25:(i+1)*25] for i in range(3)]
    checksum = sum(profile_data) & 0xFFFF

    for pg in range(3):
        _send(dev, [0x06, 0x01, 0x46, 0x06, 0x02, pg, 0x01])
        time.sleep(0.05)
        _handshake(dev)
        _send(dev, [0x06, 0x01, 0x46, 0x06, 0x19] + list(pages[pg]))
        time.sleep(0.05)
        _handshake(dev)

    _send(dev, [0x06, 0x01, 0x46, 0x06, 0x02, 0x03, 0x01])
    time.sleep(0.05)
    _handshake(dev)

    cs_lo = checksum & 0xFF
    cs_hi = (checksum >> 8) & 0xFF
    _send(dev, [0x06, 0x01, 0x46, 0x06, 0x03, 0xFF, cs_lo, cs_hi])
    time.sleep(0.05)
    _handshake(dev)


def write_dpi_direct(dpi, profile_slot=0):
    """
    One-shot DPI write: kill Swarm, write to mouse, restart Swarm.
    Returns dict with success/message/error.
    """
    try:
        _kill_swarm()

        path = _find_dongle()
        if not path:
            _start_swarm()
            return {"success": False, "error": "Dongle not found"}

        dll = _get_dll()
        dev = dll.hid_open_path(path)
        if not dev:
            _start_swarm()
            return {"success": False, "error": "Could not open device"}

        dpi_values = [dpi] * 5
        profile = build_profile(dpi_values, profile_slot)
        write_profile_to_mouse(dev, profile)
        dll.hid_close(dev)

        _start_swarm()

        return {"success": True, "message": f"DPI set to {dpi} on the mouse!"}

    except Exception as e:
        _start_swarm()
        return {"success": False, "error": str(e)}
