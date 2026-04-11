"""
frida_inject.py — Inject button mappings into Swarm II via Frida.
Uses Swarm II's persistent HID handle to write buttons directly to mouse.
"""
import frida
import time
import json
import sys
import os

# Button data template from Swarm II capture
# This is the default WWM profile with Delete on thumb_button_1
DEFAULT_PAGES = [
    [0x06,0x01,0x47,0x06,0x19, 0x00,0x00,0x00,0x00,0x00,0x01,0x01,0x00,0x00,0x02,0x01,0x00,0x00,0x03,0x01,0x00,0x00,0x09,0x01,0x00,0x00,0x0a,0x01,0x00,0x00],
    [0x06,0x01,0x47,0x06,0x19, 0x05,0x01,0x00,0x00,0x06,0x01,0x00,0x00,0x02,0x02,0x00,0x00,0x03,0x02,0x00,0x4c,0x00,0x06,0x00,0x08,0x00,0x06,0x00,0x00,0x07],
    [0x06,0x01,0x47,0x06,0x19, 0x01,0x00,0x00,0x08,0x01,0x00,0x00,0x01,0x0a,0x00,0x00,0x01,0x08,0x00,0x00,0x01,0x01,0x00,0x00,0x02,0x01,0x00,0x00,0x04,0x03],
    [0x06,0x01,0x47,0x06,0x19, 0x00,0x00,0x07,0x03,0x00,0x00,0x08,0x03,0x00,0x4b,0x00,0x06,0x00,0x4e,0x00,0x06,0x00,0x19,0x01,0x06,0x00,0x06,0x01,0x06,0x00],
    [0x06,0x01,0x47,0x06,0x19, 0x4c,0x00,0x06,0x00,0x49,0x00,0x06,0x00,0x00,0x02,0x03,0x00,0x00,0x03,0x03,0x00,0x00,0x00,0x00,0x00,0x00,0x0b,0x08,0x6b,0x02],
]

# Button slot offsets in the continuous 125-byte data stream
# (offset from start of page data, across all 5 pages concatenated)
# These are the byte positions where each button's code starts
# Keyboard entries: [scancode, modifier, 0x06, 0x00] = 4 bytes
# Standard entries: [code, type] + padding = 3 bytes
BUTTON_OFFSETS = {
    # Primary layer (offsets in the 125-byte concatenated page data)
    'left_button':     5,    # [01 01] std Click
    'right_button':    8,    # [02 01] std Menu
    'middle_button':   11,   # [03 01] std UniScroll
    'scroll_up':       14,   # [09 01] std ScrollUp
    'scroll_down':     17,   # [0a 01] std ScrollDn
    'side_button_1':   20,   # [05 01] std Fwd — or keyboard
    'side_button_2':   23,   # [06 01] std Back — or keyboard
    'dpi_up':          26,   # [02 02] DPI Up
    'dpi_down':        29,   # [03 02] DPI Down
    'thumb_button_1':  32,   # [4c 00 06 00] keyboard Delete
    'thumb_button_2':  36,   # [08 00 06 00] keyboard
    'tilt_left':       40,   # [07 01] std TiltL
    'tilt_right':      43,   # [08 01] std TiltR
    'easy_shift':      46,   # [01 0a] special
}


def build_js(pages_json):
    """Build the Frida injection JavaScript."""
    return '''
var kone = Process.getModuleByName('KONE_XP_AIR.dll');
var exports = kone.enumerateExports();
var sendAddr = null, getAddr = null;
for (var i = 0; i < exports.length; i++) {
    if (exports[i].name === 'hid_send_feature_report') sendAddr = exports[i].address;
    if (exports[i].name === 'hid_get_feature_report') getAddr = exports[i].address;
}
var nativeSend = new NativeFunction(sendAddr, 'int', ['pointer', 'pointer', 'int']);
var nativeGet = new NativeFunction(getAddr, 'int', ['pointer', 'pointer', 'int']);

var persistentHandle = null;
Interceptor.attach(sendAddr, {
    onEnter: function(args) {
        if (args[1].readU8() === 0x06 && args[1].add(2).readU8() !== 0x4d) {
            persistentHandle = args[0];
        }
    }
});

function makeBuf(arr) {
    var buf = Memory.alloc(30);
    for (var i = 0; i < 30; i++) buf.add(i).writeU8(i < arr.length ? arr[i] : 0);
    return buf;
}
function S(h, a) { return nativeSend(h, makeBuf(a), 30); }
function G(h) { var b = Memory.alloc(30); b.writeU8(0x06); nativeGet(h, b, 30); }
function HS(h) { S(h,[0x06,0x01,0x44,0x07]); Thread.sleep(0.1); G(h); Thread.sleep(0.05); }

var pages = ''' + pages_json + ''';

var sel = [[0x06,0x01,0x47,0x06,0x02,0x00,0x00],
           [0x06,0x01,0x47,0x06,0x02,0x01,0x00],
           [0x06,0x01,0x47,0x06,0x02,0x02,0x00],
           [0x06,0x01,0x47,0x06,0x02,0x03,0x00],
           [0x06,0x01,0x47,0x06,0x02,0x04,0x00]];

setTimeout(function() {
    if (!persistentHandle) { send({ok:false, err:'No handle captured'}); return; }

    for (var pg = 0; pg < 5; pg++) {
        S(persistentHandle, sel[pg]); Thread.sleep(0.05); HS(persistentHandle);
        S(persistentHandle, pages[pg]); Thread.sleep(0.05); HS(persistentHandle);
    }

    // Profile switch to activate
    Thread.sleep(0.3);
    for (var pg = 0; pg < 4; pg++) {
        S(persistentHandle, [0x06,0x01,0x46,0x06,0x02,pg,0x01]);
        Thread.sleep(0.05);
        S(persistentHandle, [0x06,0x01,0x46,0x07]);
        Thread.sleep(0.1); G(persistentHandle);
    }
    Thread.sleep(0.2);
    S(persistentHandle, [0x06,0x01,0x45,0x06,0x02,0x01,0x05]); Thread.sleep(0.05); HS(persistentHandle);
    S(persistentHandle, [0x06,0x01,0x4e,0x06,0x04,0x01,0x01,0x01,0xff]); Thread.sleep(0.05); HS(persistentHandle);
    Thread.sleep(0.5);
    for (var pg = 0; pg < 4; pg++) {
        S(persistentHandle, [0x06,0x01,0x46,0x06,0x02,pg,0x00]);
        Thread.sleep(0.05);
        S(persistentHandle, [0x06,0x01,0x46,0x07]);
        Thread.sleep(0.1); G(persistentHandle);
    }
    Thread.sleep(0.2);
    S(persistentHandle, [0x06,0x01,0x45,0x06,0x02,0x00,0x05]); Thread.sleep(0.05); HS(persistentHandle);
    S(persistentHandle, [0x06,0x01,0x4e,0x06,0x04,0x01,0x01,0x01,0xff]); Thread.sleep(0.05); HS(persistentHandle);

    send({ok:true, msg:'Buttons written!'});
}, 8000);
'''


def find_swarm_pid():
    """Find Swarm II process ID."""
    import subprocess
    result = subprocess.run(
        ['tasklist', '/FI', 'IMAGENAME eq Turtle Beach Swarm II.exe', '/FO', 'CSV', '/NH'],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split('\n'):
        if 'Turtle Beach Swarm II' in line:
            # CSV format: "name","pid","session","session#","mem"
            parts = line.strip().split(',')
            if len(parts) >= 2:
                return int(parts[1].strip('"'))
    return None


def inject_buttons(pages=None):
    """
    Inject button data into the mouse via Frida + Swarm II.
    pages: list of 5 lists, each 30 bytes (or None for default)
    Returns dict with success/error.
    """
    if pages is None:
        pages = DEFAULT_PAGES

    pid = find_swarm_pid()
    if not pid:
        return {"success": False, "error": "Swarm II not running. Start it first."}

    result = {"success": False}

    def on_msg(msg, data):
        nonlocal result
        if msg['type'] == 'send':
            p = msg['payload']
            if isinstance(p, dict):
                result = {"success": p.get('ok', False),
                          "message": p.get('msg', ''),
                          "error": p.get('err', '')}

    try:
        session = frida.attach(pid)
        js = build_js(json.dumps(pages))
        script = session.create_script(js)
        script.on('message', on_msg)
        script.load()
        time.sleep(15)  # Wait for handle capture + write + profile switch
        session.detach()
    except Exception as e:
        result = {"success": False, "error": str(e)}

    return result


if __name__ == '__main__':
    print("Injecting default button data (Delete on thumb_button_1)...")
    result = inject_buttons()
    print(f"Result: {result}")
