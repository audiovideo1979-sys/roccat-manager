"""
frida_inject.py — All mouse operations through Frida injection into Swarm II.
DPI writes, button writes, and profile switching — all via Swarm's persistent handle.
Swarm II stays running at all times.
"""
import frida
import time
import json
import subprocess

# ── Encoding tables ──────────────────────────────────────────────────────────
HID_KEYS = {
    'A': 0x04, 'B': 0x05, 'C': 0x06, 'D': 0x07, 'E': 0x08, 'F': 0x09,
    'G': 0x0A, 'H': 0x0B, 'I': 0x0C, 'J': 0x0D, 'K': 0x0E, 'L': 0x0F,
    'M': 0x10, 'N': 0x11, 'O': 0x12, 'P': 0x13, 'Q': 0x14, 'R': 0x15,
    'S': 0x16, 'T': 0x17, 'U': 0x18, 'V': 0x19, 'W': 0x1A, 'X': 0x1B,
    'Y': 0x1C, 'Z': 0x1D,
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    'Enter': 0x28, 'Escape': 0x29, 'Backspace': 0x2A, 'Tab': 0x2B,
    'Space': 0x2C, 'CapsLock': 0x39,
    'F1': 0x3A, 'F2': 0x3B, 'F3': 0x3C, 'F4': 0x3D, 'F5': 0x3E, 'F6': 0x3F,
    'F7': 0x40, 'F8': 0x41, 'F9': 0x42, 'F10': 0x43, 'F11': 0x44, 'F12': 0x45,
    'Insert': 0x49, 'Home': 0x4A, 'PageUp': 0x4B, 'Delete': 0x4C,
    'End': 0x4D, 'PageDown': 0x4E,
    'Right': 0x4F, 'Left': 0x50, 'Down': 0x51, 'Up': 0x52,
    'LCtrl': 0xE0, 'LShift': 0xE1, 'LAlt': 0xE2, 'LWin': 0xE3,
}

MOD_MAP = {
    'LCtrl': 0x01, 'Ctrl': 0x01, 'LShift': 0x02, 'Shift': 0x02,
    'LAlt': 0x04, 'Alt': 0x04, 'LWin': 0x08, 'Win': 0x08,
    'RCtrl': 0x10, 'RShift': 0x20, 'RAlt': 0x40, 'RWin': 0x80,
}

STD_CODES = {
    'Left Click': (0x01, 0x01), 'Click': (0x01, 0x01),
    'Right Click': (0x02, 0x01), 'Menu': (0x02, 0x01),
    'Middle Click': (0x03, 0x01), 'Universal Scroll': (0x03, 0x01),
    'Double-Click': (0x04, 0x01),
    'Browser Forward': (0x05, 0x01), 'Browser Back': (0x06, 0x01),
    'Browser Backward': (0x06, 0x01),
    'Tilt Left': (0x07, 0x01), 'Tilt Right': (0x08, 0x01),
    'Scroll Up': (0x09, 0x01), 'Scroll Down': (0x0a, 0x01),
    'DPI Up': (0x02, 0x02), 'DPI Down': (0x03, 0x02),
    'Easy Shift': (0x01, 0x0a),
    'Disabled': (0x00, 0x00),
}


def encode_action(action_str):
    if not action_str or action_str == 'Disabled':
        return [0x00, 0x00]
    if action_str in STD_CODES:
        c, t = STD_CODES[action_str]
        return [c, t]
    if action_str.startswith('Hotkey '):
        parts = action_str[7:].split('+')
        mod, sc = 0, 0
        for p in parts:
            p = p.strip()
            if p in MOD_MAP:
                mod |= MOD_MAP[p]
            elif p in HID_KEYS:
                sc = HID_KEYS[p]
            elif p.upper() in HID_KEYS:
                sc = HID_KEYS[p.upper()]
        if sc:
            return [sc, mod, 0x06, 0x00]
    return [0x00, 0x00]


# ── Button data template (125 bytes from Swarm II capture) ──────────────────
TEMPLATE = bytearray([
    0x00,0x00,0x00,0x00,0x00, 0x01,0x01,0x00, 0x00,0x02,0x01,0x00, 0x00,0x03,0x01,0x00, 0x00,0x09,0x01,0x00, 0x00,0x0a,0x01,0x00,0x00,
    0x05,0x01,0x00, 0x00,0x06,0x01,0x00, 0x00,0x02,0x02,0x00, 0x00,0x03,0x02,0x00, 0x4c,0x00,0x06,0x00, 0x08,0x00,0x06,0x00, 0x00,
    0x07,0x01,0x00, 0x00,0x08,0x01,0x00, 0x00,0x01,0x0a,0x00, 0x00,0x01,0x08,0x00, 0x00,0x01,0x01,0x00, 0x00,0x02,0x01,0x00, 0x00,0x04,0x03,
    0x00,0x00,0x07,0x03,0x00, 0x00,0x08,0x03,0x00, 0x4b,0x00,0x06,0x00, 0x4e,0x00,0x06,0x00, 0x19,0x01,0x06,0x00, 0x06,0x01,0x06,0x00,
    0x4c,0x00,0x06,0x00, 0x49,0x00,0x06,0x00, 0x00,0x02,0x03,0x00, 0x00,0x03,0x03,0x00, 0x00,0x00,0x00,0x00, 0x00,0x0b,0x08, 0x00,0x00,
])

# (offset, size, name)
BUTTON_MAP = [
    (5,2,'left_button'), (8,2,'right_button'), (13,2,'middle_button'),
    (17,2,'scroll_up'), (21,2,'scroll_down'),
    (25,2,'side_button_1'), (29,2,'side_button_2'),
    (33,2,'dpi_up'), (37,2,'dpi_down'),
    (40,4,'thumb_button_1'), (44,4,'thumb_button_2'),
    (49,2,'tilt_left'), (53,2,'tilt_right'),
    (57,2,'easy_shift'),
    (65,2,'es_left_button'), (69,2,'es_right_button'),
    (84,4,'es_side_button_1'), (88,4,'es_side_button_2'),
    (92,4,'es_dpi_up'), (96,4,'es_dpi_down'),
    (100,4,'es_thumb_button_1'), (104,4,'es_thumb_button_2'),
]


def build_button_pages(keybinds, easy_shift=None):
    data = bytearray(TEMPLATE)
    for offset, size, name in BUTTON_MAP:
        if name.startswith('es_'):
            action = (easy_shift or {}).get(name[3:], '')
        else:
            action = (keybinds or {}).get(name, '')
        if not action:
            continue
        enc = encode_action(action)
        for j in range(min(len(enc), size)):
            if offset + j < len(data) - 2:
                data[offset + j] = enc[j]
        for j in range(len(enc), size):
            if offset + j < len(data) - 2:
                data[offset + j] = 0x00
    cs = sum(data[:-2]) & 0xFFFF
    data[-2] = cs & 0xFF
    data[-1] = (cs >> 8) & 0xFF
    pages = []
    for i in range(5):
        pages.append([0x06, 0x01, 0x47, 0x06, 0x19] + list(data[i*25:(i+1)*25]))
    return pages


def build_dpi_pages(dpi, slot=0):
    """Build DPI profile pages (3 pages of 25 bytes)."""
    import struct
    p = bytearray(75)
    p[0] = 0x06; p[1] = 0x4E; p[2] = slot
    p[3] = 0x06; p[4] = 0x06; p[5] = 0x1f; p[6] = 0x00
    dpi_val = dpi if isinstance(dpi, int) else 800
    for i in range(5):
        struct.pack_into('<H', p, 7 + i*2, dpi_val)
        struct.pack_into('<H', p, 17 + i*2, dpi_val)
    p[27:36] = bytes([0x00,0x00,0x03,0x0a,0x06,0xff,0x05,0x00,0x00])
    for i in range(7):
        off = 36 + i*5
        if off+4 < len(p):
            p[off:off+5] = bytes([0x14,0xFF,0x00,0x48,0xFF])
    p[71:75] = bytes([0x01,0x64,0xFF,0xFF])
    pages = []
    for i in range(3):
        pages.append([0x06,0x01,0x46,0x06,0x19] + list(p[i*25:(i+1)*25]))
    return pages


# ── Frida JS template ────────────────────────────────────────────────────────
FRIDA_JS = '''
var kone = Process.getModuleByName('KONE_XP_AIR.dll');
var exports = kone.enumerateExports();
var sendAddr = null, getAddr = null;
for (var i = 0; i < exports.length; i++) {
    if (exports[i].name === 'hid_send_feature_report') sendAddr = exports[i].address;
    if (exports[i].name === 'hid_get_feature_report') getAddr = exports[i].address;
}
var nativeSend = new NativeFunction(sendAddr, 'int', ['pointer', 'pointer', 'int']);
var nativeGet = new NativeFunction(getAddr, 'int', ['pointer', 'pointer', 'int']);

var handle = null;
Interceptor.attach(sendAddr, {
    onEnter: function(args) { if (args[1].readU8() === 0x06) handle = args[0]; }
});

function B(a) { var b=Memory.alloc(30); for(var i=0;i<30;i++) b.add(i).writeU8(i<a.length?a[i]:0); return b; }
function S(a) { return nativeSend(handle, B(a), 30); }
function G() { var b=Memory.alloc(30); b.writeU8(0x06); nativeGet(handle, b, 30); }
function HS() { S([0x06,0x01,0x44,0x07]); Thread.sleep(0.1); G(); Thread.sleep(0.05); }

var CMD = %%CMD%%;

setTimeout(function() {
    if (!handle) { send({ok:false,err:'No handle - is Swarm connected to mouse?'}); return; }

    if (CMD.type === 'switch') {
        // Profile switch only
        for (var pg=0;pg<4;pg++) {
            S([0x06,0x01,0x46,0x06,0x02,pg,0x01]); Thread.sleep(0.05);
            S([0x06,0x01,0x46,0x07]); Thread.sleep(0.1); G();
        }
        Thread.sleep(0.1);
        S([0x06,0x01,0x45,0x06,0x02,CMD.slot,0x05]); Thread.sleep(0.05); HS();
        S([0x06,0x01,0x4e,0x06,0x04,CMD.slot,0x01,0x01,0xff]); Thread.sleep(0.05); HS();
        send({ok:true, msg:'Switched to profile ' + (CMD.slot+1)});
    }
    else if (CMD.type === 'push') {
        // Write DPI (3 pages via 0x46)
        if (CMD.dpi_pages) {
            var dp = CMD.dpi_pages;
            for (var s=0; s<5; s++) {
                // Write DPI to each slot
                var slot_pages = [];
                for (var i=0;i<3;i++) {
                    var pg = dp[i].slice(); // copy
                    pg[7] = s; // set slot in profile data
                    slot_pages.push(pg);
                }
                for (var pg=0;pg<3;pg++) {
                    S([0x06,0x01,0x46,0x06,0x02,pg,0x01]); Thread.sleep(0.05); HS();
                    S(slot_pages[pg]); Thread.sleep(0.05); HS();
                }
                S([0x06,0x01,0x46,0x06,0x02,0x03,0x01]); Thread.sleep(0.05); HS();
                var cs = 0;
                for (var i=5;i<30;i++) for (var pg=0;pg<3;pg++) cs += slot_pages[pg][i];
                cs = cs & 0xFFFF;
                S([0x06,0x01,0x46,0x06,0x03,0xFF,cs&0xFF,(cs>>8)&0xFF]); Thread.sleep(0.05); HS();
            }
            send({ok:true, msg:'DPI written'});
        }

        // Write buttons (5 pages via 0x47)
        if (CMD.btn_pages) {
            var bp = CMD.btn_pages;
            var sel = [[0x06,0x01,0x47,0x06,0x02,0x00,0x00],
                       [0x06,0x01,0x47,0x06,0x02,0x01,0x00],
                       [0x06,0x01,0x47,0x06,0x02,0x02,0x00],
                       [0x06,0x01,0x47,0x06,0x02,0x03,0x00],
                       [0x06,0x01,0x47,0x06,0x02,0x04,0x00]];
            for (var pg=0;pg<5;pg++) {
                S(sel[pg]); Thread.sleep(0.05); HS();
                S(bp[pg]); Thread.sleep(0.05); HS();
            }
            // Activate with profile switch
            Thread.sleep(0.3);
            for (var pg=0;pg<4;pg++) {
                S([0x06,0x01,0x46,0x06,0x02,pg,0x01]); Thread.sleep(0.05);
                S([0x06,0x01,0x46,0x07]); Thread.sleep(0.1); G();
            }
            Thread.sleep(0.2);
            S([0x06,0x01,0x45,0x06,0x02,0x01,0x05]); Thread.sleep(0.05); HS();
            S([0x06,0x01,0x4e,0x06,0x04,0x01,0x01,0x01,0xff]); Thread.sleep(0.05); HS();
            Thread.sleep(0.5);
            for (var pg=0;pg<4;pg++) {
                S([0x06,0x01,0x46,0x06,0x02,pg,0x00]); Thread.sleep(0.05);
                S([0x06,0x01,0x46,0x07]); Thread.sleep(0.1); G();
            }
            Thread.sleep(0.2);
            S([0x06,0x01,0x45,0x06,0x02,0x00,0x05]); Thread.sleep(0.05); HS();
            S([0x06,0x01,0x4e,0x06,0x04,0x01,0x01,0x01,0xff]); Thread.sleep(0.05); HS();
            send({ok:true, msg:'Buttons written'});
        }

        if (!CMD.dpi_pages && !CMD.btn_pages) {
            send({ok:true, msg:'Nothing to push'});
        }
    }
}, 2000);
'''


def find_swarm_pid():
    result = subprocess.run(
        ['tasklist', '/FI', 'IMAGENAME eq Turtle Beach Swarm II.exe', '/FO', 'CSV', '/NH'],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split('\n'):
        if 'Turtle Beach Swarm II' in line:
            parts = line.strip().split(',')
            if len(parts) >= 2:
                return int(parts[1].strip('"'))
    return None


def _run_frida(cmd_dict):
    """Run a Frida command through Swarm II's handle."""
    pid = find_swarm_pid()
    if not pid:
        return {"success": False, "error": "Swarm II not running. Start it first."}

    cmd_json = json.dumps(cmd_dict)
    js = FRIDA_JS.replace('%%CMD%%', cmd_json)

    results = []

    def on_msg(msg, data):
        if msg['type'] == 'send':
            p = msg['payload']
            if isinstance(p, dict):
                results.append(p)
        elif msg['type'] == 'error':
            results.append({'ok': False, 'err': msg.get('description', 'Unknown error')})

    try:
        session = frida.attach(pid)
        script = session.create_script(js)
        script.on('message', on_msg)
        script.load()
        time.sleep(12)
        session.detach()
    except Exception as e:
        return {"success": False, "error": str(e)}

    # Collect results
    if results:
        last = results[-1]
        return {
            "success": last.get('ok', False),
            "message": last.get('msg', ''),
            "error": last.get('err', ''),
        }
    return {"success": False, "error": "No response from Frida"}


def switch_profile(slot):
    """Switch active profile on mouse. Slot 0-4."""
    return _run_frida({"type": "switch", "slot": slot})


def push_profile(dpi=None, keybinds=None, easy_shift=None):
    """Push DPI and/or buttons to mouse."""
    cmd = {"type": "push"}
    if dpi is not None:
        cmd["dpi_pages"] = build_dpi_pages(dpi)
    if keybinds is not None:
        cmd["btn_pages"] = build_button_pages(keybinds, easy_shift)
    return _run_frida(cmd)


READ_JS = '''
// Read all 5 profiles directly from Swarm II's heap memory
var ranges = Process.enumerateRanges('rw-');
var profiles = [];

for (var slot = 0; slot < 5; slot++) {
    var profile = {slot: slot, dpi: [], buttons: []};

    // Find DPI data: 06 4e [slot] 06 06
    var dpiPattern = '06 4e ' + ('0'+slot.toString(16)).slice(-2) + ' 06 06';
    for (var r = 0; r < ranges.length; r++) {
        try {
            var found = Memory.scanSync(ranges[r].base, ranges[r].size, dpiPattern);
            if (found.length > 0) {
                var addr = found[0].address;
                var dpis = [];
                for (var i = 0; i < 5; i++) {
                    dpis.push(addr.add(7 + i*2).readU8() | (addr.add(8 + i*2).readU8() << 8));
                }
                profile.dpi = dpis;
                profile.active_stage = addr.add(6).readU8();
                profile.polling = addr.add(5).readU8();
                break;
            }
        } catch(e) {}
    }

    // Find button data: 07 7d [slot] 00 00 01 01
    var btnPattern = '07 7d ' + ('0'+slot.toString(16)).slice(-2) + ' 00 00 01 01';
    for (var r = 0; r < ranges.length; r++) {
        try {
            var found = Memory.scanSync(ranges[r].base, ranges[r].size, btnPattern);
            if (found.length > 0) {
                var addr = found[0].address;
                var data = [];
                for (var j = 0; j < 125; j++) data.push(addr.add(j).readU8());
                profile.buttons = data;
                break;
            }
        } catch(e) {}
    }

    profiles.push(profile);
}

send({ok: true, profiles: profiles});
'''

# Reverse lookup tables for decoding button data
REV_STD = {}
for name, (code, typ) in STD_CODES.items():
    if code > 0:
        REV_STD[(code, typ)] = name

REV_HID = {v: k for k, v in HID_KEYS.items()}


def decode_button_entry(data, offset):
    """Decode a button entry from raw bytes. Returns (action_string, bytes_consumed)."""
    if offset + 3 < len(data) and data[offset + 2] == 0x06 and data[offset + 3] == 0x00:
        sc = data[offset]
        mod = data[offset + 1]
        if sc in REV_HID and mod <= 0x0F:
            parts = []
            for mask, name in sorted(MOD_MAP.items(), key=lambda x: x[1]):
                if mod & MOD_MAP.get(name, 0xFF) and name in ('LCtrl','LShift','LAlt','LWin'):
                    parts.append(name)
            parts.append(REV_HID[sc])
            return 'Hotkey ' + '+'.join(parts), 4
    if offset + 1 < len(data):
        code, typ = data[offset], data[offset + 1]
        key = (code, typ)
        if key in REV_STD:
            return REV_STD[key], 2
        if code == 0 and typ == 0:
            return 'Disabled', 2
    return 'Disabled', 2


def decode_profile_buttons(raw_buttons):
    """Decode 125-byte raw button data into keybinds and easy_shift dicts."""
    if not raw_buttons or len(raw_buttons) < 50:
        return {}, {}

    # Primary layer offsets (from BUTTON_MAP)
    primary_map = [
        (5, 2, 'left_button'), (8, 2, 'right_button'), (13, 2, 'middle_button'),
        (17, 2, 'scroll_up'), (21, 2, 'scroll_down'),
        (25, 2, 'side_button_1'), (29, 2, 'side_button_2'),
        (33, 2, 'dpi_up'), (37, 2, 'dpi_down'),
        (40, 4, 'thumb_button_1'), (44, 4, 'thumb_button_2'),
        (49, 2, 'tilt_left'), (53, 2, 'tilt_right'),
        (57, 2, 'easy_shift'),
    ]

    es_map = [
        (65, 2, 'left_button'), (69, 2, 'right_button'),
        (84, 4, 'side_button_1'), (88, 4, 'side_button_2'),
        (92, 4, 'dpi_up'), (96, 4, 'dpi_down'),
        (100, 4, 'thumb_button_1'), (104, 4, 'thumb_button_2'),
    ]

    keybinds = {}
    for offset, size, name in primary_map:
        if offset < len(raw_buttons):
            action, _ = decode_button_entry(raw_buttons, offset)
            keybinds[name] = action

    easy_shift = {}
    for offset, size, name in es_map:
        if offset < len(raw_buttons):
            action, _ = decode_button_entry(raw_buttons, offset)
            easy_shift[name] = action

    return keybinds, easy_shift


def read_profiles():
    """Read all 5 profiles directly from Swarm II's heap memory."""
    pid = find_swarm_pid()
    if not pid:
        return {"success": False, "error": "Swarm II not running. Start it first."}

    result = {"success": False, "error": "Timeout"}

    def on_msg(msg, data):
        nonlocal result
        if msg['type'] == 'send':
            p = msg['payload']
            if isinstance(p, dict) and p.get('ok'):
                raw_profiles = p.get('profiles', [])
                decoded = []
                for rp in raw_profiles:
                    keybinds, easy_shift = decode_profile_buttons(rp.get('buttons', []))
                    decoded.append({
                        'slot': rp['slot'],
                        'dpi': rp.get('dpi', [800]*5),
                        'active_stage': rp.get('active_stage', 0),
                        'keybinds': keybinds,
                        'easy_shift': easy_shift,
                    })
                result = {"success": True, "profiles": decoded}

    try:
        session = frida.attach(pid)
        script = session.create_script(READ_JS)
        script.on('message', on_msg)
        script.load()
        time.sleep(5)
        session.detach()
    except Exception as e:
        result = {"success": False, "error": str(e)}

    return result


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'switch':
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        print(switch_profile(slot))
    elif len(sys.argv) > 1 and sys.argv[1] == 'push':
        print(push_profile(dpi=850, keybinds={
            'left_button': 'Left Click', 'right_button': 'Right Click',
            'thumb_button_1': 'Hotkey Delete',
        }))
    else:
        print("Usage: python frida_inject.py switch <0-4>")
        print("       python frida_inject.py push")
