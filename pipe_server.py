"""Create a named pipe server to impersonate Swarm II and send button data to Device Service."""
import ctypes
import ctypes.wintypes as wt
import time
import os
import sys
import subprocess
import glob

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
INVALID_HANDLE = wt.HANDLE(-1).value & 0xFFFFFFFFFFFFFFFF

k32 = ctypes.windll.kernel32
k32.CreateNamedPipeW.restype = wt.HANDLE
k32.CreateNamedPipeW.argtypes = [
    wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPVOID
]
k32.ConnectNamedPipe.argtypes = [wt.HANDLE, wt.LPVOID]
k32.WriteFile.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.LPVOID]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.DisconnectNamedPipe.argtypes = [wt.HANDLE]

def get_pipe_name():
    """Get the pipe name from Device Service logs."""
    log_dir = r'C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Log\DeviceService'
    logs = sorted(glob.glob(os.path.join(log_dir, '*.txt')))
    if logs:
        with open(logs[-1]) as f:
            for line in f:
                if 'Try to connect' in line:
                    name = line.split(':')[-1].strip()
        return name
    return None

def create_pipe(name):
    """Create a named pipe server."""
    pipe_path = "\\\\.\\pipe\\" + name
    print(f"Creating pipe: {pipe_path}")

    h = k32.CreateNamedPipeW(
        pipe_path,
        PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_BYTE | PIPE_WAIT,
        1, 65536, 65536, 0, None
    )

    if h == INVALID_HANDLE or h == 0:
        err = ctypes.get_last_error()
        print(f"Failed to create pipe, error={err}")
        return None

    print(f"Pipe created, handle={h}")
    return h

def write_pipe(handle, data):
    """Write data to the pipe."""
    written = wt.DWORD(0)
    buf = ctypes.create_string_buffer(data)
    result = k32.WriteFile(handle, buf, len(data), ctypes.byref(written), None)
    return written.value

def main():
    # Get pipe name
    pipe_name = get_pipe_name()
    if not pipe_name:
        print("Could not find pipe name from logs")
        return
    print(f"Pipe name: {pipe_name}")

    # Kill Swarm II (but keep Device Service)
    subprocess.run(['taskkill', '/f', '/im', 'Turtle Beach Swarm II.exe'], capture_output=True)
    time.sleep(1)
    print("Swarm II killed")

    # Create our pipe server
    handle = create_pipe(pipe_name)
    if not handle:
        return

    # Wait for Device Service to connect
    print("Waiting for Device Service to connect...")
    result = k32.ConnectNamedPipe(handle, None)
    print(f"ConnectNamedPipe result: {result}")
    print("Device Service CONNECTED!")

    # Read the INI file
    ini_path = r'C:\Users\audio\AppData\Roaming\Turtle Beach\Swarm II\Setting\KONE_XP_AIR_TB.ini'
    ini_data = open(ini_path, 'rb').read()

    # Send header (PID + identity)
    pid = os.getpid()
    header = f"{pid}\nTurtle Beach Swarm II\nPERSONAL\n"
    header_bytes = header.encode('ascii').ljust(75, b'\x00')

    n = write_pipe(handle, header_bytes)
    print(f"Sent header: {n} bytes")

    # Send INI data
    n = write_pipe(handle, ini_data)
    print(f"Sent INI: {n} bytes")

    # Wait for Device Service to process
    time.sleep(5)

    k32.DisconnectNamedPipe(handle)
    k32.CloseHandle(handle)

    print("\nDone! Test button 12!")

    # Restart Swarm II
    subprocess.Popen([r'C:\Program Files\Turtle Beach Swarm II\Turtle Beach Swarm II.exe'])

if __name__ == '__main__':
    main()
