"""
Frida hook — intercept HID write calls from SWARM II.
"""
import frida
import sys
import time

HOOK_SCRIPT = """
var hexdump2 = function(ptr, len) {
    if (len > 256) len = 256;
    var result = [];
    for (var i = 0; i < len; i++) {
        var b = ptr.add(i).readU8();
        var h = b.toString(16);
        if (h.length < 2) h = '0' + h;
        result.push(h.toUpperCase());
    }
    return result.join(' ');
};

var pSetFeature = Module.findExportByName('hid.dll', 'HidD_SetFeature');
if (pSetFeature) {
    Interceptor.attach(pSetFeature, {
        onEnter: function(args) {
            var len = args[2].toInt32();
            var data = hexdump2(args[1], len);
            send({t: 'SET_FEATURE', l: len, d: data});
        }
    });
    send({t: 'i', m: 'Hooked HidD_SetFeature'});
}

var pSetOutput = Module.findExportByName('hid.dll', 'HidD_SetOutputReport');
if (pSetOutput) {
    Interceptor.attach(pSetOutput, {
        onEnter: function(args) {
            var len = args[2].toInt32();
            var data = hexdump2(args[1], len);
            send({t: 'SET_OUTPUT', l: len, d: data});
        }
    });
    send({t: 'i', m: 'Hooked HidD_SetOutputReport'});
}

var pWriteFile = Module.findExportByName('kernel32.dll', 'WriteFile');
if (pWriteFile) {
    Interceptor.attach(pWriteFile, {
        onEnter: function(args) {
            var len = args[2].toInt32();
            if (len > 0 && len <= 512) {
                var first = args[1].readU8();
                if (first < 0x20 || first > 0x7E) {
                    var data = hexdump2(args[1], len);
                    send({t: 'WRITE', l: len, d: data});
                }
            }
        }
    });
    send({t: 'i', m: 'Hooked WriteFile'});
}

var pDevIo = Module.findExportByName('kernel32.dll', 'DeviceIoControl');
if (pDevIo) {
    Interceptor.attach(pDevIo, {
        onEnter: function(args) {
            var ioctl = args[1].toInt32() >>> 0;
            var inLen = args[3].toInt32();
            if (inLen > 0 && inLen <= 512) {
                var data = hexdump2(args[2], inLen);
                send({t: 'IOCTL', c: '0x' + ioctl.toString(16).toUpperCase(), l: inLen, d: data});
            }
        }
    });
    send({t: 'i', m: 'Hooked DeviceIoControl'});
}

send({t: 'i', m: 'ALL HOOKS READY - Change DPI in SWARM II now!'});
"""

def on_message(message, data):
    if message['type'] == 'send':
        p = message['payload']
        t = p.get('t', '')
        if t == 'i':
            print("[INFO] %s" % p['m'])
        elif t in ('SET_FEATURE', 'SET_OUTPUT', 'WRITE'):
            print("\n*** %s (len=%d) ***" % (t, p['l']))
            bs = p['d'].split(' ')
            for i in range(0, len(bs), 16):
                print("  [%03d] %s" % (i, ' '.join(bs[i:i+16])))
        elif t == 'IOCTL':
            print("\n*** DeviceIoControl (ioctl=%s, len=%d) ***" % (p['c'], p['l']))
            bs = p['d'].split(' ')
            for i in range(0, len(bs), 16):
                print("  [%03d] %s" % (i, ' '.join(bs[i:i+16])))
    elif message['type'] == 'error':
        print("[ERROR] %s" % message.get('description', message))

def main():
    print("=" * 60)
    print("Frida HID Hook for SWARM II")
    print("=" * 60)

    targets = []
    device = frida.get_local_device()
    for proc in device.enumerate_processes():
        if 'turtle' in proc.name.lower():
            targets.append((proc.pid, proc.name))

    if not targets:
        print("No SWARM II processes found!")
        return

    print("Found:")
    for pid, name in targets:
        print("  PID %d: %s" % (pid, name))

    sessions = []
    for pid, name in targets:
        print("Attaching to %s (%d)..." % (name, pid))
        try:
            session = frida.attach(pid)
            script = session.create_script(HOOK_SCRIPT)
            script.on('message', on_message)
            script.load()
            sessions.append((session, script))
            print("  OK!")
        except Exception as e:
            print("  Failed: %s" % e)

    print()
    print("LISTENING - change DPI in SWARM II and save!")
    print("Ctrl+C to stop.")
    print()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    for s, sc in sessions:
        try:
            sc.unload()
            s.detach()
        except:
            pass
    print("Done.")

if __name__ == "__main__":
    main()
