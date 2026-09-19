"""
Transports execute an op list (see sequences.py) and return one OpResult per op.

    RecordingTransport   hardware-free; records ops, returns canned responses (tests, dry runs)
    DirectHidTransport   our own handle to the receiver's vendor collection, Windows only
    FridaTransport       Swarm II's own hidapi handle, via frida_executor.js, Windows only
"""
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from . import protocol as P
from .sequences import Op, total_sleep, to_json

DONGLE_VID = 0x10F5
DONGLE_PID = 0x5017
DONGLE_USAGE_PAGE = 0xFF03
MOUSE_PID = 0x5019
SWARM_DIR = r'C:\Program Files\Turtle Beach Swarm II'
SWARM_EXE = 'Turtle Beach Swarm II.exe'
KONE_DLL = os.path.join(SWARM_DIR, 'Data', 'Devices', 'KONE_XP_AIR', 'KONE_XP_AIR.dll')
EXECUTOR_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frida_executor.js')


class TransportError(Exception):
    pass


@dataclass
class OpResult:
    op: Op
    rc: int = 0
    response: bytes = b''
    error: str = ''

    @property
    def ok(self):
        return not self.error and self.rc >= 0


def format_results(results):
    """One line per op, for logs and the A/B tool."""
    lines = []
    for r in results:
        op = r.op
        if op.kind == 'send':
            lines.append('> %-45s rc=%s%s' % (op.label or P.describe(op.data), r.rc, (' ERR ' + r.error) if r.error else ''))
        elif op.kind == 'get':
            lines.append('< get rc=%s %s%s' % (r.rc, r.response.hex(' '), (' ERR ' + r.error) if r.error else ''))
        elif op.kind == 'mark':
            lines.append('-- ' + op.label)
    return '\n'.join(lines)


# ── Recording ────────────────────────────────────────────────────────────────

class RecordingTransport:
    def __init__(self, responses=None, sleep_scale=0.0):
        self.ops = []
        self.responses = list(responses or [])
        self.sleep_scale = sleep_scale

    def run(self, ops):
        results = []
        for op in ops:
            self.ops.append(op)
            if op.kind == 'send':
                results.append(OpResult(op, rc=len(op.data)))
            elif op.kind == 'get':
                resp = self.responses.pop(0) if self.responses else P.get_feature_request()
                results.append(OpResult(op, rc=len(resp), response=bytes(resp)))
            elif op.kind == 'sleep':
                if self.sleep_scale:
                    time.sleep(op.seconds * self.sleep_scale)
                results.append(OpResult(op))
            else:
                results.append(OpResult(op))
        return results

    def sends(self):
        return [op.data for op in self.ops if op.kind == 'send']

    def clear(self):
        self.ops = []

    def close(self):
        pass


# ── Direct HID (Windows) ─────────────────────────────────────────────────────

def enumerate_candidates(vid=DONGLE_VID):
    """Every HID collection of our vendor, for matching against what Swarm's handle reports."""
    import hid
    out = []
    for d in hid.enumerate(vid, 0):
        out.append({
            'path': d['path'].decode(errors='replace') if isinstance(d['path'], bytes) else d['path'],
            'vid': '0x%04x' % d['vendor_id'], 'pid': '0x%04x' % d['product_id'],
            'usage_page': '0x%04x' % d.get('usage_page', 0), 'usage': '0x%04x' % d.get('usage', 0),
            'interface': d.get('interface_number'), 'product': d.get('product_string'),
        })
    return out


def find_dongle_path(vid=DONGLE_VID, pid=DONGLE_PID, usage_page=DONGLE_USAGE_PAGE):
    import hid
    for d in hid.enumerate(vid, pid):
        if d.get('usage_page') == usage_page:
            return d['path']
    return None


def kill_swarm(wait=2.0):
    """Stop Swarm II and its helpers (they hold the receiver open and stream lighting frames)."""
    killed = False
    for image in (SWARM_EXE, 'Turtle Beach Device Service.exe', 'ROCCAT_Swarm_Monitor.exe'):
        r = subprocess.run(['taskkill', '/f', '/im', image], capture_output=True)
        killed = killed or r.returncode == 0
    time.sleep(wait if killed else 0.3)
    return killed


def is_swarm_running():
    return find_process_pid(SWARM_EXE) is not None


def find_process_pid(image_name):
    """PID of a running image by name, via tasklist (Windows-native, no frida-version dependency)."""
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % image_name, '/FO', 'CSV', '/NH'],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if image_name.lower() in line.lower():
            parts = [p.strip('"') for p in line.strip().split('","')]
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


class DirectHidTransport:
    """Our own handle. backend='dll' calls the hidapi bundled in Swarm's KONE_XP_AIR.dll exactly as
    roccat_write.py did (the form proven to change DPI); backend='hid' uses the python `hid` package."""

    def __init__(self, path=None, backend='dll', dll_path=KONE_DLL, log=None):
        self.path = path
        self.backend = backend
        self.dll_path = dll_path
        self.log = log or (lambda m: None)
        self.dev = None
        self.dll = None

    def open(self):
        if self.path is None:
            self.path = find_dongle_path()
        if self.path is None:
            raise TransportError('receiver (VID %04x PID %04x usage page %04x) not found' % (DONGLE_VID, DONGLE_PID, DONGLE_USAGE_PAGE))
        if isinstance(self.path, str):
            self.path = self.path.encode()
        if self.backend == 'dll':
            import ctypes
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(SWARM_DIR)
            os.environ['PATH'] = SWARM_DIR + os.pathsep + os.environ.get('PATH', '')
            dll = ctypes.CDLL(self.dll_path)
            dll.hid_init.restype = ctypes.c_int
            dll.hid_open_path.restype = ctypes.c_void_p
            dll.hid_open_path.argtypes = [ctypes.c_char_p]
            dll.hid_send_feature_report.restype = ctypes.c_int
            dll.hid_send_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
            dll.hid_get_feature_report.restype = ctypes.c_int
            dll.hid_get_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
            dll.hid_close.argtypes = [ctypes.c_void_p]
            dll.hid_init()
            dev = dll.hid_open_path(self.path)
            if not dev:
                raise TransportError('hid_open_path failed for %r' % self.path)
            self.dll, self.dev = dll, dev
        elif self.backend == 'hid':
            import hid
            dev = hid.device()
            dev.open_path(self.path)
            self.dev = dev
        else:
            raise ValueError('backend must be dll or hid')
        self.log('opened %s via %s' % (self.path, self.backend))
        return self

    def run(self, ops):
        if self.dev is None:
            self.open()
        results = []
        for op in ops:
            try:
                if op.kind == 'send':
                    results.append(OpResult(op, rc=self._send(op.data)))
                elif op.kind == 'get':
                    rc, resp = self._get()
                    results.append(OpResult(op, rc=rc, response=resp))
                elif op.kind == 'sleep':
                    time.sleep(op.seconds)
                    results.append(OpResult(op))
                else:
                    results.append(OpResult(op))
            except Exception as e:  # keep going so the log shows where it broke
                results.append(OpResult(op, rc=-1, error=str(e)))
        return results

    def _send(self, data):
        data = P.packet(data)
        if self.backend == 'dll':
            return self.dll.hid_send_feature_report(self.dev, data, P.REPORT_LEN)
        return self.dev.send_feature_report(list(data))

    def _get(self):
        if self.backend == 'dll':
            import ctypes
            buf = ctypes.create_string_buffer(P.REPORT_LEN)
            buf[0] = P.REPORT_ID
            n = self.dll.hid_get_feature_report(self.dev, buf, P.REPORT_LEN)
            return n, bytes(buf.raw[:max(n, 0)])
        r = self.dev.get_feature_report(P.REPORT_ID, P.REPORT_LEN)
        return len(r), bytes(r)

    def close(self):
        if self.dev is None:
            return
        if self.backend == 'dll':
            self.dll.hid_close(self.dev)
            try:
                self.dll.hid_exit()
            except Exception:
                pass
        else:
            self.dev.close()
        self.dev = None


# ── Frida (Windows, Swarm II running) ────────────────────────────────────────

class FridaTransport:
    """Executes ops with Swarm II's own hid_device handle. Swarm must be running and connected."""

    def __init__(self, process_name=SWARM_EXE, wait_handle_s=8.0, prefer_non_lighting=True,
                 diag=False, log=None):
        self.process_name = process_name
        self.wait_handle_s = wait_handle_s
        self.prefer_non_lighting = prefer_non_lighting
        self.diag = diag
        self.log = log or (lambda m: None)
        self.last_message = None

    def find_pid(self):
        # frida 17 removed the top-level frida.enumerate_processes(); process enumeration is on the
        # device now. Fall back to tasklist so PID lookup does not depend on the frida version.
        name = self.process_name.lower()
        try:
            import frida
            for p in frida.get_local_device().enumerate_processes():
                if p.name.lower() == name:
                    return p.pid
        except Exception as e:
            self.log('frida process enumerate failed (%s); using tasklist' % e)
        return find_process_pid(self.process_name)

    def run(self, ops):
        import frida
        pid = self.find_pid()
        if pid is None:
            raise TransportError('%s is not running' % self.process_name)
        with open(EXECUTOR_JS, encoding='utf-8') as f:
            js = f.read()
        params = {'ops': to_json(ops), 'wait_handle_s': self.wait_handle_s,
                  'prefer_non_lighting': self.prefer_non_lighting, 'diag': self.diag}
        js = js.replace('%%PARAMS%%', json.dumps(params))
        done = threading.Event()
        box = {}

        def on_message(msg, data):
            if msg.get('type') == 'send':
                payload = msg.get('payload')
                if isinstance(payload, dict) and payload.get('done'):
                    box['msg'] = payload
                    done.set()
                else:
                    self.log('frida: %r' % (payload,))
            elif msg.get('type') == 'error':
                box['msg'] = {'ok': False, 'error': msg.get('description') or msg.get('stack') or str(msg)}
                done.set()

        try:
            session = frida.get_local_device().attach(pid)
        except Exception:
            try:
                session = frida.attach(pid)   # older frida
            except Exception as e:
                raise TransportError(
                    'could not attach to %s (pid %s): %s. Run the terminal as Administrator.'
                    % (self.process_name, pid, e))
        try:
            script = session.create_script(js)
            script.on('message', on_message)
            script.load()
            timeout = self.wait_handle_s + total_sleep(ops) + 15
            if not done.wait(timeout):
                raise TransportError('no reply from the injected script within %.0fs' % timeout)
        finally:
            try:
                session.detach()
            except Exception:
                pass
        msg = box.get('msg') or {}
        self.last_message = msg
        for line in msg.get('log') or []:
            self.log('frida: ' + line)
        if not msg.get('ok'):
            raise TransportError(msg.get('error') or 'injected script failed')
        by_index = {r['i']: r for r in msg.get('results', [])}
        results = []
        for i, op in enumerate(ops):
            r = by_index.get(i, {})
            resp = bytes.fromhex(r['r'].replace(' ', '')) if r.get('r') else b''
            results.append(OpResult(op, rc=r.get('rc', 0), response=resp, error=r.get('err', '')))
        return results

    def close(self):
        pass


def make_transport(kind, **kw):
    kind = (kind or 'frida').lower()
    if kind == 'recording':
        return RecordingTransport(**kw)
    if kind == 'direct':
        return DirectHidTransport(**kw)
    if kind == 'frida':
        return FridaTransport(**kw)
    raise ValueError('unknown transport %r' % kind)
