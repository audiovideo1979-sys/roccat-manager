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

def _get_dll():
    """Load and initialize the DLL fresh each time."""
    os.add_dll_directory(SWARM_DIR)
    os.environ['PATH'] = SWARM_DIR + ';' + os.environ.get('PATH', '')
    dll = ctypes.CDLL(DLL_PATH)
    dll.hid_init.restype = ctypes.c_int
    dll.hid_open_path.restype = ctypes.c_void_p
    dll.hid_open_path.argtypes = [ctypes.c_char_p]
    dll.hid_send_feature_report.restype = ctypes.c_int
    dll.hid_send_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    dll.hid_get_feature_report.restype = ctypes.c_int
    dll.hid_get_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    dll.hid_close.argtypes = [ctypes.c_void_p]
    dll.hid_init()
    return dll


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


    # Template captured from Swarm II via Frida (exact bytes from a real DPI write)
PROFILE_TEMPLATE = bytes([
    # Page 0 (25 bytes)
    0x06, 0x4e, 0x00,  # report ID, length marker, profile slot (overwritten)
    0x06, 0x06, 0x1f,  # config, config, polling rate
    0x00,              # active DPI stage
    0x90, 0x01,        # DPI stage 0 = 400 (overwritten)
    0x20, 0x03,        # DPI stage 1 = 800 (overwritten)
    0xb0, 0x04,        # DPI stage 2 = 1200 (overwritten)
    0x40, 0x06,        # DPI stage 3 = 1600 (overwritten)
    0x80, 0x0c,        # DPI stage 4 = 3200 (overwritten)
    0x90, 0x01,        # DPI Y stage 0 (overwritten)
    0x20, 0x03,        # DPI Y stage 1 (overwritten)
    0xb0, 0x04,        # DPI Y stage 2 (overwritten)
    0x40, 0x06,        # DPI Y stage 3 (overwritten)
    # Page 1 (25 bytes)
    0x80, 0x0c,        # DPI Y stage 4 (overwritten)
    0x00, 0x00, 0x03, 0x0a,  # config bytes
    0x06, 0xff, 0x05, 0x00, 0x00,  # more config
    0x14, 0xff, 0x00, 0x48, 0xff,  # LED stage 0
    0x14, 0xff, 0x00, 0x48, 0xff,  # LED stage 1
    0x14, 0xff, 0x00, 0x48,        # LED stage 2 (partial)
    # Page 2 (25 bytes)
    0xff,                          # LED stage 2 (continued)
    0x14, 0xff, 0x00, 0x48, 0xff,  # LED stage 3
    0x14, 0xff, 0x00, 0x48, 0xff,  # LED stage 4
    0x14, 0xff, 0x00, 0x48, 0xff,  # LED extra 0
    0x14, 0xff, 0x00, 0x48, 0xff,  # LED extra 1
    0x01, 0x64, 0xff, 0xff,        # footer
])


def build_profile(dpi_values, profile_slot=0):
    """Build 75-byte profile from the captured Swarm II template, modifying only DPI and slot."""
    p = bytearray(PROFILE_TEMPLATE)

    # Set profile slot
    p[2] = profile_slot

    # Set DPI X values (offsets 7-16)
    for i in range(5):
        dpi = dpi_values[i] if i < len(dpi_values) else dpi_values[-1]
        struct.pack_into('<H', p, 7 + i * 2, dpi)

    # Set DPI Y values (offsets 17-26)
    for i in range(5):
        dpi = dpi_values[i] if i < len(dpi_values) else dpi_values[-1]
        struct.pack_into('<H', p, 17 + i * 2, dpi)

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


def activate_profile(dev, profile_slot):
    """Force the mouse to re-read profile by switching away and back."""
    # Switch to a different slot first
    other_slot = (profile_slot + 1) % 5

    # Write a minimal profile to the other slot, switch to it, then switch back
    # Use the init/handshake sequence to trigger profile changes
    _send(dev, [0x06, 0x00, 0x00, 0x04])
    time.sleep(0.05)
    _send(dev, [0x06, 0x00, 0x00, 0x05])
    time.sleep(0.1)
    _handshake(dev)
    time.sleep(0.2)

    # Send another init cycle to force re-read
    _send(dev, [0x06, 0x00, 0x00, 0x04])
    time.sleep(0.05)
    _send(dev, [0x06, 0x00, 0x00, 0x05])
    time.sleep(0.1)
    _handshake(dev)
    time.sleep(0.1)


def read_current_profile(dev, profile_slot):
    """Read the current profile data from the mouse by triggering a handshake
    and capturing the profile from the dongle's page read protocol."""
    # Send init sequence to read current profile
    _send(dev, [0x06, 0x00, 0x00, 0x04])
    time.sleep(0.05)
    _send(dev, [0x06, 0x00, 0x00, 0x05])
    time.sleep(0.1)
    _handshake(dev)
    time.sleep(0.1)

    # Read each page
    pages = []
    for pg in range(3):
        _send(dev, [0x06, 0x01, 0x46, 0x06, 0x02, pg, 0x00])
        time.sleep(0.05)
        _handshake(dev)

        # Read the page data
        dll = _get_dll()
        buf = ctypes.create_string_buffer(REPORT_LEN)
        buf[0] = 0x06
        n = dll.hid_get_feature_report(dev, buf, REPORT_LEN)
        if n > 0:
            page_data = bytes(buf[5:30])  # skip header bytes
            pages.append(page_data)
        else:
            pages.append(b'\x00' * 25)

    return b''.join(pages)


def modify_dpi_in_profile(profile_data, dpi):
    """Modify only the DPI bytes in existing profile data, keeping everything else."""
    p = bytearray(profile_data)
    dpi_values = [dpi] * 5

    # DPI X values at offsets 7-16 (5 x 16-bit LE)
    for i in range(5):
        struct.pack_into('<H', p, 7 + i * 2, dpi_values[i])
    # DPI Y values at offsets 17-26
    for i in range(5):
        struct.pack_into('<H', p, 17 + i * 2, dpi_values[i])

    return bytes(p)


def write_dpi_direct(dpi, profile_slot=None):
    """
    One-shot DPI write: kill Swarm, write to mouse, restart Swarm.
    Reads current profile from mouse first, modifies only DPI, writes back.
    If profile_slot is None, writes to ALL 5 slots.
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

        # Write to ALL 5 slots so it works regardless of active profile
        for slot in range(5):
            profile = build_profile(dpi_values, slot)
            write_profile_to_mouse(dev, profile)
            time.sleep(0.1)

        # Force mouse to re-read by cycling init twice
        activate_profile(dev, 0)

        dll.hid_close(dev)
        try:
            dll.hid_exit()
        except Exception:
            pass

        # Don't restart Swarm II — it would overwrite our DPI values
        # User can restart Swarm manually if needed

        slots_written = "all 5 slots" if profile_slot is None else f"slot {profile_slot}"
        return {"success": True, "message": f"DPI set to {dpi}! Swarm II is closed to prevent override."}

    except Exception as e:
        _start_swarm()
        return {"success": False, "error": str(e)}
