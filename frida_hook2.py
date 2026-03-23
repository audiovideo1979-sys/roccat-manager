"""Minimal frida hook for SWARM II HID calls."""
import frida, sys, time

JS = """
var hid = Module.findExportByName('hid.dll', 'HidD_SetFeature');
var hid2 = Module.findExportByName('hid.dll', 'HidD_SetOutputReport');
var wf = Module.findExportByName('kernel32.dll', 'WriteFile');

send('hid.dll HidD_SetFeature: ' + hid);
send('hid.dll HidD_SetOutputReport: ' + hid2);
send('kernel32 WriteFile: ' + wf);

if (hid !== null) {
    Interceptor.attach(hid, {
        onEnter: function(args) {
            var len = args[2].toInt32();
            var arr = [];
            for (var i = 0; i < len && i < 64; i++) {
                var b = args[1].add(i).readU8().toString(16);
                if (b.length < 2) b = '0' + b;
                arr.push(b);
            }
            send('SET_FEATURE len=' + len + ' data=' + arr.join(' '));
        }
    });
    send('Hooked HidD_SetFeature OK');
}

if (hid2 !== null) {
    Interceptor.attach(hid2, {
        onEnter: function(args) {
            var len = args[2].toInt32();
            var arr = [];
            for (var i = 0; i < len && i < 64; i++) {
                var b = args[1].add(i).readU8().toString(16);
                if (b.length < 2) b = '0' + b;
                arr.push(b);
            }
            send('SET_OUTPUT len=' + len + ' data=' + arr.join(' '));
        }
    });
    send('Hooked HidD_SetOutputReport OK');
}

if (wf !== null) {
    Interceptor.attach(wf, {
        onEnter: function(args) {
            var len = args[2].toInt32();
            if (len > 0 && len <= 256) {
                var first = args[1].readU8();
                if (first <= 0x10) {
                    var arr = [];
                    for (var i = 0; i < len && i < 64; i++) {
                        var b = args[1].add(i).readU8().toString(16);
                        if (b.length < 2) b = '0' + b;
                        arr.push(b);
                    }
                    send('WRITEFILE len=' + len + ' data=' + arr.join(' '));
                }
            }
        }
    });
    send('Hooked WriteFile OK');
}

send('READY - change DPI now!');
"""

def on_msg(msg, data):
    if msg['type'] == 'send':
        print(msg['payload'])
    elif msg['type'] == 'error':
        print("[ERR] %s" % msg.get('description', ''))

# Attach to SWARM II UI only (PID from earlier)
device = frida.get_local_device()
target = None
for p in device.enumerate_processes():
    if 'swarm ii' in p.name.lower():
        target = p
        break

if not target:
    print("SWARM II not found!")
    sys.exit(1)

print("Attaching to %s (PID %d)..." % (target.name, target.pid))
session = frida.attach(target.pid)
script = session.create_script(JS)
script.on('message', on_msg)
script.load()

print("Waiting for HID calls... Change DPI in SWARM II!")
print("Ctrl+C to stop.\n")

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    pass

script.unload()
session.detach()
print("Done.")
