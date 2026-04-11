"""
Push button mappings to mouse by impersonating Swarm II's pipe server.

Flow:
1. Edit KONE_XP_AIR_TB.ini with desired button mappings
2. Write our pipe name to SWARM.ini
3. Create a named pipe server
4. Kill/restart Device Service so it connects to our pipe
5. Send the INI data through the pipe
6. Device Service pushes settings to mouse
"""
import ctypes
import ctypes.wintypes as wt
import time
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ROCCAT_Manager'))

SWARM_DIR = r'C:\Program Files\Turtle Beach Swarm II'
SETTING_DIR = os.path.join(os.environ.get('APPDATA', ''), 'Turtle Beach', 'Swarm II', 'Setting')
SWARM_INI = os.path.join(SETTING_DIR, 'SWARM.ini')
DEVICE_INI = os.path.join(SETTING_DIR, 'KONE_XP_AIR_TB.ini')

OUR_PIPE_NAME = 'tb_swarm_ii_77777777'

k32 = ctypes.windll.kernel32
k32.CreateNamedPipeW.restype = wt.HANDLE
k32.CreateNamedPipeW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPVOID]
k32.ConnectNamedPipe.argtypes = [wt.HANDLE, wt.LPVOID]
k32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPVOID]
k32.ReadFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPVOID]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.DisconnectNamedPipe.argtypes = [wt.HANDLE]

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000


def write_pipe(handle, data):
    written = wt.DWORD(0)
    buf = ctypes.create_string_buffer(data)
    k32.WriteFile(handle, buf, len(data), ctypes.byref(written), None)
    return written.value


def set_pipe_name_in_swarm_ini(pipe_name):
    """Write our pipe name to SWARM.ini so Device Service finds us."""
    with open(SWARM_INI, 'r') as f:
        content = f.read()

    import re
    new_content = re.sub(
        r'tb_swarm_ii=tb_swarm_ii_\d+',
        f'tb_swarm_ii={pipe_name}',
        content
    )

    with open(SWARM_INI, 'w') as f:
        f.write(new_content)

    print(f'SWARM.ini updated: pipe name = {pipe_name}')


def edit_buttons_in_ini(keybinds):
    """Edit button mappings in the device INI file."""
    from swarm_ini import (read_ini, extract_field, decode_qt_bytearray,
                           encode_qt_bytearray, backup_ini, INI_FILE, HID_BY_NAME)

    raw = read_ini()
    btn_data, start, end = extract_field(raw, 'm_btn_setting')
    if not btn_data:
        print('No button data in INI')
        return False

    decoded = decode_qt_bytearray(btn_data)
    new_decoded = bytearray(decoded)

    # Apply keybind changes
    # For now, just handle thumb_button_1 as a test
    # TODO: full keybind encoder
    if 'thumb_button_1' in keybinds:
        action = keybinds['thumb_button_1']
        if action.startswith('Hotkey '):
            key = action[7:]
            scancode = HID_BY_NAME.get(key, 0)
            if scancode:
                # Find and replace the scancode at the thumb_button_1 position
                # Search for Q (0x14) or whatever is currently there
                for i in range(len(new_decoded) - 3):
                    if (new_decoded[i+1] == 0x00 and new_decoded[i+2] == 0x06 and
                            new_decoded[i+3] == 0x00 and new_decoded[i] not in (0x00, 0x06)):
                        # This is a keyboard entry — check if it's in the right position
                        # For now just replace the first Q we find
                        if new_decoded[i] == 0x14:  # Q
                            new_decoded[i] = scancode
                            print(f'Changed key 0x14 -> 0x{scancode:02x} at offset {i}')
                            break

    backup_ini()
    re_encoded = encode_qt_bytearray(bytes(new_decoded))
    new_raw = raw[:start] + re_encoded + raw[end:]
    with open(INI_FILE, 'wb') as f:
        f.write(new_raw)
    print('Device INI updated')
    return True


def push_buttons():
    """Main flow: edit INI, create pipe, restart Device Service, send data."""

    # Step 1: Edit the button data in the INI
    edit_buttons_in_ini({'thumb_button_1': 'Hotkey Delete'})

    # Step 2: Kill Swarm II and Device Service
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Swarm II.exe'], capture_output=True)
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Device Service.exe'], capture_output=True)
    subprocess.run(['taskkill', '/f', '/im', 'ROCCAT_Swarm_Monitor.exe'], capture_output=True)
    time.sleep(2)
    print('All processes killed')

    # Step 3: Write our pipe name to SWARM.ini
    set_pipe_name_in_swarm_ini(OUR_PIPE_NAME)

    # Step 4: Create our named pipe server
    pipe_path = "\\\\.\\pipe\\" + OUR_PIPE_NAME
    print(f'Creating pipe: {pipe_path}')

    h = k32.CreateNamedPipeW(
        pipe_path, PIPE_ACCESS_DUPLEX, PIPE_TYPE_BYTE | PIPE_WAIT,
        1, 65536, 65536, 30000, None  # 30s timeout
    )
    INVALID = wt.HANDLE(-1).value & 0xFFFFFFFFFFFFFFFF
    if h == INVALID or h == 0:
        print(f'Pipe creation failed: {ctypes.get_last_error()}')
        return False

    print('Pipe created')

    # Step 5: Start Device Service — it will read SWARM.ini and connect to our pipe
    print('Starting Device Service...')
    subprocess.Popen([os.path.join(SWARM_DIR, 'Turtle Beach Device Service.exe')])

    # Wait for connection
    print('Waiting for Device Service to connect...')
    result = k32.ConnectNamedPipe(h, None)
    print(f'Device Service CONNECTED! (result={result})')

    # Step 6: Send the INI data (same format as Swarm II)
    ini_data = open(DEVICE_INI, 'rb').read()

    # Header: PID + identity
    pid = os.getpid()
    header = f'{pid}\nTurtle Beach Swarm II\nPERSONAL\n'.encode('ascii')

    n1 = write_pipe(h, header)
    print(f'Sent header: {n1} bytes')

    # Send INI in chunks (Swarm sends it in ~3405 byte chunks)
    # But first, let's try sending it all at once
    n2 = write_pipe(h, ini_data)
    print(f'Sent INI: {n2} bytes')

    # Wait for Device Service to process
    print('Waiting for Device Service to process...')
    time.sleep(5)

    # Read any response
    buf = ctypes.create_string_buffer(4096)
    read = wt.DWORD(0)
    try:
        k32.ReadFile(h, buf, 4096, ctypes.byref(read), None)
        if read.value > 0:
            print(f'Response: {bytes(buf[:read.value]).hex()[:100]}')
    except:
        pass

    k32.DisconnectNamedPipe(h)
    k32.CloseHandle(h)

    # Start Swarm II back up
    print('Starting Swarm II...')
    subprocess.Popen([os.path.join(SWARM_DIR, 'Turtle Beach Swarm II.exe')])

    print('\nDone! Test button 12 — should be Delete!')
    return True


if __name__ == '__main__':
    push_buttons()
